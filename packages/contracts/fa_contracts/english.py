"""English display text for legacy records, without rewriting stored scientific data."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CYRILLIC = re.compile(r"[\u0400-\u04ff]")


@lru_cache(maxsize=1)
def _catalogue():
    messages = json.loads((ROOT / "english-messages.json").read_text(encoding="utf-8"))
    old = json.loads((ROOT / "dictionaries.ru.json").read_text(encoding="utf-8"))
    new = json.loads((ROOT / "dictionaries.en.json").read_text(encoding="utf-8"))
    for key, entries in old.items():
        labels = {item["value"]: item["label"] for item in new[key]}
        messages.update({item["label"]: labels[item["value"]] for item in entries})
    messages.update({"неизвестно": "unknown", "мм": "mm", "см/с": "cm/s", "кПа": "kPa", "с": "s"})
    # Short unit symbols are replaced only as complete strings.
    fragments = [key for key in messages if len(key.strip()) > 2]
    pattern = re.compile("|".join(re.escape(key) for key in sorted(fragments, key=len, reverse=True)))
    return messages, pattern


@lru_cache(maxsize=4096)
def english_text(value: str) -> str:
    if not CYRILLIC.search(value):
        return value
    messages, pattern = _catalogue()
    return messages.get(value, pattern.sub(lambda match: messages[match[0]], value))


def english_display(value: Any, field: str = "") -> Any:
    if isinstance(value, str):
        # Preserve original source quotations, numeric representations and user questions.
        if field in {"question", "raw_value", "raw_unit", "excerpt"}:
            return value
        if field in {"name", "title"} and CYRILLIC.search(value):
            messages, _ = _catalogue()
            return messages.get(value, value)
        return english_text(value)
    if isinstance(value, list):
        return [english_display(item, field) for item in value]
    if isinstance(value, dict):
        return {key: english_display(item, key) for key, item in value.items()}
    return value
