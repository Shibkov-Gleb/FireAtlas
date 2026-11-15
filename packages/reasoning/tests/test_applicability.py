"""Тесты A2-04: детерминированная применимость (ТЗ 22.3).

Запуск из корня репозитория:
    PYTHONPATH=packages/reasoning:packages/contracts python -m pytest -q packages/reasoning/tests
"""
from __future__ import annotations

import copy
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "reasoning"))
sys.path.insert(0, str(ROOT / "packages" / "contracts"))

import fa_contracts as c  # noqa: E402
from fa_reasoning.applicability import RULES_VERSION, assess_applicability  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "data_release_fixture"
REV = "test-rev-1"


# --- построители тестовых объектов ---------------------------------------------------------------
def q(value=None, unit="fraction", status=None, raw=None, raw_unit=None, ev=("ev_x",), qualifier="eq", unc=None):
    if status is None:
        status = "reported" if value is not None else "not_reported"
    known = status in ("measured", "reported", "derived")
    return {"value": value if known else None, "unit": unit, "status": status,
            "qualifier": qualifier if known else None, "raw_value": raw, "raw_unit": raw_unit,
            "uncertainty": unc if known else None, "evidence_ids": list(ev), "derivation": None}


def run(rid, inv="inv_a", material="mat_pmma", geometry="film", gravity="microgravity", o2=None, p=None, flow=None,
        outcome="unknown", metrics=()):
    ev = [f"ev_{rid}"]
    return {
        "id": rid, "data_revision": REV, "investigation_id": inv, "source_test_id": rid, "material_id": material,
        "sample": {"geometry": geometry, "thickness": q(unit="m", ev=ev), "initial_diameter": q(unit="m", ev=ev)},
        "conditions": {
            "gravity_regime": gravity, "gravity_level": q(unit="g_fraction", ev=ev),
            "oxygen_fraction": o2 if o2 is not None else q(unit="fraction", ev=ev),
            "nitrogen_fraction": q(unit="fraction", ev=ev), "co2_fraction": q(unit="fraction", ev=ev),
            "helium_fraction": q(unit="fraction", ev=ev),
            "pressure": p if p is not None else q(unit="Pa", ev=ev),
            "airflow_speed": flow if flow is not None else q(unit="m_s", ev=ev),
            "flow_configuration": "unknown", "ambient_temperature": q(unit="K", ev=ev),
        },
        "metrics": list(metrics),
        "terminal_outcome": {"category": outcome, "raw_label": None, "interpretation_status": "unmapped",
                             "evidence_ids": ev},
        "regime_tags": [], "evidence_ids": ev, "quality_notes": [],
    }


def inv(iid="inv_a", scopes=("prevention",), coverage=()):
    return {"id": iid, "data_revision": REV, "psi_id": "PSI-1", "acronym": iid, "title": iid, "objectives": [],
            "setup_summary": "", "scopes": list(scopes), "fuel_states": ["solid"], "gravity_regimes": ["microgravity"],
            "material_ids": [], "source_ids": [], "claim_ids": [], "conditions_coverage": list(coverage),
            "available_assets": []}


def evidence_for(runs):
    ids = sorted({e for r in runs for e in r["evidence_ids"]} | {"ev_x"})
    return [{"id": i, "data_revision": REV} for i in ids]


def scenario(task="prevention", gravity="microgravity", materials=(), geometry=None, o2=None, p=None, flow=None):
    return {"scenario_id": "sc_test", "name": "Тест", "environment": "orbital_habitat", "celestial_body": None,
            "safety_task": task, "material_ids": list(materials), "geometry": geometry,
            "oxygen_fraction": o2, "pressure": p, "airflow_speed": flow, "gravity_regime": gravity, "assumptions": []}


def user_q(value, unit, qualifier="eq", unc=None):
    """Значение, введенное пользователем (D-006): reported, без доказательств."""
    return q(value, unit=unit, raw=None, ev=(), qualifier=qualifier, unc=unc)


def factor(res, field):
    return next(f for f in res["factors"] if f["field"] == field)


def check_contract(res, evidence):
    assert not c.errors_for("ApplicabilityResult", res), c.errors_for("ApplicabilityResult", res)
    allowed = {e["id"] for e in evidence}
    for f in res["factors"]:
        assert set(f["evidence_ids"]) <= allowed, f
    assert len({f["field"] for f in res["factors"]}) == len(res["factors"])  # FE использует field как ключ строки
    assert res["basis"]["reviewed_rules_version"] == RULES_VERSION


# Опыт, где все условия известны: PMMA, пленка, 21 % O2, 101.3 кПа, 10 см/с
def full_run(rid="r1", **kw):
    args = dict(o2=q(0.21, "fraction", raw="21", raw_unit="%", ev=[f"ev_{rid}"]),
                p=q(101325.0, "Pa", raw="760", raw_unit="mmHg", ev=[f"ev_{rid}"]),
                flow=q(0.10, "m_s", raw="10", raw_unit="cm/s", ev=[f"ev_{rid}"]))
    args.update(kw)
    return run(rid, **args)


def full_scenario(**kw):
    args = dict(materials=["mat_pmma"], geometry="film", o2=user_q(0.21, "fraction"), p=user_q(101325.0, "Pa"),
                flow=user_q(0.10, "m_s"))
    args.update(kw)
    return scenario(**args)


# --- тесты -------------------------------------------------------------------------------------------
def test_direct_evidence_only_with_joint_run():
    runs = [full_run("r1")]
    ev = evidence_for(runs)
    res = assess_applicability(full_scenario(), [inv()], runs, ev)
    check_contract(res, ev)
    assert res["overall"] == "direct_evidence"
    assert factor(res, "joint_conditions")["status"] == "match"
    assert "ev_r1" in factor(res, "joint_conditions")["evidence_ids"]


def test_conditions_met_separately_are_not_direct():
    """Каждое условие встречается, но в разных опытах -> нет совместной записи -> не direct."""
    r_o2 = full_run("r1", p=q(50000.0, "Pa", raw="375", raw_unit="mmHg", ev=["ev_r1"]))
    r_p = full_run("r2", o2=q(0.30, "fraction", raw="30", raw_unit="%", ev=["ev_r2"]))
    runs = [r_o2, r_p]
    ev = evidence_for(runs)
    res = assess_applicability(full_scenario(), [inv()], runs, ev)
    check_contract(res, ev)
    assert factor(res, "oxygen_fraction")["status"] == "match"
    assert factor(res, "pressure")["status"] == "match"
    assert factor(res, "joint_conditions")["status"] == "mismatch"
    assert res["overall"] == "related_evidence"


def test_moon_partial_gravity_never_direct():
    runs = [full_run("r1")]
    ev = evidence_for(runs)
    res = assess_applicability(full_scenario(gravity="partial"), [inv()], runs, ev)
    check_contract(res, ev)
    g = factor(res, "gravity_regime")
    assert g["status"] == "not_covered" and "частичная" in g["explanation"]
    assert any(gp["field"] == "gravity_regime" for gp in res["gaps"])
    assert res["overall"] == "related_evidence"


def test_simulated_partial_does_not_replace_partial():
    runs = [full_run("r1", gravity="simulated_partial")]
    ev = evidence_for(runs)
    res = assess_applicability(full_scenario(gravity="partial"), [inv()], runs, ev)
    check_contract(res, ev)
    g = factor(res, "gravity_regime")
    assert g["status"] == "not_covered" and "не подменяют" in g["explanation"]
    assert res["overall"] != "direct_evidence"


def test_earth_scenario_with_microgravity_data_is_mismatch():
    runs = [full_run("r1")]
    res = assess_applicability(full_scenario(gravity="normal"), [inv()], runs, evidence_for(runs))
    assert factor(res, "gravity_regime")["status"] == "mismatch"
    assert res["overall"] == "related_evidence"


def test_oxygen_outside_observed_shows_difference_explicitly():
    """Лунная база ~30 % O2 при опытах только на 21 %: различие видно, порог не подбирается."""
    runs = [full_run("r1"), full_run("r2", o2=q(0.16, "fraction", raw="16", raw_unit="%", ev=["ev_r2"]))]
    ev = evidence_for(runs)
    res = assess_applicability(full_scenario(o2=user_q(0.30, "fraction")), [inv()], runs, ev)
    check_contract(res, ev)
    f = factor(res, "oxygen_fraction")
    assert f["status"] == "mismatch"
    assert "16 %" in f["explanation"] and "21 %" in f["explanation"]  # диапазон и ближайшее значение
    assert f["evidence_ids"] == ["ev_r1"]  # ближайший опыт
    assert res["overall"] == "related_evidence"


@pytest.mark.parametrize("raw,target,expected", [
    ("21", 0.212, "match"),     # точность записи "21" % = 0.5 % -> 0.212 совпадает
    ("21", 0.216, "mismatch"),
    ("22.2", 0.222, "match"),
    ("22.2", 0.221, "mismatch"),  # точность "22.2" % = 0.05 %
])
def test_tolerance_comes_from_source_precision(raw, target, expected):
    runs = [full_run("r1", o2=q(float(raw) / 100, "fraction", raw=raw, raw_unit="%", ev=["ev_r1"]))]
    res = assess_applicability(full_scenario(o2=user_q(target, "fraction")), [inv()], runs, evidence_for(runs))
    assert factor(res, "oxygen_fraction")["status"] == expected


def test_uncertainty_widens_match():
    runs = [full_run("r1", o2=q(0.21, "fraction", raw="21", raw_unit="%", ev=["ev_r1"], unc=0.01))]
    res = assess_applicability(full_scenario(o2=user_q(0.219, "fraction")), [inv()], runs, evidence_for(runs))
    assert factor(res, "oxygen_fraction")["status"] == "match"


def test_scenario_upper_bound_on_pressure():
    """Сценарий «давление не выше 70 кПа» (qualifier=lte)."""
    runs = [full_run("r1", p=q(68947.6, "Pa", raw="10", raw_unit="psi", ev=["ev_r1"]))]
    res = assess_applicability(full_scenario(p=user_q(70000.0, "Pa", qualifier="lte")), [inv()], runs, evidence_for(runs))
    f = factor(res, "pressure")
    assert f["status"] == "match" and "≤" in f["explanation"]


def test_bound_in_source_is_not_a_value():
    runs = [full_run("r1", flow=q(0.05, "m_s", raw="5", raw_unit="cm/s", ev=["ev_r1"], qualifier="lt"))]
    res = assess_applicability(full_scenario(flow=user_q(0.05, "m_s")), [inv()], runs, evidence_for(runs))
    assert factor(res, "airflow_speed")["status"] == "unknown"
    assert res["overall"] != "direct_evidence"


def test_missing_critical_condition_blocks_direct():
    runs = [full_run("r1")]
    res = assess_applicability(full_scenario(p=None), [inv()], runs, evidence_for(runs))
    assert factor(res, "pressure")["status"] == "unknown"
    assert any(g["field"] == "pressure" for g in res["gaps"])
    assert res["overall"] == "related_evidence"


def test_not_reported_in_source_is_unknown_not_safe():
    runs = [full_run("r1", p=q(None, "Pa", ev=["ev_r1"]))]
    ev = evidence_for(runs)
    cov = [{"field": "conditions.pressure", "min_value": None, "max_value": None, "unit": "Pa", "known_count": 0,
            "unknown_count": 1, "derivation_evidence_ids": ["ev_r1"]}]
    res = assess_applicability(full_scenario(), [inv(coverage=cov)], runs, ev)
    check_contract(res, ev)
    f = factor(res, "pressure")
    assert f["status"] == "unknown" and "не сообщается" in f["explanation"]
    assert res["overall"] != "direct_evidence"


def test_material_matched_by_id_and_composition_not_claimed():
    runs = [full_run("r1", material="mat_pmma_black")]
    res = assess_applicability(full_scenario(materials=["mat_pmma"]), [inv()], runs, evidence_for(runs))
    assert factor(res, "material_ids")["status"] == "mismatch"  # похожее название не считается совпадением
    res = assess_applicability(full_scenario(materials=["mat_pmma_black"]), [inv()], runs, evidence_for(runs))
    f = factor(res, "material_ids")
    assert f["status"] == "match" and "состава не заявляется" in f["explanation"]


def test_task_mismatch_is_insufficient():
    runs = [full_run("r1")]
    res = assess_applicability(full_scenario(task="suppression"), [inv(scopes=("prevention",))], runs, evidence_for(runs))
    assert factor(res, "safety_task")["status"] == "mismatch"
    assert res["overall"] == "insufficient_evidence"


def test_detection_requires_smoke_measurements():
    flame = [full_run("r1")]
    res = assess_applicability(scenario(task="detection"), [inv(scopes=("detection",))], flame, evidence_for(flame))
    assert factor(res, "smoke_measurement")["status"] == "mismatch"
    assert res["overall"] == "insufficient_evidence"
    smoke = [full_run("r2", outcome="smoke_measurement")]
    res = assess_applicability(scenario(task="detection"), [inv(scopes=("detection",))], smoke, evidence_for(smoke))
    assert factor(res, "smoke_measurement")["status"] == "match"


def test_evidence_limited_to_allowed_ids():
    runs = [full_run("r1"), full_run("r2")]
    ev = [{"id": "ev_r2", "data_revision": REV}]  # ev_r1 не входит в bundle
    res = assess_applicability(full_scenario(), [inv()], runs, ev)
    check_contract(res, ev)
    assert res["overall"] == "direct_evidence"
    assert all("ev_r1" not in f["evidence_ids"] for f in res["factors"])


def test_no_citable_joint_run_is_not_direct():
    runs = [full_run("r1")]
    res = assess_applicability(full_scenario(), [inv()], runs, [])
    assert res["overall"] != "direct_evidence"


def test_empty_input_is_insufficient():
    res = assess_applicability(full_scenario(), [], [], [], data_revision=REV)
    check_contract(res, [])
    assert res["overall"] == "insufficient_evidence"
    assert res["basis"]["data_revision"] == REV


def test_deterministic_and_order_independent():
    runs = [full_run(f"r{i}", o2=q(0.15 + i / 100, "fraction", raw=str(15 + i), raw_unit="%", ev=[f"ev_r{i}"]))
            for i in range(10)]
    ev = evidence_for(runs)
    sc = full_scenario(o2=user_q(0.40, "fraction"))
    first = assess_applicability(sc, [inv()], runs, ev)
    shuffled = copy.deepcopy(runs)
    random.Random(1).shuffle(shuffled)
    assert assess_applicability(sc, [inv()], shuffled, list(reversed(ev))) == first
    assert json.dumps(first, ensure_ascii=False)  # сериализуется


def test_input_not_mutated():
    runs = [full_run("r1")]
    sc = full_scenario()
    before = copy.deepcopy((sc, runs))
    assess_applicability(sc, [inv()], runs, evidence_for(runs))
    assert (sc, runs) == before


# --- фикстурный пакет бэкенда (реальные строки FLEX из приложения А) ------------------------------------
def _load(name):
    return [json.loads(line) for line in (FIXTURE / name).read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def corpus():
    return {"inv": {i["id"]: i for i in _load("investigations.jsonl")}, "runs": _load("runs.jsonl"),
            "ev": _load("evidence.jsonl")}


def test_flex_methanol_air_at_one_atmosphere_is_direct(corpus):
    flex = corpus["inv"]["inv_psi69"]
    runs = [r for r in corpus["runs"] if r["investigation_id"] == "inv_psi69"]
    sc = scenario(task="suppression", materials=["mat_methanol"], o2=user_q(0.21, "fraction"), p=user_q(101325.0, "Pa"))
    res = assess_applicability(sc, [flex], runs, corpus["ev"])
    check_contract(res, corpus["ev"])
    assert res["overall"] == "direct_evidence"
    assert res["basis"]["data_revision"] == flex["data_revision"]
    assert "ev_psi69_30cal03" in factor(res, "joint_conditions")["evidence_ids"]


def test_flex_for_lunar_atmosphere_is_related(corpus):
    flex = corpus["inv"]["inv_psi69"]
    runs = [r for r in corpus["runs"] if r["investigation_id"] == "inv_psi69"]
    sc = scenario(task="suppression", gravity="partial", materials=["mat_methanol"], o2=user_q(0.30, "fraction"),
                  p=user_q(70300.0, "Pa"))
    res = assess_applicability(sc, [flex], runs, corpus["ev"])
    check_contract(res, corpus["ev"])
    assert res["overall"] == "related_evidence"
    assert factor(res, "gravity_regime")["status"] == "not_covered"
    assert factor(res, "oxygen_fraction")["status"] == "mismatch"
