"""Единый формат ошибок CT-12 и таблица раздела 14."""
from __future__ import annotations

from typing import Any

STATUS = {
    "MALFORMED_JSON": 400,
    "SESSION_REQUIRED": 401,
    "ACCESS_DENIED": 403,
    "NOT_FOUND": 404,
    "WORKSPACE_CONFLICT": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "JOB_ALREADY_FINISHED": 409,
    "REPORT_NOT_READY": 409,
    "DATA_REVISION_GONE": 410,
    "RESOURCE_EXPIRED": 410,
    "VALIDATION_ERROR": 422,
    "INVALID_CURSOR": 422,
    "RATE_LIMITED": 429,
    "INTERNAL_ERROR": 500,
    "MODEL_PROVIDER_ERROR": 502,
    "AI_UNAVAILABLE": 503,
    "DATA_NOT_READY": 503,
    "JOB_TIMEOUT": 504,
}

DEFAULT_MESSAGES = {
    "MALFORMED_JSON": "Invalid request: the body must be a JSON object.",
    "SESSION_REQUIRED": "The session was not found or has expired. Create a new guest workspace.",
    "ACCESS_DENIED": "Access denied.",
    "NOT_FOUND": "Object not found.",
    "WORKSPACE_CONFLICT": "The context changed. Refresh it before retrying.",
    "IDEMPOTENCY_CONFLICT": "This request was already submitted with different data.",
    "JOB_ALREADY_FINISHED": "The job has already finished.",
    "REPORT_NOT_READY": "The report is not ready yet.",
    "DATA_REVISION_GONE": "This data revision is no longer available.",
    "RESOURCE_EXPIRED": "The retention period has expired.",
    "VALIDATION_ERROR": "The request failed validation.",
    "INVALID_CURSOR": "The list changed. Reload it.",
    "RATE_LIMITED": "Too many requests. Try again later.",
    "INTERNAL_ERROR": "Internal service error. Report the request_id.",
    "MODEL_PROVIDER_ERROR": "The answer generation service is unavailable.",
    "AI_UNAVAILABLE": "AI is temporarily unavailable. The catalog and sources remain available.",
    "DATA_NOT_READY": "The data have not been published yet. Try again later.",
    "JOB_TIMEOUT": "No answer was received before the deadline.",
}

RETRYABLE = {"RATE_LIMITED", "INTERNAL_ERROR", "MODEL_PROVIDER_ERROR", "AI_UNAVAILABLE", "DATA_NOT_READY", "JOB_TIMEOUT"}


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        details: list[dict[str, Any]] | None = None,
        *,
        data_revision: str | None = None,
        headers: dict[str, str] | None = None,
        retryable: bool | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.status = STATUS[code]
        self.message = message or DEFAULT_MESSAGES[code]
        self.details = [
            {"field": d.get("field"), "reason": d.get("reason"), "current_revision": d.get("current_revision")}
            for d in (details or [])
        ]
        self.data_revision = data_revision
        self.headers = headers or {}
        self.retryable = (code in RETRYABLE) if retryable is None else retryable

    def body(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details, "retryable": self.retryable}


def validation_error(violations: list[dict], message: str | None = None) -> ApiError:
    if message is None and violations and all(v.get("reason") == "unexpected_field" for v in violations):
        message = "The request contains invalid fields."
    return ApiError("VALIDATION_ERROR", message, [dict(v) for v in violations])
