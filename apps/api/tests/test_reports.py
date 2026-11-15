"""BE-07 (таблица) и BE-09 (PDF). AT-09, AT-10, AT-12, AT-16, AT-19, AT-21, AT-22."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import threading
import time
import uuid

import pytest

from conftest import FIX_REV, poll, scenario, set_scenario, start_analysis
from fire_atlas_api import providers as P

import fa_contracts as c

CMP = "/api/v1/comparisons"


# --- сравнение ---------------------------------------------------------------------
def test_at09_different_methods_partially_compatible(server):
    r = server.client().post(CMP, {"investigation_ids": ["inv_psi25", "inv_psi69"], "data_revision": FIX_REV})
    assert r.status == 200, r.raw
    d = r.data
    assert d["comparability"]["status"] == "partially_compatible"
    codes = {x["code"] for x in d["comparability"]["reasons"]}
    assert {"different_object", "different_metrics"} <= codes
    rows = {row["field"]: row for row in d["rows"]}
    p = {cl["investigation_id"]: cl for cl in rows["conditions.pressure"]["cells"]}
    assert p["inv_psi25"]["status"] == "not_reported" and p["inv_psi25"]["value_text"] is None  # пропуск не равен совпадению
    assert rows["sample.initial_diameter"]["cells"][1]["value_text"] == "1.61 мм - 2.06 мм"
    assert "Время горения (5)" in rows["measured_metrics"]["cells"][1]["value_text"]
    assert d["applicability"] is None and d["limitations"]


@pytest.mark.parametrize("ids,status", [
    (["inv_psi25", "inv_psi69", "inv_psi101", "inv_psi4"], 422),
    (["inv_psi25"], 422),
    (["inv_psi25", "inv_psi25"], 422),
    (["inv_psi25", "inv_nope"], 404),
])
def test_comparison_bounds(server, ids, status):
    r = server.client().post(CMP, {"investigation_ids": ids, "data_revision": FIX_REV})
    assert r.status == status


def test_comparison_with_moon_scenario(server):
    r = server.client().post(CMP, {"investigation_ids": ["inv_psi25", "inv_psi69"], "data_revision": FIX_REV,
                                   "scenario": scenario("moon")})
    ap = r.data["applicability"]
    assert ap["overall"] != "direct_evidence"
    g = next(f for f in ap["factors"] if f["field"] == "gravity_regime")
    assert g["status"] == "not_covered"
    assert any(gp["field"] == "gravity_regime" for gp in ap["gaps"])


def test_applicability_endpoint_and_guard(server, providers):
    cl = server.client()
    body = {"scenario": scenario("moon"), "investigation_ids": ["inv_psi69"], "data_revision": FIX_REV}
    r = cl.post("/api/v1/applicability", body)
    assert r.status == 200 and not c.errors_for("ApplicabilityResultEnvelope", r.json)
    providers["applicability"] = lambda sc, invs, runs, ev: {
        "overall": "direct_evidence", "factors": [], "gaps": [],
        "basis": {"reviewed_rules_version": "bad", "data_revision": FIX_REV}}
    r = cl.post("/api/v1/applicability", body)
    assert r.status == 500 and r.error["code"] == "INTERNAL_ERROR"  # direct_evidence для partial не публикуется


# --- отчеты ------------------------------------------------------------------------
def _report(cl, answer_ids=(), inv_ids=("inv_psi25", "inv_psi69"), title="Вентиляция и горение материалов",
            include_comparison=True, key=None, ws_rev=None):
    ws_rev = ws_rev or cl.get("/api/v1/workspaces/current").data["revision"]
    body = {"workspace_revision": ws_rev, "title": title, "answer_ids": list(answer_ids), "investigation_ids": list(inv_ids),
            "include_comparison": include_comparison, "locale": "ru"}
    return cl.post("/api/v1/reports", body, headers={"Idempotency-Key": key or str(uuid.uuid4())}), body


def _pdf_text(raw: bytes, tmp_path) -> str:
    p = tmp_path / "r.pdf"
    p.write_bytes(raw)
    # UTF-8 явно: иначе на Windows вывод читается в cp1251 и кириллица теряется
    return subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(p), "-"], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def _answer(cl, sc_name="orbital", selected=("inv_psi69",)):
    set_scenario(cl, scenario(sc_name))
    job = poll(cl, start_analysis(cl, selected=selected)[0].data["id"])
    assert job["state"] == "succeeded", job
    return job["result_id"]


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext не установлен")
def test_report_ready_download_and_content(guest, tmp_path):
    ans = _answer(guest)
    r, _ = _report(guest, answer_ids=[ans])
    assert r.status == 202 and r.data["type"] == "report" and r.data["result_kind"] == "report"
    job = poll(guest, r.data["id"])
    assert job["state"] == "succeeded", job
    rep = guest.get(f"/api/v1/reports/{job['result_id']}")
    assert rep.status == 200 and rep.data["state"] == "ready" and not c.errors_for("ReportEnvelope", rep.json)
    assert rep.data["download_path"] == f"/api/v1/reports/{rep.data['id']}/download"
    dl = guest.get(rep.data["download_path"])
    assert dl.status == 200 and dl.headers["content-type"] == "application/pdf" and dl.raw.startswith(b"%PDF-")
    assert hashlib.sha256(dl.raw).hexdigest() == rep.data["sha256"]
    assert "attachment" in dl.headers["content-disposition"]
    text = _pdf_text(dl.raw, tmp_path)
    for needle in ["Вентиляция и горение материалов", FIX_REV, "Как поток воздуха влияет на горение?", "Орбитальная станция",
                   "Сравнение исследований", "Первоисточники", "https://psi.nasa.gov/physci/repo/data/investigations/PSI-69",
                   "Исходная гипотеза (не результат)", "не является заключением о безопасности"]:
        assert needle in text, needle
    again = guest.get(rep.data["download_path"])  # повторное скачивание не создает новый отчет
    assert again.raw == dl.raw


def test_at21_report_reflects_snapshot_not_later_changes(guest, tmp_path, monkeypatch):
    import fire_atlas_api.report_pdf as rp

    gate = threading.Event()
    real = rp.render_report

    def slow(snap, out, font_dir):
        gate.wait(5)
        return real(snap, out, font_dir)

    monkeypatch.setattr(rp, "render_report", slow)
    ans = _answer(guest, "orbital")
    r, _ = _report(guest, answer_ids=[ans])
    poll(guest, r.data["id"], until={"exporting"})
    set_scenario(guest, scenario("moon"))  # пространство меняется во время экспорта
    gate.set()
    job = poll(guest, r.data["id"])
    rep = guest.get(f"/api/v1/reports/{job['result_id']}").data
    pdf = guest.get(rep["download_path"]).raw
    if shutil.which("pdftotext"):
        text = _pdf_text(pdf, tmp_path)
        assert "Орбитальная станция" in text and "Лунная база" not in text
    assert rep["source_workspace_revision"] == r.data["input_context"]["workspace_revision"]


def test_report_with_two_contexts_and_insufficient(guest, tmp_path):
    a1 = _answer(guest, "orbital")
    a2 = _answer(guest, "moon", selected=("inv_psi25",))
    r, _ = _report(guest, answer_ids=[a1, a2])
    job = poll(guest, r.data["id"])
    pdf = guest.get(f"/api/v1/reports/{job['result_id']}/download").raw
    if shutil.which("pdftotext"):
        text = _pdf_text(pdf, tmp_path)
        assert "Ответы получены в разных контекстах" in text
        assert "Недостаточно доказательств" in text and "частичной гравитации" in text


def test_report_validation_and_conflicts(guest, server):
    r, _ = _report(guest, ws_rev=99)
    assert r.status == 409 and r.error["code"] == "WORKSPACE_CONFLICT"
    r, _ = _report(guest, answer_ids=["ans_foreign"])
    assert r.status == 422 and r.error["details"][0] == {"field": "answer_ids[0]", "reason": "not_in_workspace", "current_revision": None}
    r, _ = _report(guest, answer_ids=[], inv_ids=[])
    assert r.status == 422
    r, _ = _report(guest, title="ab")
    assert r.status == 422


def test_report_idempotency_and_isolation(server):
    a, b = server.client(), server.client()
    a.post("/api/v1/workspaces", {})
    b.post("/api/v1/workspaces", {})
    key = str(uuid.uuid4())
    r1, body = _report(a, key=key)
    r2 = a.post("/api/v1/reports", body, headers={"Idempotency-Key": key})
    assert r2.data["id"] == r1.data["id"]
    job = poll(a, r1.data["id"])
    with server.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM reports WHERE job_id=?", (r1.data["id"],)).fetchone()[0] == 1
    assert b.get(f"/api/v1/reports/{job['result_id']}").status == 403
    assert b.get(f"/api/v1/reports/{job['result_id']}/download").status == 403


def test_at22_expired_report(guest, server):
    job = poll(guest, _report(guest)[0].data["id"])
    rid = job["result_id"]
    with server.db.write() as conn:
        conn.execute("UPDATE reports SET expires_at='2026-01-01T00:00:00.000Z' WHERE id=?", (rid,))
    rep = guest.get(f"/api/v1/reports/{rid}")
    assert rep.data["state"] == "expired" and rep.data["download_path"] is None
    dl = guest.get(f"/api/v1/reports/{rid}/download")
    assert dl.status == 410 and dl.error["code"] == "RESOURCE_EXPIRED"
    time.sleep(0.5)  # watchdog удаляет файл
    with server.db.read() as conn:
        assert conn.execute("SELECT state FROM reports WHERE id=?", (rid,)).fetchone()[0] == "expired"
    assert not (server.settings.reports_dir / f"{rid}.pdf").exists()


def test_report_preparing_and_active_limit(guest, server, monkeypatch):
    import fire_atlas_api.report_pdf as rp

    gate = threading.Event()
    real = rp.render_report
    monkeypatch.setattr(rp, "render_report", lambda s, o, f: (gate.wait(5), real(s, o, f))[1])
    j1 = _report(guest)[0].data["id"]
    j2 = _report(guest)[0].data["id"]
    r3, _ = _report(guest)
    assert r3.status == 429 and "Retry-After" in r3.headers  # не больше 2 активных экспортов
    poll(guest, j1, until={"exporting"})
    with server.db.read() as conn:  # result_id появляется только при succeeded, поэтому id берем из БД
        rid = conn.execute("SELECT id FROM reports WHERE job_id=?", (j1,)).fetchone()[0]
    assert guest.get(f"/api/v1/reports/{rid}").data["state"] == "preparing"
    dl = guest.get(f"/api/v1/reports/{rid}/download")
    assert dl.status == 409 and dl.error["code"] == "REPORT_NOT_READY" and dl.error["retryable"] is True
    gate.set()
    assert poll(guest, j1)["state"] == poll(guest, j2)["state"] == "succeeded"
