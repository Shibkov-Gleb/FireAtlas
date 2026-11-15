"""BE-08 / BE-10: анализы, задачи, идемпотентность, отмена, дедлайн, восстановление, лимиты.

AT-11, AT-12, AT-14, AT-16, AT-17, AT-19, AT-20, AT-25 (часть бэкенда).
"""
from __future__ import annotations

import copy
import json
import threading
import time
import uuid

import pytest

from conftest import FIX_REV, LiveServer, poll, scenario, set_scenario, start_analysis
from fire_atlas_api import providers as P
from fire_atlas_api.db import Database, dumps, iso, plus, utcnow

import fa_contracts as c


def _answers_count(server) -> int:
    with server.db.read() as conn:
        return conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]


# --- успешный путь ----------------------------------------------------------------
def test_at11_success_answer_is_valid_and_bound_to_context(guest):
    ws_rev = set_scenario(guest, scenario("orbital"))
    r, _ = start_analysis(guest)
    assert r.status == 202, r.raw
    assert r.data["state"] == "queued" and r.data["result_kind"] == "answer"
    assert r.data["input_context"] == {"workspace_revision": ws_rev, "data_revision": FIX_REV, "scenario_id": "orbital_custom"}
    job = poll(guest, r.data["id"])
    assert job["state"] == "succeeded", job
    assert job["stage"] is None and job["result_id"].startswith("ans_")
    a = guest.get(f"/api/v1/answers/{job['result_id']}")
    assert a.status == 200 and not c.errors_for("AnalysisResultEnvelope", a.json)
    ans = a.data
    assert ans["status"] == "answered" and ans["workspace_revision"] == ws_rev
    assert ans["scenario_snapshot"]["scenario_id"] == "orbital_custom"
    assert ans["retrieval_mode"] == "curated"
    used = {e for b in ans["answer_blocks"] for e in b["evidence_ids"]}
    assert used <= {ci["evidence_id"] for ci in ans["citations"]}  # каждая ссылка блока имеет citation
    cit = next(ci for ci in ans["citations"] if ci["evidence_id"] == "ev_psi69_30cal03")
    assert cit["label"] == "FLEX (PSI-69) - Experimental Table, версия 5, строка 30CAL03"  # строит бэкенд из реестра
    assert ans["applicability"]["overall"] != "direct_evidence"  # заглушка A2-04 консервативна
    # ответ можно сохранить в пространстве
    rev = guest.get("/api/v1/workspaces/current").data["revision"]
    s = guest.patch("/api/v1/workspaces/current", {"saved_answer_ids": [ans["id"]]}, headers={"If-Match": f'"{rev}"'})
    assert s.status == 200 and s.data["saved_answer_ids"] == [ans["id"]]


def test_at12_moon_scenario_insufficient_and_never_direct(guest):
    set_scenario(guest, scenario("moon"))
    r, _ = start_analysis(guest, selected=("inv_psi25",))
    job = poll(guest, r.data["id"])
    ans = guest.get(f"/api/v1/answers/{job['result_id']}").data
    assert ans["status"] == "insufficient_evidence"
    ap = ans["applicability"]
    assert ap["overall"] != "direct_evidence"
    assert {"field": "gravity_regime", "status": "not_covered"}.items() <= next(
        f for f in ap["factors"] if f["field"] == "gravity_regime").items()
    assert ans["follow_up_questions"]


def test_new_guest_gets_orbital_scenario(guest):
    """D-039: у нового гостя сценарий по умолчанию - пресет орбитальной станции (фронтенд не получает null)."""
    sc = guest.get("/api/v1/workspaces/current").data["scenario"]
    assert sc is not None and sc["scenario_id"] == "orbital_custom" and sc["gravity_regime"] == "microgravity"
    assert all(a["origin"] == "preset_source" and a["source_ids"] for a in sc["assumptions"])


def test_job_without_scenario_has_null_applicability(guest):
    set_scenario(guest, None)  # null по-прежнему допустим (D-016)
    r, _ = start_analysis(guest)
    job = poll(guest, r.data["id"])
    assert guest.get(f"/api/v1/answers/{job['result_id']}").data["applicability"] is None


# --- идемпотентность (AT-16) -----------------------------------------------------------
def test_at16_same_key_same_job(guest, server):
    key = str(uuid.uuid4())
    r1, body = start_analysis(guest, key=key)
    before = _answers_count(server)
    r2 = guest.post("/api/v1/analyses", body, headers={"Idempotency-Key": key})
    assert r2.status == 202 and r2.data["id"] == r1.data["id"]
    poll(guest, r1.data["id"])
    r3 = guest.post("/api/v1/analyses", body, headers={"Idempotency-Key": key.upper()})
    assert r3.data["id"] == r1.data["id"] and r3.data["state"] == "succeeded"  # повтор после завершения - текущее состояние
    assert _answers_count(server) == before + 1
    r4 = guest.post("/api/v1/analyses", {**body, "question": "Другой вопрос"}, headers={"Idempotency-Key": key})
    assert r4.status == 409 and r4.error["code"] == "IDEMPOTENCY_CONFLICT"


def test_idempotency_key_required_and_scoped(guest, server):
    _, body = start_analysis(guest)
    r = guest.post("/api/v1/analyses", body)
    assert r.status == 422 and r.error["details"][0]["field"] == "Idempotency-Key"
    r = guest.post("/api/v1/analyses", body, headers={"Idempotency-Key": "not-a-uuid"})
    assert r.status == 422


def test_concurrent_duplicate_posts_create_one_job(server):
    cl = server.client()
    cl.post("/api/v1/workspaces", {})
    key = str(uuid.uuid4())
    _, body = start_analysis(cl, key=key)  # первый
    ids = set()

    def go(_):
        return cl.post("/api/v1/analyses", body, headers={"Idempotency-Key": key}).data["id"]

    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(6) as ex:
        ids |= set(ex.map(go, range(6)))
    assert len(ids) == 1


# --- проверки входа --------------------------------------------------------------------
def test_stale_workspace_revision_conflict(guest):
    rev = set_scenario(guest, scenario("orbital"))
    r, _ = start_analysis(guest, ws_rev=rev - 1)
    assert r.status == 409 and r.error["code"] == "WORKSPACE_CONFLICT"
    assert r.error["details"][0]["current_revision"] == rev


@pytest.mark.parametrize("kw,field", [
    ({"rev": "fixture-other-r1"}, "data_revision"),
    ({"selected": ("inv_unknown",)}, "selected_investigation_ids[0]"),
    ({"question": "ab"}, "question"),
])
def test_analysis_validation(guest, kw, field):
    r, _ = start_analysis(guest, **kw)
    assert r.status == 422 and r.error["details"][0]["field"] == field


def test_analysis_requires_session(server):
    r = server.client().post("/api/v1/analyses", {}, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status == 401


# --- отказы AI (AT-14) ----------------------------------------------------------------
def test_at14_provider_failure_failed_job_with_fallback(guest, providers, server):
    def boom(req):
        raise P.ProviderError("upstream 503")

    providers["reasoner"] = boom
    before = _answers_count(server)
    r, _ = start_analysis(guest)
    job = poll(guest, r.data["id"])
    assert job["state"] == "failed" and job["error"]["code"] == "MODEL_PROVIDER_ERROR" and job["error"]["retryable"]
    assert "upstream" not in job["error"]["message"]  # внутренняя деталь не утекает
    assert job["fallback_evidence_ids"] and job["result_id"] is None
    assert _answers_count(server) == before
    for e in job["fallback_evidence_ids"]:
        assert guest.get(f"/api/v1/evidence/{e}?data_revision={FIX_REV}").status == 200  # каталог работает


def test_retrieval_unavailable(guest, providers):
    def down(req):
        raise P.RetrievalUnavailable("index missing")

    providers["retriever"] = down
    r, _ = start_analysis(guest)
    job = poll(guest, r.data["id"])
    assert job["state"] == "failed" and job["error"]["code"] == "AI_UNAVAILABLE" and job["fallback_evidence_ids"] == []


def test_retrieval_other_revision_rejected(guest, providers):
    real = providers["retriever"]

    def wrong_rev(req):
        out = real(req)
        out["data_revision"] = "psi-old-r1"
        return out

    providers["retriever"] = wrong_rev
    job = poll(guest, start_analysis(guest)[0].data["id"])
    assert job["error"]["code"] == "AI_UNAVAILABLE"


def _bad_reasoner(mutate, calls):
    def f(req):
        calls.append(1)
        out = P.stub_reason(req)
        return mutate(out, req) if len(calls) <= mutate.bad_times else out
    return f


@pytest.mark.parametrize("name,mutate", [
    ("foreign_evidence", lambda o, r: (o["answer_blocks"][0].__setitem__("evidence_ids", ["ev_not_in_bundle"]), o)[1]),
    ("url_in_text", lambda o, r: (o["answer_blocks"][0].__setitem__("text", "См. https://evil.example"), o)[1]),
    ("html_in_text", lambda o, r: (o["answer_blocks"][0].__setitem__("text", "<script>x</script>"), o)[1]),
    ("schema", lambda o, r: (o.__setitem__("extra", 1), o)[1]),
    ("self_reported_invalid", lambda o, r: (o["validation_summary"].__setitem__("quantities_valid", False), o)[1]),
])
def test_invalid_reasoning_never_published(guest, providers, server, name, mutate):
    calls: list = []
    mutate.bad_times = 99
    providers["reasoner"] = _bad_reasoner(mutate, calls)
    before = _answers_count(server)
    job = poll(guest, start_analysis(guest)[0].data["id"])
    assert job["state"] == "failed" and job["error"]["code"] == "VALIDATION_FAILED", job
    assert len(calls) == 2  # ровно один исправляющий проход
    assert _answers_count(server) == before and job["fallback_evidence_ids"]


def test_one_correcting_pass_can_succeed(guest, providers):
    calls: list = []
    mutate = lambda o, r: (o["answer_blocks"][0].__setitem__("evidence_ids", ["ev_not_in_bundle"]), o)[1]  # noqa: E731
    mutate.bad_times = 1
    providers["reasoner"] = _bad_reasoner(mutate, calls)
    job = poll(guest, start_analysis(guest)[0].data["id"])
    assert job["state"] == "succeeded" and len(calls) == 2


def test_direct_evidence_for_partial_gravity_rejected(guest, providers):
    def liar(req):
        out = P.stub_reason(req)
        out["status"] = "answered"
        out["applicability"] = {"overall": "direct_evidence", "factors": [], "gaps": [],
                                "basis": {"reviewed_rules_version": "x", "data_revision": FIX_REV}}
        return out

    providers["reasoner"] = liar
    set_scenario(guest, scenario("moon"))
    job = poll(guest, start_analysis(guest)[0].data["id"])
    assert job["state"] == "failed" and job["error"]["code"] == "VALIDATION_FAILED"


# --- отмена и поздний ответ (AT-17) ---------------------------------------------------------
def _slow(providers, seconds, gate: threading.Event | None = None):
    def slow(req):
        if gate:
            gate.wait(seconds)
        else:
            time.sleep(seconds)
        return P.stub_reason(req)
    providers["reasoner"] = slow


def test_at17_cancel_then_late_answer_not_published(guest, providers, server):
    gate = threading.Event()
    _slow(providers, 10, gate)
    before = _answers_count(server)
    jid = start_analysis(guest)[0].data["id"]
    poll(guest, jid, until={"reasoning"})
    d = guest.request("DELETE", f"/api/v1/jobs/{jid}")
    assert d.status == 204 and d.raw == b""
    gate.set()  # модель "ответила" после отмены
    time.sleep(0.3)
    job = guest.get(f"/api/v1/jobs/{jid}").data
    assert job["state"] == "cancelled" and job["result_id"] is None
    assert _answers_count(server) == before
    again = guest.request("DELETE", f"/api/v1/jobs/{jid}")
    assert again.status == 409 and again.error["code"] == "JOB_ALREADY_FINISHED"


def test_cancel_finished_job_conflict(guest):
    jid = start_analysis(guest)[0].data["id"]
    poll(guest, jid)
    r = guest.request("DELETE", f"/api/v1/jobs/{jid}")
    assert r.status == 409 and r.error["details"][0]["reason"] == "succeeded"


# --- смена сценария во время анализа (AT-20) ------------------------------------------------------
def test_at20_scenario_change_during_analysis_keeps_snapshot(guest, providers):
    gate = threading.Event()
    _slow(providers, 10, gate)
    rev0 = set_scenario(guest, scenario("orbital"))
    jid = start_analysis(guest)[0].data["id"]
    poll(guest, jid, until={"reasoning"})
    set_scenario(guest, scenario("moon"))
    gate.set()
    job = poll(guest, jid)
    ans = guest.get(f"/api/v1/answers/{job['result_id']}").data
    assert ans["scenario_snapshot"]["scenario_id"] == "orbital_custom" and ans["workspace_revision"] == rev0
    assert guest.get("/api/v1/workspaces/current").data["scenario"]["scenario_id"] == "moon_base"


# --- изоляция (AT-19) -----------------------------------------------------------------------
def test_at19_jobs_and_answers_isolated(server):
    a, b = server.client(), server.client()
    a.post("/api/v1/workspaces", {})
    b.post("/api/v1/workspaces", {})
    job = poll(a, start_analysis(a)[0].data["id"])
    assert b.get(f"/api/v1/jobs/{job['id']}").error["code"] == "ACCESS_DENIED"
    assert b.get(f"/api/v1/answers/{job['result_id']}").status == 403
    assert b.request("DELETE", f"/api/v1/jobs/{job['id']}").status == 403
    assert b.get("/api/v1/jobs/job_nonexistent").status == 404


# --- лимиты (BE-10) ---------------------------------------------------------------------------
def test_active_job_limit_429(guest, providers):
    gate = threading.Event()
    _slow(providers, 10, gate)
    j1 = start_analysis(guest)[0]
    r2, _ = start_analysis(guest)
    assert r2.status == 429 and r2.error["code"] == "RATE_LIMITED" and int(r2.headers["Retry-After"]) >= 1
    assert r2.error["retryable"] is True
    gate.set()
    poll(guest, j1.data["id"])


def test_per_minute_limit_429(guest):
    for _ in range(5):
        poll(guest, start_analysis(guest)[0].data["id"])
    r, _ = start_analysis(guest)
    assert r.status == 429 and 1 <= int(r.headers["Retry-After"]) <= 61


# --- дедлайн и выключенный анализ ----------------------------------------------------------------
def test_deadline_expires_job(make_server):
    with make_server(analysis_deadline_s=1) as srv:
        def slow(req):
            time.sleep(1.6)
            return P.stub_reason(req)
        srv.app.state.providers["reasoner"] = slow
        cl = srv.client()
        cl.post("/api/v1/workspaces", {})
        job = poll(cl, start_analysis(cl)[0].data["id"])
        assert job["state"] == "expired" and job["error"]["code"] == "JOB_TIMEOUT"
        time.sleep(0.8)  # модель вернулась после дедлайна
        assert cl.get(f"/api/v1/jobs/{job['id']}").data["state"] == "expired"
        with srv.db.read() as conn:
            assert conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0] == 0


def test_analysis_disabled(make_server):
    with make_server(feature_analysis=False) as srv:
        cl = srv.client()
        cl.post("/api/v1/workspaces", {})
        r, _ = start_analysis(cl)
        assert r.status == 503 and r.error["code"] == "AI_UNAVAILABLE"
        assert cl.get("/api/v1/config").data["feature_flags"]["analysis"] is False
        assert cl.get(f"/api/v1/investigations/inv_psi69?data_revision={FIX_REV}").status == 200


# --- перезапуск (AT-25) -----------------------------------------------------------------------------
def test_at25_restart_recovers_or_expires_running_jobs(tmp_path, release_dir):
    from conftest import prepared_settings

    s = prepared_settings(tmp_path, release_dir)
    db = Database(s.db_path)
    now = utcnow()
    with db.write() as conn:
        conn.execute("INSERT INTO workspaces VALUES ('ws_restart', 'h', 1, ?, ?, ?, ?, ?)",
                     (FIX_REV, dumps({"scenario": None, "selected_investigation_ids": [], "saved_investigation_ids": [],
                                      "saved_answer_ids": []}), iso(now), iso(now), iso(plus(now, days=7))))
        inp = {"workspace_id": "ws_restart", "scenario_snapshot": None,
               "request": {"question": "Что измерено во FLEX?", "locale": "ru", "workspace_revision": 1, "data_revision": FIX_REV,
                           "selected_investigation_ids": ["inv_psi69"], "mode": "evidence_answer"},
               "input_context": {"workspace_revision": 1, "data_revision": FIX_REV, "scenario_id": None}}
        for jid, deadline in (("job_alive", plus(now, seconds=30)), ("job_dead", plus(now, seconds=-5))):
            conn.execute("INSERT INTO jobs (id, workspace_id, type, state, stage, created_at, updated_at, deadline_at, input, attempts) "
                         "VALUES (?, 'ws_restart', 'analysis', 'running', 'reasoning', ?, ?, ?, ?, 1)",
                         (jid, iso(now), iso(now), iso(deadline), dumps(inp)))
    with LiveServer(s) as srv:
        for _ in range(100):
            with srv.db.read() as conn:
                st = dict(conn.execute("SELECT id, state FROM jobs").fetchall())
            if st["job_alive"] in ("succeeded", "failed") and st["job_dead"] == "expired":
                break
            time.sleep(0.05)
        assert st == {"job_alive": "succeeded", "job_dead": "expired"}
