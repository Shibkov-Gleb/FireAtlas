"""POST /search (BE-05) и GET /scenario-presets (D-007)."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import secrets
import threading
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

import fa_contracts as c
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from .db import iso, plus, utcnow
from .errors import ApiError, validation_error
from .http import binding_hash, decode_cursor, encode_cursor, ok, query_param, read_json, require_revision
from .providers import AIError, RetrievalUnavailable
from .search import applied_filters, build_items, check_ranked, evaluate, validate_request
from .validation import check_retrieval

log = logging.getLogger("fire_atlas.search")
PRESETS_PATH = Path(__file__).with_name("scenario_presets.json")


class SlidingWindow:
    """Не больше N запросов в минуту на ключ (клиентский адрес). Память процесса, P0 - один процесс."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """None - разрешено; иначе через сколько секунд повторить."""
        if self.per_minute <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return max(1, math.ceil(60 - (now - q[0])))
            q.append(now)
            if len(self._hits) > 10000:  # не растем бесконечно на сканировании адресов
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    del self._hits[k]
            return None


class TTLCache:
    """Полная выдача по ключу запроса: страницы курсора берутся из одного снимка ранжирования."""

    def __init__(self, ttl_s: float = 300, size: int = 256):
        self.ttl, self.size = ttl_s, size
        self._d: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            v = self._d.get(key)
            if v is None or v[0] < time.monotonic():
                self._d.pop(key, None)
                return None
            self._d.move_to_end(key)
            return v[1]

    def put(self, key: str, value) -> None:
        with self._lock:
            self._d[key] = (time.monotonic() + self.ttl, value)
            self._d.move_to_end(key)
            while len(self._d) > self.size:
                self._d.popitem(last=False)


_CORPUS_CACHE: dict[tuple[str, str], tuple[dict[str, dict], dict[str, list[dict]]]] = {}
_CORPUS_LOCK = threading.Lock()


def _corpus(db, rev: str) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """Исследования и опыты ревизии для жестких фильтров. Опубликованная ревизия неизменяема (CT-01), поэтому
    разбор кэшируется: раньше каждый поиск заново читал и разбирал все опыты (508 на psi-20261115-r2, ~55 мс).
    Объекты только читаются; кэш держит не больше двух ревизий."""
    key = (str(db.path.resolve()), rev)
    with _CORPUS_LOCK:
        hit = _CORPUS_CACHE.get(key)
    if hit is not None:
        return hit
    with db.read() as conn:
        rows = conn.execute("SELECT id, body FROM entities WHERE data_revision = ? AND entity_type = 'investigation' "
                            "ORDER BY id", (rev,)).fetchall()
    invs = {r["id"]: json.loads(r["body"]) for r in rows}
    value = (invs, db.runs_for(rev, list(invs)))
    with _CORPUS_LOCK:
        if len(_CORPUS_CACHE) >= 2:
            _CORPUS_CACHE.pop(next(iter(_CORPUS_CACHE)))
        _CORPUS_CACHE[key] = value
    return value


async def _retrieve(request: Request, rreq: dict, invs: dict, runs_by: dict) -> dict:
    s = request.app.state.settings
    db = request.app.state.db
    provider = request.app.state.providers["retriever"]
    t0 = time.perf_counter()
    try:
        res = await asyncio.wait_for(run_in_threadpool(provider, rreq), timeout=s.search_deadline_s)
    except AIError:
        raise
    except TimeoutError:
        raise RetrievalUnavailable("retrieve: превышен дедлайн поиска")
    except Exception as e:  # noqa: BLE001 - дефект модуля AI не должен ронять поиск
        log.exception("retriever_crashed")
        raise RetrievalUnavailable(repr(e)[:300])
    finally:
        request.app.state.metrics.stage("search", "retrieving", (time.perf_counter() - t0) * 1000)
    # Проверка выхода модуля - CPU-работа на сотни мс: в пуле потоков, чтобы не останавливать остальные запросы.
    bundle = await run_in_threadpool(check_retrieval, res, rreq, db)
    ev_ref = sorted({e for it in res["ranked_items"] for r in it["match_reasons"] + it["differences"] for e in r["evidence_ids"]})
    await run_in_threadpool(check_ranked, res["ranked_items"], invs, runs_by,
                            db.existing_ids(rreq["data_revision"], "evidence", ev_ref))
    ev_by_inv: dict[str, list[str]] = {}
    for item in bundle["items"]:
        for iid in item["investigation_ids"]:
            ev_by_inv.setdefault(iid, []).append(item["evidence"]["id"])
    return {"ranked": res["ranked_items"], "mode": res["mode"], "warnings": res["warnings"], "ev_by_inv": ev_by_inv}


async def _compute(request: Request, rev: str, body: dict, af: dict) -> dict:
    s = request.app.state.settings
    db = request.app.state.db
    invs, runs_by = await run_in_threadpool(_corpus, db, rev)
    mat_ids = sorted({m for i in invs.values() for m in i["material_ids"]} | set(af["material_ids"]))
    materials = db.get_entities(rev, "material", mat_ids)
    dicts = request.app.state.dictionaries
    evals = {iid: evaluate(inv, runs_by[iid], af, dicts, materials) for iid, inv in invs.items()}
    query = body["query"]
    include_related = body.get("include_related", False)
    rreq = {"request_id": "req_s" + secrets.token_hex(8), "question": query, "locale": "ru",
            "scenario": body.get("scenario"), "filters": af, "selected_investigation_ids": [],
            "data_revision": rev, "top_k": 20, "deadline_at": iso(plus(utcnow(), seconds=s.search_deadline_s)),
            "include_related": include_related}
    c.validate("InternalRetrievalRequest", rreq)
    try:
        r = await _retrieve(request, rreq, invs, runs_by)
    except AIError as e:
        log.warning(json.dumps({"event": "search_retrieval_failed", "code": e.code, "detail": str(e)[:300],
                                "request_id": request.state.request_id}, ensure_ascii=False))
        if query:
            # Без ранжирования нельзя честно ответить на текстовый запрос (FR-05): каталог и фильтры работают.
            raise ApiError("AI_UNAVAILABLE", "Поиск по тексту временно недоступен. Работают фильтры без текста, "
                                             "каталог и источники.", data_revision=rev)
        r = {"ranked": None, "mode": "curated", "ev_by_inv": {},
             "warnings": [{"code": "RETRIEVAL_UNAVAILABLE", "field": None,
                           "message": "Ранжирование недоступно; показаны исследования, прошедшие фильтры."}]}
    warnings = list({w["code"]: w for w in r["warnings"]}.values())
    if s.feature_semantic_search and r["mode"] != "hybrid" and all(w["code"] != "SEMANTIC_SEARCH_UNAVAILABLE" for w in warnings):
        warnings.append({"code": "SEMANTIC_SEARCH_UNAVAILABLE", "field": None,
                         "message": "Семантический поиск недоступен; используется поиск по тексту и фильтрам."})
    items = build_items(invs, evals, r["ranked"], r["ev_by_inv"], query, include_related, body.get("sort", "relevance"))
    return {"items": items, "mode": r["mode"], "warnings": warnings}


async def search(request: Request):
    s = request.app.state.settings
    wait = request.app.state.search_limiter.hit(request.client.host if request.client else "-")
    if wait is not None:
        raise ApiError("RATE_LIMITED", "Слишком много поисковых запросов. Повторите позже.",
                       [{"field": None, "reason": "per_minute_limit"}], headers={"Retry-After": str(wait)})
    body = await read_json(request, "SearchRequest")
    rev = require_revision(request, body["data_revision"])
    af = applied_filters(body.get("filters"))
    validate_request(body, af)
    limit = body.get("limit", 20)
    if limit > s.search_limit_max:
        raise validation_error([{"field": "limit", "reason": "out_of_range"}])
    provider = request.app.state.providers["retriever"]
    key = binding_hash({"q": body["query"], "f": af, "sc": body.get("scenario"), "rel": body.get("include_related", False),
                        "sort": body.get("sort", "relevance"), "p": id(provider)})
    binding = {"k": "search", "rev": rev, "h": key}
    offset = decode_cursor(s.cursor_secret, body["cursor"], binding)["off"] if body.get("cursor") else 0
    cache: TTLCache = request.app.state.search_cache
    res = cache.get(f"{rev}:{key}")
    if res is None:
        res = await _compute(request, rev, body, af)
        cache.put(f"{rev}:{key}", res)
    items = res["items"]
    page = items[offset:offset + limit]
    nxt = encode_cursor(s.cursor_secret, {**binding, "off": offset + limit}) if offset + limit < len(items) else None
    data = {"items": page, "next_cursor": nxt, "total": len(items), "retrieval_mode": res["mode"], "applied_filters": af}
    return ok(request, data, "SearchResultEnvelope", data_revision=rev, warnings=res["warnings"])


# --- Пресеты сред (D-007) ---------------------------------------------------
def load_presets(path: Path) -> list[dict]:
    """Пресеты проверяются по контракту при старте: ошибка в файле - сервер не стартует."""
    presets = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(presets, list):
        raise RuntimeError(f"{path}: ожидается массив ScenarioPreset")
    ids = set()
    for n, p in enumerate(presets):
        viol = c.errors_for("ScenarioPreset", p)
        if viol:
            raise RuntimeError(f"{path}[{n}]: {viol[0]['field']}: {viol[0]['reason']}")
        if p["preset_id"] in ids:
            raise RuntimeError(f"{path}: повтор preset_id {p['preset_id']}")
        ids.add(p["preset_id"])
        sc = p["scenario"]
        for f in ("gravity_regime", "oxygen_fraction", "pressure", "airflow_speed"):
            if f == "gravity_regime" or sc[f] is not None:
                if not any(a["field"] == f and a["origin"] == "preset_source" for a in sc["assumptions"]):
                    raise RuntimeError(f"{path}: у пресета {p['preset_id']} условие {f} без происхождения (FR-15)")
    return presets


def available_presets(db, presets: list[dict], rev: str) -> tuple[list[dict], list[dict]]:
    """Пресеты, источники и материалы которых есть в ревизии, и предупреждения о скрытых."""
    src = sorted({x for p in presets for a in p["scenario"]["assumptions"] for x in a["source_ids"]})
    mats = sorted({m for p in presets for m in p["scenario"]["material_ids"]})
    have_src, have_mat = db.existing_ids(rev, "source", src), db.existing_ids(rev, "material", mats)
    items, warnings = [], []
    for p in presets:
        sc = p["scenario"]
        need_src = {x for a in sc["assumptions"] for x in a["source_ids"]}
        if need_src <= have_src and set(sc["material_ids"]) <= have_mat:
            items.append(p)
        else:
            # Без источника происхождение условий не подтверждено (FR-15); PATCH такого сценария тоже вернет 422.
            warnings.append({"code": "PRESET_SOURCE_MISSING", "field": f"presets.{p['preset_id']}",
                             "message": f"Пресет «{p['label']}» скрыт: в этой версии данных нет его источника."})
    return items, warnings


DEFAULT_PRESET_ID = "orbital_habitat"


def default_scenario(db, presets: list[dict], rev: str) -> dict | None:
    """D-039: сценарий нового гостя - пресет орбитальной станции (рабочий контекст по умолчанию в продуктовом
    видении). null, если пресет недоступен в ревизии; схема по-прежнему допускает null (D-016)."""
    items, _ = available_presets(db, presets, rev)
    p = next((p for p in items if p["preset_id"] == DEFAULT_PRESET_ID), None)
    return json.loads(json.dumps(p["scenario"])) if p else None


async def list_presets(request: Request):
    rev = require_revision(request, query_param(request, "data_revision", "DataRevision"))
    items, warnings = available_presets(request.app.state.db, request.app.state.presets, rev)
    return ok(request, {"items": items}, "ScenarioPresetListEnvelope", data_revision=rev, warnings=warnings)
