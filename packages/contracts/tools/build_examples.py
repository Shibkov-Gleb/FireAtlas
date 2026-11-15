"""Генератор contracts/examples (CT-16).

Запуск:  python3 packages/contracts/tools/build_examples.py
Результат: examples/<operationId>/<case>.json + examples/index.json

Правила:
* Реальные числа - только контрольные записи FLEX из приложения А ТЗ.
* Все остальное научное содержимое помечено [FIXTURE] и не является корпусом.
* fixture=true хранится в метаданных примера и в index.json, а не в сущностях.
"""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "examples"

REV = "psi-20261115-r1"
CV = "1.2.0"
T0 = "2026-11-15T09:00:00Z"
MMHG = 133.322387


def meta(req="req_demo01", rev=REV, warnings=None):
    return {"request_id": req, "contract_version": CV, "data_revision": rev, "warnings": warnings or []}


def env(data, **kw):
    return {"data": data, "meta": meta(**kw)}


def err(code, message, retryable=False, details=None, req="req_demo02", rev=REV):
    return {
        "error": {"code": code, "message": message, "details": details or [], "retryable": retryable},
        "meta": meta(req=req, rev=rev),
    }


def q(value, unit, status="reported", raw_value=None, raw_unit=None, ev=(), qualifier="eq", uncertainty=None):
    known = status in ("measured", "reported", "derived")
    return {
        "value": value if known else None,
        "unit": unit,
        "status": status,
        "qualifier": qualifier if known else None,
        "raw_value": raw_value,
        "raw_unit": raw_unit,
        "uncertainty": uncertainty if known else None,
        "evidence_ids": list(ev),
        "derivation": None,
    }


def unknown(unit, ev=()):
    return q(None, unit, status="not_reported", ev=ev)


def locator(page=None, section=None, row_key=None, start_s=None, end_s=None):
    return {"page": page, "section": section, "row_key": row_key, "start_s": start_s, "end_s": end_s}


# ----------------------------------------------------------------------------
# Источники
# ----------------------------------------------------------------------------
SOURCES = {
    "src_psi25_dataset": {
        "id": "src_psi25_dataset", "data_revision": REV,
        "title": "BASS-II (PSI-25) - набор данных NASA PSI",
        "kind": "repository",
        "canonical_url": "https://psi.nasa.gov/physci/repo/data/investigations/PSI-25",
        "doi": None, "publication_date": None, "retrieved_at": "2026-11-15T08:00:00Z",
        "license": None, "availability": "metadata_only", "local_asset_id": None, "sha256": None,
    },
    "src_ntrs_20160000593": {
        "id": "src_ntrs_20160000593", "data_revision": REV,
        "title": "Результаты BASS-II, NASA NTRS 20160000593",
        "kind": "report",
        "canonical_url": "https://ntrs.nasa.gov/citations/20160000593",
        "doi": None, "publication_date": None, "retrieved_at": "2026-11-15T08:00:00Z",
        "license": None, "availability": "metadata_only", "local_asset_id": None, "sha256": None,
    },
    "src_psi69_exptable": {
        "id": "src_psi69_exptable", "data_revision": REV,
        "title": "FLEX (PSI-69) - Experimental Table, версия 5",
        "kind": "experimental_table",
        "canonical_url": "https://psi.nasa.gov/physci/repo/data/investigations/PSI-69",
        "doi": None, "publication_date": None, "retrieved_at": "2026-11-15T08:00:00Z",
        "license": None, "availability": "available",
        "local_asset_id": "asset_psi69_exptable_v5",
        "sha256": "0" * 63 + "1",
    },
    "src_psi101_dataset": {
        "id": "src_psi101_dataset", "data_revision": REV,
        "title": "SAME-R (PSI-101) - набор данных NASA PSI",
        "kind": "repository",
        "canonical_url": "https://psi.nasa.gov/physci/repo/data/investigations/PSI-101",
        "doi": None, "publication_date": None, "retrieved_at": "2026-11-15T08:00:00Z",
        "license": None, "availability": "unavailable", "local_asset_id": None, "sha256": None,
    },
    "src_track_flame_in_freefall": {
        "id": "src_track_flame_in_freefall", "data_revision": REV,
        "title": "Flame in Freefall - условия трека NASA Space Apps 2026",
        "kind": "publication",
        "canonical_url": "https://www.spaceappschallenge.org/2026/challenges/flame-in-freefall/?tab=details",
        "doi": None, "publication_date": None, "retrieved_at": "2026-11-15T08:00:00Z",
        "license": None, "availability": "metadata_only", "local_asset_id": None, "sha256": None,
    },
}

# ----------------------------------------------------------------------------
# FLEX: приложение А (реальные контрольные записи)
# ----------------------------------------------------------------------------
FLEX_ROWS = [
    # test_id, diameter_mm, time_s, outcome_raw, pressure_mmHg
    ("20CAL08", "1.69", "4.3", "Disruption", "757.7"),
    ("20CAL10", "1.86", "5.0", "Extinction", "762"),
    ("20CAL12", "1.61", "3.2", "Extinction", "764.2"),
    ("30CAL02", "2.06", "7.64", "Extinction", "760"),
    ("30CAL03", "1.92", "6.34", "Extinction", "760"),
]


def flex_evidence(tid, d, t, outcome, p):
    return {
        "id": f"ev_psi69_{tid.lower()}", "data_revision": REV,
        "source_id": "src_psi69_exptable", "kind": "table_row",
        "locator": locator(row_key=tid),
        "excerpt": None,
        "table_values": [
            {"field": "Test ID", "raw_value": tid, "raw_unit": None},
            {"field": "Initial diameter", "raw_value": d, "raw_unit": "mm"},
            {"field": "Burn time", "raw_value": t, "raw_unit": "s"},
            {"field": "Pressure", "raw_value": p, "raw_unit": "mmHg"},
            {"field": "Outcome", "raw_value": outcome, "raw_unit": None},
        ],
        "verified": True,
        "verification_note": "Сверено с Experimental Table FLEX PSI-69 v5 (приложение А ТЗ). Пример для контракта.",
    }


def flex_run(tid, d, t, outcome, p):
    ev = f"ev_psi69_{tid.lower()}"
    return {
        "id": f"run_psi69_{tid.lower()}", "data_revision": REV,
        "investigation_id": "inv_psi69", "source_test_id": tid,
        "material_id": "mat_methanol",
        "sample": {
            "geometry": "droplet",
            "thickness": q(None, "m", status="not_applicable"),
            "initial_diameter": q(round(float(d) / 1000, 8), "m", raw_value=d, raw_unit="mm", ev=[ev]),
        },
        "conditions": {
            "gravity_regime": "microgravity",
            "gravity_level": unknown("g_fraction"),
            "oxygen_fraction": q(0.21, "fraction", raw_value="0.21", raw_unit="mole fraction", ev=[ev]),
            # D-036: состав атмосферы серии из Experimental Table FLEX v5 (воздух: N2 0.79, CO2 0, He 0)
            "nitrogen_fraction": q(0.79, "fraction", raw_value="0.79", raw_unit="mole fraction", ev=[ev]),
            "co2_fraction": q(0.0, "fraction", raw_value="0", raw_unit="mole fraction", ev=[ev]),
            "helium_fraction": q(0.0, "fraction", raw_value="0", raw_unit="mole fraction", ev=[ev]),
            "pressure": q(round(float(p) * MMHG, 2), "Pa", raw_value=p, raw_unit="mmHg", ev=[ev]),
            "airflow_speed": unknown("m_s"),
            "flow_configuration": "unknown",
            "ambient_temperature": unknown("K"),
        },
        "metrics": [{"metric_key": "burn_duration", "quantity": q(float(t), "s", raw_value=t, raw_unit="s", ev=[ev])}],
        "terminal_outcome": {
            "category": outcome.lower(),
            "raw_label": outcome,
            "interpretation_status": "source_explicit",
            "evidence_ids": [ev],
        },
        "regime_tags": [],
        "evidence_ids": [ev],
        "quality_notes": ["Начальная доля кислорода 0.21 по описанию серии (приложение А)."],
    }


EVIDENCE = {e["id"]: e for e in (flex_evidence(*r) for r in FLEX_ROWS)}
RUNS = {r["id"]: r for r in (flex_run(*row) for row in FLEX_ROWS)}

EVIDENCE["ev_psi25_fixture01"] = {
    "id": "ev_psi25_fixture01", "data_revision": REV,
    "source_id": "src_ntrs_20160000593", "kind": "text_excerpt",
    "locator": locator(section="[FIXTURE] Results"),
    "excerpt": "[FIXTURE] Заглушка фрагмента отчета BASS-II. Реальный текст, страницу и проверку поставляет AI 1 (A1-03).",
    "table_values": [], "verified": True,
    "verification_note": "[FIXTURE] Только для проверки формы контракта.",
}
EVIDENCE["ev_psi25_fixture02"] = {
    "id": "ev_psi25_fixture02", "data_revision": REV,
    "source_id": "src_psi25_dataset", "kind": "metadata",
    "locator": locator(section="[FIXTURE] Test matrix"),
    "excerpt": None, "table_values": [], "verified": True,
    "verification_note": "[FIXTURE] Запись без значения давления - пример отсутствующего параметра (AT-05).",
}
EVIDENCE["ev_psi101_fixture01"] = {
    "id": "ev_psi101_fixture01", "data_revision": REV,
    "source_id": "src_psi101_dataset", "kind": "metadata",
    "locator": locator(section="[FIXTURE] Dataset description"),
    "excerpt": None, "table_values": [], "verified": True,
    "verification_note": "[FIXTURE] Источник недоступен; метаданные доступны (AT-26).",
}
EVIDENCE["ev_track_partial_gravity"] = {
    "id": "ev_track_partial_gravity", "data_revision": REV,
    "source_id": "src_track_flame_in_freefall", "kind": "text_excerpt",
    "locator": locator(section="[FIXTURE] Details"),
    "excerpt": "[FIXTURE] В описании трека указано отсутствие данных частичной гравитации в PSI (DR-07). Точную цитату фиксирует AI 1.",
    "table_values": [], "verified": True, "verification_note": "[FIXTURE]",
}

RUNS["run_psi25_fixture01"] = {
    "id": "run_psi25_fixture01", "data_revision": REV,
    "investigation_id": "inv_psi25", "source_test_id": None,
    "material_id": "mat_psi25_fixture_solid",
    "sample": {"geometry": "unknown", "thickness": unknown("m"), "initial_diameter": q(None, "m", status="not_applicable")},
    "conditions": {
        "gravity_regime": "microgravity",
        "gravity_level": unknown("g_fraction"),
        "oxygen_fraction": unknown("fraction", ev=["ev_psi25_fixture02"]),
        "nitrogen_fraction": unknown("fraction"),
        "co2_fraction": unknown("fraction"),
        "helium_fraction": unknown("fraction"),
        "pressure": unknown("Pa", ev=["ev_psi25_fixture02"]),
        "airflow_speed": unknown("m_s"),
        "flow_configuration": "unknown",
        "ambient_temperature": unknown("K"),
    },
    "metrics": [],
    "terminal_outcome": {"category": "unknown", "raw_label": None, "interpretation_status": "unmapped", "evidence_ids": []},
    "regime_tags": [],
    "evidence_ids": ["ev_psi25_fixture02"],
    "quality_notes": ["[FIXTURE] Давление не сообщено в источнике: value=null, status=not_reported. Нормальное давление не подставляется."],
}

MATERIALS = {
    "mat_methanol": {"id": "mat_methanol", "label": "Метанол", "state": "liquid", "composition": "CH3OH", "aliases": ["methanol"]},
    "mat_psi25_fixture_solid": {"id": "mat_psi25_fixture_solid", "label": "[FIXTURE] твердый образец", "state": "solid", "composition": None, "aliases": []},
}

CLAIMS = {
    "clm_psi69_30cal03_burn": {
        "id": "clm_psi69_30cal03_burn", "data_revision": REV, "investigation_ids": ["inv_psi69"],
        "kind": "observation", "text": "В опыте 30CAL03 время горения капли метанола составило 6,34 с.",
        "supporting_evidence_ids": ["ev_psi69_30cal03"], "contradicting_evidence_ids": [],
        "applicable_run_ids": ["run_psi69_30cal03"],
        "limitations": ["Одна запись; не устанавливает зависимость времени горения от диаметра."],
        "review_status": "reviewed",
    },
    "clm_psi25_fixture_hyp": {
        "id": "clm_psi25_fixture_hyp", "data_revision": REV, "investigation_ids": ["inv_psi25"],
        "kind": "hypothesis", "text": "[FIXTURE] Исходная гипотеза исследования - отображается отдельно от результатов.",
        "supporting_evidence_ids": [], "contradicting_evidence_ids": [], "applicable_run_ids": [],
        "limitations": [], "review_status": "reviewed",
    },
    "clm_psi25_fixture_obs": {
        "id": "clm_psi25_fixture_obs", "data_revision": REV, "investigation_ids": ["inv_psi25"],
        "kind": "observation", "text": "[FIXTURE] Наблюдение BASS-II о слабом потоке; текст и условия поставляет AI 1 (A1-05).",
        "supporting_evidence_ids": ["ev_psi25_fixture01"], "contradicting_evidence_ids": [], "applicable_run_ids": [],
        "limitations": ["[FIXTURE] Результат относится к условиям опыта."], "review_status": "reviewed",
    },
}


def investigation(id_, psi, acr, title, scopes, fuels, mats, srcs, claims, cov=None, assets=()):
    return {
        "id": id_, "data_revision": REV, "psi_id": psi, "acronym": acr, "title": title,
        "objectives": [f"[FIXTURE] Цель {acr}; формулировку поставляет AI 1."],
        "setup_summary": f"[FIXTURE] Краткое описание установки {acr}.",
        "scopes": scopes, "fuel_states": fuels, "gravity_regimes": ["microgravity"],
        "material_ids": mats, "source_ids": srcs, "claim_ids": claims,
        "conditions_coverage": cov or [], "available_assets": list(assets),
    }


FLEX_DIAM = [float(r[1]) / 1000 for r in FLEX_ROWS]
INVESTIGATIONS = {
    "inv_psi25": investigation(
        "inv_psi25", "PSI-25", "BASS-II", "Burning and Suppression of Solids - II",
        ["prevention", "suppression"], ["solid"], ["mat_psi25_fixture_solid"],
        ["src_psi25_dataset", "src_ntrs_20160000593"], ["clm_psi25_fixture_obs", "clm_psi25_fixture_hyp"],
        cov=[{"field": "conditions.pressure", "min_value": None, "max_value": None, "unit": "Pa",
              "known_count": 0, "unknown_count": 1, "derivation_evidence_ids": []}],
    ),
    "inv_psi69": investigation(
        "inv_psi69", "PSI-69", "FLEX", "Flame Extinguishment Experiment",
        ["suppression"], ["liquid"], ["mat_methanol"], ["src_psi69_exptable"], ["clm_psi69_30cal03_burn"],
        cov=[
            {"field": "sample.initial_diameter", "min_value": min(FLEX_DIAM), "max_value": max(FLEX_DIAM), "unit": "m",
             "known_count": 5, "unknown_count": 0, "derivation_evidence_ids": [f"ev_psi69_{r[0].lower()}" for r in FLEX_ROWS]},
            {"field": "conditions.oxygen_fraction", "min_value": 0.21, "max_value": 0.21, "unit": "fraction",
             "known_count": 5, "unknown_count": 0, "derivation_evidence_ids": [f"ev_psi69_{r[0].lower()}" for r in FLEX_ROWS]},
        ],
        assets=["src_psi69_exptable"],
    ),
    "inv_psi101": investigation(
        "inv_psi101", "PSI-101", "SAME-R", "Smoke Aerosol Measurement Experiment - Refurbished",
        ["detection"], ["solid"], [], ["src_psi101_dataset"], [],
    ),
}

ORBITAL = {
    "scenario_id": "orbital_custom", "name": "Орбитальная станция", "environment": "orbital_habitat",
    "celestial_body": None, "safety_task": "prevention", "material_ids": [], "geometry": None,
    "oxygen_fraction": None, "pressure": None, "airflow_speed": None, "gravity_regime": "microgravity",
    "assumptions": [{"field": "gravity_regime", "text": "Орбитальная среда задает микрогравитационный контекст; давление и кислород пресетом не задаются.",
                     "origin": "preset_source", "source_ids": ["src_track_flame_in_freefall"]}],
}
MOON = {
    "scenario_id": "moon_base", "name": "Лунная база", "environment": "surface_habitat",
    "celestial_body": "moon", "safety_task": "prevention", "material_ids": [], "geometry": None,
    "oxygen_fraction": None, "pressure": None, "airflow_speed": None, "gravity_regime": "partial",
    "assumptions": [{"field": "gravity_regime", "text": "Целевой режим - частичная гравитация Луны. Наличие сценария не означает наличие опытов в корпусе.",
                     "origin": "preset_source", "source_ids": ["src_track_flame_in_freefall"]}],
}
USER_O2 = copy.deepcopy(ORBITAL)
USER_O2["scenario_id"] = "orbital_user_o2"
USER_O2["oxygen_fraction"] = q(0.21, "fraction", raw_value="21", raw_unit="%")
USER_O2["assumptions"].append({"field": "oxygen_fraction", "text": "Доля кислорода задана пользователем.", "origin": "user", "source_ids": []})


def workspace(rev=3, scenario=ORBITAL, selected=("inv_psi25",), saved=(), answers=()):
    return {
        "id": "ws_demo01", "revision": rev, "scenario": scenario,
        "selected_investigation_ids": list(selected), "saved_investigation_ids": list(saved),
        "saved_answer_ids": list(answers), "data_revision": REV,
        "created_at": T0, "updated_at": "2026-11-15T09:05:00Z", "expires_at": "2026-11-22T09:05:00Z",
    }


EMPTY_FILTERS = {
    "scopes": [], "investigation_ids": [], "material_ids": [], "fuel_states": [], "gravity_regimes": [],
    "oxygen_range": None, "pressure_range": None, "airflow_range": None, "has_measurements": None, "include_unknown": False,
}


def reason(code, text, field=None, ev=()):
    return {"code": code, "text": text, "field": field, "evidence_ids": list(ev)}


def job(state="queued", stage=None, result_id=None, error=None, type_="analysis", fallback=(), scenario_id="orbital_custom", rev=3):
    return {
        "id": "job_demo01", "type": type_, "state": state, "stage": stage,
        "created_at": T0, "updated_at": "2026-11-15T09:00:05Z" if state != "queued" else T0,
        "deadline_at": "2026-11-15T09:00:45Z" if type_ == "analysis" else "2026-11-15T09:00:30Z",
        "result_kind": "answer" if type_ == "analysis" else "report",
        "result_id": result_id, "error": error,
        "input_context": {"workspace_revision": rev, "data_revision": REV, "scenario_id": scenario_id},
        "fallback_evidence_ids": list(fallback),
    }


def citation(ev_id, label):
    e = EVIDENCE[ev_id]
    return {"evidence_id": ev_id, "source_id": e["source_id"], "label": label, "locator": e["locator"]}


APPLICABILITY_MOON = {
    "overall": "related_evidence",
    "factors": [
        {"field": "gravity_regime", "status": "not_covered",
         "explanation": "Целевой режим - частичная гравитация; в корпусе только микрогравитация. Перенос требует обоснования.",
         "evidence_ids": ["ev_track_partial_gravity"]},
        {"field": "oxygen_fraction", "status": "unknown", "explanation": "Доля кислорода базы не задана.", "evidence_ids": []},
        {"field": "pressure", "status": "unknown", "explanation": "Давление базы не задано.", "evidence_ids": []},
        {"field": "material_ids", "status": "unknown", "explanation": "Материал не выбран.", "evidence_ids": []},
    ],
    "gaps": [
        {"field": "gravity_regime", "description": "Нет прямых опытов частичной гравитации в PSI.",
         "suggested_next_step": "Изучить связанные микрогравитационные исследования с явной оговоркой; сохранить пробел в отчете."},
        {"field": "oxygen_fraction", "description": "Не задана атмосфера базы.", "suggested_next_step": "Указать долю кислорода и давление сценария."},
    ],
    "basis": {"reviewed_rules_version": "applicability-rules-0.1-fixture", "data_revision": REV},
}

BLOCK_30CAL03 = {
    "id": "block_demo01", "kind": "observation",
    "text": "В опыте 30CAL03 время горения составило 6,34 с.",
    "evidence_ids": ["ev_psi69_30cal03"],
    "quantities": [{"name": "burn_duration", "quantity": q(6.34, "s", raw_value="6.34", raw_unit="s", ev=["ev_psi69_30cal03"]),
                    "evidence_ids": ["ev_psi69_30cal03"]}],
}
VALID = {"schema_valid": True, "references_valid": True, "quantities_valid": True, "scope_valid": True}


def answer(id_, status, blocks, citations, limitations, follow_ups, applicability, question, scenario=ORBITAL):
    return {
        "id": id_, "data_revision": REV, "workspace_revision": 3, "scenario_snapshot": scenario,
        "question": question, "status": status, "answer_blocks": blocks, "applicability": applicability,
        "citations": citations, "limitations": limitations, "follow_up_questions": follow_ups,
        "retrieval_mode": "lexical", "reasoning_revision": "reasoning-0.1-fixture",
        "validation_summary": VALID, "created_at": "2026-11-15T09:00:20Z",
    }


def report(state, **kw):
    base = {
        "id": "rpt_demo01", "state": state, "title": "Вентиляция и горение материалов",
        "source_workspace_revision": 4, "data_revision": REV, "created_at": "2026-11-15T10:00:00Z",
        "expires_at": "2026-11-16T10:00:00Z", "download_path": None, "sha256": None, "error": None,
    }
    base.update(kw)
    return base


DICTIONARIES = json.loads((ROOT / "dictionaries.ru.json").read_text(encoding="utf-8"))  # источник правды подписей

CONFIG = {
    "contract_version": CV, "active_data_revision": REV,
    "feature_flags": {"analysis": True, "reports": True, "semantic_search": False, "video_preview": False},
    "limits": {"search_limit_max": 100, "run_limit_max": 200, "measurement_limit_max": 1000, "question_chars_max": 2000,
               "comparison_max": 3, "analysis_deadline_s": 45, "report_deadline_s": 30},
    "dictionaries": {**DICTIONARIES, "materials": sorted(({"value": m["id"], "label": m["label"]} for m in MATERIALS.values()),
                                                       key=lambda e: e["label"])},  # D-040
    "measurement_axes": [{"x_key": "sample.initial_diameter", "y_key": "metrics.burn_duration", "investigation_ids": ["inv_psi69"]}],
    "retention": {"workspace_days": 7, "report_hours": 24},
}

FLEX_POINTS = [
    {"run_id": f"run_psi69_{r[0].lower()}", "x": round(float(r[1]) / 1000, 8), "y": float(r[2]),
     "outcome": r[3].lower(), "evidence_ids": [f"ev_psi69_{r[0].lower()}"]}
    for r in FLEX_ROWS
]
AXES = {
    "x_axis": {"key": "sample.initial_diameter", "label": "Начальный диаметр капли", "unit": "m"},
    "y_axis": {"key": "metrics.burn_duration", "label": "Время горения", "unit": "s"},
}
NO_EXCL = {"missing_x": 0, "missing_y": 0, "unusable_unit": 0, "unverified_record": 0, "filtered_out": 0}

COOKIE = "fa_session=<opaque>; HttpOnly; SameSite=Lax; Path=/api; Max-Age=604800"
IDEM = {"Idempotency-Key": "2f65cc3a-0120-4c42-a000-8e4633a22300"}

E = []  # (operation_id, case, description, default, request, response)


def ex(op, case, desc, request, status, body, headers=None, default=False):
    E.append({
        "operation_id": op, "case": case, "description": desc, "fixture": True, "default": default,
        "request": {"path_params": {}, "query": {}, "headers": {}, "body": None, **(request or {})},
        "response": {"status": status, "headers": headers or {}, "body": body},
    })


# --- system ---------------------------------------------------------------
ex("getConfig", "ok", "Конфигурация с активной ревизией", {}, 200, env(CONFIG), default=True)
ex("getConfig", "data_not_ready", "Корпус еще не импортирован", {}, 503,
   err("DATA_NOT_READY", "Данные еще не опубликованы. Попробуйте позже.", retryable=True, rev=None))

# --- workspace ------------------------------------------------------------
ex("createWorkspace", "created", "Новый гость: сценарий орбитальной станции по умолчанию (D-039)", {"body": {}}, 201,
   env(workspace(rev=1, selected=())), headers={"Set-Cookie": COOKIE, "ETag": '"1"'}, default=True)  # D-039
ex("createWorkspace", "existing_session", "Сессия уже действует - выбор не очищается", {"body": {}}, 200,
   env(workspace()), headers={"ETag": '"3"'})
ex("getCurrentWorkspace", "ok", "Текущее пространство", {}, 200, env(workspace()), headers={"ETag": '"3"'}, default=True)
ex("getCurrentWorkspace", "session_required", "Нет cookie сессии", {}, 401,
   err("SESSION_REQUIRED", "Сессия не найдена. Создайте новое гостевое пространство.", rev=None))
ex("patchCurrentWorkspace", "set_moon", "Смена сценария на лунную базу",
   {"headers": {"If-Match": '"3"'}, "body": {"scenario": MOON}}, 200,
   env(workspace(rev=4, scenario=MOON)), headers={"ETag": '"4"'}, default=True)
ex("patchCurrentWorkspace", "user_oxygen", "Пользователь задал долю кислорода 0.21",
   {"headers": {"If-Match": '"3"'}, "body": {"scenario": USER_O2}}, 200,
   env(workspace(rev=4, scenario=USER_O2)), headers={"ETag": '"4"'})
ex("patchCurrentWorkspace", "conflict", "Устаревшая revision (Б.5)",
   {"headers": {"If-Match": '"3"'}, "body": {"selected_investigation_ids": ["inv_psi25", "inv_psi69"]}}, 409,
   err("WORKSPACE_CONFLICT", "Контекст изменился. Обновите его перед повтором.",
       details=[{"field": "workspace_revision", "reason": "stale_revision", "current_revision": 4}]))
ex("patchCurrentWorkspace", "fourth_selected", "Четвертое исследование в сравнении (AT-10)",
   {"headers": {"If-Match": '"3"'}, "body": {"selected_investigation_ids": ["inv_psi25", "inv_psi69", "inv_psi101", "inv_psi4"]}}, 422,
   err("VALIDATION_ERROR", "В сравнении может быть не больше трех исследований. Текущий набор сохранен.",
       details=[{"field": "selected_investigation_ids", "reason": "items_count_out_of_range", "current_revision": None}]))

# --- search ---------------------------------------------------------------
SEARCH_REQ = {
    "query": "влияние вентиляции на твердые материалы", "locale": "ru", "data_revision": REV,
    "filters": {"scopes": ["prevention"], "investigation_ids": [], "material_ids": [], "fuel_states": ["solid"],
                "gravity_regimes": ["microgravity"], "oxygen_range": {"min": 0.18, "max": 0.23, "unit": "fraction"},
                "pressure_range": None, "airflow_range": None, "has_measurements": None, "include_unknown": True},
    "scenario": None, "include_related": False, "cursor": None, "limit": 20,
}
ex("search", "oxygen_021", "Вентиляция и твердые материалы, кислород 0.18-0.23 (Б.2, include_unknown=true)",
   {"body": SEARCH_REQ}, 200, env({
       "items": [{
           "investigation": INVESTIGATIONS["inv_psi25"], "relevance_category": "direct",
           "match_reasons": [reason("fuel_state", "Твердые образцы", "fuel_states"),
                             reason("scope", "Направление: предотвращение", "scopes"),
                             reason("query_terms", "[FIXTURE] Совпадение по теме потока воздуха", None, ["ev_psi25_fixture01"])],
           "differences": [],
           "missing_fields": ["conditions.oxygen_fraction"],
           "matching_run_ids": ["run_psi25_fixture01"], "related": False, "evidence_ids": ["ev_psi25_fixture01"],
       }],
       "next_cursor": None, "total": 1, "retrieval_mode": "lexical", "applied_filters": SEARCH_REQ["filters"],
   }), default=True)
EMPTY_REQ = copy.deepcopy(SEARCH_REQ)
EMPTY_REQ["filters"]["include_unknown"] = False
EMPTY_REQ["filters"]["pressure_range"] = {"min": 30000, "max": 40000, "unit": "Pa"}
ex("search", "hard_range_empty", "Жесткий диапазон без совпадений (AT-04): 200 и пустые items",
   {"body": EMPTY_REQ}, 200, env({"items": [], "next_cursor": None, "total": 0, "retrieval_mode": "lexical",
                                  "applied_filters": EMPTY_REQ["filters"]}))
SEM_REQ = {"query": "дым и чувствительность датчиков", "locale": "ru", "data_revision": REV}
ex("search", "semantic_unavailable", "Семантический слой недоступен - lexical с предупреждением (FR-05)",
   {"body": SEM_REQ}, 200, {
       "data": {"items": [{
           "investigation": INVESTIGATIONS["inv_psi101"], "relevance_category": "direct",
           "match_reasons": [reason("scope", "Направление: обнаружение", "scopes")], "differences": [],
           "missing_fields": [], "matching_run_ids": [], "related": False, "evidence_ids": ["ev_psi101_fixture01"]}],
           "next_cursor": None, "total": 1, "retrieval_mode": "lexical", "applied_filters": EMPTY_FILTERS},
       "meta": meta(warnings=[{"code": "SEMANTIC_SEARCH_UNAVAILABLE", "message": "Семантический поиск недоступен; используется поиск по тексту и фильтрам.", "field": None}]),
   })
ex("search", "unexpected_field", "Неожиданное поле запроса -> 422",
   {"body": {"query": "x", "locale": "ru", "data_revision": REV, "sortBy": "date"}}, 422,
   err("VALIDATION_ERROR", "Запрос содержит недопустимые поля.",
       details=[{"field": "sortBy", "reason": "unexpected_field", "current_revision": None}]))

# --- catalog --------------------------------------------------------------
ex("getInvestigation", "flex", "Карточка FLEX", {"path_params": {"id": "inv_psi69"}, "query": {"data_revision": REV}}, 200,
   env({"investigation": INVESTIGATIONS["inv_psi69"], "claims": [CLAIMS["clm_psi69_30cal03_burn"]],
        "sources": [SOURCES["src_psi69_exptable"]], "run_summary": {"total": 5, "verified_count": 5, "excluded_count": 0}}), default=True)
ex("getInvestigation", "bass_with_hypothesis", "BASS-II: наблюдение и отдельно гипотеза",
   {"path_params": {"id": "inv_psi25"}, "query": {"data_revision": REV}}, 200,
   env({"investigation": INVESTIGATIONS["inv_psi25"],
        "claims": [CLAIMS["clm_psi25_fixture_obs"], CLAIMS["clm_psi25_fixture_hyp"]],
        "sources": [SOURCES["src_psi25_dataset"], SOURCES["src_ntrs_20160000593"]],
        "run_summary": {"total": 1, "verified_count": 1, "excluded_count": 0}}))
ex("getInvestigation", "not_found", "Нет такого исследования", {"path_params": {"id": "inv_psi999"}, "query": {"data_revision": REV}}, 404,
   err("NOT_FOUND", "Исследование не найдено."))
ex("getInvestigation", "revision_gone", "Ревизия удалена", {"path_params": {"id": "inv_psi69"}, "query": {"data_revision": "psi-20261012-r1"}}, 410,
   err("DATA_REVISION_GONE", "Эта версия данных больше недоступна. Откройте актуальную версию.",
       details=[{"field": "data_revision", "reason": "gone", "current_revision": REV}]))
ex("listInvestigationRuns", "flex", "Опыты FLEX", {"path_params": {"id": "inv_psi69"}, "query": {"data_revision": REV, "limit": 20}}, 200,
   env({"items": [RUNS[f"run_psi69_{r[0].lower()}"] for r in FLEX_ROWS], "next_cursor": None, "total": 5}), default=True)
ex("listInvestigationRuns", "invalid_cursor", "Недействительный курсор",
   {"path_params": {"id": "inv_psi69"}, "query": {"data_revision": REV, "cursor": "garbage"}}, 422,
   err("INVALID_CURSOR", "Список изменился. Загрузите его заново.",
       details=[{"field": "cursor", "reason": "invalid", "current_revision": None}]))
ex("getRun", "flex_30cal03", "Контрольная запись FLEX 30CAL03 (приложение А)",
   {"path_params": {"id": "run_psi69_30cal03"}, "query": {"data_revision": REV}}, 200, env(RUNS["run_psi69_30cal03"]), default=True)
ex("getRun", "missing_pressure", "Неизвестное давление: null и причина (AT-05)",
   {"path_params": {"id": "run_psi25_fixture01"}, "query": {"data_revision": REV}}, 200, env(RUNS["run_psi25_fixture01"]))
ex("queryMeasurements", "flex_5_points", "График FLEX: пять контрольных точек (AT-07)",
   {"body": {"investigation_id": "inv_psi69", "data_revision": REV, "run_ids": [], "x_metric": "sample.initial_diameter",
             "y_metric": "metrics.burn_duration", "cursor": None, "limit": 200}}, 200,
   env({**AXES, "points": FLEX_POINTS, "excluded_count": 0, "exclusions_by_reason": NO_EXCL, "truncated": False, "next_cursor": None}),
   default=True)
ex("queryMeasurements", "no_points", "Нет измерений: все записи исключены с причинами",
   {"body": {"investigation_id": "inv_psi25", "data_revision": REV, "x_metric": "sample.initial_diameter", "y_metric": "metrics.burn_duration"}},
   200, env({"x_axis": AXES["x_axis"], "y_axis": AXES["y_axis"], "points": [], "excluded_count": 1,
             "exclusions_by_reason": {**NO_EXCL, "missing_x": 1}, "truncated": False, "next_cursor": None}))
ex("queryMeasurements", "unsupported_axes", "Неподдерживаемая пара осей",
   {"body": {"investigation_id": "inv_psi69", "data_revision": REV, "x_metric": "conditions.pressure", "y_metric": "metrics.flame_spread_rate"}},
   422, err("VALIDATION_ERROR", "Эта пара показателей не поддерживается.",
            details=[{"field": "y_metric", "reason": "unsupported_axis", "current_revision": None}]))

COMP_ROWS = [
    {"field": "object", "label": "Основной объект", "cells": [
        {"investigation_id": "inv_psi25", "value_text": "Твердые образцы", "status": "known", "evidence_ids": ["ev_psi25_fixture01"]},
        {"investigation_id": "inv_psi69", "value_text": "Капли жидкого топлива (метанол)", "status": "known", "evidence_ids": ["ev_psi69_30cal03"]}]},
    {"field": "conditions.pressure", "label": "Давление", "cells": [
        {"investigation_id": "inv_psi25", "value_text": None, "status": "not_reported", "evidence_ids": ["ev_psi25_fixture02"]},
        {"investigation_id": "inv_psi69", "value_text": "около 101 кПа (757.7-764.2 мм рт. ст.)", "status": "known",
         "evidence_ids": [f"ev_psi69_{r[0].lower()}" for r in FLEX_ROWS]}]},
    {"field": "sample.initial_diameter", "label": "Начальный диаметр капли", "cells": [
        {"investigation_id": "inv_psi25", "value_text": None, "status": "not_applicable", "evidence_ids": []},
        {"investigation_id": "inv_psi69", "value_text": "1.61-2.06 мм", "status": "known",
         "evidence_ids": [f"ev_psi69_{r[0].lower()}" for r in FLEX_ROWS]}]},
]
ex("compareInvestigations", "different_methods", "Два исследования с разными методиками (AT-09)",
   {"body": {"investigation_ids": ["inv_psi25", "inv_psi69"], "data_revision": REV, "scenario": None}}, 200,
   env({"investigations": [INVESTIGATIONS["inv_psi25"], INVESTIGATIONS["inv_psi69"]], "rows": COMP_ROWS,
        "comparability": {"status": "partially_compatible", "reasons": [
            reason("different_object", "Разные объекты: твердые образцы и капли жидкого топлива"),
            reason("different_metrics", "Разные измеряемые показатели; общий численный вывод не строится")]},
        "applicability": None,
        "limitations": ["Сравниваются задачи и условия; численные результаты не объединяются (DR-06).",
                        "Отсутствие поля не трактуется как совпадение."]}), default=True)
ex("compareInvestigations", "too_many", "Четыре исследования -> 422",
   {"body": {"investigation_ids": ["inv_psi25", "inv_psi69", "inv_psi101", "inv_psi4"], "data_revision": REV}}, 422,
   err("VALIDATION_ERROR", "Сравнить можно от двух до трех исследований.",
       details=[{"field": "investigation_ids", "reason": "items_count_out_of_range", "current_revision": None}]))
ex("assessApplicability", "moon_no_direct", "Лунная база без прямых данных (AT-12)",
   {"body": {"scenario": MOON, "investigation_ids": ["inv_psi25"], "data_revision": REV}}, 200, env(APPLICABILITY_MOON), default=True)
ex("listScenarioPresets", "ok", "Пресеты сред [предложение D-007]", {"query": {"data_revision": REV}}, 200,
   env({"items": [{"preset_id": "orbital_habitat", "label": "Орбитальная станция", "scenario": ORBITAL},
                  {"preset_id": "moon_base", "label": "Лунная база", "scenario": MOON}]}), default=True)
ex("getEvidence", "flex_30cal03", "Доказательство строки 30CAL03",
   {"path_params": {"id": "ev_psi69_30cal03"}, "query": {"data_revision": REV}}, 200,
   env({"evidence": EVIDENCE["ev_psi69_30cal03"], "source": SOURCES["src_psi69_exptable"]}), default=True)
ex("getSource", "available", "Источник с локальным файлом", {"path_params": {"id": "src_psi69_exptable"}, "query": {"data_revision": REV}},
   200, env(SOURCES["src_psi69_exptable"]), default=True)
ex("getSource", "unavailable_file", "Файл недоступен, метаданные доступны (AT-26)",
   {"path_params": {"id": "src_psi101_dataset"}, "query": {"data_revision": REV}}, 200, env(SOURCES["src_psi101_dataset"]))

# --- analysis -------------------------------------------------------------
AREQ = {"question": "Как поток воздуха влияет на горение?", "locale": "ru", "workspace_revision": 3, "data_revision": REV,
        "selected_investigation_ids": ["inv_psi25"], "mode": "evidence_answer"}
ex("createAnalysis", "accepted", "Задача принята (Б.3)", {"headers": IDEM, "body": AREQ}, 202, env(job()), default=True)
ex("createAnalysis", "workspace_conflict", "workspace_revision устарела", {"headers": IDEM, "body": AREQ}, 409,
   err("WORKSPACE_CONFLICT", "Контекст изменился. Обновите его перед повтором.",
       details=[{"field": "workspace_revision", "reason": "stale_revision", "current_revision": 4}]))
ex("createAnalysis", "idempotency_conflict", "Тот же ключ, другое тело", {"headers": IDEM, "body": {**AREQ, "question": "Другой вопрос"}}, 409,
   err("IDEMPOTENCY_CONFLICT", "Этот запрос уже отправлялся с другими данными. Запустите новый анализ.",
       details=[{"field": "Idempotency-Key", "reason": "body_mismatch", "current_revision": None}]))
ex("createAnalysis", "rate_limited", "Лимит запусков", {"headers": IDEM, "body": AREQ}, 429,
   err("RATE_LIMITED", "Слишком много запусков. Повторите через несколько секунд.", retryable=True),
   headers={"Retry-After": "12"})
ex("getJob", "running", "Выполняется: этап reasoning", {"path_params": {"id": "job_demo01"}}, 200,
   env(job(state="running", stage="reasoning")), default=True)
ex("getJob", "succeeded", "Готово", {"path_params": {"id": "job_demo01"}}, 200,
   env(job(state="succeeded", result_id="ans_demo01")))
ex("getJob", "provider_failed", "Отказ провайдера модели (AT-14): failed + найденные материалы", {"path_params": {"id": "job_demo01"}}, 200,
   env(job(state="failed", error={"code": "MODEL_PROVIDER_ERROR", "message": "Сервис генерации ответа недоступен. Найденные материалы доступны для просмотра.",
                                   "details": [], "retryable": True},
           fallback=["ev_psi25_fixture01", "ev_psi25_fixture02"])))
ex("getJob", "validation_failed", "Ответ не прошел проверку", {"path_params": {"id": "job_demo01"}}, 200,
   env(job(state="failed", error={"code": "VALIDATION_FAILED", "message": "Ответ не прошел проверку источников. Откройте найденные материалы.",
                                   "details": [], "retryable": True}, fallback=["ev_psi25_fixture01"])))
ex("getJob", "cancelled", "Отменено пользователем (AT-17)", {"path_params": {"id": "job_demo01"}}, 200, env(job(state="cancelled", stage="reasoning")))
ex("getJob", "expired", "Истек дедлайн", {"path_params": {"id": "job_demo01"}}, 200,
   env(job(state="expired", stage="reasoning", error={"code": "JOB_TIMEOUT", "message": "Ответ не получен за отведенное время.",
                                                      "details": [], "retryable": True})))
ex("cancelJob", "cancelled", "Отмена принята", {"path_params": {"id": "job_demo01"}}, 204, None, default=True)
ex("cancelJob", "already_finished", "Задача уже завершена", {"path_params": {"id": "job_demo01"}}, 409,
   err("JOB_ALREADY_FINISHED", "Задача уже завершена.", details=[{"field": "state", "reason": "succeeded", "current_revision": None}]))

ANS_OK = answer("ans_demo01", "answered",
                [{"id": "block_summary", "kind": "summary", "text": "В контрольной записи FLEX 30CAL03 капля метанола горела 6,34 с до погасания.",
                  "evidence_ids": ["ev_psi69_30cal03"], "quantities": [BLOCK_30CAL03["quantities"][0]]},
                 BLOCK_30CAL03,
                 {"id": "block_limit", "kind": "limitation", "text": "Одна запись не устанавливает зависимость времени горения от диаметра капли.",
                  "evidence_ids": [], "quantities": []}],
                [citation("ev_psi69_30cal03", "FLEX PSI-69, Experimental Table v5, строка 30CAL03")],
                ["Результат относится к условиям опыта: метанол, доля кислорода 0.21, микрогравитация."],
                ["Сравнить с другими записями серии 30CAL?"], None,
                "Сколько горела капля в опыте 30CAL03?")
ex("getAnswer", "answered", "Успешный ответ со ссылками (AT-11)", {"path_params": {"id": "ans_demo01"}}, 200, env(ANS_OK), default=True)
ANS_INSUF = answer("ans_demo02", "insufficient_evidence",
                   [{"id": "block_limit1", "kind": "limitation",
                     "text": "В корпусе нет опытов частичной гравитации, поэтому прямого ответа для лунной базы нет. Доступны связанные микрогравитационные исследования.",
                     "evidence_ids": ["ev_track_partial_gravity"], "quantities": []}],
                   [citation("ev_track_partial_gravity", "Flame in Freefall - условия трека")],
                   ["Отсутствие данных не означает безопасность."],
                   ["Какой материал рассматривается?", "Какие давление и доля кислорода на базе?"],
                   APPLICABILITY_MOON, "Как будет гореть материал на лунной базе?", scenario=MOON)
ex("getAnswer", "insufficient_evidence", "Недостаток доказательств (AT-13, AT-12)", {"path_params": {"id": "ans_demo02"}}, 200, env(ANS_INSUF))
ANS_CONF = answer("ans_demo03", "conflicting_evidence",
                  [{"id": "block_c1", "kind": "observation", "text": "[FIXTURE] Первое основание сообщает один исход.",
                    "evidence_ids": ["ev_psi25_fixture01"], "quantities": []},
                   {"id": "block_c2", "kind": "observation", "text": "[FIXTURE] Второе основание при других условиях сообщает другой исход.",
                    "evidence_ids": ["ev_psi25_fixture02"], "quantities": []},
                   {"id": "block_c3", "kind": "limitation", "text": "[FIXTURE] Условия опытов различаются; общий вывод не делается.",
                    "evidence_ids": [], "quantities": []}],
                  [citation("ev_psi25_fixture01", "[FIXTURE] Отчет BASS-II"), citation("ev_psi25_fixture02", "[FIXTURE] Таблица BASS-II")],
                  ["[FIXTURE] Основания противоречат друг другу."], [], None, "[FIXTURE] Вопрос с расходящимися основаниями")
ex("getAnswer", "conflicting_evidence", "Противоречие оснований [FIXTURE]", {"path_params": {"id": "ans_demo03"}}, 200, env(ANS_CONF))
ex("getAnswer", "access_denied", "Чужой ответ (AT-19)", {"path_params": {"id": "ans_other"}}, 403,
   err("ACCESS_DENIED", "Этот ответ принадлежит другой сессии."))

# --- reports --------------------------------------------------------------
RREQ = {"workspace_revision": 4, "title": "Вентиляция и горение материалов", "answer_ids": ["ans_demo01"],
        "investigation_ids": ["inv_psi25", "inv_psi69"], "include_comparison": True, "locale": "ru"}
ex("createReport", "accepted", "Экспорт принят", {"headers": IDEM, "body": RREQ}, 202,
   env(job(type_="report", rev=4, scenario_id="moon_base")), default=True)
ex("createReport", "foreign_answer", "Ответ из другой ревизии/пространства", {"headers": IDEM, "body": {**RREQ, "answer_ids": ["ans_other"]}}, 422,
   err("VALIDATION_ERROR", "Ответ не принадлежит текущему пространству.",
       details=[{"field": "answer_ids[0]", "reason": "not_in_workspace", "current_revision": None}]))
ex("getReport", "ready", "Отчет готов", {"path_params": {"id": "rpt_demo01"}}, 200,
   env(report("ready", download_path="/api/v1/reports/rpt_demo01/download", sha256="a" * 64)), default=True)
ex("getReport", "preparing", "Отчет готовится", {"path_params": {"id": "rpt_demo01"}}, 200, env(report("preparing")))
ex("getReport", "expired", "Отчет истек (метаданные доступны)", {"path_params": {"id": "rpt_demo01"}}, 200,
   env(report("expired", created_at="2026-11-15T00:00:00Z", expires_at="2026-11-16T00:00:00Z")))
ex("downloadReport", "expired", "Скачивание истекшего отчета (AT-22)", {"path_params": {"id": "rpt_demo01"}}, 410,
   err("RESOURCE_EXPIRED", "Срок хранения отчета истек. Создайте отчет заново."), default=True)
ex("downloadReport", "preparing", "Отчет еще готовится", {"path_params": {"id": "rpt_demo01"}}, 409,
   err("REPORT_NOT_READY", "Отчет еще готовится.", retryable=True))


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    index = []
    for e in E:
        d = OUT / e["operation_id"]
        d.mkdir(exist_ok=True)
        p = d / f"{e['case']}.json"
        p.write_text(json.dumps(e, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        index.append({"operation_id": e["operation_id"], "case": e["case"], "status": e["response"]["status"],
                      "default": e["default"], "fixture": True, "file": str(p.relative_to(OUT)), "description": e["description"]})
    (OUT / "index.json").write_text(json.dumps({"fixture": True, "data_revision": REV, "examples": index},
                                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Фикстурные сущности - для тестов бэкенда и мок-сервера
    fx = {"data_revision": REV, "sources": SOURCES, "evidence": EVIDENCE, "runs": RUNS, "materials": MATERIALS,
          "claims": CLAIMS, "investigations": INVESTIGATIONS, "scenarios": {"orbital": ORBITAL, "moon": MOON}}
    (ROOT / "fixtures_entities.json").write_text(json.dumps(fx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"written {len(E)} examples")


if __name__ == "__main__":
    main()
