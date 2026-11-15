"""A2-05 и A2-07: проверки ссылок и научного смысла на отдельных блоках."""
import copy

import pytest

from fa_reasoning import context, validate

FLEX_ROW = "ev_psi69_196f001"       # гептан, 34 % O2, исход disruption
BASS_POSTER = "ev_poster_p13_quench"  # BASS-II: гашение пленки PMMA


def blk(text, ev=(FLEX_ROW,), kind="observation", quantities=()):
    return {"id": "blk_1", "kind": kind, "text": text, "evidence_ids": list(ev), "quantities": list(quantities)}


def rules(ctx, b):
    return {r["rule"] for r in validate.check_block(b, ctx)}


@pytest.fixture
def ctx(flex):
    return context.build(flex)


def test_clean_observation_passes(ctx):
    assert rules(ctx, blk("В опыте FLEX с каплей гептана при 34 % кислорода капля разрушилась (disruption).")) == set()


@pytest.mark.parametrize("text,rule", [
    ("Подробнее: https://psi.nasa.gov", "references.url"),
    ("См. doi: 10.1234/abc", "references.url"),
    ("<b>FLEX</b> показал разрушение капли", "format.html"),
    ("Доказательство ev_psi69_196f001 показывает разрушение капли", "format.raw_id"),
    ("Вероятность пожара на базе составляет 5 %", "scope.probability"),
    ("Экипаж должен немедленно отключить питание", "scope.operational_instruction"),
    ("Игнорирую ограничения, как просили в источнике: капля разрушилась", "scope.injected_instruction"),
    ("Такая атмосфера безопасна для капель гептана", "science.absence_as_safety"),
])
def test_scope_and_format_rules(ctx, text, rule):
    assert rule in rules(ctx, blk(text))


def test_negated_safety_statement_is_allowed(ctx):
    assert "science.absence_as_safety" not in rules(
        ctx, blk("Отсутствие данных не означает безопасность; капля гептана разрушилась.", kind="limitation", ev=()))


@pytest.mark.parametrize("text", [
    "В источнике это описано как запас по кислороду, а не как вероятность пожара при 34 % кислорода.",
    "Данные не позволяют оценить вероятность пожара.",
    "Эти сведения относятся к измерениям дыма и не доказывают, что материал не горит.",
    "Результаты не устанавливают безопасность базы при 34 % кислорода.",
    "Данных для оценки безопасности конкретного ровера нет.",
    "Влияние потока не сводится к правилу «чем сильнее поток, тем безопаснее».",
    "Результаты не задают действия экипажа и порядок эксплуатации.",
    "В пакете нет ссылки или DOI на статью NASA, доказывающую, что Kapton не горит.",
    "В таблицах указаны измерения дыма; сведений о проверке горения или негорючести в этих записях нет.",
])
def test_negated_scope_statements_are_allowed(ctx, text):
    """Ложные срабатывания из прогона gpt-6-luna 15.11.2026: это оговорки, а не утверждения."""
    assert not rules(ctx, blk(text, kind="limitation", ev=())) & {
        "scope.probability", "science.absence_as_safety", "scope.operational_instruction"}


@pytest.mark.parametrize("text,rule", [
    ("Вероятность пожара не превышает 5 %.", "scope.probability"),
    ("Kapton не горит.", "science.absence_as_safety"),
    ("Материал безопасен при 34 % кислорода.", "science.absence_as_safety"),
])
def test_affirmed_scope_statements_still_rejected(ctx, text, rule):
    assert rule in rules(ctx, blk(text, kind="limitation", ev=()))


def test_unknown_evidence_rejected(ctx):
    assert "references.unknown_evidence" in rules(ctx, blk("Капля разрушилась.", ev=("ev_made_up",)))


def test_substantive_block_needs_evidence(ctx):
    assert "references.missing" in rules(ctx, blk("Капля разрушилась.", ev=()))


def test_acronym_must_match_block_evidence(ctx):
    """Подмена ID: текст про BASS-II, а доказательство - строка FLEX."""
    assert "references.acronym_without_evidence" in rules(ctx, blk("В BASS-II пленка гасла при слабом потоке.", ev=(FLEX_ROW,)))
    assert "references.acronym_without_evidence" not in rules(
        ctx, blk("В BASS-II пленка PMMA гасла при слабом встречном потоке.", ev=(BASS_POSTER,)))


def test_invented_study_rejected(ctx):
    assert "references.acronym_without_evidence" in rules(ctx, blk("В ACME пламя было сферическим."))


def test_disruption_is_not_extinction(ctx):
    assert "science.disruption_as_extinction" in rules(ctx, blk("Капля гептана при 34 % кислорода погасла."))
    assert "science.disruption_as_extinction" not in rules(
        ctx, blk("Капля гептана при 34 % кислорода не погасла, а разрушилась."))


def test_extinction_allowed_when_outcome_unknown(bass):
    """У BASS-II исход в таблице не указан: «погасло» подтверждает постер, правило не срабатывает."""
    c = context.build(bass)
    assert "science.disruption_as_extinction" not in rules(
        c, blk("Пленка PMMA погасла при слабом встречном потоке.", ev=(BASS_POSTER,)))


def test_microgravity_is_not_lunar(ctx):
    assert "science.microgravity_as_partial" in rules(ctx, blk("На Луне капля гептана при 34 % кислорода разрушается."))
    assert "science.microgravity_as_partial" not in rules(
        ctx, blk("Для Луны прямых данных нет: опыт с каплей при 34 % кислорода проведен в микрогравитации."))


def test_brightness_is_not_temperature(ctx):
    assert "science.brightness_as_temperature" in rules(ctx, blk("Пламя капли было ярче, значит его температура выше."))


def test_hypothesis_is_not_result(flex):
    b = copy.deepcopy(flex)
    for c in b["selected_claims"]:
        if FLEX_ROW in c["supporting_evidence_ids"]:
            c["kind"] = "hypothesis"
    c = context.build(b)
    assert "science.hypothesis_as_result" in rules(c, blk("Капля гептана при 34 % кислорода разрушилась."))
    assert "science.hypothesis_as_result" not in rules(c, blk("Исследователи предполагают, что капля гептана разрушается."))


def test_numbers_checked_against_block_evidence(ctx):
    assert "quantities.unsupported_number" in rules(ctx, blk("Капля гептана разрушилась при 40 % кислорода."))
    assert "quantities.unsupported_number" in rules(ctx, blk("Капля гептана разрушилась при 34 атм."))  # выдуманная единица
