"""A2-02. Адаптер модели через API, совместимый с OpenAI (OpenAI, Gemini).

Ключ берется из настроек и передается только в заголовке запроса к провайдеру. Ответ модели всегда
разбирается и проверяется кодом: структурированный выход не считается гарантией.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Callable

from .config import LLMConfig
from .errors import ModelOutputError, ProviderError, ReasoningTimeout

# transport(url, headers, body_bytes, timeout_s) -> (http_status, response_bytes)
Transport = Callable[[str, dict, bytes, float], tuple[int, bytes]]


def urllib_transport(url: str, headers: dict, body: bytes, timeout_s: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (TimeoutError, socket.timeout) as e:
        raise ReasoningTimeout("модель не ответила до дедлайна") from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise ReasoningTimeout("модель не ответила до дедлайна") from e
        raise ProviderError(f"провайдер недоступен: {type(e.reason).__name__}") from e
    except OSError as e:
        raise ProviderError(f"провайдер недоступен: {type(e).__name__}") from e


class ChatModel:
    """Вызов модели: messages + JSON Schema -> (разобранный JSON, сведения о модели)."""

    def __init__(self, cfg: LLMConfig, transport: Transport = urllib_transport):
        if not cfg.api_key:
            raise ProviderError(f"ключ провайдера {cfg.provider} не задан")
        self.cfg = cfg
        self.transport = transport

    def __call__(self, messages: list[dict], schema: dict, timeout_s: float) -> tuple[dict, dict]:
        cfg = self.cfg
        body: dict = {"model": cfg.model, "messages": messages, cfg.max_tokens_param: cfg.max_tokens}
        if cfg.structured == "json_schema":
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "fire_atlas_answer", "strict": True, "schema": schema}}
        else:
            body["response_format"] = {"type": "json_object"}
        if cfg.temperature is not None:
            body["temperature"] = cfg.temperature
        if cfg.reasoning_effort:
            body["reasoning_effort"] = cfg.reasoning_effort
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {cfg.api_key}"}
        status, raw = self.transport(f"{cfg.base_url}/chat/completions", headers,
                                     json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout_s)
        if status in (408, 504):
            raise ReasoningTimeout(f"провайдер вернул HTTP {status}")
        if status >= 400:
            raise ProviderError(f"провайдер вернул HTTP {status}: {_error_text(raw)}")
        try:
            data = json.loads(raw)
            choice = data["choices"][0]
            msg = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ProviderError("провайдер вернул ответ неизвестного формата") from e
        meta = {"model": cfg.model, "model_version": data.get("model") or cfg.model, "provider": cfg.provider,
                "usage": data.get("usage")}
        if msg.get("refusal"):
            raise ModelOutputError("модель отказалась отвечать")
        if choice.get("finish_reason") == "length":
            raise ModelOutputError("ответ модели обрезан по лимиту токенов")
        content = msg.get("content")
        if isinstance(content, list):  # некоторые провайдеры возвращают части
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return parse_json(content), meta


def parse_json(content) -> dict:
    if not isinstance(content, str) or not content.strip():
        raise ModelOutputError("пустой ответ модели")
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    try:
        obj = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ModelOutputError("ответ модели не JSON")
        try:
            obj = json.loads(text[start:end + 1])
        except ValueError as e:
            raise ModelOutputError("ответ модели не JSON") from e
    if not isinstance(obj, dict):
        raise ModelOutputError("ответ модели не объект JSON")
    return obj


def _error_text(raw: bytes) -> str:
    try:
        err = json.loads(raw)
        err = err[0] if isinstance(err, list) and err else err
        return str((err.get("error") or {}).get("message", ""))[:200]
    except Exception:  # noqa: BLE001
        return ""
