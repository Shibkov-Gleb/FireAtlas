"""GET /config, /health/live, /health/ready (BE-04, BE-12)."""
from __future__ import annotations

import json

import fa_contracts as c
from starlette.requests import Request
from starlette.responses import JSONResponse

from .errors import ApiError
from .http import ok

DICTIONARIES_PATH = c.CONTRACTS_DIR / "dictionaries.en.json"
MEASUREMENT_AXES = [("sample.initial_diameter", "metrics.burn_duration")]


def load_dictionaries() -> dict:
    return json.loads(DICTIONARIES_PATH.read_text(encoding="utf-8"))


def material_dictionary(db, rev: str | None) -> list[dict]:
    """D-040: подписи материалов ревизии (value = material_id). Других публичных источников подписей нет."""
    if not rev:
        return []
    with db.read() as conn:
        rows = conn.execute("SELECT id, body FROM entities WHERE data_revision = ? AND entity_type = 'material'",
                            (rev,)).fetchall()
    entries = [{"value": r["id"], "label": json.loads(r["body"])["label"]} for r in rows]
    return sorted(entries, key=lambda e: (e["label"].casefold(), e["value"]))


async def get_config(request: Request):
    s = request.app.state.settings
    db = request.app.state.db
    active = db.active_revision()
    axes = []
    if active:
        from .api_catalog import investigations_with_axes

        for x, y in MEASUREMENT_AXES:
            axes.append({"x_key": x, "y_key": y, "investigation_ids": investigations_with_axes(db, active, x, y)})
    data = {
        "contract_version": c.contract_version(),
        "active_data_revision": active,
        "feature_flags": {
            "analysis": s.feature_analysis,
            "reports": s.feature_reports,
            "semantic_search": s.feature_semantic_search,
            "video_preview": s.feature_video_preview,
        },
        "limits": {
            "search_limit_max": s.search_limit_max,
            "run_limit_max": s.run_limit_max,
            "measurement_limit_max": s.measurement_limit_max,
            "question_chars_max": s.question_chars_max,
            "comparison_max": s.comparison_max,
            "analysis_deadline_s": s.analysis_deadline_s,
            "report_deadline_s": s.report_deadline_s,
        },
        "dictionaries": {**request.app.state.dictionaries, "materials": material_dictionary(db, active)},
        "measurement_axes": axes,
        "retention": {"workspace_days": s.workspace_days, "report_hours": s.report_hours},
    }
    return ok(request, data, "ConfigEnvelope", data_revision=active)


async def health_live(request: Request):
    return JSONResponse({"status": "ok", "checks": {"storage": True, "active_revision": None}})


async def health_ready(request: Request):
    db = request.app.state.db
    storage = db.ping()
    active = db.active_revision() if storage else None
    ready = storage and active is not None
    return JSONResponse({"status": "ok" if ready else "not_ready", "checks": {"storage": storage, "active_revision": active}},
                        status_code=200 if ready else 503)


def require_active(request: Request) -> str:
    active = request.app.state.db.active_revision()
    if active is None:
        raise ApiError("DATA_NOT_READY")
    return active
