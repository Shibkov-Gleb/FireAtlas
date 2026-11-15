"""A2-02: адаптер модели и настройки без сети."""
import json

import pytest

from fa_reasoning.config import from_env, read_dotenv
from fa_reasoning.errors import ModelOutputError, ProviderError, ReasoningTimeout
from fa_reasoning.llm import ChatModel, parse_json

KEY = "sk-test-not-a-real-key"


def cfg(**env):
    return from_env({"OPENAI_API_KEY": KEY, **env})


def transport(status=200, content='{"status": "answered"}', finish="stop", seen=None):
    def t(url, headers, body, timeout):
        if seen is not None:
            seen.update(url=url, headers=headers, body=json.loads(body), timeout=timeout)
        payload = {"model": "gpt-test-2026", "choices": [{"finish_reason": finish, "message": {"content": content}}],
                   "usage": {"total_tokens": 10}}
        return status, json.dumps(payload).encode()
    return t


def test_request_uses_strict_schema_and_key_only_in_header():
    seen = {}
    out, meta = ChatModel(cfg(), transport(seen=seen))([{"role": "user", "content": "q"}], {"type": "object"}, 20)
    assert out == {"status": "answered"}
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"]["Authorization"] == f"Bearer {KEY}"
    assert seen["body"]["response_format"]["json_schema"]["strict"] is True
    assert seen["body"]["model"] == "gpt-6-luna" and "temperature" not in seen["body"]
    assert KEY not in json.dumps(seen["body"])
    assert meta["model_version"] == "gpt-test-2026"
    assert seen["timeout"] == 20


def test_key_not_in_repr():
    assert KEY not in repr(cfg())


@pytest.mark.parametrize("status,exc", [(500, ProviderError), (429, ProviderError), (401, ProviderError),
                                        (408, ReasoningTimeout), (504, ReasoningTimeout)])
def test_http_errors(status, exc):
    with pytest.raises(exc):
        ChatModel(cfg(), transport(status=status))([], {}, 5)


def test_truncated_answer_is_format_error():
    with pytest.raises(ModelOutputError):
        ChatModel(cfg(), transport(finish="length"))([], {}, 5)


def test_missing_key():
    with pytest.raises(ProviderError):
        ChatModel(from_env({"FA_LLM_PROVIDER": "openai"}))


def test_parse_json_variants():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Ответ: {"a": 1}') == {"a": 1}
    for bad in ("", "не json", "[1, 2]", None):
        with pytest.raises(ModelOutputError):
            parse_json(bad)


def test_provider_selection():
    assert from_env({}).provider == "none"
    assert from_env({"GEMINI_API_KEY": "g"}).provider == "gemini"
    g = from_env({"FA_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "g", "FA_LLM_MODEL": "gemini-x"})
    assert g.base_url.endswith("/v1beta/openai") and g.model == "gemini-x" and g.max_tokens_param == "max_tokens"
    assert from_env({"FA_LLM_PROVIDER": "offline"}).provider == "offline"
    with pytest.raises(ValueError):
        from_env({"FA_LLM_PROVIDER": "deepseek"})


def test_dotenv_reads_only_model_keys(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# comment\nOPENAI_API_KEY=abc\nFA_CURSOR_SECRET=zzz\nFA_LLM_MODEL=m1 # note\nGEMINI_API_KEY=\n",
                 encoding="utf-8")
    assert read_dotenv(p) == {"OPENAI_API_KEY": "abc", "FA_LLM_MODEL": "m1"}
