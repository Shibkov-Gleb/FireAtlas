"""Общие HTTP-помощники: envelope, разбор JSON, ревизии, курсоры."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from typing import Any

import fa_contracts as c
from fa_contracts.english import english_display
from starlette.requests import Request
from starlette.responses import JSONResponse

from .errors import ApiError, validation_error

log = logging.getLogger("fire_atlas.api")
JSON_CT = "application/json"


def meta(request: Request, data_revision: str | None, warnings: list[dict] | None = None) -> dict:
    return {
        "request_id": request.state.request_id,
        "contract_version": c.contract_version(),
        "data_revision": data_revision,
        "warnings": warnings or [],
    }


class ContractJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(english_display(content), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def ok(request: Request, data: Any, schema: str, *, status: int = 200, data_revision: str | None = None,
       warnings: list[dict] | None = None, headers: dict[str, str] | None = None) -> JSONResponse:
    body = {"data": data, "meta": meta(request, data_revision, warnings)}
    settings = request.app.state.settings
    if settings.validate_responses:
        violations = c.errors_for(schema, body)
        if violations:
            # Расхождение кода с контрактом - дефект бэкенда. Клиенту не отдаем невалидный объект.
            log.error("response_contract_violation", extra={"schema": schema, "violations": violations,
                                                             "request_id": request.state.request_id})
            raise ApiError("INTERNAL_ERROR", "The server response failed contract validation. Report the request_id.")
    return ContractJSONResponse(body, status_code=status, headers=headers)


async def read_json(request: Request, schema: str) -> dict:
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype != JSON_CT:
        raise ApiError("MALFORMED_JSON", "Content-Type: application/json is required.",
                       [{"field": "Content-Type", "reason": "unsupported_media_type"}])
    raw = await request.body()
    if len(raw) > request.app.state.settings.max_body_bytes:
        raise validation_error([{"field": "$", "reason": "body_too_large"}], "The request is too large.")
    try:
        body = c.strict_json_loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ApiError("MALFORMED_JSON")
    if not isinstance(body, dict):
        raise ApiError("MALFORMED_JSON")
    body = _sanitize(body)
    violations = c.errors_for(schema, body)
    if violations:
        raise validation_error(violations)
    return body


def _sanitize(v: Any) -> Any:
    """11.2: строки обрезаются по краям; управляющие символы удаляются."""
    if isinstance(v, str):
        return "".join(ch for ch in v if ch in "\n\t" or ord(ch) >= 32 and ord(ch) != 127).strip()
    if isinstance(v, list):
        return [_sanitize(x) for x in v]
    if isinstance(v, dict):
        return {k: _sanitize(x) for k, x in v.items()}
    return v


def query_param(request: Request, name: str, schema: str, required: bool = True) -> str | None:
    val = request.query_params.get(name)
    if val is None:
        if required:
            raise validation_error([{"field": name, "reason": "required"}])
        return None
    for v in c.errors_for(schema, val):
        raise validation_error([{"field": name, "reason": v["reason"]}])
    return val


def int_param(request: Request, name: str, default: int, lo: int, hi: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        val = int(raw)
    except ValueError:
        raise validation_error([{"field": name, "reason": "wrong_type"}])
    if not lo <= val <= hi:
        raise validation_error([{"field": name, "reason": "out_of_range"}])
    return val


def require_revision(request: Request, rev: str) -> str:
    """Ревизия обязательна и не заменяется активной (BE-04)."""
    db = request.app.state.db
    request.state.data_revision = rev
    active = db.active_revision()
    if active is None:
        raise ApiError("DATA_NOT_READY", data_revision=None)
    if not db.revision_exists(rev):
        raise ApiError("DATA_REVISION_GONE", details=[{"field": "data_revision", "reason": "unknown_or_removed",
                                                       "current_revision": active}], data_revision=rev)
    return rev


def dedupe(items: list) -> list:
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# --- Курсоры: непрозрачные, подписанные, привязаны к ревизии/фильтрам ----------
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def encode_cursor(secret: bytes, payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(secret, raw, hashlib.sha256).digest()[:12]
    return _b64(raw) + "." + _b64(sig)


def decode_cursor(secret: bytes, cursor: str, binding: dict) -> dict:
    try:
        body, sig = cursor.split(".", 1)
        raw = _unb64(body)
        if not hmac.compare_digest(hmac.new(secret, raw, hashlib.sha256).digest()[:12], _unb64(sig)):
            raise ValueError
        payload = json.loads(raw)
    except Exception:
        raise ApiError("INVALID_CURSOR", details=[{"field": "cursor", "reason": "invalid"}])
    for k, v in binding.items():
        if payload.get(k) != v:
            raise ApiError("INVALID_CURSOR", details=[{"field": "cursor", "reason": f"bound_to_other_{k}"}])
    return payload


def binding_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
