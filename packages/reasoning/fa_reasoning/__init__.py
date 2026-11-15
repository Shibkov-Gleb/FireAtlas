"""Модуль AI 2 Fire Atlas: применимость (A2-04), ответы с доказательствами и их проверка (A2-03, A2-05…A2-08)."""
from .applicability import RULES_VERSION, assess_applicability
from .reason import REASONING_REVISION, reason

__all__ = ["REASONING_REVISION", "RULES_VERSION", "assess_applicability", "reason"]
