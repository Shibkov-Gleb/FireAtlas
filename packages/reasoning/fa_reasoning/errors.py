"""Ошибки модуля AI 2 (A2-08).

Бэкенд различает ошибки по классу исключения (D-025, apps/api/fire_atlas_api/providers.py):
  ProviderError     -> MODEL_PROVIDER_ERROR  (провайдер модели недоступен или вернул ошибку)
  ReasoningTimeout  -> REASONING_TIMEOUT     (не успели до дедлайна)
  ContractViolation -> VALIDATION_FAILED     (модель вернула неверную структуру даже после исправления)
Научная недостаточность - не ошибка: это ответ со статусом insufficient_evidence.

Если модуль работает в одном процессе с бэкендом, используются классы бэкенда. Без бэкенда
(тесты AI 2, оценка) - собственные классы с теми же кодами.
"""
from __future__ import annotations

try:  # pragma: no cover - ветка зависит от окружения
    from fire_atlas_api.providers import AIError, ContractViolation, ProviderError, ReasoningTimeout
except Exception:  # noqa: BLE001 - бэкенд не установлен
    class AIError(Exception):
        code = "INTERNAL_ERROR"
        retryable = True

        def __init__(self, message: str = ""):
            super().__init__(message or self.code)

    class ProviderError(AIError):
        code = "MODEL_PROVIDER_ERROR"

    class ReasoningTimeout(AIError):
        code = "REASONING_TIMEOUT"

    class ContractViolation(AIError):
        code = "VALIDATION_FAILED"


class ModelOutputError(Exception):
    """Ответ модели не разобран как JSON нужной структуры. Внутренняя ошибка: дает один исправляющий проход,
    затем превращается в ContractViolation."""


__all__ = ["AIError", "ContractViolation", "ModelOutputError", "ProviderError", "ReasoningTimeout"]
