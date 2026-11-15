"""POST /comparisons, POST /applicability (BE-07)."""
from __future__ import annotations

from starlette.requests import Request

from .comparison import build_table
from .errors import ApiError
from .http import ok, read_json, require_revision
from .providers import ContractViolation
from .validation import check_applicability


def _load(request: Request, rev: str, ids: list[str]) -> list[dict]:
    db = request.app.state.db
    found = db.get_entities(rev, "investigation", ids)
    missing = [i for i in ids if i not in found]
    if missing:
        raise ApiError("NOT_FOUND", f"Исследование {missing[0]} не найдено в версии данных {rev}.",
                       [{"field": "investigation_ids", "reason": f"not_found:{missing[0]}"}], data_revision=rev)
    return [found[i] for i in ids]


def _applicability(request: Request, scenario: dict, invs: list[dict], rev: str) -> dict:
    db = request.app.state.db
    runs_by = db.runs_for(rev, [i["id"] for i in invs])
    runs = [r for rs in runs_by.values() for r in rs]
    ev_ids = sorted({e for r in runs for e in r["evidence_ids"]})
    evidence = list(db.get_entities(rev, "evidence", ev_ids).values())
    try:
        result = request.app.state.providers["applicability"](scenario, invs, runs, evidence)
        return check_applicability(result, scenario, rev, runs)
    except ContractViolation as e:
        raise ApiError("INTERNAL_ERROR", "Оценка применимости не прошла проверку. Сообщите request_id.") from e


async def compare(request: Request):
    body = await read_json(request, "ComparisonRequest")
    rev = require_revision(request, body["data_revision"])
    invs = _load(request, rev, body["investigation_ids"])
    db = request.app.state.db
    runs_by = db.runs_for(rev, body["investigation_ids"])
    materials = db.get_entities(rev, "material", sorted({m for i in invs for m in i["material_ids"]}))
    table = build_table(invs, runs_by, materials, request.app.state.dictionaries)
    scenario = body.get("scenario")
    data = {"investigations": invs, "rows": table["rows"], "comparability": table["comparability"],
            "applicability": _applicability(request, scenario, invs, rev) if scenario else None,
            "limitations": table["limitations"]}
    return ok(request, data, "ComparisonResponseEnvelope", data_revision=rev)


async def applicability(request: Request):
    body = await read_json(request, "ApplicabilityRequest")
    rev = require_revision(request, body["data_revision"])
    invs = _load(request, rev, body["investigation_ids"])
    return ok(request, _applicability(request, body["scenario"], invs, rev), "ApplicabilityResultEnvelope", data_revision=rev)
