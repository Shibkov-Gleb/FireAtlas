"""CT-15. reason(ReasoningRequest) -> ReasoningResponse: ответ с доказательствами (A2-03, A2-05…A2-08).

Подключение к бэкенду (D-025):  FA_REASONER=py:fa_reasoning.reason:reason

Цепочка: пакет -> промпт -> модель (JSON по схеме) -> разбор -> проверки каждого блока -> при отклонениях
один исправляющий проход, если позволяет дедлайн -> отбрасывание непроверенных блоков -> обязательные
ограничения -> сборка ответа -> проверка по контракту. Агентов и цепочек вызовов нет.

Ошибки (A2-08):
  * пакет пуст / прямых данных нет  -> ответ insufficient_evidence (это не ошибка);
  * провайдер недоступен, нет ключа -> ProviderError (MODEL_PROVIDER_ERROR), текст ответа не выдумывается;
  * не успели до дедлайна           -> ReasoningTimeout (REASONING_TIMEOUT);
  * модель дважды вернула не тот формат -> ContractViolation (VALIDATION_FAILED).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Callable

from . import context as context_mod
from . import validate
from .config import LLMConfig, from_env
from .context import Context
from .errors import ContractViolation, ModelOutputError, ProviderError, ReasoningTimeout
from .llm import ChatModel
from .offline import compose as offline_compose
from .prompt import FIELD_LABELS, MODEL_SCHEMA, PROMPT_REVISION, build_messages, repair_message

log = logging.getLogger("fire_atlas.reasoning")

REASONING_REVISION = f"ai2-r1.0+{PROMPT_REVISION}"
SAFETY_MARGIN_S = 3.0      # время бэкенду на проверку и публикацию после ответа модели
MIN_MODEL_TIME_S = 2.0
MAX_CITATIONS = 20
MAX_EV_PER_BLOCK = 6
STATUSES = ("answered", "insufficient_evidence", "conflicting_evidence")
KINDS = ("summary", "observation", "synthesis", "limitation")

# Model: (messages, json_schema, timeout_s) -> (разобранный JSON, {"model", "model_version", ...})
Model = Callable[[list[dict], dict, float], tuple[dict, dict]]

LIM_PARTIAL = ("Прямых данных частичной гравитации в корпусе нет: результаты микрогравитации переносятся на Луну "
               "или Марс только с обоснованием.")
LIM_NO_SAFETY = "Отсутствие данных не означает безопасность."
LIM_DISRUPTION = "Disruption (разрушение капли) и догорание - не погасание пламени."
LIM_REJECTED = "Часть утверждений не подтвердилась доказательствами при проверке и не показана."
LIM_NOT_ADVICE = "Ответ объясняет результаты исследований и не является оценкой безопасности или инструкцией."
BLOCK_INSUFFICIENT = "Прямых доказательств для ответа на этот вопрос в корпусе недостаточно."

FOLLOW_UPS = [
    ("material", "Какой материал и какая форма образца рассматриваются?"),
    ("oxygen", "Какие доля кислорода и давление атмосферы рассматриваются?"),
    ("pressure", "Какие доля кислорода и давление атмосферы рассматриваются?"),
    ("airflow", "Какая скорость потока воздуха рассматривается?"),
]
FOLLOW_UP_PARTIAL = "Показать связанные результаты микрогравитации с явной оговоркой о переносе на частичную гравитацию?"
FOLLOW_UP_DEFAULT = "Уточните задачу (предотвращение, обнаружение или подавление), материал и условия атмосферы."


# -----------------------------------------------------------------------------
# Публичная функция
# -----------------------------------------------------------------------------
def reason(req: dict, *, model: Model | None = None, config: LLMConfig | None = None,
           now: Callable[[], datetime] | None = None) -> dict:
    clock = now or (lambda: datetime.now(timezone.utc))
    bundle = req["evidence_bundle"]
    limits = req["output_limits"]
    deadline = _parse_ts(req["deadline_at"])
    ctx = context_mod.build(bundle)
    t0 = time.perf_counter()

    if not bundle["items"]:
        draft = {"status": "insufficient_evidence", "blocks": [], "limitations": [], "follow_up_questions": []}
        return _finish(ctx, limits, draft, [], meta=None, t0=t0)

    if model is None:
        model = _default_model(ctx, limits, config or from_env())

    messages = build_messages(ctx, limits)
    started = time.perf_counter()
    try:
        draft, meta = _ask(model, messages, deadline, clock)
        blocks, rejections = _check_draft(draft, ctx)
        problems = None
    except ModelOutputError as e:
        draft, meta, blocks, rejections, problems = None, None, [], [], [f"Неверный формат ответа: {e}"]

    first_call_s = time.perf_counter() - started
    need_repair = problems is not None or any(r["block_id"] is None or r["block_id"].startswith("blk_") for r in rejections)
    if (meta or {}).get("model") == "offline-claims":
        need_repair = False  # офлайн-режим детерминирован: повтор даст тот же результат
    if need_repair and _remaining(deadline, clock) > first_call_s + SAFETY_MARGIN_S:
        fix = problems or [f"{r['rule']}: {r['reason']}" for r in rejections]
        try:
            draft2, meta2 = _ask(model, messages + [{"role": "assistant", "content": json.dumps(draft or {}, ensure_ascii=False)},
                                                   repair_message(fix)], deadline, clock)
            blocks2, rejections2 = _check_draft(draft2, ctx)
            if draft is None or _score(blocks2, rejections2) >= _score(blocks, rejections):
                draft, meta, blocks = draft2, meta2, blocks2
                rejections = rejections + [dict(r, rule="repair:" + r["rule"]) for r in rejections2]
        except ModelOutputError as e:
            if draft is None:
                raise ContractViolation(f"модель дважды вернула неверный формат: {e}") from e
    elif draft is None:
        raise ContractViolation(f"модель вернула неверный формат: {problems[0]}")

    draft = dict(draft, blocks=blocks)
    return _finish(ctx, limits, draft, rejections, meta=meta, t0=t0, checked=True)


def _default_model(ctx: Context, limits: dict, cfg: LLMConfig) -> Model:
    if cfg.provider == "offline":
        def offline(_messages, _schema, _timeout):
            return offline_compose(ctx, limits), {"model": "offline-claims", "model_version": REASONING_REVISION}
        return offline
    if cfg.provider == "none":
        raise ProviderError("модель не настроена: задайте OPENAI_API_KEY или FA_LLM_PROVIDER")
    return ChatModel(cfg)


# -----------------------------------------------------------------------------
# Вызов модели и разбор
# -----------------------------------------------------------------------------
def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _remaining(deadline: datetime, clock) -> float:
    return (deadline - clock()).total_seconds()


def _ask(model: Model, messages: list[dict], deadline: datetime, clock) -> tuple[dict, dict]:
    left = _remaining(deadline, clock) - SAFETY_MARGIN_S
    if left < MIN_MODEL_TIME_S:
        raise ReasoningTimeout("до дедлайна не осталось времени на вызов модели")
    raw, meta = model(messages, MODEL_SCHEMA, left)
    if _remaining(deadline, clock) <= 0:
        raise ReasoningTimeout("модель ответила после дедлайна")  # поздний ответ не публикуется
    return _parse_draft(raw), meta or {}


def _parse_draft(raw) -> dict:
    if not isinstance(raw, dict):
        raise ModelOutputError("ответ не объект")
    status = raw.get("status")
    if status not in STATUSES:
        raise ModelOutputError(f"неизвестный status {status!r}")
    blocks = raw.get("blocks")
    if not isinstance(blocks, list):
        raise ModelOutputError("нет списка blocks")
    out_blocks = []
    for b in blocks:
        if not isinstance(b, dict) or b.get("kind") not in KINDS or not isinstance(b.get("text"), str):
            raise ModelOutputError("блок неверной структуры")
        ev, facts = b.get("evidence_ids", []), b.get("fact_ids", [])
        if not isinstance(ev, list) or not all(isinstance(x, str) for x in ev):
            raise ModelOutputError("evidence_ids не список строк")
        if not isinstance(facts, list) or not all(isinstance(x, str) for x in facts):
            raise ModelOutputError("fact_ids не список строк")
        out_blocks.append({"kind": b["kind"], "text": b["text"], "evidence_ids": ev, "fact_ids": facts})
    lists = {}
    for k in ("limitations", "follow_up_questions"):
        v = raw.get(k, [])
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ModelOutputError(f"{k} не список строк")
        lists[k] = v
    return {"status": status, "blocks": out_blocks, **lists}


_MD_RE = re.compile(r"(\*\*|__|`|^#+\s*|^\s*[-*•]\s+)", re.M)


def _clean(text: str) -> str:
    text = _MD_RE.sub("", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _check_draft(draft: dict, ctx: Context) -> tuple[list[dict], list[dict]]:
    """Собирает блоки контракта из черновика модели и отбрасывает непроверенные."""
    blocks, rejections = [], []
    for n, b in enumerate(draft["blocks"], start=1):
        bid = f"blk_{n}"
        text = _clean(b["text"])[:1500]
        if not text:
            continue
        model_ev = list(dict.fromkeys(e.strip() for e in b["evidence_ids"] if e.strip()))
        fact_ev: list[str] = []
        quantities, bad_facts = [], []
        for fid in dict.fromkeys(f.strip().upper() for f in b["fact_ids"]):
            fact = ctx.facts.get(fid)
            if fact is None:
                bad_facts.append(fid)
                continue
            fact_ev += [e for e in fact.evidence_ids if e not in fact_ev]
            if fact.quantity is not None and len(quantities) < 20:
                quantities.append({"name": FIELD_LABELS.get(fact.field, fact.field)[:128], "quantity": fact.quantity,
                                   "evidence_ids": list(fact.evidence_ids)})
        # Основания величин - первыми; не больше MAX_EV_PER_BLOCK ссылок на блок, чтобы ответ уложился в 20 citations
        ev = list(dict.fromkeys(fact_ev + model_ev))[:MAX_EV_PER_BLOCK]
        quantities = [q for q in quantities if set(q["evidence_ids"]) <= set(ev)]
        block = {"id": bid, "kind": b["kind"], "text": text, "evidence_ids": ev, "quantities": quantities}
        rej = validate.check_block(block, ctx, answered=draft["status"] == "answered")
        if bad_facts:
            rej.append({"rule": "references.unknown_fact", "block_id": bid, "reason": f"Неизвестные факты: {', '.join(bad_facts[:5])}."})
        if rej:
            for r in rej:
                if "Текст:" not in r["reason"]:
                    r["reason"] = (r["reason"] + f" Текст: «{text[:160]}».")[:500]
            rejections += rej
            continue
        blocks.append(block)
    return blocks, rejections


def _score(blocks: list[dict], rejections: list[dict]) -> tuple[int, int]:
    return (sum(b["kind"] in validate.SUBSTANTIVE for b in blocks), -len(rejections))


# -----------------------------------------------------------------------------
# Сборка ответа
# -----------------------------------------------------------------------------
def _finish(ctx: Context, limits: dict, draft: dict, rejections: list[dict], *, meta: dict | None, t0: float,
            checked: bool = False) -> dict:
    blocks = list(draft["blocks"])
    status = draft["status"]
    substantive = [b for b in blocks if b["kind"] in validate.SUBSTANTIVE]

    # Статус по правилам корпуса, а не по уверенности модели
    if ctx.partial_gravity_uncovered:
        status = "insufficient_evidence"
    if status == "conflicting_evidence" and len(substantive) < 2:
        status = "answered" if substantive else "insufficient_evidence"
    if status == "answered" and not substantive:
        status = "insufficient_evidence"

    # Порядок: краткий ответ, наблюдения и обобщения, ограничения
    order = {"summary": 0, "observation": 1, "synthesis": 1, "limitation": 2}
    blocks.sort(key=lambda b: order[b["kind"]])
    if status == "insufficient_evidence" and not any(b["kind"] == "limitation" for b in blocks):
        blocks.append({"id": "blk_x", "kind": "limitation", "text": BLOCK_INSUFFICIENT, "evidence_ids": [], "quantities": []})

    blocks = _fit_limits(blocks, limits, rejections)
    blocks = _cap_evidence(blocks, rejections)
    if status == "answered" and not any(b["kind"] in validate.SUBSTANTIVE for b in blocks):
        status = "insufficient_evidence"
    for n, b in enumerate(blocks, start=1):
        b["id"] = f"blk_{n}"

    used_ev = [e for b in blocks for e in b["evidence_ids"] + [x for q in b["quantities"] for x in q["evidence_ids"]]]
    limitations = _limitations(ctx, draft.get("limitations", []), status, used_ev, rejections)
    follow_ups = _follow_ups(ctx, draft.get("follow_up_questions", []), status, limits, rejections)

    resp = {
        "status": status,
        "answer_blocks": blocks,
        "applicability": None,  # D-028: детерминированную применимость вызывает бэкенд (assess_applicability)
        "citations": _citations(ctx, used_ev),
        "limitations": limitations,
        "follow_up_questions": follow_ups,
        "reasoning_revision": REASONING_REVISION,
        "validation_summary": {"schema_valid": True, "references_valid": True, "quantities_valid": True, "scope_valid": True},
        "audit": {"checked_evidence_ids": list(ctx.allowed_ev), "rejections": rejections[:50],
                  "model": (meta or {}).get("model"), "model_version": (meta or {}).get("model_version")},
    }
    _self_check(resp, ctx)
    log.info(json.dumps({"event": "reasoning_done", "status": status, "blocks": len(blocks), "rejections": len(rejections),
                         "model": resp["audit"]["model"], "ms": round((time.perf_counter() - t0) * 1000),
                         "usage": (meta or {}).get("usage")}, ensure_ascii=False))
    return resp


def _fit_limits(blocks: list[dict], limits: dict, rejections: list[dict]) -> list[dict]:
    lim = [b for b in blocks if b["kind"] == "limitation"][:2]
    rest = [b for b in blocks if b["kind"] != "limitation"]
    rest = rest[: max(0, limits["max_blocks"] - len(lim))]
    out = rest + lim
    while sum(len(b["text"]) for b in out) > limits["max_total_chars"] and len(out) > 1:
        drop = next((b for b in reversed(out) if b["kind"] in ("observation", "synthesis")), out[-1])
        out.remove(drop)
        rejections.append({"rule": "limits.total_chars", "block_id": drop["id"], "reason": "Превышен общий объем ответа."})
    return out


def _cap_evidence(blocks: list[dict], rejections: list[dict]) -> list[dict]:
    """Не больше 20 разных доказательств на ответ: у каждого должен быть citation."""
    used: list[str] = []
    out = []
    for b in blocks:
        keep = []
        for e in b["evidence_ids"]:
            if e in used or len(used) < MAX_CITATIONS:
                keep.append(e)
                if e not in used:
                    used.append(e)
        quantities = [q for q in b["quantities"] if all(e in used for e in q["evidence_ids"])]
        if b["kind"] in validate.SUBSTANTIVE and b["evidence_ids"] and not keep:
            rejections.append({"rule": "limits.citations", "block_id": b["id"], "reason": "Превышен лимит ссылок ответа."})
            continue
        out.append(dict(b, evidence_ids=keep, quantities=quantities))
    return out


def _limitations(ctx: Context, model_lims: list[str], status: str, used_ev: list[str], rejections: list[dict]) -> list[str]:
    out: list[str] = []
    if ctx.partial_gravity_uncovered:
        out.append(LIM_PARTIAL)
    if status == "insufficient_evidence" or not ctx.coverage.get("direct_evidence_available", True):
        out.append(LIM_NO_SAFETY)
    if ctx.outcomes(used_ev) & {"disruption", "burn_to_completion"}:
        out.append(LIM_DISRUPTION)
    for i, text in enumerate(model_lims):
        text = _clean(text)[:1000]
        if not text:
            continue
        rej = validate.check_limitation(text, i, ctx)
        if rej:
            rejections += rej
            continue
        out.append(text)
    if any(r["block_id"] for r in rejections):
        out.append(LIM_REJECTED)
    out.append(LIM_NOT_ADVICE)
    return list(dict.fromkeys(out))[:20]


def _follow_ups(ctx: Context, model_fu: list[str], status: str, limits: dict, rejections: list[dict]) -> list[str]:
    out: list[str] = []
    for i, text in enumerate(model_fu):
        text = _clean(text)[:500]
        if not text:
            continue
        rej = validate.check_follow_up(text, i)
        if rej:
            rejections += rej
            continue
        out.append(text)
    if status == "insufficient_evidence" and not out:
        if ctx.partial_gravity_uncovered:
            out.append(FOLLOW_UP_PARTIAL)
        missing = " ".join(ctx.coverage.get("missing_fields", [])).lower()
        sc = ctx.scenario or {}
        for key, q in FOLLOW_UPS:
            if key in missing or (key == "material" and sc and not sc.get("material_ids")):
                out.append(q)
        if not out:
            out.append(FOLLOW_UP_DEFAULT)
    return list(dict.fromkeys(out))[: limits["max_follow_ups"]]


def _citations(ctx: Context, used_ev: list[str]) -> list[dict]:
    out = []
    for e in dict.fromkeys(used_ev):
        item = ctx.items.get(e)
        if not item:
            continue
        src, loc = item["source_metadata"], item["evidence"]["locator"]
        where = loc.get("row_key") or (f"стр. {loc['page']}" if loc.get("page") else None) or loc.get("section")
        label = f"{src['title']}, {where}" if where else src["title"]
        out.append({"evidence_id": e, "source_id": item["evidence"]["source_id"], "label": label[:300], "locator": loc})
    return out[:MAX_CITATIONS]


def _self_check(resp: dict, ctx: Context) -> None:
    """Ответ не уходит в бэкенд, если не проходит контракт или ссылается за пределы пакета."""
    try:
        import fa_contracts as c  # noqa: PLC0415 - пакет контрактов есть в окружении бэкенда
    except ImportError:  # pragma: no cover
        c = None
    if c is not None:
        viol = c.errors_for("InternalReasoningResponse", resp)
        if viol:
            raise ContractViolation(f"reason: {viol[0]['field']}: {viol[0]['reason']}")
    allowed = set(ctx.allowed_ev)
    for b in resp["answer_blocks"]:
        if not set(b["evidence_ids"]) <= allowed:
            raise ContractViolation("reason: ссылка вне пакета после проверки")
