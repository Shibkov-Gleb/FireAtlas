"""POST /analyses, /jobs/{id}, /answers/{id} (BE-08); /reports (BE-09); лимиты (BE-10)."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import timedelta

import fa_contracts as c
from starlette.requests import Request
from starlette.responses import FileResponse, Response

from .api_workspace import session_workspace
from .comparison import build_table
from .db import dumps, iso, parse_iso, plus, utcnow
from .errors import ApiError, validation_error
from .jobs import TERMINAL, body_hash, job_to_api, new_job_id
from .http import dedupe, ok, read_json

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
PUBLISHED_CLAIMS = {("observation", "reviewed"), ("synthesis", "reviewed"), ("hypothesis", "reviewed")}


def _idem_key(request: Request) -> str:
    key = request.headers.get("idempotency-key")
    if key is None:
        raise validation_error([{"field": "Idempotency-Key", "reason": "required"}], "Нужен заголовок Idempotency-Key (UUID).")
    if not UUID_RE.match(key.strip()):
        raise validation_error([{"field": "Idempotency-Key", "reason": "invalid_format"}])
    return key.strip().lower()


def _replay(conn, ws_id: str, op: str, key: str, h: str):
    row = conn.execute("SELECT body_hash, job_id FROM idempotency_keys WHERE workspace_id=? AND operation=? AND key=?",
                       (ws_id, op, key)).fetchone()
    if row is None:
        return None
    if row["body_hash"] != h:
        raise ApiError("IDEMPOTENCY_CONFLICT", "Этот ключ уже использован с другими данными. Запустите новое действие.",
                       [{"field": "Idempotency-Key", "reason": "body_mismatch"}])
    return conn.execute("SELECT * FROM jobs WHERE id=?", (row["job_id"],)).fetchone()


def _check_ws_revision(conn, ws_id: str, expected: int) -> dict:
    row = conn.execute("SELECT revision, state FROM workspaces WHERE id=?", (ws_id,)).fetchone()
    if row["revision"] != expected:
        raise ApiError("WORKSPACE_CONFLICT", details=[{"field": "workspace_revision", "reason": "stale_revision",
                                                       "current_revision": row["revision"]}])
    return json.loads(row["state"])


def _rate_limit(conn, ws_id: str, job_type: str, active_max: int, per_minute: int | None) -> None:
    now = utcnow()
    active = conn.execute("SELECT deadline_at FROM jobs WHERE workspace_id=? AND type=? AND state IN ('queued','running') "
                          "ORDER BY deadline_at", (ws_id, job_type)).fetchall()
    if len(active) >= active_max:
        wait = max(1, int((parse_iso(active[0]["deadline_at"]) - now).total_seconds()) + 1)
        raise ApiError("RATE_LIMITED", "Предыдущая задача еще выполняется. Дождитесь ее завершения или отмените ее.",
                       [{"field": None, "reason": "active_job_limit"}], headers={"Retry-After": str(wait)})
    if per_minute:
        window = iso(plus(now, seconds=-60))
        recent = conn.execute("SELECT created_at FROM jobs WHERE workspace_id=? AND type=? AND created_at > ? ORDER BY created_at",
                              (ws_id, job_type, window)).fetchall()
        if len(recent) >= per_minute:
            wait = max(1, int(60 - (now - parse_iso(recent[0]["created_at"])).total_seconds()) + 1)
            raise ApiError("RATE_LIMITED", "Слишком много запусков за минуту. Повторите позже.",
                           [{"field": None, "reason": "per_minute_limit"}], headers={"Retry-After": str(wait)})


def _insert_job(conn, ws_id: str, job_type: str, deadline_s: int, inp: dict, op: str, key: str, h: str) -> str:
    now = utcnow()
    job_id = new_job_id()
    conn.execute("INSERT INTO jobs (id, workspace_id, type, state, stage, created_at, updated_at, deadline_at, input) "
                 "VALUES (?, ?, ?, 'queued', NULL, ?, ?, ?, ?)",
                 (job_id, ws_id, job_type, iso(now), iso(now), iso(now + timedelta(seconds=deadline_s)), dumps(inp)))
    conn.execute("INSERT INTO idempotency_keys VALUES (?, ?, ?, ?, ?, ?)", (ws_id, op, key, h, job_id, iso(now)))
    return job_id


def _job_response(request: Request, row) -> Response:
    job = job_to_api(row)
    return ok(request, job, "JobEnvelope", status=202, data_revision=job["input_context"]["data_revision"])


# --- анализ ----------------------------------------------------------------------
async def create_analysis(request: Request):
    s = request.app.state.settings
    if not s.feature_analysis:
        raise ApiError("AI_UNAVAILABLE", "Анализ AI сейчас выключен. Каталог, сравнение и источники доступны.")
    ws = session_workspace(request)
    key = _idem_key(request)
    body = await read_json(request, "AnalysisRequest")
    if body["data_revision"] != ws["data_revision"]:
        raise validation_error([{"field": "data_revision", "reason": "must_match_workspace", "current_revision": ws["data_revision"]}])
    known = request.app.state.db.existing_ids(ws["data_revision"], "investigation", body["selected_investigation_ids"])
    missing = [{"field": f"selected_investigation_ids[{i}]", "reason": "not_found_in_revision"}
               for i, x in enumerate(body["selected_investigation_ids"]) if x not in known]
    if missing:
        raise validation_error(missing)
    h = body_hash(body)
    db = request.app.state.db
    with db.write() as conn:
        existing = _replay(conn, ws["id"], "analysis", key, h)
        if existing is not None:
            return _job_response(request, existing)
        state = _check_ws_revision(conn, ws["id"], body["workspace_revision"])
        _rate_limit(conn, ws["id"], "analysis", s.analysis_active_max, s.analysis_per_minute)
        scenario = state["scenario"]
        inp = {
            "workspace_id": ws["id"], "request": body, "scenario_snapshot": scenario,
            "input_context": {"workspace_revision": body["workspace_revision"], "data_revision": ws["data_revision"],
                              "scenario_id": scenario["scenario_id"] if scenario else None},
        }
        job_id = _insert_job(conn, ws["id"], "analysis", s.analysis_deadline_s, inp, "analysis", key, h)
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    request.app.state.runner.submit(job_id)
    return _job_response(request, row)


def _own_job(request: Request):
    ws = session_workspace(request)
    with request.app.state.db.read() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (request.path_params["id"],)).fetchone()
    if row is None:
        raise ApiError("NOT_FOUND", "Задача не найдена.")
    if row["workspace_id"] != ws["id"]:
        raise ApiError("ACCESS_DENIED", "Задача принадлежит другой сессии.")
    return ws, row


async def get_job(request: Request):
    _, row = _own_job(request)
    job = job_to_api(row)
    return ok(request, job, "JobEnvelope", data_revision=job["input_context"]["data_revision"])


async def cancel_job(request: Request):
    _, row = _own_job(request)
    now = iso(utcnow())
    with request.app.state.db.write() as conn:
        cur = conn.execute("UPDATE jobs SET state='cancelled', updated_at=? WHERE id=? AND state IN ('queued','running')",
                           (now, row["id"]))
        if cur.rowcount == 1 and row["type"] == "report":
            conn.execute("UPDATE reports SET state='failed', error=? WHERE job_id=? AND state='preparing'",
                         (dumps({"code": "EXPORT_FAILED", "message": "Экспорт отменен пользователем.", "details": [],
                                 "retryable": True}), row["id"]))
        state = conn.execute("SELECT state FROM jobs WHERE id=?", (row["id"],)).fetchone()["state"]
    if cur.rowcount != 1:
        raise ApiError("JOB_ALREADY_FINISHED", details=[{"field": "state", "reason": state}])
    request.app.state.metrics.job_finished(row["type"], "cancelled", None)
    return Response(status_code=204)


async def get_answer(request: Request):
    ws = session_workspace(request)
    with request.app.state.db.read() as conn:
        row = conn.execute("SELECT workspace_id, body FROM answers WHERE id=?", (request.path_params["id"],)).fetchone()
    if row is None:
        raise ApiError("NOT_FOUND", "Ответ не найден.")
    if row["workspace_id"] != ws["id"]:
        raise ApiError("ACCESS_DENIED", "Этот ответ принадлежит другой сессии.")
    answer = json.loads(row["body"])
    return ok(request, answer, "AnalysisResultEnvelope", data_revision=answer["data_revision"])


# --- отчеты ----------------------------------------------------------------------
def _report_snapshot(request: Request, ws: dict, body: dict, state: dict, conn) -> dict:
    db = request.app.state.db
    rev = ws["data_revision"]
    answers = []
    if body["answer_ids"]:
        q = ",".join("?" * len(body["answer_ids"]))
        rows = {r["id"]: r for r in conn.execute(f"SELECT id, workspace_id, data_revision, body FROM answers WHERE id IN ({q})",
                                                  body["answer_ids"])}
        bad = [{"field": f"answer_ids[{i}]", "reason": "not_in_workspace"} for i, a in enumerate(body["answer_ids"])
               if a not in rows or rows[a]["workspace_id"] != ws["id"] or rows[a]["data_revision"] != rev]
        if bad:
            raise validation_error(bad, "Ответ не принадлежит текущему пространству или его версии данных.")
        answers = [json.loads(rows[a]["body"]) for a in body["answer_ids"]]
    invs_map = db.get_entities(rev, "investigation", body["investigation_ids"])
    bad = [{"field": f"investigation_ids[{i}]", "reason": "not_found_in_revision"}
           for i, x in enumerate(body["investigation_ids"]) if x not in invs_map]
    if bad:
        raise validation_error(bad)
    invs = [invs_map[i] for i in body["investigation_ids"]]
    claim_ids = dedupe([cid for i in invs for cid in i["claim_ids"]])
    claims = [cl for cl in db.get_entities(rev, "claim", claim_ids).values() if (cl["kind"], cl["review_status"]) in PUBLISHED_CLAIMS]
    src_ids = dedupe([s for i in invs for s in i["source_ids"]] + [cit["source_id"] for a in answers for cit in a["citations"]])
    sources = db.get_entities(rev, "source", src_ids)
    materials = db.get_entities(rev, "material", dedupe([m for i in invs for m in i["material_ids"]]))
    comparison = None
    if body["include_comparison"] and 2 <= len(invs) <= 3:
        runs = db.runs_for(rev, [i["id"] for i in invs])
        comparison = build_table(invs, runs, materials, request.app.state.dictionaries)
    return {
        "title": body["title"], "created_at": iso(utcnow()), "contract_version": c.contract_version(),
        "data_revision": rev, "workspace_revision": body["workspace_revision"], "scenario": state["scenario"],
        "answers": answers, "investigations": invs, "claims": claims, "materials": materials,
        "sources": [sources[s] for s in src_ids if s in sources], "comparison": comparison,
        "dictionaries": request.app.state.dictionaries,
    }


async def create_report(request: Request):
    s = request.app.state.settings
    if not s.feature_reports:
        raise ApiError("AI_UNAVAILABLE", "Экспорт отчетов сейчас выключен.")
    ws = session_workspace(request)
    key = _idem_key(request)
    body = await read_json(request, "ReportRequest")
    body["answer_ids"] = dedupe(body["answer_ids"])
    body["investigation_ids"] = dedupe(body["investigation_ids"])
    h = body_hash(body)
    db = request.app.state.db
    with db.write() as conn:
        existing = _replay(conn, ws["id"], "report", key, h)
        if existing is not None:
            return _job_response(request, existing)
        state = _check_ws_revision(conn, ws["id"], body["workspace_revision"])
        snapshot = _report_snapshot(request, ws, body, state, conn)
        _rate_limit(conn, ws["id"], "report", s.reports_active_max, None)
        report_id = "rpt_" + secrets.token_hex(12)
        snapshot["report_id"] = report_id
        scenario = state["scenario"]
        inp = {"workspace_id": ws["id"], "report_id": report_id, "snapshot": snapshot,
               "input_context": {"workspace_revision": body["workspace_revision"], "data_revision": ws["data_revision"],
                                 "scenario_id": scenario["scenario_id"] if scenario else None}}
        job_id = _insert_job(conn, ws["id"], "report", s.report_deadline_s, inp, "report", key, h)
        now = utcnow()
        conn.execute("INSERT INTO reports (id, workspace_id, job_id, state, title, source_workspace_revision, data_revision, "
                     "created_at, expires_at) VALUES (?, ?, ?, 'preparing', ?, ?, ?, ?, ?)",
                     (report_id, ws["id"], job_id, body["title"], body["workspace_revision"], ws["data_revision"],
                      iso(now), iso(plus(now, hours=s.report_hours))))
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    request.app.state.runner.submit(job_id)
    return _job_response(request, row)


def _own_report(request: Request):
    ws = session_workspace(request)
    with request.app.state.db.read() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id=?", (request.path_params["id"],)).fetchone()
    if row is None:
        raise ApiError("NOT_FOUND", "Отчет не найден.")
    if row["workspace_id"] != ws["id"]:
        raise ApiError("ACCESS_DENIED", "Отчет принадлежит другой сессии.")
    return row


def report_to_api(row) -> dict:
    state = row["state"]
    if state == "ready" and row["expires_at"] <= iso(utcnow()):
        state = "expired"
    return {
        "id": row["id"], "state": state, "title": row["title"], "source_workspace_revision": row["source_workspace_revision"],
        "data_revision": row["data_revision"], "created_at": row["created_at"], "expires_at": row["expires_at"],
        "download_path": f"/api/v1/reports/{row['id']}/download" if state == "ready" else None,
        "sha256": row["sha256"] if state == "ready" else None,
        "error": json.loads(row["error"]) if row["error"] and state == "failed" else None,
    }


async def get_report(request: Request):
    rep = report_to_api(_own_report(request))
    return ok(request, rep, "ReportEnvelope", data_revision=rep["data_revision"])


async def download_report(request: Request):
    row = _own_report(request)
    rep = report_to_api(row)
    request.state.data_revision = rep["data_revision"]
    if rep["state"] == "expired":
        raise ApiError("RESOURCE_EXPIRED", "Срок хранения отчета истек. Создайте отчет заново.")
    if rep["state"] == "preparing":
        raise ApiError("REPORT_NOT_READY", "Отчет еще готовится.", retryable=True)
    if rep["state"] == "failed":
        raise ApiError("REPORT_NOT_READY", "Отчет не был создан. Запустите экспорт заново.", retryable=False)
    path = request.app.state.settings.reports_dir / row["file_name"]
    if not path.is_file():
        raise ApiError("RESOURCE_EXPIRED", "Файл отчета больше недоступен. Создайте отчет заново.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
        raise ApiError("INTERNAL_ERROR", "Файл отчета поврежден. Создайте отчет заново.")
    return FileResponse(path, media_type="application/pdf", filename=f"fire-atlas-{row['id']}.pdf",
                        headers={"Cache-Control": "no-store"})


__all__ = ["create_analysis", "get_job", "cancel_job", "get_answer", "create_report", "get_report", "download_report", "TERMINAL"]
