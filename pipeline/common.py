"""Shared helpers for building a Fire Atlas data release (AI 1).

Implements the data contracts of the technical specification, part 2:
Quantity (CT-02), Source (CT-03), Evidence (CT-04) and unit conversion.
"""
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

SCHEMA_VERSION = "1.1.0"
CONVERSION_TABLE_VERSION = "conv-1"
# Agreed normalisation factors (spec section 11.3).
TO_SI = {
    ("mmHg", "Pa"): 133.322387,
    ("atm", "Pa"): 101325.0,
    ("kPa", "Pa"): 1000.0,
    ("psi", "Pa"): 6894.757293,
    ("mm", "m"): 1e-3,
    ("cm", "m"): 1e-2,
    ("in", "m"): 0.0254,
    ("micron", "m"): 1e-6,
    ("nm", "m"): 1e-9,
    ("cm/s", "m_s"): 1e-2,
    ("%", "fraction"): 1e-2,
    ("mole fraction", "fraction"): 1.0,
    ("s", "s"): 1.0,
}
UNITS = {"Pa", "m_s", "m", "s", "K", "fraction", "g_fraction", "count", "dimensionless"}
STATUSES = {"measured", "reported", "derived", "not_reported", "not_applicable", "unusable"}
QUALIFIERS = {"eq", "lt", "lte", "gt", "gte", None}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MISSING = {"", "-", "–", "—", "none", "n/a", "na"}


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(text):
    """Trim and drop control characters (spec 11.2)."""
    if text is None:
        return None
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(text)).strip()


def quantity(raw, raw_unit, unit, evidence_ids, status="reported"):
    """Build a Quantity from a raw source string.

    Returns (quantity, note). `note` is None or a quality note explaining why
    the value could not be used. Nothing is ever imputed.
    """
    raw = clean(raw)
    base = {"value": None, "unit": unit, "status": "not_reported", "qualifier": None,
            "raw_value": None, "raw_unit": raw_unit, "uncertainty": None,
            "evidence_ids": list(evidence_ids), "derivation": None}
    if raw is None or raw.lower() in MISSING:
        base["raw_value"] = raw if raw else None
        return base, None
    base["raw_value"] = raw
    try:
        number = float(raw)
    except ValueError:
        base["status"] = "unusable"
        return base, f"non-numeric source value {raw!r}"
    if not math.isfinite(number):
        base["status"] = "unusable"
        return base, f"non-finite source value {raw!r}"
    base.update(value=number * TO_SI[(raw_unit, unit)], status=status, qualifier="eq")
    return base, None


def absent(unit, evidence_ids, status="not_reported"):
    """Quantity for a field the source does not contain or that does not apply."""
    return {"value": None, "unit": unit, "status": status, "qualifier": None,
            "raw_value": None, "raw_unit": None, "uncertainty": None,
            "evidence_ids": list(evidence_ids), "derivation": None}


def check_quantity(q, where, errors):
    if set(q) != {"value", "unit", "status", "qualifier", "raw_value", "raw_unit",
                  "uncertainty", "evidence_ids", "derivation"}:
        errors.append(f"{where}: wrong Quantity keys")
        return
    if q["unit"] not in UNITS:
        errors.append(f"{where}: unknown unit {q['unit']}")
    if q["status"] not in STATUSES or q["qualifier"] not in QUALIFIERS:
        errors.append(f"{where}: bad status/qualifier")
    known = q["status"] in {"measured", "reported", "derived"}
    if known != (q["value"] is not None):
        errors.append(f"{where}: value/status mismatch")
    if known and not q["evidence_ids"]:
        errors.append(f"{where}: known value without evidence")
    if q["value"] is not None:
        if not math.isfinite(q["value"]):
            errors.append(f"{where}: non-finite value")
        elif q["unit"] in {"m", "s", "Pa", "m_s"} and q["value"] < 0:
            errors.append(f"{where}: negative value")
        elif q["unit"] == "fraction" and not 0 <= q["value"] <= 1:
            errors.append(f"{where}: fraction outside 0-1")


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n")


def utc_z(ts):
    """ISO time -> UTC with Z suffix, as the backend contract requires."""
    from datetime import datetime, timezone
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
