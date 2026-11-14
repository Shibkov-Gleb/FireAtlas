"""Подключение модулей AI 1 (retrieve, CT-13), AI 2 (reason, CT-15; assess_applicability, A2-04).

Спецификация провайдера (FA_RETRIEVER / FA_REASONER / FA_APPLICABILITY):
  stub                         - встроенная заглушка бэкенда (только dev/test, D-024)
  py:package.module:function   - функция в том же процессе; вход и выход - dict по схеме контракта
  http(s)://host/internal/...  - отдельный процесс; Authorization: Bearer FA_INTERNAL_TOKEN

Бэкенд не доверяет выходу ни одного провайдера: схема и ссылки проверяются в validation.py.
"""
from __future__ import annotations

import importlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from .db import Database


class AIError(Exception):
    code = "INTERNAL_ERROR"
    retryable = True

    def __init__(self, message: str = ""):
        super().__init__(message or self.code)


class RetrievalUnavailable(AIError):
    code = "AI_UNAVAILABLE"


class ProviderError(AIError):
    code = "MODEL_PROVIDER_ERROR"


class ReasoningTimeout(AIError):
    code = "REASONING_TIMEOUT"


class ContractViolation(AIError):
    code = "VALIDATION_FAILED"


INTERNAL_CODE_MAP = {
    "VALIDATION_FAILED": ContractViolation,
    "REASONING_TIMEOUT": ReasoningTimeout,
    "MODEL_PROVIDER_ERROR": ProviderError,
    "AI_UNAVAILABLE": RetrievalUnavailable,
    "RETRIEVAL_FAILED": RetrievalUnavailable,
}

Fn = Callable[[dict], dict]


def _http(url: str, token: str | None, kind: type[AIError]) -> Fn:
    def call(payload: dict) -> dict:
        deadline = payload.get("deadline_at")
        timeout = 30.0
        if deadline:
            left = (datetime.fromisoformat(deadline.replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds()
            timeout = max(0.5, left)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read())
                raise INTERNAL_CODE_MAP.get(body.get("code"), kind)(body.get("message", ""))
            except (ValueError, AttributeError):
                raise kind(f"HTTP {e.code}")
        except TimeoutError:
            raise ReasoningTimeout("internal call timeout") if kind is ProviderError else kind("timeout")
        except (urllib.error.URLError, OSError) as e:
            raise kind(str(e))

    return call


def _py(spec: str) -> Callable:
    mod, _, attr = spec[3:].partition(":")
    if not mod or not attr:
        raise RuntimeError(f"неверная спецификация провайдера {spec!r}; ожидается py:package.module:function")
    return getattr(importlib.import_module(mod), attr)


def load(spec: str, kind: str, db: Database, token: str | None) -> Callable:
    if spec == "stub":
        return {"retriever": lambda: StubRetriever(db), "reasoner": lambda: stub_reason,
                "applicability": lambda: stub_assess_applicability}[kind]()
    if spec.startswith("py:"):
        return _py(spec)
    if spec.startswith(("http://", "https://")):
        if kind == "applicability":
            raise RuntimeError("applicability подключается только как py: (детерминированная функция в процессе)")
        return _http(spec, token, RetrievalUnavailable if kind == "retriever" else ProviderError)
    raise RuntimeError(f"неизвестный провайдер {kind}: {spec!r}")


# =============================================================================
# Заглушки бэкенда (dev/test). Не заменяют работу AI 1 и AI 2 и явно помечены.
# =============================================================================
STUB_RETRIEVAL_REVISION = "be-stub-retrieval-0"
STUB_REASONING_REVISION = "be-stub-reasoning-0"
STUB_RULES_VERSION = "be-stub-applicability-0"
KNOWN = {"measured", "reported", "derived"}


def _walk_q(obj: Any, path: str = ""):
    if isinstance(obj, dict):
        if "metric_key" in obj and "quantity" in obj:
            yield f"{path}.{obj['metric_key']}", obj["quantity"]
            return
        if {"value", "unit", "status", "evidence_ids", "derivation"} <= obj.keys():
            yield path, obj
            return
        for k, v in obj.items():
            yield from _walk_q(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_q(v, path)


class StubRetriever:
    """Подборка (mode=curated) по структурированным данным: без ранжирования и без текстового поиска."""

    def __init__(self, db: Database):
        self.db = db

    def __call__(self, req: dict) -> dict:
        rev = req["data_revision"]
        with self.db.read() as conn:
            rows = conn.execute("SELECT entity_type, id, body FROM entities WHERE data_revision = ? "
                                "AND entity_type IN ('investigation','run','claim','evidence','source')", (rev,)).fetchall()
        if not rows:
            raise RetrievalUnavailable(f"нет данных ревизии {rev}")
        E: dict[str, dict[str, dict]] = {}
        for r in rows:
            E.setdefault(r["entity_type"], {})[r["id"]] = json.loads(r["body"])
        inv_ids = req["selected_investigation_ids"] or sorted(E.get("investigation", {}))
        runs = [r for r in E.get("run", {}).values() if r["investigation_id"] in inv_ids]
        claims = [c for c in E.get("claim", {}).values()
                  if c["review_status"] == "reviewed" and set(c["investigation_ids"]) & set(inv_ids)]

        ev_order: list[str] = []
        ev_inv: dict[str, set] = {}
        ev_runs: dict[str, set] = {}
        for c in claims:
            for e in c["supporting_evidence_ids"] + c["contradicting_evidence_ids"]:
                ev_order.append(e)
                ev_inv.setdefault(e, set()).update(c["investigation_ids"])
        for r in sorted(runs, key=lambda r: r["id"]):
            for e in r["evidence_ids"]:
                ev_order.append(e)
                ev_inv.setdefault(e, set()).add(r["investigation_id"])
                ev_runs.setdefault(e, set()).add(r["id"])
        items, chars = [], 0
        for e in dict.fromkeys(ev_order):
            ev = E.get("evidence", {}).get(e)
            if ev is None or len(items) >= 20:
                continue
            ln = len(ev["excerpt"] or "")
            if chars + ln > 24000:
                continue
            chars += ln
            facts = []
            for rid in sorted(ev_runs.get(e, ())):
                for path, q in _walk_q(E["run"][rid]):
                    if e in q["evidence_ids"] and q["status"] in KNOWN and len(facts) < 10:
                        facts.append({"field": path, "quantity": q, "text_value": None, "evidence_ids": [e]})
            items.append({"evidence": ev, "source_metadata": E["source"][ev["source_id"]],
                          "investigation_ids": sorted(ev_inv.get(e, ())), "run_ids": sorted(ev_runs.get(e, ())),
                          "normalized_facts": facts})
        scenario = req["scenario"]
        regimes = {r["conditions"]["gravity_regime"] for r in runs}
        gravity_ok = scenario is None or scenario["gravity_regime"] in regimes
        coverage = {
            "matching_investigation_ids": sorted(inv_ids),
            "matching_run_ids": sorted(r["id"] for r in runs),
            "missing_fields": [] if gravity_ok else ["conditions.gravity_regime"],
            "target_gravity_covered": gravity_ok,
            "direct_evidence_available": gravity_ok and bool(items),
            "reasons": [] if gravity_ok else [{"code": "gravity_not_covered", "field": "gravity_regime", "evidence_ids": [],
                                               "text": "В корпусе нет опытов с целевым режимом гравитации."}],
        }
        bundle = {
            "bundle_id": "bnd_" + req["request_id"][4:], "data_revision": rev, "question": req["question"],
            "scenario": scenario, "items": items,
            "allowed_evidence_ids": [i["evidence"]["id"] for i in items],
            "allowed_source_ids": sorted({i["source_metadata"]["id"] for i in items}),
            "selected_claims": claims, "coverage": coverage, "retrieval_revision": STUB_RETRIEVAL_REVISION,
        }
        ranked = [{"investigation_id": i, "rank_score": round(1 / (n + 1), 4), "relevance_category": "contextual",
                   "match_reasons": [], "differences": [], "missing_fields": [], "matching_run_ids": []}
                  for n, i in enumerate(inv_ids)]
        return {"request_id": req["request_id"], "data_revision": rev, "retrieval_revision": STUB_RETRIEVAL_REVISION,
                "mode": "curated", "ranked_items": ranked, "evidence_bundle": bundle, "coverage": coverage,
                "warnings": [{"code": "RETRIEVAL_STUB", "message": "Поиск AI 1 не подключен; используется подборка бэкенда.",
                              "field": None}]}


def stub_reason(req: dict) -> dict:
    b = req["evidence_bundle"]
    allowed = b["allowed_evidence_ids"]
    by_ev = {i["evidence"]["id"]: i for i in b["items"]}
    blocks, used = [], []
    status = "answered"
    cov = b["coverage"]
    if not allowed or not cov["direct_evidence_available"]:
        status = "insufficient_evidence"
        reasons = "; ".join(r["text"] for r in cov["reasons"]) or "Подходящих доказательств не найдено."
        used = allowed[:3]
        blocks.append({"id": "blk_1", "kind": "limitation", "evidence_ids": used, "quantities": [],
                       "text": f"[ЗАГЛУШКА AI 2] Прямых данных недостаточно. {reasons} Отсутствие данных не означает безопасность."})
    else:
        used = allowed[:5]
        acr = sorted({inv for e in used for inv in by_ev[e]["investigation_ids"]})
        blocks.append({"id": "blk_1", "kind": "summary", "evidence_ids": used, "quantities": [],
                       "text": f"[ЗАГЛУШКА AI 2] Это не сгенерированный ответ. Найдено доказательств: {len(allowed)}; "
                               f"исследования: {', '.join(acr)}. Откройте источники ниже."})
        for n, c in enumerate([c for c in b["selected_claims"] if c["kind"] == "observation"][:3], start=2):
            ev = [e for e in c["supporting_evidence_ids"] if e in allowed]
            if ev:
                blocks.append({"id": f"blk_{n}", "kind": "observation", "text": c["text"][:1500], "evidence_ids": ev,
                               "quantities": []})
                used += [e for e in ev if e not in used]
        blocks.append({"id": f"blk_{len(blocks) + 1}", "kind": "limitation", "evidence_ids": [], "quantities": [],
                       "text": "Результаты относятся к условиям конкретных опытов."})
    citations = [{"evidence_id": e, "source_id": by_ev[e]["source_metadata"]["id"],
                  "label": by_ev[e]["source_metadata"]["title"], "locator": by_ev[e]["evidence"]["locator"]} for e in used]
    return {
        "status": status, "answer_blocks": blocks[:8], "applicability": None, "citations": citations,
        "limitations": ["Ответ сформирован заглушкой бэкенда; модуль AI 2 не подключен."],
        "follow_up_questions": ["Какой материал и какие условия атмосферы рассматриваются?"] if status != "answered" else [],
        "reasoning_revision": STUB_REASONING_REVISION,
        "validation_summary": {"schema_valid": True, "references_valid": True, "quantities_valid": True, "scope_valid": True},
        "audit": {"checked_evidence_ids": used, "rejections": [], "model": None, "model_version": None},
    }


def stub_assess_applicability(scenario: dict, investigations: list[dict], runs: list[dict], evidence: list[dict]) -> dict:
    """Консервативная заглушка A2-04: никогда не выдает direct_evidence. Заменяется функцией AI 2."""
    factors, gaps = [], []
    regimes = {r["conditions"]["gravity_regime"] for r in runs} | {g for i in investigations for g in i["gravity_regimes"]}
    target = scenario["gravity_regime"]
    if target in regimes:
        g_status, g_text = "match", "Режим гравитации представлен в выбранных исследованиях."
    elif target in ("partial", "simulated_partial"):
        g_status, g_text = "not_covered", "Целевой режим - частичная гравитация; прямых опытов в корпусе нет. Перенос требует обоснования."
        gaps.append({"field": "gravity_regime", "description": "Нет прямых опытов частичной гравитации.",
                     "suggested_next_step": "Изучить связанные исследования с явной оговоркой; сохранить пробел в отчете."})
    else:
        g_status, g_text = "mismatch", "Режим гравитации сценария отличается от режимов исследований."
    factors.append({"field": "gravity_regime", "status": g_status, "explanation": g_text, "evidence_ids": []})
    scopes = {s for i in investigations for s in i["scopes"]}
    factors.append({"field": "safety_task", "status": "match" if scenario["safety_task"] in scopes else "mismatch",
                    "explanation": "Задача сценария совпадает с направлением исследования." if scenario["safety_task"] in scopes
                    else "Направление исследований отличается от задачи сценария.", "evidence_ids": []})
    mats = {m for i in investigations for m in i["material_ids"]}
    if not scenario["material_ids"]:
        factors.append({"field": "material_ids", "status": "unknown", "explanation": "Материал не выбран.", "evidence_ids": []})
    else:
        hit = set(scenario["material_ids"]) & mats
        factors.append({"field": "material_ids", "status": "match" if hit else "mismatch",
                        "explanation": "Материал есть в исследованиях (по material_id)." if hit else "Выбранного материала нет в исследованиях.",
                        "evidence_ids": []})
    cov_field = {"oxygen_fraction": "conditions.oxygen_fraction", "pressure": "conditions.pressure",
                 "airflow_speed": "conditions.airflow_speed"}
    for f, cf in cov_field.items():
        q = scenario[f]
        if q is None or q["value"] is None:
            factors.append({"field": f, "status": "unknown", "explanation": "Условие сценария не задано.", "evidence_ids": []})
            gaps.append({"field": f, "description": "Условие сценария не задано.", "suggested_next_step": "Указать значение в сценарии."})
            continue
        covs = [c for i in investigations for c in i["conditions_coverage"] if c["field"] == cf and c["known_count"] > 0]
        if not covs:
            factors.append({"field": f, "status": "not_covered", "explanation": "В исследованиях нет сообщенных значений.", "evidence_ids": []})
            continue
        ev = sorted({e for c in covs for e in c["derivation_evidence_ids"]})
        inside = any(c["min_value"] is not None and c["max_value"] is not None and c["min_value"] <= q["value"] <= c["max_value"]
                     for c in covs)
        factors.append({"field": f, "status": "unknown" if inside else "mismatch", "evidence_ids": ev,
                        "explanation": "Значение внутри наблюдаемого диапазона; совместный опыт с таким сочетанием не проверен."
                        if inside else "Значение вне наблюдаемого диапазона исследований."})
    overall = "related_evidence" if scenario["safety_task"] in scopes else "insufficient_evidence"
    return {"overall": overall, "factors": factors, "gaps": gaps,
            "basis": {"reviewed_rules_version": STUB_RULES_VERSION,
                      "data_revision": (investigations[0]["data_revision"] if investigations else "unknown")}}
