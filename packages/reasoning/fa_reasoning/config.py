"""Настройки подключения модели (A2-02). Ключи берутся только из окружения или локального .env.

Переменные:
  FA_LLM_PROVIDER      openai | gemini | offline | none. По умолчанию: openai, если есть OPENAI_API_KEY,
                       иначе gemini, если есть GEMINI_API_KEY, иначе none (анализ вернет MODEL_PROVIDER_ERROR).
                       offline - ответ из проверенных выводов без модели (для отладки и запасного режима).
  FA_LLM_MODEL         название модели; по умолчанию gpt-6-luna / gemini-3.5-flash (решение команды 15.11.2026).
  FA_LLM_BASE_URL      адрес API, совместимого с OpenAI (по умолчанию - официальный адрес провайдера).
  FA_LLM_MAX_TOKENS    лимит токенов ответа вместе с рассуждением модели (по умолчанию 8000).
  FA_LLM_REASONING_EFFORT  если задано (low | medium | high) - передается моделям с рассуждением.
  FA_LLM_TEMPERATURE   если задано - передается модели; некоторые модели принимают только значение по умолчанию.
  FA_LLM_STRUCTURED    json_schema (строгая схема, по умолчанию) | json_object (только «верни JSON»).
  OPENAI_API_KEY, GEMINI_API_KEY - ключи. Никогда не попадают в код, логи и ответ.
  FA_DOTENV            путь к .env; по умолчанию ищется .env в текущей папке и выше.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROVIDERS = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-6-luna", "key": "OPENAI_API_KEY",
               "max_tokens_param": "max_completion_tokens"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-3.5-flash",
               "key": "GEMINI_API_KEY", "max_tokens_param": "max_tokens"},
}
_DOTENV_KEYS = ("OPENAI_API_KEY", "GEMINI_API_KEY")
_DOTENV_PREFIX = "FA_LLM_"


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str | None
    api_key: str | None
    base_url: str | None
    max_tokens: int = 8000
    reasoning_effort: str | None = None
    max_tokens_param: str = "max_completion_tokens"
    temperature: float | None = None
    structured: str = "json_schema"

    def __repr__(self) -> str:  # ключ не должен попасть в логи
        return f"LLMConfig(provider={self.provider!r}, model={self.model!r}, key={'set' if self.api_key else 'none'})"


def _find_dotenv() -> Path | None:
    explicit = os.environ.get("FA_DOTENV")
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        for d in (start, *start.parents):
            p = d / ".env"
            if p.is_file():
                return p
    return None


def read_dotenv(path: Path | None = None) -> dict[str, str]:
    """Читает из .env только ключи моделей и FA_LLM_*. Остальное (настройки бэкенда) не трогает."""
    path = path or _find_dotenv()
    out: dict[str, str] = {}
    if not path:
        return out
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.split(" #", 1)[0].strip().strip('"').strip("'")
        if v and (k in _DOTENV_KEYS or k.startswith(_DOTENV_PREFIX)):
            out[k] = v
    return out


def from_env(env: dict[str, str] | None = None) -> LLMConfig:
    if env is None:
        env = {**read_dotenv(), **{k: v for k, v in os.environ.items() if v}}
    provider = env.get("FA_LLM_PROVIDER", "").strip().lower()
    if not provider:
        provider = "openai" if env.get("OPENAI_API_KEY") else "gemini" if env.get("GEMINI_API_KEY") else "none"
    if provider in ("offline", "none"):
        return LLMConfig(provider=provider, model=None, api_key=None, base_url=None)
    if provider not in PROVIDERS:
        raise ValueError(f"FA_LLM_PROVIDER: неизвестный провайдер {provider!r}")
    p = PROVIDERS[provider]
    temp = env.get("FA_LLM_TEMPERATURE")
    return LLMConfig(
        provider=provider,
        model=env.get("FA_LLM_MODEL") or p["model"],
        api_key=env.get(p["key"]) or None,
        base_url=(env.get("FA_LLM_BASE_URL") or p["base_url"]).rstrip("/"),
        max_tokens=int(env.get("FA_LLM_MAX_TOKENS", "8000")),
        reasoning_effort=env.get("FA_LLM_REASONING_EFFORT") or None,
        max_tokens_param=p["max_tokens_param"],
        temperature=float(temp) if temp not in (None, "") else None,
        structured=env.get("FA_LLM_STRUCTURED", "json_schema"),
    )
