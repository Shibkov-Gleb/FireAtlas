"""Общие помощники тестов AI 2. Пакеты в fixtures/bundles получены поиском AI 1 на ревизии psi-20261115-r2."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
for p in ("packages/reasoning", "packages/contracts", "apps/api"):
    if str(ROOT / p) not in sys.path:
        sys.path.insert(0, str(ROOT / p))

BUNDLES = Path(__file__).parent / "fixtures" / "bundles"
LIMITS = {"max_blocks": 8, "max_follow_ups": 3, "max_total_chars": 10000}
FAR = "2099-01-01T00:00:00Z"


def load_bundle(name: str) -> dict:
    return json.loads((BUNDLES / f"{name}.json").read_text(encoding="utf-8"))


def make_req(bundle: dict, deadline: str = FAR) -> dict:
    return {"request_id": "req_test", "evidence_bundle": bundle, "locale": "ru", "output_limits": dict(LIMITS),
            "deadline_at": deadline, "reasoning_revision": "default"}


class FakeModel:
    """Подставная модель: отдает заготовленные ответы по очереди и запоминает вызовы."""

    def __init__(self, *answers, meta=None):
        self.answers = list(answers)
        self.calls: list[list[dict]] = []
        self.meta = meta or {"model": "fake", "model_version": "fake-1"}

    def __call__(self, messages, schema, timeout_s):
        self.calls.append(copy.deepcopy(messages))
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return copy.deepcopy(a), dict(self.meta)


def block(kind, text, ev=(), facts=()):
    return {"kind": kind, "text": text, "evidence_ids": list(ev), "fact_ids": list(facts)}


def draft(status="answered", blocks=(), limitations=(), follow_ups=()):
    return {"status": status, "blocks": list(blocks), "limitations": list(limitations),
            "follow_up_questions": list(follow_ups)}


def backend_problems(resp, bundle):
    """Повторная проверка бэкенда (check_reasoning). None, если бэкенд недоступен в окружении."""
    try:
        from fire_atlas_api.validation import check_reasoning
    except Exception:  # noqa: BLE001
        return None
    return check_reasoning(resp, bundle, bundle.get("scenario"), LIMITS)


@pytest.fixture
def flex():
    return load_bundle("flex_30_34")


@pytest.fixture
def moon():
    return load_bundle("moon_30")


@pytest.fixture
def bass():
    return load_bundle("bass_ventilation")
