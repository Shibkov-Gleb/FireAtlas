"""Гостевые пространства (BE-03, 13.3).

* Доступ - только по HttpOnly cookie; ID пространства не секрет и доступа не дает.
* Токен хранится в БД как sha256; сам токен знает только браузер.
* PATCH: If-Match обязателен; обновление условное (WHERE revision = ?), поэтому
  параллельное изменение никогда не теряется - проигравший получает 409 (AT-18).
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets

from starlette.requests import Request

from .db import dumps, iso, plus, utcnow
from .errors import ApiError, validation_error
from .http import dedupe, ok, read_json

ETAG_RE = re.compile(r'^(?:W/)?"([1-9][0-9]*)"$')
EMPTY_STATE = {"scenario": None, "selected_investigation_ids": [], "saved_investigation_ids": [], "saved_answer_ids": []}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _to_api(row) -> dict:
    state = json.loads(row["state"])
    return {
        "id": row["id"],
        "revision": row["revision"],
        "scenario": state["scenario"],
        "selected_investigation_ids": state["selected_investigation_ids"],
        "saved_investigation_ids": state["saved_investigation_ids"],
        "saved_answer_ids": state["saved_answer_ids"],
        "data_revision": row["data_revision"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
    }


def _etag(rev: int) -> str:
    return f'"{rev}"'


def session_workspace(request: Request, touch: bool = True) -> dict:
    """Возвращает пространство текущей сессии или 401. Продлевает срок жизни (7 суток с последнего действия)."""
    s = request.app.state.settings
    token = request.cookies.get(s.cookie_name)
    if not token or len(token) > 128:
        raise ApiError("SESSION_REQUIRED")
    db = request.app.state.db
    now = utcnow()
    with db.write() as conn:
        row = conn.execute("SELECT * FROM workspaces WHERE session_hash = ?", (_hash(token),)).fetchone()
        if row is None or row["expires_at"] <= iso(now):
            raise ApiError("SESSION_REQUIRED")
        if touch:
            conn.execute("UPDATE workspaces SET expires_at = ? WHERE id = ?", (iso(plus(now, days=s.workspace_days)), row["id"]))
            row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (row["id"],)).fetchone()
    ws = _to_api(row)
    request.state.data_revision = ws["data_revision"]
    request.state.workspace_id = ws["id"]
    return ws


async def create_workspace(request: Request):
    await read_json(request, "EmptyObject")
    s = request.app.state.settings
    try:
        ws = session_workspace(request)
        return ok(request, ws, "WorkspaceEnvelope", status=200, data_revision=ws["data_revision"],
                  headers={"ETag": _etag(ws["revision"])})
    except ApiError as e:
        if e.code != "SESSION_REQUIRED":
            raise
    db = request.app.state.db
    active = db.active_revision()
    if active is None:
        raise ApiError("DATA_NOT_READY")
    token = secrets.token_urlsafe(32)
    now = utcnow()
    ws_id = "ws_" + secrets.token_hex(12)
    with db.write() as conn:
        conn.execute(
            "INSERT INTO workspaces (id, session_hash, revision, data_revision, state, created_at, updated_at, expires_at) "
            "VALUES (?, ?, 1, ?, ?, ?, ?, ?)",
            (ws_id, _hash(token), active, dumps(EMPTY_STATE), iso(now), iso(now), iso(plus(now, days=s.workspace_days))),
        )
        row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    ws = _to_api(row)
    resp = ok(request, ws, "WorkspaceEnvelope", status=201, data_revision=active, headers={"ETag": _etag(1)})
    resp.set_cookie(s.cookie_name, token, max_age=s.workspace_days * 86400, path="/api", httponly=True,
                    samesite="lax", secure=s.cookie_secure)
    return resp


async def get_workspace(request: Request):
    ws = session_workspace(request)
    return ok(request, ws, "WorkspaceEnvelope", data_revision=ws["data_revision"], headers={"ETag": _etag(ws["revision"])})


def _validate_refs(request: Request, ws: dict, patch: dict) -> None:
    db = request.app.state.db
    rev = ws["data_revision"]
    problems = []
    for field in ("selected_investigation_ids", "saved_investigation_ids"):
        if field in patch:
            known = db.existing_ids(rev, "investigation", patch[field])
            problems += [{"field": f"{field}[{i}]", "reason": "not_found_in_revision"}
                         for i, x in enumerate(patch[field]) if x not in known]
    if "saved_answer_ids" in patch and patch["saved_answer_ids"]:
        ids = patch["saved_answer_ids"]
        with db.read() as conn:
            q = ",".join("?" * len(ids))
            own = {r[0] for r in conn.execute(
                f"SELECT id FROM answers WHERE workspace_id = ? AND data_revision = ? AND id IN ({q})", (ws["id"], rev, *ids))}
        problems += [{"field": f"saved_answer_ids[{i}]", "reason": "not_in_workspace"} for i, x in enumerate(ids) if x not in own]
    sc = patch.get("scenario")
    if sc:
        known = db.existing_ids(rev, "material", sc["material_ids"])
        problems += [{"field": f"scenario.material_ids[{i}]", "reason": "not_found_in_revision"}
                     for i, x in enumerate(sc["material_ids"]) if x not in known]
        src_ids = dedupe([s for a in sc["assumptions"] for s in a["source_ids"]])
        known_src = db.existing_ids(rev, "source", src_ids)
        problems += [{"field": "scenario.assumptions.source_ids", "reason": f"not_found_in_revision:{x}"}
                     for x in src_ids if x not in known_src]
    if problems:
        raise validation_error(problems, "Изменение ссылается на объекты, которых нет в данных пространства.")


async def patch_workspace(request: Request):
    if_match = request.headers.get("if-match")
    ws = session_workspace(request)
    if if_match is None:
        raise validation_error([{"field": "If-Match", "reason": "required"}], "Нужен заголовок If-Match с ревизией пространства.")
    m = ETAG_RE.match(if_match.strip())
    if not m:
        raise validation_error([{"field": "If-Match", "reason": "invalid_format"}])
    expected = int(m.group(1))
    patch = await read_json(request, "WorkspacePatch")
    for k in ("selected_investigation_ids", "saved_investigation_ids", "saved_answer_ids"):
        if k in patch:
            patch[k] = dedupe(patch[k])
    _validate_refs(request, ws, patch)

    s = request.app.state.settings
    db = request.app.state.db
    now = utcnow()
    with db.write() as conn:
        row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws["id"],)).fetchone()
        state = json.loads(row["state"])
        state.update(patch)
        cur = conn.execute(
            "UPDATE workspaces SET state = ?, revision = revision + 1, updated_at = ?, expires_at = ? "
            "WHERE id = ? AND revision = ?",
            (dumps(state), iso(now), iso(plus(now, days=s.workspace_days)), ws["id"], expected),
        )
        if cur.rowcount != 1:
            current = conn.execute("SELECT revision FROM workspaces WHERE id = ?", (ws["id"],)).fetchone()[0]
            raise ApiError("WORKSPACE_CONFLICT",
                           details=[{"field": "workspace_revision", "reason": "stale_revision", "current_revision": current}],
                           data_revision=ws["data_revision"])
        row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws["id"],)).fetchone()
    new = _to_api(row)
    return ok(request, new, "WorkspaceEnvelope", data_revision=new["data_revision"], headers={"ETag": _etag(new["revision"])})
