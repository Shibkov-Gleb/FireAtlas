"""A2-06: числа и единицы."""
import pytest

from fa_reasoning.numbers import NumberPool, extract, unsupported


def fams(text):
    return [(n.value, n.family) for n in extract(text)]


def test_identifiers_are_not_numbers():
    assert extract("CO2, O2, PSI-25, BASS-II, FLEX-2, опыт 30CAL03, 196F001, диаметр M1/M0") == []


def test_units_are_recognized():
    got = fams("21 % и 71,9 кПа, 0,7 атм, 539,1 мм рт. ст., 1,92 мм, 5 см/с, 4,2 с, 88 nm, 13.6 % O2")
    assert got == [(21, "pct"), (71.9, "kpa"), (0.7, "atm"), (539.1, "mmhg"), (1.92, "mm"), (5, "cms"),
                   (4.2, "s"), (88, "nm"), (13.6, "pct")]


def test_one_letter_unit_vs_preposition():
    """«с» - и секунды, и предлог: «0,14 с CO2» - это доля с CO2, а не 0,14 секунды."""
    assert fams("при 0,14 с CO2 и 0,13 с гелием") == [(0.14, None), (0.13, None)]
    assert fams("горение длилось 4,2 с.") == [(4.2, "s")]


def test_thousands_separator():
    assert fams("101 325 Па") == [(101325, "pa")]


@pytest.fixture
def pool():
    p = NumberPool()
    p.add_quantity({"value": 0.34, "unit": "fraction", "raw_value": "0.34", "raw_unit": "mole fraction"})
    p.add_quantity({"value": 71874.0988317, "unit": "Pa", "raw_value": "539.1", "raw_unit": "mmHg"})
    p.add_quantity({"value": 0.00192, "unit": "m", "raw_value": "1.92", "raw_unit": "mm"})
    p.add_text("15 droplets ended in disruption and 2 burned to completion")
    return p


@pytest.mark.parametrize("text", [
    "при 34 % кислорода", "доля кислорода 0,34", "давление 71,9 кПа", "около 0,71 атм", "539,1 мм рт. ст.",
    "71874 Па", "капля 1,92 мм", "0,192 см", "15 капель", "2 капли догорели", "34,0 %",
])
def test_supported_with_allowed_conversions(pool, text):
    assert unsupported(text, pool) == []


@pytest.mark.parametrize("text", [
    "при 35 % кислорода",       # другое значение
    "0,34 атм",                 # подмена единицы: доля выдана за давление
    "0,8 атм",
    "1,9 см",                   # 1,92 мм это 0,192 см
    "в 17 опытах",              # счетчика нет в данных
    "34,05 %",                  # точность выше исходной
])
def test_unsupported(pool, text):
    assert unsupported(text, pool)
