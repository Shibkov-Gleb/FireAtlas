"""Поиск исследований (BE-05): жесткие фильтры бэкенда + ранжирование AI 1 (CT-13).

Разделение ответственности (D-032):
* Фильтры из запроса жесткие. Их проверяет бэкенд по опубликованному корпусу, детерминированно и
  одинаково для любого провайдера. Модуль AI 1 не может вернуть исследование, которое фильтр отсек,
  как прямое совпадение.
* Порядок, relevance_category и смысловые причины соответствия дает retrieve (AI 1). Бэкенд
  проверяет выход: схема, ревизия, существование ID, принадлежность опытов исследованию.
* include_related=true добавляет исследования, которые retrieve счел связанными, но которые не
  прошли жесткие фильтры. Они идут после прямых, помечены related=true, а у differences есть
  причина несовпадения с фильтром.
"""
from __future__ import annotations

import math
from typing import Any

from .errors import validation_error
from .providers import ContractViolation

KNOWN = {"measured", "reported", "derived"}
EMPTY_FILTERS: dict[str, Any] = {
    "scopes": [], "investigation_ids": [], "material_ids": [], "fuel_states": [], "gravity_regimes": [],
    "oxygen_range": None, "pressure_range": None, "airflow_range": None, "has_measurements": None,
    "include_unknown": False,
}
# фильтр -> (поле Investigation, словарь подписей, префикс причины)
LIST_FILTERS = {
    "scopes": ("scopes", "scope", "Направление"),
    "fuel_states": ("fuel_states", "fuel_state", "Состояние горючего"),
    "gravity_regimes": ("gravity_regimes", "gravity_regime", "Гравитация"),
    "material_ids": ("material_ids", None, "Материал"),
}
REASON_CODE = {"scopes": "scope", "fuel_states": "fuel_state", "gravity_regimes": "gravity_regime",
               "material_ids": "material", "investigation_ids": "investigation_id",
               "has_measurements": "has_measurements"}
# фильтр диапазона -> (имя в run.conditions, путь поля, единица, подпись)
RANGE_FILTERS = {
    "oxygen_range": ("oxygen_fraction", "conditions.oxygen_fraction", "fraction", "Доля кислорода"),
    "pressure_range": ("pressure", "conditions.pressure", "Pa", "Давление"),
    "airflow_range": ("airflow_speed", "conditions.airflow_speed", "m_s", "Скорость потока"),
}


def applied_filters(filters: dict | None) -> dict:
    return {**EMPTY_FILTERS, **(filters or {})}


def has_any_filter(af: dict) -> bool:
    return any(af[k] != EMPTY_FILTERS[k] for k in EMPTY_FILTERS if k != "include_unknown")


def validate_request(body: dict, af: dict) -> None:
    problems = []
    if not body["query"] and not has_any_filter(af):
        problems.append({"field": "query", "reason": "empty_query_without_filters"})
    for name in RANGE_FILTERS:
        rng = af[name]
        if rng and rng["min"] is not None and rng["max"] is not None and rng["min"] > rng["max"]:
            problems.append({"field": f"filters.{name}", "reason": "min_greater_than_max"})
    if problems:
        raise validation_error(problems)


def _label(dicts: dict, name: str | None, value: str, materials: dict[str, dict]) -> str:
    if name is None:
        return materials.get(value, {}).get("label", value)
    return next((d["label"] for d in dicts.get(name, []) if d["value"] == value), value)


def _in(v: float, rng: dict) -> bool:
    return (rng["min"] is None or v >= rng["min"]) and (rng["max"] is None or v <= rng["max"])


def _run_value(run: dict, cond: str, unit: str) -> tuple[float | None, list[str]]:
    q = run["conditions"].get(cond)
    if not isinstance(q, dict) or q.get("status") not in KNOWN or q.get("value") is None:
        return None, []
    if q["unit"] != unit or not math.isfinite(q["value"]):
        return None, []
    return q["value"], q["evidence_ids"]


def _has_measurements(runs: list[dict]) -> bool:
    return any(m["quantity"]["status"] in KNOWN and m["quantity"]["value"] is not None
               for r in runs for m in r["metrics"])


def evaluate(inv: dict, runs: list[dict], af: dict, dicts: dict, materials: dict[str, dict]) -> dict:
    """Проверка одного исследования по жестким фильтрам.

    Возвращает {passes, matching_run_ids (None - фильтров диапазона нет), match_reasons, differences, missing_fields}.
    Значение неизвестно (нет данных) -> поле в missing_fields; проходит только при include_unknown.
    """
    reasons: list[dict] = []
    diffs: list[dict] = []
    missing: list[str] = []
    failed = False

    if af["investigation_ids"] and inv["id"] not in af["investigation_ids"]:
        failed = True
        diffs.append({"code": "filter_mismatch", "field": "investigation_ids", "evidence_ids": [],
                      "text": "Не входит в выбранный список исследований."})

    for fname, (ifield, dname, prefix) in LIST_FILTERS.items():
        wanted = af[fname]
        if not wanted:
            continue
        have = inv[ifield]
        hit = [v for v in have if v in wanted]
        if hit:
            text = f"{prefix}: " + ", ".join(_label(dicts, dname, v, materials) for v in hit)
            reasons.append({"code": REASON_CODE[fname], "text": text[:300], "field": ifield, "evidence_ids": []})
        elif not have:
            missing.append(ifield)
        else:
            failed = True
            text = f"{prefix}: " + ", ".join(_label(dicts, dname, v, materials) for v in have) + " - не совпадает с фильтром"
            diffs.append({"code": "filter_mismatch", "text": text[:300], "field": ifield, "evidence_ids": []})

    if af["has_measurements"] is not None:
        has = _has_measurements(runs)
        if has != af["has_measurements"]:
            failed = True
            diffs.append({"code": "filter_mismatch", "field": "has_measurements", "evidence_ids": [],
                          "text": "Есть опыты с измерениями" if has else "Нет опытов с измерениями"})
        elif has:
            reasons.append({"code": "has_measurements", "text": "Есть опыты с измерениями", "field": None,
                            "evidence_ids": []})

    range_set = [n for n in RANGE_FILTERS if af[n]]
    run_ok = {r["id"]: True for r in runs}
    for name in range_set:
        cond, path, unit, label = RANGE_FILTERS[name]
        rng = af[name]
        known = {}
        for r in runs:
            v, ev = _run_value(r, cond, unit)
            if v is not None:
                known[r["id"]] = (v, ev)
        if known:
            inside = {rid for rid, (v, _) in known.items() if _in(v, rng)}
            for r in runs:
                if r["id"] in known:
                    run_ok[r["id"]] &= r["id"] in inside
                else:
                    run_ok[r["id"]] &= af["include_unknown"]
            if inside:
                ev = sorted({e for rid in inside for e in known[rid][1]})[:20]
                reasons.append({"code": name, "text": f"{label}: есть опыты в диапазоне фильтра", "field": path,
                                "evidence_ids": ev})
            else:
                failed = True
                lo, hi = min(v for v, _ in known.values()), max(v for v, _ in known.values())
                diffs.append({"code": "filter_mismatch", "field": path, "evidence_ids": [],
                              "text": f"{label}: значения опытов {lo:g}-{hi:g} вне диапазона фильтра"})
            continue
        # Опытов с сообщенным значением нет - агрегат исследования (conditions_coverage).
        cov = next((c for c in inv["conditions_coverage"] if c["field"] == path and c["known_count"] > 0
                    and c["min_value"] is not None and c["max_value"] is not None and c["unit"] == unit), None)
        for r in runs:
            run_ok[r["id"]] &= af["include_unknown"]
        if cov is None:
            missing.append(path)
            continue
        overlap = (rng["max"] is None or cov["min_value"] <= rng["max"]) and (rng["min"] is None or cov["max_value"] >= rng["min"])
        if overlap:
            reasons.append({"code": name, "text": f"{label}: диапазон исследования пересекается с фильтром", "field": path,
                            "evidence_ids": cov["derivation_evidence_ids"][:20]})
        else:
            failed = True
            diffs.append({"code": "filter_mismatch", "field": path, "evidence_ids": cov["derivation_evidence_ids"][:20],
                          "text": f"{label}: диапазон исследования {cov['min_value']:g}-{cov['max_value']:g} вне фильтра"})

    matching = None
    if range_set:
        matching = [r["id"] for r in runs if run_ok[r["id"]]]
        # Значения есть, но ни один опыт не удовлетворяет всем диапазонам одновременно.
        if runs and not matching and not failed and any(_run_value(r, RANGE_FILTERS[n][0], RANGE_FILTERS[n][2])[0] is not None
                                                        for r in runs for n in range_set):
            failed = True
            diffs.append({"code": "filter_mismatch", "field": None, "evidence_ids": [],
                          "text": "Нет опыта, который одновременно попадает во все диапазоны фильтра"})

    if missing and not af["include_unknown"]:
        failed = True
    return {"passes": not failed, "matching_run_ids": matching, "match_reasons": reasons, "differences": diffs,
            "missing_fields": missing}


def check_ranked(ranked: list[dict], invs: dict[str, dict], runs_by: dict[str, list[dict]], existing_ev: set[str]) -> None:
    """Проверка ranked_items модуля AI 1 сверх схемы (CT-13)."""
    seen = set()
    for it in ranked:
        iid = it["investigation_id"]
        if iid in seen:
            raise ContractViolation(f"ranked_items: повтор {iid}")
        seen.add(iid)
        if iid not in invs:
            raise ContractViolation(f"ranked_items: {iid} нет в ревизии")
        own = {r["id"] for r in runs_by.get(iid, [])}
        if not set(it["matching_run_ids"]) <= own:
            raise ContractViolation(f"ranked_items: опыт не принадлежит {iid}")
        for r in it["match_reasons"] + it["differences"]:
            if not set(r["evidence_ids"]) <= existing_ev:
                raise ContractViolation(f"ranked_items: причина {r['code']} ссылается на неизвестное доказательство")


def _merge_reasons(own: list[dict], extra: list[dict], limit: int = 20) -> list[dict]:
    out, codes = list(own), {(r["code"], r["field"]) for r in own}
    for r in extra:
        if (r["code"], r["field"]) not in codes:
            out.append(r)
            codes.add((r["code"], r["field"]))
    return out[:limit]


def build_items(invs: dict[str, dict], evals: dict[str, dict], ranked: list[dict] | None, ev_by_inv: dict[str, list[str]],
                query: str, include_related: bool, sort: str) -> list[dict]:
    """Итоговая выдача. ranked=None - retrieve недоступен (подборка бэкенда по фильтрам)."""
    passing = [i for i in invs if evals[i]["passes"]]
    direct, related = [], []
    ranked_ids = set()
    for it in sorted(ranked or [], key=lambda x: -x["rank_score"]):  # sorted стабилен: при равенстве - порядок AI 1
        iid = it["investigation_id"]
        ranked_ids.add(iid)
        ev = evals[iid]
        if ev["passes"]:
            direct.append((iid, it["relevance_category"], it, False))
        elif include_related:
            cat = "related" if it["relevance_category"] == "direct" else it["relevance_category"]
            related.append((iid, cat, it, True))
    if not query or ranked is None:
        # Только фильтры (или AI недоступен): все прошедшие фильтр, неранжированные - по аббревиатуре.
        rest = sorted((i for i in passing if i not in ranked_ids), key=lambda i: (invs[i]["acronym"].casefold(), i))
        direct += [(i, "direct" if query == "" else "contextual", None, False) for i in rest]
    out = []
    for iid, cat, it, is_rel in direct + related:
        ev = evals[iid]
        prov_runs = it["matching_run_ids"] if it else []
        runs = ev["matching_run_ids"] if ev["matching_run_ids"] is not None else prov_runs
        out.append({
            "investigation": invs[iid],
            "relevance_category": cat,
            "match_reasons": _merge_reasons(ev["match_reasons"], it["match_reasons"] if it else []),
            "differences": _merge_reasons(ev["differences"], it["differences"] if it else []),
            "missing_fields": list(dict.fromkeys(ev["missing_fields"] + (it["missing_fields"] if it else [])))[:50],
            "matching_run_ids": list(dict.fromkeys(runs)),
            "related": is_rel,
            "evidence_ids": ev_by_inv.get(iid, [])[:50],
        })
    if sort == "acronym":
        out.sort(key=lambda x: (x["related"], x["investigation"]["acronym"].casefold(), x["investigation"]["id"]))
    return out
