"""BE-07: таблица сравнения 2-3 исследований по общим признакам (FR-11, DR-06).

Сравниваются задачи и условия, численные результаты не объединяются.
Отсутствие поля не трактуется как совпадение: такая ячейка получает not_reported.
"""
from __future__ import annotations

from collections import Counter

LIMITATIONS = [
    "Research goals, subjects and conditions are compared; numerical results from different methods are not combined (DR-06).",
    "Missing information in a source is not treated as a match.",
]
COVERAGE_ROWS = [
    ("conditions.oxygen_fraction", "Oxygen fraction"),
    ("conditions.co2_fraction", "CO₂ fraction (diluent)"),
    ("conditions.helium_fraction", "Helium fraction (diluent)"),
    ("conditions.pressure", "Pressure"),
    ("conditions.airflow_speed", "Calibrated airflow speed"),
    ("sample.initial_diameter", "Initial sample diameter"),
    ("sample.thickness", "Sample thickness"),
]
OPTIONAL_ROWS = {"conditions.co2_fraction", "conditions.helium_fraction"}


def _labels(dictionaries: dict, name: str) -> dict[str, str]:
    return {e["value"]: e["label"] for e in dictionaries.get(name, [])}


def fmt_value(v: float, unit: str) -> str:
    if unit == "Pa":
        return f"{v / 1000:.4g} kPa"
    if unit == "m":
        return f"{v * 1000:.4g} mm"
    if unit == "m_s":
        return f"{v:.4g} m/s"
    if unit == "s":
        return f"{v:.4g} s"
    if unit == "K":
        return f"{v:.4g} K"
    return f"{v:.4g}"


def fmt_range(lo, hi, unit: str) -> str:
    if lo is None and hi is None:
        return ""
    if lo is not None and hi is not None and lo == hi:
        return fmt_value(lo, unit)
    return f"{fmt_value(lo, unit) if lo is not None else '?'} - {fmt_value(hi, unit) if hi is not None else '?'}"


def build_table(investigations: list[dict], runs_by_inv: dict[str, list[dict]], materials: dict[str, dict],
                dictionaries: dict) -> dict:
    L = {k: _labels(dictionaries, k) for k in ("fuel_state", "scope", "gravity_regime", "geometry", "metric_key", "outcome_category")}

    def cell(inv, text, status="known", ev=()):
        return {"investigation_id": inv["id"], "value_text": text if status == "known" else None, "status": status,
                "evidence_ids": sorted(set(ev))}

    def simple(field, label, fn):
        cells = []
        for inv in investigations:
            text = fn(inv)
            cells.append(cell(inv, text) if text else cell(inv, None, "not_reported"))
        return {"field": field, "label": label, "cells": cells}

    rows = [
        simple("title", "Investigation", lambda i: f"{i['acronym']} ({i['psi_id']}): {i['title']}"),
        simple("fuel_states", "Fuel state", lambda i: ", ".join(L["fuel_state"].get(x, x) for x in i["fuel_states"])),
        simple("geometry", "Sample geometries", lambda i: ", ".join(sorted({L["geometry"].get(r["sample"]["geometry"], r["sample"]["geometry"])
                                                                           for r in runs_by_inv.get(i["id"], [])
                                                                           if r["sample"]["geometry"] != "unknown"}))),
        simple("materials", "Materials", lambda i: ", ".join(materials[m]["label"] for m in i["material_ids"] if m in materials)),
        simple("objectives", "Objective", lambda i: "; ".join(i["objectives"])),
        simple("setup_summary", "Setup", lambda i: i["setup_summary"]),
        simple("scopes", "Research area", lambda i: ", ".join(L["scope"].get(x, x) for x in i["scopes"])),
        simple("gravity_regimes", "Gravity regime", lambda i: ", ".join(L["gravity_regime"].get(x, x) for x in i["gravity_regimes"])),
    ]
    metric_sets: dict[str, set] = {}
    m_cells = []
    for inv in investigations:
        keys: Counter = Counter()
        ev: set = set()
        for r in runs_by_inv.get(inv["id"], []):
            for m in r["metrics"]:
                if m["quantity"]["status"] in ("measured", "reported", "derived"):
                    keys[m["metric_key"]] += 1
                    ev.update(m["quantity"]["evidence_ids"][:1])
        metric_sets[inv["id"]] = set(keys)
        text = ", ".join(f"{L['metric_key'].get(k, k)} ({n})" for k, n in sorted(keys.items()))
        m_cells.append(cell(inv, text, ev=list(ev)[:10]) if keys else cell(inv, None, "not_reported"))
    rows.append({"field": "measured_metrics", "label": "Measured metrics (record count)", "cells": m_cells})
    o_cells = []
    for inv in investigations:
        cnt = Counter(r["terminal_outcome"]["category"] for r in runs_by_inv.get(inv["id"], []))
        cnt.pop("unknown", None)
        text = ", ".join(f"{L['outcome_category'].get(k, k)}: {n}" for k, n in sorted(cnt.items()))
        o_cells.append(cell(inv, text) if cnt else cell(inv, None, "not_reported"))
    rows.append({"field": "outcomes", "label": "Test run outcomes", "cells": o_cells})
    for field, label in COVERAGE_ROWS:
        if field in OPTIONAL_ROWS and not any(c["field"] == field and c["known_count"] > 0
                                              for inv in investigations for c in inv["conditions_coverage"]):
            continue  # разбавители показываются, только если хотя бы у одного исследования есть значения (D-036)
        cells = []
        for inv in investigations:
            cov = next((c for c in inv["conditions_coverage"] if c["field"] == field), None)
            if cov and cov["known_count"] > 0 and (cov["min_value"] is not None or cov["max_value"] is not None):
                text = fmt_range(cov["min_value"], cov["max_value"], cov["unit"])
                if cov["unknown_count"]:
                    text += f" (unknown in {cov['unknown_count']} records)"
                cells.append(cell(inv, text, ev=cov["derivation_evidence_ids"]))
            else:
                cells.append(cell(inv, None, "not_reported", ev=cov["derivation_evidence_ids"] if cov else ()))
        rows.append({"field": field, "label": label, "cells": cells})

    reasons = []
    fuels = [frozenset(i["fuel_states"]) for i in investigations]
    same_object = len(set(fuels)) == 1 and bool(fuels[0])
    if not same_object:
        reasons.append({"code": "different_object", "field": "fuel_states", "evidence_ids": [],
                        "text": "Different research subjects: " + "; ".join(
                            f"{i['acronym']} - {', '.join(L['fuel_state'].get(x, x) for x in i['fuel_states']) or 'not specified'}"
                            for i in investigations)})
    sets = list(metric_sets.values())
    common_metrics = set.intersection(*sets) if sets else set()
    if not common_metrics:
        reasons.append({"code": "different_metrics", "field": "measured_metrics", "evidence_ids": [],
                        "text": "There are no shared measured metrics; no combined numerical conclusion is drawn."})
    common_scope = set.intersection(*(set(i["scopes"]) for i in investigations))
    if not common_scope:
        reasons.append({"code": "different_scope", "field": "scopes", "evidence_ids": [],
                        "text": "Different research areas."})
    if same_object and common_metrics:
        status = "compatible"
        reasons.append({"code": "same_object_and_metrics", "field": None, "evidence_ids": [],
                        "text": "Shared subject and metrics; check methods and conditions before comparing numbers."})
    elif not same_object and not common_metrics and not common_scope:
        status = "incompatible"
    else:
        status = "partially_compatible"
    limitations = list(LIMITATIONS)
    if any(cl["status"] == "not_reported" for r in rows for cl in r["cells"]):
        limitations.append("Some information is not reported in the sources; those cells are marked.")
    return {"rows": rows, "comparability": {"status": status, "reasons": reasons}, "limitations": limitations}
