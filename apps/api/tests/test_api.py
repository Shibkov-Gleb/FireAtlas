"""Публичный API: envelope, ошибки, пространства, каталог, измерения.

Покрывает AT-04*, AT-05, AT-06, AT-07, AT-18, AT-19, AT-26 в части бэкенда.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import sys
from pathlib import Path

import pytest

from conftest import FIX_REV, ORIGIN

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "contracts"))
import fa_contracts as c  # noqa: E402

R = f"data_revision={FIX_REV}"
APPENDIX_A = {  # приложение А: test_id -> (диаметр мм, время с, исход)
    "20CAL08": (1.69, 4.3, "disruption"), "20CAL10": (1.86, 5.0, "extinction"), "20CAL12": (1.61, 3.2, "extinction"),
    "30CAL02": (2.06, 7.64, "extinction"), "30CAL03": (1.92, 6.34, "extinction"),
}


# --- система ---------------------------------------------------------------
def test_health_and_config(server):
    cl = server.client()
    assert cl.get("/health/live").status == 200
    ready = cl.get("/health/ready")
    assert ready.status == 200 and ready.json["checks"]["active_revision"] == FIX_REV
    r = cl.get("/api/v1/config")
    assert r.status == 200
    assert not c.errors_for("ConfigEnvelope", r.json)
    assert r.data["active_data_revision"] == FIX_REV
    assert r.data["feature_flags"] == {"analysis": True, "reports": True, "semantic_search": False, "video_preview": False}
    assert r.data["measurement_axes"] == [{"x_key": "sample.initial_diameter", "y_key": "metrics.burn_duration",
                                           "investigation_ids": ["inv_psi69"]}]
    assert r.headers["X-Request-Id"] == r.json["meta"]["request_id"]


def test_not_ready_without_corpus(empty_server):
    cl = empty_server.client()
    assert cl.get("/health/ready").status == 503
    r = cl.post("/api/v1/workspaces", {})
    assert r.status == 503 and r.error["code"] == "DATA_NOT_READY" and r.error["retryable"] is True
    r = cl.get("/api/v1/investigations/inv_psi69?data_revision=x")
    assert r.status == 503 and r.error["code"] == "DATA_NOT_READY"
    assert cl.get("/api/v1/config").data["active_data_revision"] is None


def test_unknown_route_uses_envelope(server):
    r = server.client().get("/api/v1/nope")
    assert r.status == 404 and not c.errors_for("ErrorResponse", r.json)


# --- пространства ------------------------------------------------------------
def test_workspace_create_and_reuse(server):
    cl = server.client()
    r1 = cl.post("/api/v1/workspaces", {})
    assert r1.status == 201 and r1.headers["ETag"] == '"1"'
    assert "fa_session" in cl.cookies
    sc = r1.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=lax" in sc and "path=/api" in sc
    assert r1.data["data_revision"] == FIX_REV and r1.data["revision"] == 1
    r2 = cl.post("/api/v1/workspaces", {})
    assert r2.status == 200 and r2.data["id"] == r1.data["id"]


def test_session_required(server):
    r = server.client().get("/api/v1/workspaces/current")
    assert r.status == 401 and r.error["code"] == "SESSION_REQUIRED"
    cl = server.client()
    cl.cookies["fa_session"] = "forged"
    assert cl.get("/api/v1/workspaces/current").status == 401


def test_patch_requires_if_match(guest):
    r = guest.patch("/api/v1/workspaces/current", {"selected_investigation_ids": ["inv_psi25"]})
    assert r.status == 422 and r.error["details"][0]["field"] == "If-Match"


def test_patch_updates_dedupes_and_bumps_revision(guest):
    r = guest.patch("/api/v1/workspaces/current", {"selected_investigation_ids": ["inv_psi69", "inv_psi25", "inv_psi69"]},
                    headers={"If-Match": '"1"'})
    assert r.status == 200, r.raw
    assert r.data["selected_investigation_ids"] == ["inv_psi69", "inv_psi25"]
    assert r.data["revision"] == 2 and r.headers["ETag"] == '"2"'
    assert r.data["saved_investigation_ids"] == []  # непереданные поля не меняются
    g = guest.get("/api/v1/workspaces/current")
    assert g.data["selected_investigation_ids"] == ["inv_psi69", "inv_psi25"] and g.data["revision"] == 2


def test_patch_scenario_moon(guest):
    moon = json.loads((c.EXAMPLES_DIR / "patchCurrentWorkspace" / "set_moon.json").read_text())["request"]["body"]["scenario"]
    r = guest.patch("/api/v1/workspaces/current", {"scenario": moon}, headers={"If-Match": '"1"'})
    assert r.status == 200 and r.data["scenario"]["gravity_regime"] == "partial"


def test_patch_stale_revision_conflict(guest):
    assert guest.patch("/api/v1/workspaces/current", {"saved_investigation_ids": ["inv_psi25"]},
                       headers={"If-Match": '"1"'}).status == 200
    r = guest.patch("/api/v1/workspaces/current", {"saved_investigation_ids": ["inv_psi69"]}, headers={"If-Match": '"1"'})
    assert r.status == 409 and r.error["code"] == "WORKSPACE_CONFLICT"
    assert r.error["details"][0]["current_revision"] == 2
    assert guest.get("/api/v1/workspaces/current").data["saved_investigation_ids"] == ["inv_psi25"]


def test_at18_concurrent_patches_exactly_one_wins(guest):
    def go(i):
        return guest.patch("/api/v1/workspaces/current", {"saved_investigation_ids": [["inv_psi25", "inv_psi69", "inv_psi101"][i % 3]]},
                           headers={"If-Match": '"1"'}).status

    with cf.ThreadPoolExecutor(8) as ex:
        statuses = list(ex.map(go, range(8)))
    assert statuses.count(200) == 1 and statuses.count(409) == 7
    assert guest.get("/api/v1/workspaces/current").data["revision"] == 2


@pytest.mark.parametrize("body,field,reason", [
    ({"selected_investigation_ids": ["inv_psi25", "inv_psi69", "inv_psi101", "inv_x"]}, "selected_investigation_ids",
     "items_count_out_of_range"),
    ({"selected_investigation_ids": ["inv_unknown"]}, "selected_investigation_ids[0]", "not_found_in_revision"),
    ({"saved_answer_ids": ["ans_not_mine"]}, "saved_answer_ids[0]", "not_in_workspace"),
    ({"revision": 5}, "revision", "unexpected_field"),
    ({}, "$", "empty_object"),
])
def test_patch_validation(guest, body, field, reason):
    r = guest.patch("/api/v1/workspaces/current", body, headers={"If-Match": '"1"'})
    assert r.status == 422, r.raw
    assert {"field": field, "reason": reason, "current_revision": None} in r.error["details"]
    assert guest.get("/api/v1/workspaces/current").data["revision"] == 1


def test_at19_sessions_isolated(server):
    a, b = server.client(), server.client()
    wa = a.post("/api/v1/workspaces", {}).data
    wb = b.post("/api/v1/workspaces", {}).data
    assert wa["id"] != wb["id"]
    with server.db.write() as conn:  # ответ, принадлежащий A
        conn.execute("INSERT INTO answers VALUES (?, ?, ?, ?, ?)", ("ans_owned_by_a", wa["id"], FIX_REV, "{}", "2026-11-15T00:00:00Z"))
    r = b.patch("/api/v1/workspaces/current", {"saved_answer_ids": ["ans_owned_by_a"]}, headers={"If-Match": '"1"'})
    assert r.status == 422
    r = a.patch("/api/v1/workspaces/current", {"saved_answer_ids": ["ans_owned_by_a"]}, headers={"If-Match": '"1"'})
    assert r.status == 200 and r.data["saved_answer_ids"] == ["ans_owned_by_a"]
    assert b.get("/api/v1/workspaces/current").data["saved_answer_ids"] == []


# --- CSRF и разбор запроса --------------------------------------------------------
def test_csrf_foreign_origin_rejected(server):
    cl = server.client()
    r = cl.post("/api/v1/workspaces", {}, origin="https://evil.example")
    assert r.status == 403 and r.error["code"] == "ACCESS_DENIED"
    r = cl.post("/api/v1/workspaces", {}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status == 403


def test_malformed_and_wrong_content_type(guest):
    r = guest.request("POST", "/api/v1/measurements/query", raw_body=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status == 400 and r.error["code"] == "MALFORMED_JSON"
    r = guest.request("POST", "/api/v1/measurements/query", raw_body=b'{"a": NaN}', headers={"Content-Type": "application/json"})
    assert r.status == 400
    r = guest.request("POST", "/api/v1/measurements/query", raw_body=b"x=1", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status == 400 and r.error["details"][0]["field"] == "Content-Type"


# --- каталог ------------------------------------------------------------------
def test_investigation_detail(server):
    r = server.client().get(f"/api/v1/investigations/inv_psi25?{R}")
    assert r.status == 200
    kinds = [cl["kind"] for cl in r.data["claims"]]
    assert kinds == ["observation", "hypothesis"]  # гипотеза отдается с явным kind
    assert [s["id"] for s in r.data["sources"]] == ["src_psi25_dataset", "src_ntrs_20160000593"]
    assert r.json["meta"]["data_revision"] == FIX_REV


@pytest.mark.parametrize("url,status,code", [
    ("/api/v1/investigations/inv_psi69", 422, "VALIDATION_ERROR"),  # ревизия обязательна (BE-04)
    ("/api/v1/investigations/inv_psi69?data_revision=psi-19990101-r1", 410, "DATA_REVISION_GONE"),
    (f"/api/v1/investigations/inv_psi999?{R}", 404, "NOT_FOUND"),
    (f"/api/v1/runs/run_nope?{R}", 404, "NOT_FOUND"),
    (f"/api/v1/investigations/inv_psi69/runs?{R}&limit=201", 422, "VALIDATION_ERROR"),
])
def test_catalog_errors(server, url, status, code):
    r = server.client().get(url)
    assert r.status == status and r.error["code"] == code
    assert not c.errors_for("ErrorResponse", r.json)
    if status == 410:
        assert r.error["details"][0]["current_revision"] == FIX_REV


def test_runs_pagination_and_cursor_binding(server):
    cl = server.client()
    seen, url, pages = [], f"/api/v1/investigations/inv_psi69/runs?{R}&limit=2", 0
    while url:
        r = cl.get(url)
        assert r.status == 200 and r.data["total"] == 5
        seen += [x["source_test_id"] for x in r.data["items"]]
        nxt = r.data["next_cursor"]
        url = f"/api/v1/investigations/inv_psi69/runs?{R}&limit=2&cursor={nxt}" if nxt else None
        pages += 1
    assert pages == 3 and seen == sorted(APPENDIX_A)
    first = cl.get(f"/api/v1/investigations/inv_psi69/runs?{R}&limit=2").data["next_cursor"]
    r = cl.get(f"/api/v1/investigations/inv_psi25/runs?{R}&cursor={first}")
    assert r.status == 422 and r.error["code"] == "INVALID_CURSOR"
    r = cl.get(f"/api/v1/investigations/inv_psi69/runs?{R}&cursor={first[:-2]}xx")
    assert r.status == 422 and r.error["code"] == "INVALID_CURSOR"


def test_at05_at06_units_and_missing_values(server):
    cl = server.client()
    run = cl.get(f"/api/v1/runs/run_psi69_30cal03?{R}").data
    assert run["sample"]["initial_diameter"]["value"] == pytest.approx(0.00192, rel=1e-6)
    assert run["sample"]["initial_diameter"]["raw_value"] == "1.92" and run["sample"]["initial_diameter"]["raw_unit"] == "mm"
    assert abs(run["conditions"]["pressure"]["value"] - 760 * 133.322387) <= 1
    assert run["conditions"]["oxygen_fraction"]["value"] == 0.21
    assert run["terminal_outcome"]["raw_label"] == "Extinction"
    missing = cl.get(f"/api/v1/runs/run_psi25_fixture01?{R}").data["conditions"]["pressure"]
    assert missing["value"] is None and missing["status"] == "not_reported"  # нормальное давление не подставлено


def test_evidence_and_sources(server):
    cl = server.client()
    r = cl.get(f"/api/v1/evidence/ev_psi69_30cal03?{R}")
    assert r.status == 200 and r.data["source"]["id"] == "src_psi69_exptable"
    assert r.data["evidence"]["locator"]["row_key"] == "30CAL03"
    asset = cl.get(f"/api/v1/sources/src_psi69_exptable/asset?{R}")
    assert asset.status == 200 and b"30CAL03,1.92,6.34,760,Extinction" in asset.raw
    # AT-26: файла нет - метаданные и остальные источники доступны
    assert cl.get(f"/api/v1/sources/src_psi101_dataset/asset?{R}").status == 404
    meta = cl.get(f"/api/v1/sources/src_psi101_dataset?{R}")
    assert meta.status == 200 and meta.data["availability"] == "unavailable"


# --- измерения (BE-06) ---------------------------------------------------------------
MQ = {"investigation_id": "inv_psi69", "data_revision": FIX_REV, "x_metric": "sample.initial_diameter",
      "y_metric": "metrics.burn_duration"}


def test_at07_flex_points_match_appendix_a(guest):
    r = guest.post("/api/v1/measurements/query", MQ)
    assert r.status == 200, r.raw
    d = r.data
    assert d["x_axis"]["unit"] == "m" and d["y_axis"]["unit"] == "s"
    assert d["excluded_count"] == 0 and d["truncated"] is False and len(d["points"]) == 5
    for p in d["points"]:
        tid = p["run_id"].split("_")[-1].upper()
        diam_mm, t, outcome = APPENDIX_A[tid]
        assert p["x"] * 1000 == pytest.approx(diam_mm, rel=1e-6)
        assert p["y"] == pytest.approx(t, rel=1e-6)
        assert p["outcome"] == outcome
        assert p["evidence_ids"] == [f"ev_psi69_{tid.lower()}"]


def test_measurements_exclusions_filters_and_paging(guest):
    r = guest.post("/api/v1/measurements/query", {**MQ, "investigation_id": "inv_psi25"})
    assert r.data["points"] == [] and r.data["exclusions_by_reason"]["missing_x"] == 1  # не рисуется как ноль
    r = guest.post("/api/v1/measurements/query", {**MQ, "filters": {"outcome_categories": ["extinction"]}})
    assert len(r.data["points"]) == 4 and r.data["exclusions_by_reason"]["filtered_out"] == 1
    p1 = guest.post("/api/v1/measurements/query", {**MQ, "limit": 3})
    assert len(p1.data["points"]) == 3 and p1.data["truncated"] is True
    p2 = guest.post("/api/v1/measurements/query", {**MQ, "limit": 3, "cursor": p1.data["next_cursor"]})
    assert len(p2.data["points"]) == 2 and p2.data["next_cursor"] is None
    ids = [p["run_id"] for p in p1.data["points"] + p2.data["points"]]
    assert len(set(ids)) == 5
    bad = guest.post("/api/v1/measurements/query", {**MQ, "limit": 3, "cursor": p1.data["next_cursor"],
                                                    "filters": {"outcome_categories": ["disruption"]}})
    assert bad.status == 422 and bad.error["code"] == "INVALID_CURSOR"


def test_measurements_validation(guest):
    r = guest.post("/api/v1/measurements/query", {**MQ, "y_metric": "metrics.flame_spread_rate"})
    assert r.status == 422 and r.error["details"][0]["reason"] == "unsupported_axis"
    r = guest.post("/api/v1/measurements/query", {**MQ, "run_ids": ["run_psi25_fixture01"]})
    assert r.status == 422 and r.error["details"][0]["reason"] == "not_in_investigation"
    r = guest.post("/api/v1/measurements/query", {**MQ, "unexpected": True})
    assert r.status == 422 and r.error["details"][0] == {"field": "unexpected", "reason": "unexpected_field", "current_revision": None}
