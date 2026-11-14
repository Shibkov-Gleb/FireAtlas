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
    "MALFORMED_JSON": "Некорректный запрос: тело должно быть JSON-объектом.",
    "SESSION_REQUIRED": "Сессия не найдена или истекла. Создайте новое гостевое пространство.",
    "ACCESS_DENIED": "Доступ запрещен.",
    "NOT_FOUND": "Объект не найден.",
    "WORKSPACE_CONFLICT": "Контекст изменился. Обновите его перед повтором.",
    "IDEMPOTENCY_CONFLICT": "Этот запрос уже отправлялся с другими данными.",
    "JOB_ALREADY_FINISHED": "Задача уже завершена.",
    "REPORT_NOT_READY": "Отчет еще не готов.",
    "DATA_REVISION_GONE": "Эта версия данных больше недоступна.",
    "RESOURCE_EXPIRED": "Срок хранения истек.",
    "VALIDATION_ERROR": "Запрос не прошел проверку.",
    "INVALID_CURSOR": "Список изменился. Загрузите его заново.",
    "RATE_LIMITED": "Слишком много запросов. Повторите позже.",
    "INTERNAL_ERROR": "Внутренняя ошибка сервиса. Сообщите request_id.",
    "MODEL_PROVIDER_ERROR": "Сервис генерации ответа недоступен.",
    "AI_UNAVAILABLE": "AI временно недоступен. Каталог и источники работают.",
    "DATA_NOT_READY": "Данные еще не опубликованы. Попробуйте позже.",
    "JOB_TIMEOUT": "Ответ не получен за отведенное время.",
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
        message = "Запрос содержит недопустимые поля."
    return ApiError("VALIDATION_ERROR", message, [dict(v) for v in violations])
