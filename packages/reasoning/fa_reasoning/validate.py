"""Проверки ответа AI 2: ссылки (A2-05), числа (A2-06), научный смысл (A2-07).

Каждая проверка возвращает список отклонений {rule, block_id, reason}. Отклоненный блок не публикуется,
причина сохраняется в audit.rejections. Самооценка модели не используется.
"""
from __future__ import annotations

import re

from . import numbers
from .context import Context, norm_acronym

SUBSTANTIVE = ("summary", "observation", "synthesis")

HTML_RE = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>")
URL_RE = re.compile(r"(https?://|www\.|\bdoi\s*:|\b10\.\d{4,9}/)", re.I)
RAW_ID_RE = re.compile(r"\b(ev|src|inv|run|clm|mat|ans|job)_[A-Za-z0-9_-]+")

# Обозначения исследований NASA: упоминание требует доказательства этого исследования в блоке
ACRONYM_RE = re.compile(r"(?<![\w-])(BASS-II|BASS|FLEX-2|FLEX|SAME-R|SAME|Saffire(?:-I{1,3})?|ACME|CFI-G|CFI|SPICE|SLICE|"
                        r"DAFT-2|DAFT|E-FIELD|BRE|LUCI|FM2|MDCA|SoFIE)(?![\w-])")

_NEG = r"(не\s+означа|не\s+явля|не\s+оценива|не\s+дела|не\s+гарантир|нельзя|не\s+позволя|не\s+следует\s+(считать|делать)|не\s+подтвержда|не\s+да[её]т|без\s+обоснования|не\s+заменя|не\s+равн)"
NEGATION_RE = re.compile(_NEG, re.I)
LIMIT_WORDS_RE = re.compile(r"(\bнет\b|\bне\s|отсутств|не\s+представлен|перенос|требует\s+обоснования|оговорк|огранич|не\s+изуча|не\s+испыт)", re.I)

# A2-07: запрещенные подмены
EXTINCTION_RE = re.compile(r"(погас|погаш|затух|extinction|extinguish)", re.I)
EXT_NEG_RE = re.compile(r"(\bне\b|\bни\b|\bнет\b|\bбез\b|\b(none|not|no|never|without)\b)", re.I)
DISRUPTION_RE = re.compile(r"(разруш|разрыв|распад|disruption|дробл)", re.I)
PARTIAL_RE = re.compile(r"(на\s+Луне|лунн\w*\s+(гравитац|услови|сил\w*\s+тяжест)|на\s+Марсе|марсианск\w*\s+(гравитац|услови)|"
                        r"частичн\w*\s+(гравитац|невесомост)|partial\s+gravity|lunar\s+gravity)", re.I)
BRIGHT_RE = re.compile(r"(ярк|ярч|свечени|светил|тускл|светим|bright|luminos|dim\b|dimmer)", re.I)
TEMP_RE = re.compile(r"(температур|горяч\w*|нагрет\w*\s+сильнее|temperature)", re.I)
# Утверждение «безопасно»: допустимо, только если перед ним в предложении стоит отрицание
# («не устанавливают безопасность») или речь об оценке безопасности как таковой.
SAFE_RE = re.compile(r"(безопас(?:н|ен)|\bsafe\b|(риск|опасност)\w*\s+(пожара\s+)?(отсутств|нет\b|низк|минимал|исключ)|"
                     r"исключ\w*\s+(пожар|возгоран))", re.I)
SAFETY_TOPIC_RE = re.compile(r"(оценк\w*|суждени\w*|вывод\w*|данн\w*)\s+(о\s+|об\s+|для\s+)?(безопасност|риск)", re.I)
# Утверждение «не горит»: в нем уже есть «не», поэтому допустимо только с отрицанием утверждения («не доказывают, что не горит»)
NONFLAM_RE = re.compile(r"(не\s+(за)?гор(ит|ят|ится|ятся|ел|ела|ели)\b|не\s+воспламен|негорюч(ий|ая|ее|ие|его|ей|им|ими)\b|"
                        r"non-?flammable|does\s+not\s+burn)", re.I)
META_NEG_RE = re.compile(r"(не\s+(доказыва|означа|устанавлива|подтвержда|показыва|следует|позволя|гарантир)|нельзя|"
                         r"не\s+дают\s+основани|\bnot\s+(prove|show|mean))", re.I)
NEG_BEFORE_RE = re.compile(r"(\bне\b|\bнет\b|\bнельзя\b|\bни\b|\bбез\b|\bnot\b|\bno\b)", re.I)
PROBABILITY_RE = re.compile(r"(вероятност\w*|шанс\w*|риск\w*)[^.!?]{0,60}(\d|процент|%)|(\d+[.,]?\d*\s*%)[^.!?]{0,30}(вероятност|риск|шанс)", re.I)
INSTRUCTION_RE = re.compile(r"(экипаж\w*\s+(долж|следует|необходимо|нужно|надо)|пошагов|немедленно|наденьте|покиньте|"
                            r"отключите|эвакуир|используйте\s+огнетушител|возьмите|откройте|закройте\s+люк|"
                            r"(шаг|step)\s*\d)", re.I)
META_RE = re.compile(r"(игнорир\w*\s+(все\s+)?(правил|ограничен|инструкц)|system\s+prompt|системн\w+\s+(промпт|инструкц)|"
                     r"как\s+языков\w+\s+модель|as\s+an\s+ai)", re.I)
SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?")


def _rej(rule: str, block_id: str | None, reason: str) -> dict:
    return {"rule": rule, "block_id": block_id, "reason": reason[:500]}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_RE.findall(text) if s.strip()]


def _affirmed(rx: re.Pattern, s: str, neg: re.Pattern = NEG_BEFORE_RE) -> re.Match | None:
    """Совпадение rx в предложении, перед которым нет отрицания («а не как вероятность», «не задают действия экипажа»)."""
    for m in rx.finditer(s):
        if not neg.search(s[: m.start()]):
            return m
    return None


def _quote(s: str) -> str:
    return f" Текст: «{s[:160]}»."


# -----------------------------------------------------------------------------
# Общие проверки текста (для блоков, ограничений и уточняющих вопросов)
# -----------------------------------------------------------------------------
def check_text(text: str, where: str | None, *, is_limitation: bool = False, outcomes: set[str] | frozenset = frozenset()) -> list[dict]:
    out = []
    if HTML_RE.search(text):
        out.append(_rej("format.html", where, "В тексте HTML-разметка."))
    if URL_RE.search(text):
        out.append(_rej("references.url", where, "В тексте URL или DOI: ссылки строит только бэкенд."))
    if RAW_ID_RE.search(text):
        out.append(_rej("format.raw_id", where, "В тексте внутренний ID сущности."))
    if META_RE.search(text):
        out.append(_rej("scope.injected_instruction", where, "Текст следует инструкции или обсуждает служебные указания."))
    sentences = _sentences(text)
    hit = next((s for s in sentences if _affirmed(PROBABILITY_RE, s)), None)
    if hit:
        out.append(_rej("scope.probability", where, "Оценка вероятности или риска пожара не выдается." + _quote(hit)))
    hit = next((s for s in sentences if _affirmed(INSTRUCTION_RE, s)), None)
    if hit:
        out.append(_rej("scope.operational_instruction", where, "Инструкции экипажу или эксплуатации не выдаются." + _quote(hit)))
    for s in sentences:
        safe = _affirmed(SAFE_RE, s) and not SAFETY_TOPIC_RE.search(s) and not NEGATION_RE.search(s)
        nonflam = _affirmed(NONFLAM_RE, s, re.compile(f"{META_NEG_RE.pattern}|{NEG_BEFORE_RE.pattern}", re.I)) \
            and "no_ignition" not in outcomes
        if safe or nonflam:
            out.append(_rej("science.absence_as_safety", where, "Утверждение о безопасности или негорючести." + _quote(s)))
            break
    return out


# -----------------------------------------------------------------------------
# Проверки блока ответа
# -----------------------------------------------------------------------------
def check_block(block: dict, ctx: Context, *, answered: bool = True) -> list[dict]:
    """answered=False: черновик со статусом insufficient/conflicting; краткий ответ «данных недостаточно»
    может не иметь ссылок, если в нем нет чисел."""
    bid, kind, text = block["id"], block["kind"], block["text"]
    ev_ids = block["evidence_ids"]
    out: list[dict] = []
    outcomes = ctx.outcomes(ev_ids)
    out += check_text(text, bid, is_limitation=kind == "limitation", outcomes=outcomes)

    # A2-05 ссылки
    foreign = [e for e in ev_ids if e not in ctx.items]
    if foreign:
        out.append(_rej("references.unknown_evidence", bid, f"Ссылки вне разрешенного пакета: {', '.join(foreign[:5])}."))
    known = [e for e in ev_ids if e in ctx.items]
    # Краткий ответ «данных недостаточно» может быть без ссылок, если его числа - только из вопроса и сценария
    no_data_summary = kind == "summary" and not answered and not numbers.unsupported(text, ctx.context_numbers)
    if kind in SUBSTANTIVE and not known and not no_data_summary:
        out.append(_rej("references.missing", bid, "Содержательный блок без доказательств."))
    if kind == "synthesis" and len(set(known)) < 2 and not any(
            c["kind"] == "synthesis" for e in known for c in ctx.claims_by_ev.get(e, [])):
        out.append(_rej("references.synthesis_basis", bid, "Обобщение требует минимум двух доказательств или проверенного обобщения."))
    if kind in SUBSTANTIVE and known:
        for m in ACRONYM_RE.finditer(text):
            acr = norm_acronym(m.group(1))
            if not any(acr in ctx.haystack.get(e, "") for e in known):
                in_bundle = any(acr in h for h in ctx.haystack.values())
                out.append(_rej("references.acronym_without_evidence", bid,
                                f"Упомянуто {m.group(1)}, но среди доказательств блока его нет"
                                + ("" if in_bundle else " (и в пакете тоже)") + "."))
                break
    for q in block.get("quantities", []):
        if not set(q["evidence_ids"]) <= set(ctx.items):
            out.append(_rej("references.quantity_evidence", bid, f"Величина {q['name']} ссылается на доказательство вне пакета."))

    # A2-06 числа
    pool = ctx.numbers_for(known) if kind != "limitation" else ctx.global_numbers
    for q in block.get("quantities", []):
        pool.add_quantity(q["quantity"])
    bad = numbers.unsupported(text, pool)
    if bad:
        out.append(_rej("quantities.unsupported_number", bid,
                        f"Числа не подтверждаются доказательствами блока: {', '.join(bad[:5])}."))

    # A2-07 научный смысл
    if kind in SUBSTANTIVE and outcomes and not outcomes & {"extinction", "unknown"}:
        # Исходы опытов блока - без погасания: утвердительное «погасло» здесь подмена (Disruption/догорание != Extinction)
        for s in _sentences(text):
            if EXTINCTION_RE.search(s) and not EXT_NEG_RE.search(s) and not NEGATION_RE.search(s):
                out.append(_rej("science.disruption_as_extinction", bid,
                                f"Погасание при исходах опытов {', '.join(sorted(outcomes))}: «{s[:160]}»."))
                break
    if kind in SUBSTANTIVE:
        partial_data = any(f.field == "conditions.gravity_regime" and f.text_value in ("partial", "simulated_partial")
                           for e in known for f in ctx.facts_by_ev.get(e, []))
        if not partial_data:
            for s in _sentences(text):
                if PARTIAL_RE.search(s) and not LIMIT_WORDS_RE.search(s):
                    out.append(_rej("science.microgravity_as_partial", bid,
                                    f"Результат представлен как наблюдение в частичной гравитации: «{s[:160]}»."))
                    break
        for s in _sentences(text):
            if BRIGHT_RE.search(s) and TEMP_RE.search(s) and not NEGATION_RE.search(s):
                if not any(f.field.endswith("temperature") for e in known for f in ctx.facts_by_ev.get(e, [])):
                    out.append(_rej("science.brightness_as_temperature", bid,
                                    "Яркость пламени использована как показатель температуры без измерения температуры."))
                    break
        if kind in ("observation", "summary") and known:
            supporting = [c for e in known for c in ctx.claims_by_ev.get(e, [])]
            if supporting and all(c["kind"] == "hypothesis" for c in supporting) and not re.search(r"гипотез|предпола[гж]|возможно|hypothes", text, re.I):
                out.append(_rej("science.hypothesis_as_result", bid, "Гипотеза исследования представлена как результат."))
    return out


def check_follow_up(text: str, idx: int) -> list[dict]:
    return check_text(text, f"follow_up_{idx}")


def check_limitation(text: str, idx: int, ctx: Context) -> list[dict]:
    out = check_text(text, f"limitation_{idx}", is_limitation=True)
    bad = numbers.unsupported(text, ctx.global_numbers)
    if bad:
        out.append(_rej("quantities.unsupported_number", f"limitation_{idx}", f"Числа не подтверждаются: {', '.join(bad[:5])}."))
    return out
