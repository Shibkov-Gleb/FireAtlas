"""Индекс пакета доказательств (CT-14) для промпта и проверок.

Факты пакета получают короткие ID (F1, F2, ...): модель ссылается на них, а величины в ответ
подставляет код, поэтому модель не может изменить число, единицу или статус величины.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .numbers import NumberPool

PARTIAL = frozenset({"partial", "simulated_partial"})


def norm_acronym(s: str) -> str:
    """BASS-II -> bass2, SAME-R -> samer, inv_psi25_bass2 -> invpsi25bass2."""
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    return re.sub(r"ii\b", "2", s) if s.endswith("ii") else s


@dataclass
class Fact:
    fid: str
    field: str
    quantity: dict | None
    text_value: str | None
    evidence_ids: list[str]


@dataclass
class Context:
    bundle: dict
    question: str
    scenario: dict | None
    allowed_ev: list[str]
    allowed_src: set[str]
    items: dict[str, dict]                     # evidence_id -> item
    facts: dict[str, Fact]                     # F1 -> Fact
    facts_by_ev: dict[str, list[Fact]]
    claims: list[dict]
    claims_by_ev: dict[str, list[dict]]
    haystack: dict[str, str]                   # evidence_id -> нормализованный текст для поиска обозначений
    global_numbers: NumberPool = field(default_factory=NumberPool)

    @property
    def coverage(self) -> dict:
        return self.bundle["coverage"]

    @property
    def partial_gravity_uncovered(self) -> bool:
        sc = self.scenario
        return bool(sc) and sc.get("gravity_regime") in PARTIAL and not self.coverage.get("target_gravity_covered", False)

    def outcomes(self, evidence_ids) -> set[str]:
        return {f.text_value for e in evidence_ids for f in self.facts_by_ev.get(e, [])
                if f.field == "terminal_outcome.category" and f.text_value}

    def numbers_for(self, evidence_ids) -> NumberPool:
        """Величины, которыми можно подтвердить числа блока с этими доказательствами."""
        pool = NumberPool()
        pool.extend(self.context_numbers)
        for e in evidence_ids:
            item = self.items.get(e)
            if not item:
                continue
            ev = item["evidence"]
            pool.add_text(ev.get("excerpt"))
            for tv in ev.get("table_values") or []:
                pool.add_quantity({"value": None, "raw_value": tv.get("raw_value"), "raw_unit": tv.get("raw_unit")})
            loc = ev.get("locator") or {}
            pool.add_value(loc.get("page"), None)
            pool.add_text(loc.get("row_key"))
            for f in self.facts_by_ev.get(e, []):
                pool.add_quantity(f.quantity)
                pool.add_text(f.text_value)
            for c in self.claims_by_ev.get(e, []):
                pool.add_text(c["text"])
                for lim in c.get("limitations", []):
                    pool.add_text(lim)
        return pool

    @property
    def context_numbers(self) -> NumberPool:
        """Числа вопроса и сценария: пользователь может назвать свои условия."""
        pool = NumberPool()
        pool.add_text(self.question)
        sc = self.scenario or {}
        for k in ("oxygen_fraction", "pressure", "airflow_speed"):
            pool.add_quantity(sc.get(k))
        return pool


def build(bundle: dict) -> Context:
    items = {i["evidence"]["id"]: i for i in bundle["items"]}
    facts: dict[str, Fact] = {}
    facts_by_ev: dict[str, list[Fact]] = {}
    n = 0
    for ev_id, item in items.items():
        for f in item.get("normalized_facts", []):
            if f.get("field") == "claim.text":
                continue  # текст вывода передается в разделе выводов
            n += 1
            fact = Fact(f"F{n}", f["field"], f.get("quantity"), f.get("text_value"), list(f["evidence_ids"]))
            facts[fact.fid] = fact
            for e in fact.evidence_ids:
                facts_by_ev.setdefault(e, []).append(fact)
    allowed = list(bundle["allowed_evidence_ids"])
    claims = [c for c in bundle.get("selected_claims", []) if c.get("review_status", "reviewed") == "reviewed"]
    claims_by_ev: dict[str, list[dict]] = {}
    for c in claims:
        for e in c.get("supporting_evidence_ids", []):
            claims_by_ev.setdefault(e, []).append(c)
    haystack = {}
    for ev_id, item in items.items():
        parts = [item["source_metadata"].get("title", ""), *item.get("investigation_ids", []),
                 item["evidence"].get("excerpt") or "", (item["evidence"].get("locator") or {}).get("row_key") or ""]
        parts += [c["text"] for c in claims_by_ev.get(ev_id, [])]
        haystack[ev_id] = " ".join(norm_acronym(w) for w in re.split(r"[\s(),;:]+", " ".join(parts)) if w)
    ctx = Context(bundle=bundle, question=bundle.get("question", ""), scenario=bundle.get("scenario"),
                  allowed_ev=allowed, allowed_src=set(bundle.get("allowed_source_ids", [])), items=items, facts=facts,
                  facts_by_ev=facts_by_ev, claims=claims, claims_by_ev=claims_by_ev, haystack=haystack)
    ctx.global_numbers = ctx.numbers_for(allowed)
    return ctx
