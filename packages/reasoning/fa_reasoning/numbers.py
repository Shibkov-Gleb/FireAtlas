"""A2-06. Числа в тексте и их проверка по данным с разрешенными преобразованиями единиц.

Каждое число в тексте ответа должно совпасть с известной величиной (факт, вывод, строка источника,
условие сценария) после перевода в ту же единицу и округления до точности, с которой число записано.
Пример: факт 0.34 (доля) подтверждает «34 %» и «0,34»; давление 71874 Па подтверждает «71,9 кПа» и «0,71 атм».
Поиск цифр без единиц и без пересчета недостаточен (ТЗ A2-06), поэтому единица рядом с числом учитывается.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Семейство единиц -> (величина, перевод в СИ, перевод из СИ)
_FAMILIES: dict[str, tuple[str, callable, callable]] = {
    "frac": ("fraction", lambda v: v, lambda v: v),
    "pct": ("fraction", lambda v: v / 100, lambda v: v * 100),
    "pa": ("pressure", lambda v: v, lambda v: v),
    "kpa": ("pressure", lambda v: v * 1e3, lambda v: v / 1e3),
    "atm": ("pressure", lambda v: v * 101325, lambda v: v / 101325),
    "mmhg": ("pressure", lambda v: v * 133.322368, lambda v: v / 133.322368),
    "psi": ("pressure", lambda v: v * 6894.757, lambda v: v / 6894.757),
    "m": ("length", lambda v: v, lambda v: v),
    "cm": ("length", lambda v: v / 1e2, lambda v: v * 1e2),
    "mm": ("length", lambda v: v / 1e3, lambda v: v * 1e3),
    "um": ("length", lambda v: v / 1e6, lambda v: v * 1e6),
    "nm": ("length", lambda v: v / 1e9, lambda v: v * 1e9),
    "inch": ("length", lambda v: v * 0.0254, lambda v: v / 0.0254),
    "ms": ("speed", lambda v: v, lambda v: v),
    "cms": ("speed", lambda v: v / 1e2, lambda v: v * 1e2),
    "mms": ("speed", lambda v: v / 1e3, lambda v: v * 1e3),
    "s": ("time", lambda v: v, lambda v: v),
    "K": ("temperature", lambda v: v, lambda v: v),
    "C": ("temperature", lambda v: v + 273.15, lambda v: v - 273.15),
}
_DIM_FAMILIES: dict[str, list[str]] = {}
for _f, (_dim, _, _) in _FAMILIES.items():
    _DIM_FAMILIES.setdefault(_dim, []).append(_f)

# Канонические единицы контракта (Quantity.unit) -> семейство
CANONICAL = {"fraction": "frac", "Pa": "pa", "m": "m", "m_s": "ms", "s": "s", "K": "K"}

# Подписи единиц в тексте (русские и английские). Длинные варианты раньше коротких.
_UNIT_PATTERNS = [
    (r"мм\s*рт\.?\s*ст\.?", "mmhg"), (r"mm\s*Hg|mmHg", "mmhg"),
    (r"см/с|см/сек|cm/s|cm\s*s-1", "cms"), (r"мм/с|mm/s", "mms"), (r"м/с|m/s", "ms"),
    (r"кПа|kPa", "kpa"), (r"Па|Pa", "pa"), (r"атм|atm", "atm"), (r"psi", "psi"),
    (r"мкм|µm|μm|microns?|микрон\w*", "um"), (r"нм|nm", "nm"), (r"мм|mm", "mm"), (r"см|cm", "cm"),
    (r"inch(?:es)?|дюйм\w*|\"|″", "inch"),
    (r"mole\s+fraction|мольн\w*\s+дол\w*", "frac"),
    (r"%|процент\w*|percent", "pct"),
    (r"°\s*[CС]", "C"), (r"[KК]", "K"),
    (r"секунд\w*|сек|seconds?|с|s", "s"),
    (r"м|m", "m"),
]
_UNIT_RE = re.compile(
    r"\s*(?:" + "|".join(f"(?P<u{i}>{p})" for i, (p, _) in enumerate(_UNIT_PATTERNS)) + r")(?![A-Za-zА-Яа-яЁё0-9/])")
_UNIT_NAMES = [name for _, name in _UNIT_PATTERNS]
_AMBIGUOUS_UNITS = {"с", "s", "м", "m", "K", "К"}

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_THOUSANDS_RE = re.compile(r"(?<=\d)[   ](?=\d{3}(?!\d))")
_LETTER = re.compile(r"[A-Za-zА-Яа-яЁё]")

# Сырые единицы источников (raw_unit) -> семейство
_RAW_UNIT_RE = [(re.compile(r"^\s*(?:" + p + r")\s*$", re.I), name) for p, name in _UNIT_PATTERNS]


@dataclass(frozen=True)
class Num:
    value: float
    decimals: int
    family: str | None
    raw: str


def unit_family(raw_unit: str | None) -> str | None:
    if not raw_unit:
        return None
    for rx, name in _RAW_UNIT_RE:
        if rx.match(raw_unit):
            return name
    return None


def extract(text: str) -> list[Num]:
    """Числа текста с единицей рядом (если она есть). Части обозначений (CO2, PSI-25, 30CAL03, M1/M0) пропускаются."""
    text = _THOUSANDS_RE.sub("", text or "")
    out: list[Num] = []
    for m in _NUM_RE.finditer(text):
        s, e = m.span()
        before = text[s - 1] if s > 0 else ""
        before2 = text[s - 2] if s > 1 else ""
        after = text[e] if e < len(text) else ""
        if before and (_LETTER.match(before) or before in "_"):
            continue
        if before == "-" and before2 and _LETTER.match(before2):
            continue  # PSI-25, FLEX-2
        if after and _LETTER.match(after) and not _UNIT_RE.match(text, e):
            continue  # 30CAL03, 196F001
        raw = m.group(0)
        num = raw.replace(",", ".")
        decimals = len(num.split(".", 1)[1]) if "." in num else 0
        fam = None
        um = _UNIT_RE.match(text, e)
        if um:
            for i, name in enumerate(_UNIT_NAMES):
                if um.group(f"u{i}") is not None:
                    fam = name
                    break
            # Однобуквенные «с», «м», «К» - чаще предлоги или начало слова («0,14 с CO2»): единица, только если дальше
            # не идет слово или число
            if um.group(0).strip() in _AMBIGUOUS_UNITS:
                rest = text[um.end():].lstrip()
                if rest and (_LETTER.match(rest[0]) or rest[0].isdigit()):
                    fam = None
        out.append(Num(float(num), decimals, fam, raw))
    return out


@dataclass
class NumberPool:
    """Известные величины, которыми можно подтвердить числа текста."""
    si: list[tuple[str, float]] = field(default_factory=list)   # (величина, значение в СИ)
    plain: list[float] = field(default_factory=list)            # безразмерные числа (счетчики, номера, годы)

    def add_value(self, value: float | None, family: str | None) -> None:
        if value is None:
            return
        value = float(value)
        if family in _FAMILIES:
            dim, to_si, _ = _FAMILIES[family]
            self.si.append((dim, to_si(value)))
        self.plain.append(value)

    def add_quantity(self, q: dict | None) -> None:
        if not q:
            return
        if q.get("value") is not None:
            self.add_value(q["value"], CANONICAL.get(q.get("unit")))
        if q.get("raw_value"):
            fam = unit_family(q.get("raw_unit"))
            for n in extract(str(q["raw_value"])):
                self.add_value(n.value, fam or n.family)

    def add_text(self, text: str | None) -> None:
        for n in extract(text or ""):
            self.add_value(n.value, n.family)

    def extend(self, other: "NumberPool") -> None:
        self.si += other.si
        self.plain += other.plain

    def supports(self, n: Num) -> bool:
        tol = 0.5 * 10 ** (-n.decimals)

        def close(c: float) -> bool:
            return abs(n.value - abs(c)) <= tol + 1e-9 * max(1.0, abs(c))

        if n.family:
            dim, _, from_si = _FAMILIES[n.family]
            return any(d == dim and close(from_si(v)) for d, v in self.si)
        if any(close(v) for v in self.plain):
            return True
        # число без единицы: допускаются переводы величины в любую единицу той же размерности
        return any(close(_FAMILIES[f][2](v)) for d, v in self.si for f in _DIM_FAMILIES[d])


def unsupported(text: str, pool: NumberPool) -> list[str]:
    """Числа текста, которые не подтверждаются известными величинами."""
    return [n.raw + (f" ({n.family})" if n.family else "") for n in extract(text) if not pool.supports(n)]
