"""Офлайн-режим без генеративной модели (FA_LLM_PROVIDER=offline).

Ответ собирается только из проверенных выводов пакета (reviewed Claim) и их доказательств. Текст выводов
приводится как в корпусе, без пересказа, и ответ явно помечен как собранный без модели. Режим нужен для
отладки полного маршрута без ключа и как запасной вариант демонстрации; он не выдает себя за ответ модели.
"""
from __future__ import annotations

from .context import Context

OFFLINE_NOTE = ("Ответ собран из проверенных выводов корпуса без генеративной модели; формулировки выводов "
                "приводятся по источникам.")


def compose(ctx: Context, limits: dict) -> dict:
    blocks = []
    used_claims = []
    for c in ctx.claims:
        if c["kind"] not in ("observation", "synthesis"):
            continue  # гипотезы не выдаются за результат
        ev = [e for e in c.get("supporting_evidence_ids", []) if e in ctx.items]
        if not ev:
            continue
        blocks.append({"kind": c["kind"], "text": c["text"][:1500], "evidence_ids": ev[:5], "fact_ids": []})
        used_claims.append(c)
        if len(blocks) >= min(5, limits["max_blocks"] - 2):
            break
    if not blocks:
        return {"status": "insufficient_evidence", "blocks": [
            {"kind": "limitation", "text": "В пакете нет проверенных выводов, которые отвечают на вопрос.",
             "evidence_ids": [], "fact_ids": []}],
            "limitations": [OFFLINE_NOTE], "follow_up_questions": []}
    summary_ev = []
    for b in blocks:
        for e in b["evidence_ids"][:1]:
            if e not in summary_ev:
                summary_ev.append(e)
    blocks.insert(0, {"kind": "summary", "evidence_ids": summary_ev, "fact_ids": [],
                      "text": "По вопросу найдены проверенные выводы исследований. Они приведены ниже вместе с "
                              "доказательствами; применимость ограничена условиями опытов."})
    limitations = [OFFLINE_NOTE]
    for c in used_claims:
        for lim in c.get("limitations", []):
            if lim not in limitations:
                limitations.append(lim)
    return {"status": "answered", "blocks": blocks, "limitations": limitations[:10], "follow_up_questions": []}
