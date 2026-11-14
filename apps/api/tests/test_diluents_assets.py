"""D-036 (состав атмосферы), D-037 (пути conditions_coverage), D-038 (файлы источников).

Проверки выведены из интеграции с первым настоящим пакетом AI 1.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from conftest import FIX_REV, LiveServer, make_settings
from test_import import _copy, _rewrite
from fire_atlas_api.db import Database
from fire_atlas_api.importer import _sha256, import_release, stage_assets
from fire_atlas_api.validation import check_retrieval
from fire_atlas_api.providers import StubRetriever

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "contracts"))
import fa_contracts as c  # noqa: E402

R = f"data_revision={FIX_REV}"


@pytest.fixture
def db(tmp_path) -> Database:
    d = Database(tmp_path / "db.sqlite3")
    d.migrate()
    return d


def _codes(rep, kind="warnings"):
    return [x["code"] for x in rep[kind]]


# --- D-036 -----------------------------------------------------------------------
def test_flex_runs_expose_atmosphere_composition(server):
    run = server.client().get(f"/api/v1/runs/run_psi69_30cal03?{R}").data
    cond = run["conditions"]
    assert (cond["oxygen_fraction"]["value"], cond["nitrogen_fraction"]["value"], cond["co2_fraction"]["value"],
            cond["helium_fraction"]["value"]) == (0.21, 0.79, 0.0, 0.0)
    assert cond["co2_fraction"]["status"] == "reported" and cond["co2_fraction"]["evidence_ids"] == ["ev_psi69_30cal03"]
    other = server.client().get(f"/api/v1/runs/run_psi25_fixture01?{R}").data["conditions"]
    assert other["co2_fraction"]["status"] == "not_reported" and other["co2_fraction"]["value"] is None


def test_measurement_diluent_filters(server):
    cl = server.client()
    base = {"investigation_id": "inv_psi69", "data_revision": FIX_REV, "x_metric": "sample.initial_diameter",
            "y_metric": "metrics.burn_duration"}
    r = cl.post("/api/v1/measurements/query", {**base, "filters": {"co2_range": {"min": 0, "max": 0, "unit": "fraction"}}})
    assert r.status == 200 and len(r.data["points"]) == 5  # все пять опытов приложения А - в воздухе
    r = cl.post("/api/v1/measurements/query", {**base, "filters": {"co2_range": {"min": 0.1, "max": None, "unit": "fraction"}}})
    assert r.status == 200 and r.data["points"] == [] and r.data["exclusions_by_reason"]["filtered_out"] == 5
    r = cl.post("/api/v1/measurements/query", {**base, "filters": {"helium_range": {"min": 0.5, "max": 0.2, "unit": "fraction"}}})
    assert r.status == 422 and r.error["details"][0]["field"] == "filters.helium_range"
    r = cl.post("/api/v1/measurements/query", {**base, "filters": {"co2_range": {"min": 0, "max": 70, "unit": "fraction"}}})
    assert r.status == 422  # проценты вместо доли отклоняет схема


def test_legacy_package_without_diluent_fields_is_filled(db, release_dir, tmp_path):
    rel = _copy(release_dir, tmp_path)

    def strip(rows):
        for r in rows:
            for k in ("nitrogen_fraction", "co2_fraction", "helium_fraction"):
                r["conditions"].pop(k)
        return rows

    _rewrite(rel, "runs.jsonl", strip)
    rep = import_release(db, rel, "dev")
    assert rep["accepted"], rep["errors"]
    assert _codes(rep).count("LEGACY_CONDITIONS_FILLED") == 1  # одно предупреждение на файл, а не на запись
    run = db.get_entity(FIX_REV, "run", "run_psi69_30cal03")
    assert run["conditions"]["co2_fraction"]["status"] == "not_reported"
    assert not c.errors_for("TestRun", run)


def test_composition_sum_warning(db, release_dir, tmp_path):
    rel = _copy(release_dir, tmp_path)

    def bad(rows):
        for r in rows:
            if r["source_test_id"] == "30CAL03":
                r["conditions"]["co2_fraction"]["value"] = 0.5  # 0.21 + 0.79 + 0.5 = 1.5
        return rows

    _rewrite(rel, "runs.jsonl", bad)
    rep = import_release(db, rel, "dev")
    assert rep["accepted"]
    w = [x for x in rep["warnings"] if x["code"] == "COMPOSITION_SUM"]
    assert len(w) == 1 and w[0]["entity_id"] == "run_psi69_30cal03" and w[0]["file"] == "runs.jsonl"


# --- D-037 ------------------------------------------------------------------------
def test_coverage_field_must_be_a_path(db, release_dir, tmp_path):
    rel = _copy(release_dir, tmp_path)

    def bare(rows):
        for inv in rows:
            for cov in inv["conditions_coverage"]:
                cov["field"] = cov["field"].split(".", 1)[1]  # "oxygen_fraction" вместо "conditions.oxygen_fraction"
        return rows

    _rewrite(rel, "investigations.jsonl", bare)
    rep = import_release(db, rel, "dev")
    assert not rep["accepted"]
    errs = [e for e in rep["errors"] if e["code"] == "COVERAGE_FIELD_UNKNOWN"]
    assert errs and "'conditions.oxygen_fraction'" in " ".join(e["message"] for e in errs)
    assert db.active_revision() is None


# --- D-038 ------------------------------------------------------------------------
def _release_with_raw_source(release_dir: Path, tmp: Path) -> tuple[Path, Path, bytes]:
    """Источник FLEX без local_asset_id, но с sha256 - как в пакете AI 1; файл лежит в raw/ под своим именем."""
    rel = _copy(release_dir, tmp)
    raw = tmp / "raw" / "PSI-69"
    raw.mkdir(parents=True)
    data = b"Test ID,Burn time (s)\n30CAL03,6.34\n"
    (raw / "PSI-69_Experimental table_FLEX.csv").write_bytes(data)
    (raw / "unrelated.xlsx").write_bytes(b"PK-not-a-source")

    def unassign(rows):
        for s in rows:
            if s["id"] == "src_psi69_exptable":
                s["local_asset_id"], s["sha256"] = None, __import__("hashlib").sha256(data).hexdigest()
        return rows

    _rewrite(rel, "sources.jsonl", unassign)
    return rel, tmp / "raw", data


def test_stage_and_assign_assets(release_dir, tmp_path):
    rel, raw, data = _release_with_raw_source(release_dir, tmp_path)
    s = make_settings(tmp_path / "srv", assets_dir=tmp_path / "assets")
    out = stage_assets(rel, raw, s.assets_dir)
    assert [x["file"] for x in out["staged"]] == ["asset_psi69_exptable.csv"] and out["missing"] == []
    assert stage_assets(rel, raw, s.assets_dir)["staged"]  # повтор идемпотентен
    db = Database(s.db_path)
    db.migrate()
    rep = import_release(db, rel, "dev", assets_dir=s.assets_dir)
    assert rep["accepted"], rep["errors"]
    src = db.get_entity(FIX_REV, "source", "src_psi69_exptable")
    assert src["local_asset_id"] == "asset_psi69_exptable"
    with LiveServer(s) as srv:
        r = srv.client().get(f"/api/v1/sources/src_psi69_exptable/asset?{R}")
        assert r.status == 200 and r.raw == data and r.headers["Content-Type"].startswith("text/csv")


def test_missing_asset_file_leaves_source_without_file(db, release_dir, tmp_path):
    rel, raw, _ = _release_with_raw_source(release_dir, tmp_path)
    rep = import_release(db, rel, "dev", assets_dir=tmp_path / "empty_assets")
    assert rep["accepted"]
    assert "ASSET_NOT_STAGED" in _codes(rep)
    assert db.get_entity(FIX_REV, "source", "src_psi69_exptable")["local_asset_id"] is None


def test_tampered_asset_is_not_assigned(db, release_dir, tmp_path):
    rel, raw, _ = _release_with_raw_source(release_dir, tmp_path)
    assets = tmp_path / "assets"
    stage_assets(rel, raw, assets)
    (assets / "asset_psi69_exptable.csv").write_bytes(b"tampered")
    rep = import_release(db, rel, "dev", assets_dir=assets)
    assert rep["accepted"] and "ASSET_NOT_STAGED" in _codes(rep)
    assert db.get_entity(FIX_REV, "source", "src_psi69_exptable")["local_asset_id"] is None


def test_retrieval_source_metadata_may_lack_backend_asset_id(server):
    """Модуль AI 1 читает пакет (local_asset_id=null), а в реестре бэкенд уже назначил ID: это не нарушение."""
    rq = {"request_id": "req_meta1", "question": "погасание капли", "locale": "ru", "scenario": None,
          "filters": {"scopes": [], "investigation_ids": [], "material_ids": [], "fuel_states": [], "gravity_regimes": [],
                      "oxygen_range": None, "pressure_range": None, "airflow_range": None, "has_measurements": None,
                      "include_unknown": False},
          "selected_investigation_ids": ["inv_psi69"], "data_revision": FIX_REV, "top_k": 12,
          "deadline_at": "2099-01-01T00:00:00Z", "include_related": False}
    out = StubRetriever(server.db)(rq)
    item = next(i for i in out["evidence_bundle"]["items"] if i["source_metadata"]["id"] == "src_psi69_exptable")
    registered = copy.deepcopy(item["source_metadata"])
    assert registered["local_asset_id"]
    item["source_metadata"]["local_asset_id"] = None
    bundle = check_retrieval(out, rq, server.db)
    assert next(i for i in bundle["items"] if i["source_metadata"]["id"] == "src_psi69_exptable")["source_metadata"] == registered
    item2 = next(i for i in out["evidence_bundle"]["items"] if i["source_metadata"]["id"] == "src_psi69_exptable")
    item2["source_metadata"]["title"] = "чужое название"
    with pytest.raises(Exception):
        check_retrieval(out, rq, server.db)
