"""Повторная проверка выходов AI-модулей перед публикацией (CT-13..CT-15, BE-08).

Бэкенд не публикует результат, который не прошел эти проверки, независимо от
validation_summary, который вернул модуль.
"""
from __future__ import annotations

import re

import fa_contracts as c

from .db import Database
from .providers import ContractViolation, RetrievalUnavailable

HTML_RE = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>")
URL_RE = re.compile(r"(https?://|www\.)", re.I)
MAX_EXCERPT_TOTAL = 24000


def check_retrieval(result: dict, req: dict, db: Database) -> dict:
    """Возвращает проверенный bundle или бросает RetrievalUnavailable/ContractViolation."""
    viol = c.errors_for("InternalRetrievalResult", result)
    if viol:
        raise ContractViolation(f"retrieve: {viol[0]['field']}: {viol[0]['reason']}")
    rev = req["data_revision"]
    if result["data_revision"] != rev or result["evidence_bundle"]["data_revision"] != rev:
        raise RetrievalUnavailable("retrieve вернул другую ревизию данных")  # нельзя молча использовать чужой индекс (CT-13)
    if result["request_id"] != req["request_id"]:
        raise ContractViolation("retrieve: request_id не совпадает")
    b = result["evidence_bundle"]
    ids = [i["evidence"]["id"] for i in b["items"]]
    if len(ids) > 20 or len(set(ids)) != len(ids):
        raise ContractViolation("bundle: больше 20 доказательств или повторы")
    if set(ids) != set(b["allowed_evidence_ids"]):
        raise ContractViolation("bundle: allowed_evidence_ids не совпадает с items")
    if sum(len(i["evidence"]["excerpt"] or "") for i in b["items"]) > MAX_EXCERPT_TOTAL:
        raise ContractViolation("bundle: превышен общий объем excerpt")
    registered = db.get_entities(rev, "evidence", ids)
    src_ids = sorted({i["source_metadata"]["id"] for i in b["items"]})
    sources = db.get_entities(rev, "source", src_ids)
    for item in b["items"]:
        ev = item["evidence"]
        reg = registered.get(ev["id"])
        if reg is None or reg != ev:
            raise ContractViolation(f"bundle: доказательство {ev['id']} не совпадает с опубликованным корпусом")
        reg_src = sources.get(ev["source_id"])
        # local_asset_id назначает бэкенд при импорте (D-038): модуль AI 1 читает пакет и видит там null.
        if (reg_src is None or item["source_metadata"]["id"] != ev["source_id"]
                or {k: v for k, v in item["source_metadata"].items() if k != "local_asset_id"}
                != {k: v for k, v in reg_src.items() if k != "local_asset_id"}):
            raise ContractViolation(f"bundle: метаданные источника {ev['source_id']} не совпадают с корпусом")
        item["source_metadata"] = reg_src  # дальше идет запись реестра, а не копия модуля
        for f in item["normalized_facts"]:
            if not set(f["evidence_ids"]) <= set(ids):
                raise ContractViolation("bundle: normalized_fact ссылается на доказательство вне bundle")
    if set(b["allowed_source_ids"]) != set(src_ids):
        raise ContractViolation("bundle: allowed_source_ids не совпадает с items")
    run_ids = sorted({r for i in b["items"] for r in i["run_ids"]} | set(b["coverage"]["matching_run_ids"]))
    if db.existing_ids(rev, "run", run_ids) != set(run_ids):
        raise ContractViolation("bundle: ссылка на несуществующий опыт")
    return b


def check_reasoning(resp: dict, bundle: dict, scenario: dict | None, limits: dict) -> list[str]:
    """Возвращает список нарушений (пустой - можно публиковать)."""
    problems: list[str] = []
    viol = c.errors_for("InternalReasoningResponse", resp)
    if viol:
        return [f"schema {v['field']}: {v['reason']}" for v in viol]
    allowed = set(bundle["allowed_evidence_ids"])
    allowed_src = set(bundle["allowed_source_ids"])
    ev_source = {i["evidence"]["id"]: i["evidence"]["source_id"] for i in bundle["items"]}
    vs = resp["validation_summary"]
    if not all(vs.values()):
        problems.append("validation_summary модуля содержит false")
    if len(resp["answer_blocks"]) > limits["max_blocks"] or len(resp["follow_up_questions"]) > limits["max_follow_ups"]:
        problems.append("превышены output_limits")
    total = sum(len(b["text"]) for b in resp["answer_blocks"])
    if total > limits["max_total_chars"]:
        problems.append("превышен max_total_chars")
    texts = [b["text"] for b in resp["answer_blocks"]] + resp["limitations"] + resp["follow_up_questions"]
    for t in texts:
        if HTML_RE.search(t):
            problems.append("в тексте найдена HTML-разметка")
            break
    for t in texts:
        if URL_RE.search(t):
            problems.append("в тексте найден URL; ссылки строит только бэкенд")
            break
    ids_used = set()
    for b in resp["answer_blocks"]:
        ids_used |= set(b["evidence_ids"])
        for qr in b["quantities"]:
            ids_used |= set(qr["evidence_ids"]) | set(qr["quantity"]["evidence_ids"])
    for cit in resp["citations"]:
        ids_used.add(cit["evidence_id"])
        if cit["source_id"] not in allowed_src or ev_source.get(cit["evidence_id"]) != cit["source_id"]:
            problems.append(f"citation {cit['evidence_id']}: источник не соответствует доказательству")
    ap = resp["applicability"]
    if ap:
        for f in ap["factors"]:
            ids_used |= set(f["evidence_ids"])
    foreign = sorted(ids_used - allowed)
    if foreign:
        problems.append(f"ссылки вне разрешенного bundle: {foreign[:5]}")
    if resp["status"] == "answered" and not any(b["kind"] in ("observation", "synthesis", "summary") for b in resp["answer_blocks"]):
        problems.append("answered без содержательных блоков")
    cov = bundle["coverage"]
    if ap and ap["overall"] == "direct_evidence":
        if not cov["direct_evidence_available"]:
            problems.append("direct_evidence при coverage.direct_evidence_available=false")
        if scenario and scenario["gravity_regime"] in ("partial", "simulated_partial") and not cov["target_gravity_covered"]:
            problems.append("direct_evidence для частичной гравитации без прямых опытов (13.6)")
    if ap and ap["basis"]["data_revision"] != bundle["data_revision"]:
        problems.append("applicability.basis.data_revision не совпадает")
    return problems


def check_applicability(result: dict, scenario: dict, data_revision: str, runs: list[dict]) -> dict:
    viol = c.errors_for("ApplicabilityResult", result)
    if viol:
        raise ContractViolation(f"applicability: {viol[0]['field']}: {viol[0]['reason']}")
    if result["basis"]["data_revision"] != data_revision:
        raise ContractViolation("applicability: другая ревизия")
    if result["overall"] == "direct_evidence" and scenario["gravity_regime"] in ("partial", "simulated_partial"):
        if not any(r["conditions"]["gravity_regime"] == scenario["gravity_regime"] for r in runs):
            raise ContractViolation("applicability: direct_evidence без опытов целевой гравитации (13.6)")
    return result
