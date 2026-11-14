"""Чтение научного каталога (BE-04), измерения (BE-06), доступ к файлам (BE-11).

Все научные объекты читаются строго по переданной data_revision. Модель не вызывается.
"""
from __future__ import annotations

import hashlib
import json
import math

from starlette.requests import Request
from starlette.responses import FileResponse

from .errors import ApiError, validation_error
from .http import binding_hash, decode_cursor, encode_cursor, int_param, ok, query_param, read_json, require_revision

KNOWN = {"measured", "reported", "derived"}
PUBLISHED_CLAIMS = {("observation", "reviewed"), ("synthesis", "reviewed"), ("hypothesis", "reviewed")}
AXIS_UNITS = {
    "sample.initial_diameter": "m", "sample.thickness": "m",
    "conditions.oxygen_fraction": "fraction", "conditions.pressure": "Pa", "conditions.airflow_speed": "m_s",
    "conditions.ambient_temperature": "K", "conditions.gravity_level": "g_fraction",
    "metrics.burn_duration": "s", "metrics.visible_extinction_diameter": "m", "metrics.flame_spread_rate": "m_s",
    "metrics.particle_diameter": "m",
}
AXIS_LABELS = {
    "sample.initial_diameter": "Начальный диаметр", "sample.thickness": "Толщина образца",
    "conditions.oxygen_fraction": "Доля кислорода", "conditions.pressure": "Давление",
    "conditions.airflow_speed": "Скорость потока (калиброванная)", "conditions.ambient_temperature": "Температура среды",
    "conditions.gravity_level": "Уровень гравитации", "metrics.burn_duration": "Время горения",
    "metrics.visible_extinction_diameter": "Диаметр видимого погасания",
    "metrics.flame_spread_rate": "Скорость распространения пламени", "metrics.particle_diameter": "Диаметр частиц",
}
ASSET_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".csv": "text/csv", ".txt": "text/plain",
               ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
               ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _not_found(what: str, rev: str):
    return ApiError("NOT_FOUND", f"{what} не найден в версии данных {rev}.", data_revision=rev)


def _entity(request: Request, etype: str, id_: str, what: str) -> tuple[dict, str]:
    rev = require_revision(request, query_param(request, "data_revision", "DataRevision"))
    obj = request.app.state.db.get_entity(rev, etype, id_)
    if obj is None:
        raise _not_found(what, rev)
    return obj, rev


async def get_investigation(request: Request):
    inv, rev = _entity(request, "investigation", request.path_params["id"], "Исследование")
    db = request.app.state.db
    claims = db.get_entities(rev, "claim", inv["claim_ids"])
    published = [claims[cid] for cid in inv["claim_ids"]
                 if cid in claims and (claims[cid]["kind"], claims[cid]["review_status"]) in PUBLISHED_CLAIMS]
    sources = db.get_entities(rev, "source", inv["source_ids"])
    with db.read() as conn:
        total = conn.execute("SELECT COUNT(*) FROM entities WHERE data_revision = ? AND entity_type = 'run' AND investigation_id = ?",
                             (rev, inv["id"])).fetchone()[0]
    data = {
        "investigation": inv,
        "claims": published,
        "sources": [sources[s] for s in inv["source_ids"] if s in sources],
        # В опубликованный корпус входят только проверенные записи; карантин не импортируется (CT-09).
        "run_summary": {"total": total, "verified_count": total, "excluded_count": 0},
    }
    return ok(request, data, "InvestigationDetailEnvelope", data_revision=rev)


async def list_runs(request: Request):
    inv_id = request.path_params["id"]
    inv, rev = _entity(request, "investigation", inv_id, "Исследование")
    s = request.app.state.settings
    limit = int_param(request, "limit", 20, 1, s.run_limit_max)
    cursor = query_param(request, "cursor", "Cursor", required=False)
    binding = {"k": "runs", "rev": rev, "inv": inv_id}
    after = decode_cursor(s.cursor_secret, cursor, binding)["after"] if cursor else None
    db = request.app.state.db
    with db.read() as conn:
        args: list = [rev, inv_id]
        where = ""
        if after:
            where = " AND (sort_key > ? OR (sort_key = ? AND id > ?))"
            args += [after[0], after[0], after[1]]
        rows = conn.execute(
            "SELECT id, sort_key, body FROM entities WHERE data_revision = ? AND entity_type = 'run' AND investigation_id = ?"
            + where + " ORDER BY sort_key, id LIMIT ?", (*args, limit + 1)).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM entities WHERE data_revision = ? AND entity_type = 'run' AND investigation_id = ?",
                             (rev, inv_id)).fetchone()[0]
    items = [json.loads(r["body"]) for r in rows[:limit]]
    nxt = None
    if len(rows) > limit:
        last = rows[limit - 1]
        nxt = encode_cursor(s.cursor_secret, {**binding, "after": [last["sort_key"], last["id"]]})
    return ok(request, {"items": items, "next_cursor": nxt, "total": total}, "RunPageEnvelope", data_revision=rev)


async def get_run(request: Request):
    run, rev = _entity(request, "run", request.path_params["id"], "Опыт")
    return ok(request, run, "TestRunEnvelope", data_revision=rev)


async def get_evidence(request: Request):
    ev, rev = _entity(request, "evidence", request.path_params["id"], "Доказательство")
    src = request.app.state.db.get_entity(rev, "source", ev["source_id"])
    if src is None:  # импорт гарантирует ссылочную целостность; сюда попадать не должны
        raise ApiError("INTERNAL_ERROR")
    return ok(request, {"evidence": ev, "source": src}, "EvidenceDetailEnvelope", data_revision=rev)


async def get_source(request: Request):
    src, rev = _entity(request, "source", request.path_params["id"], "Источник")
    return ok(request, src, "SourceEnvelope", data_revision=rev)


async def get_source_asset(request: Request):
    """BE-11: только зарегистрированный asset; путь не принимается из запроса; sha256 сверяется."""
    src, rev = _entity(request, "source", request.path_params["id"], "Источник")
    asset_id = src["local_asset_id"]
    unavailable = ApiError("NOT_FOUND", "Файл источника недоступен. Метаданные и ссылка на оригинал доступны.", data_revision=rev)
    if not asset_id or src["availability"] != "available":
        raise unavailable
    base = request.app.state.settings.assets_dir.resolve()
    matches = [p for p in base.glob(asset_id + ".*") if p.suffix.lower() in ASSET_TYPES]
    if len(matches) != 1:
        raise unavailable
    path = matches[0].resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise unavailable
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != src["sha256"]:
        raise unavailable
    return FileResponse(path, media_type=ASSET_TYPES[path.suffix.lower()], filename=f"{src['id']}{path.suffix.lower()}")


# --- Измерения (BE-06) ------------------------------------------------------
def axis_quantity(run: dict, key: str) -> dict | None:
    group, name = key.split(".", 1)
    if group == "metrics":
        return next((m["quantity"] for m in run["metrics"] if m["metric_key"] == name), None)
    return run.get(group, {}).get(name)


def axis_value(run: dict, key: str) -> tuple[float | None, str | None]:
    """(значение, причина исключения)."""
    qv = axis_quantity(run, key)
    if qv is None or qv["status"] not in KNOWN or qv["value"] is None:
        return None, "missing"
    if qv["unit"] != AXIS_UNITS[key] or not math.isfinite(qv["value"]):
        return None, "unusable_unit"
    return qv["value"], None


def investigations_with_axes(db, rev: str, x: str, y: str) -> list[str]:
    with db.read() as conn:
        rows = conn.execute("SELECT investigation_id, body FROM entities WHERE data_revision = ? AND entity_type = 'run'", (rev,))
        out = set()
        for r in rows:
            run = json.loads(r["body"])
            if axis_value(run, x)[0] is not None and axis_value(run, y)[0] is not None:
                out.add(r["investigation_id"])
    return sorted(out)


def _in_range(qv: dict | None, rng: dict | None) -> bool | None:
    if rng is None:
        return True
    if qv is None or qv["status"] not in KNOWN:
        return None
    v = qv["value"]
    return (rng["min"] is None or v >= rng["min"]) and (rng["max"] is None or v <= rng["max"])


async def query_measurements(request: Request):
    body = await read_json(request, "MeasurementRequest")
    rev = require_revision(request, body["data_revision"])
    s = request.app.state.settings
    db = request.app.state.db
    inv_id, x, y = body["investigation_id"], body["x_metric"], body["y_metric"]
    if db.get_entity(rev, "investigation", inv_id) is None:
        raise _not_found("Исследование", rev)
    from .api_system import MEASUREMENT_AXES

    if (x, y) not in MEASUREMENT_AXES:
        raise validation_error([{"field": "y_metric", "reason": "unsupported_axis"}], "Эта пара показателей не поддерживается.")
    for rng_name in ("oxygen_range", "pressure_range", "co2_range", "helium_range"):
        rng = (body.get("filters") or {}).get(rng_name)
        if rng and rng["min"] is not None and rng["max"] is not None and rng["min"] > rng["max"]:
            raise validation_error([{"field": f"filters.{rng_name}", "reason": "min_greater_than_max"}])
    limit = body.get("limit", 200)
    if limit > s.measurement_limit_max:
        raise validation_error([{"field": "limit", "reason": "out_of_range"}])
    run_ids = list(dict.fromkeys(body.get("run_ids") or []))
    filters = body.get("filters") or {}

    with db.read() as conn:
        rows = conn.execute("SELECT id, sort_key, body FROM entities WHERE data_revision = ? AND entity_type = 'run' "
                            "AND investigation_id = ? ORDER BY sort_key, id", (rev, inv_id)).fetchall()
    runs = [(r["sort_key"], r["id"], json.loads(r["body"])) for r in rows]
    if run_ids:
        present = {rid for _, rid, _ in runs}
        foreign = [i for i, rid in enumerate(run_ids) if rid not in present]
        if foreign:
            raise validation_error([{"field": f"run_ids[{i}]", "reason": "not_in_investigation"} for i in foreign])
        wanted = set(run_ids)
        runs = [t for t in runs if t[1] in wanted]

    excl = {"missing_x": 0, "missing_y": 0, "unusable_unit": 0, "unverified_record": 0, "filtered_out": 0}
    points = []
    for sort_key, rid, run in runs:
        if filters.get("outcome_categories") and run["terminal_outcome"]["category"] not in filters["outcome_categories"]:
            excl["filtered_out"] += 1
            continue
        if filters.get("material_ids") and run["material_id"] not in filters["material_ids"]:
            excl["filtered_out"] += 1
            continue
        if not (_in_range(run["conditions"].get("oxygen_fraction"), filters.get("oxygen_range"))
                and _in_range(run["conditions"].get("pressure"), filters.get("pressure_range"))
                and _in_range(run["conditions"].get("co2_fraction"), filters.get("co2_range"))
                and _in_range(run["conditions"].get("helium_fraction"), filters.get("helium_range"))):
            excl["filtered_out"] += 1
            continue
        xv, xr = axis_value(run, x)
        yv, yr = axis_value(run, y)
        if xr or yr:
            if "unusable_unit" in (xr, yr):
                excl["unusable_unit"] += 1
            elif xr:
                excl["missing_x"] += 1
            else:
                excl["missing_y"] += 1
            continue
        ev = list(dict.fromkeys(axis_quantity(run, x)["evidence_ids"] + axis_quantity(run, y)["evidence_ids"]))
        points.append(((sort_key, rid), {"run_id": rid, "x": xv, "y": yv, "outcome": run["terminal_outcome"]["category"],
                                         "evidence_ids": ev}))

    binding = {"k": "meas", "rev": rev, "q": binding_hash({k: body.get(k) for k in ("investigation_id", "run_ids", "x_metric",
                                                                                     "y_metric", "filters")})}
    if body.get("cursor"):
        after = tuple(decode_cursor(s.cursor_secret, body["cursor"], binding)["after"])
        points = [p for p in points if p[0] > after]
    page = points[:limit]
    nxt = encode_cursor(s.cursor_secret, {**binding, "after": list(page[-1][0])}) if len(points) > limit else None
    data = {
        "x_axis": {"key": x, "label": AXIS_LABELS[x], "unit": AXIS_UNITS[x]},
        "y_axis": {"key": y, "label": AXIS_LABELS[y], "unit": AXIS_UNITS[y]},
        "points": [p[1] for p in page],
        "excluded_count": sum(excl.values()),
        "exclusions_by_reason": excl,
        "truncated": nxt is not None,
        "next_cursor": nxt,
    }
    return ok(request, data, "MeasurementResponseEnvelope", data_revision=rev)
