"""Фоновые задачи: анализ (BE-08) и экспорт отчета (BE-09).

Модель состояний (13.8): queued -> running|cancelled|expired; running -> succeeded|failed|cancelled|expired.
Каждый переход - условный UPDATE по текущему нетерминальному состоянию, поэтому
отмена, дедлайн и завершение конкурируют безопасно: поздний результат не публикуется (AT-17).
Перезапуск процесса: задачи с непрошедшим дедлайном выполняются заново, остальные - expired (AT-25).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import fa_contracts as c

from .db import Database, dumps, iso, parse_iso, plus, utcnow
from .metrics import Metrics
from .providers import AIError, ContractViolation
from .settings import Settings
from .validation import check_applicability, check_reasoning, check_retrieval

log = logging.getLogger("fire_atlas.jobs")

TERMINAL = {"succeeded", "failed", "cancelled", "expired"}
ACTIVE = ("queued", "running")
OUTPUT_LIMITS = {"max_blocks": 8, "max_follow_ups": 3, "max_total_chars": 10000}
JOB_MESSAGES = {
    "MODEL_PROVIDER_ERROR": "The answer generation service is unavailable. Retrieved materials remain available to explore.",
    "VALIDATION_FAILED": "The answer failed source validation and was not published. Open the retrieved materials.",
    "REASONING_TIMEOUT": "The reasoning module exceeded its deadline. Retrieved materials remain available.",
    "AI_UNAVAILABLE": "Evidence retrieval is temporarily unavailable. The catalog and sources remain available.",
    "JOB_TIMEOUT": "No answer was received before the deadline.",
    "EXPORT_FAILED": "The PDF could not be prepared. Retry the export.",
    "INTERNAL_ERROR": "An internal error occurred while running the job. Report the request_id.",
}
EMPTY_FILTERS = {"scopes": [], "investigation_ids": [], "material_ids": [], "fuel_states": [], "gravity_regimes": [],
                 "oxygen_range": None, "pressure_range": None, "airflow_range": None, "has_measurements": None,
                 "include_unknown": False}


class Abort(Exception):
    """Задача уже не running (отменена или истекла) - тихо прекращаем работу."""


def job_error(code: str, message: str | None = None) -> dict:
    return {"code": code, "message": message or JOB_MESSAGES.get(code, JOB_MESSAGES["INTERNAL_ERROR"]), "details": [],
            "retryable": True}


def job_to_api(row) -> dict:
    inp = json.loads(row["input"])
    return {
        "id": row["id"], "type": row["type"], "state": row["state"], "stage": row["stage"],
        "created_at": row["created_at"], "updated_at": row["updated_at"], "deadline_at": row["deadline_at"],
        "result_kind": "answer" if row["type"] == "analysis" else "report",
        "result_id": row["result_id"] if row["state"] == "succeeded" else None,
        "error": json.loads(row["error"]) if row["error"] else None,
        "input_context": inp["input_context"],
        "fallback_evidence_ids": json.loads(row["fallback_evidence_ids"]),
    }


def citation_label(source: dict, loc: dict) -> str:
    parts = [source["title"]]
    if loc["page"] is not None:
        parts.append(f"p. {loc['page']}")
    if loc["section"]:
        parts.append(loc["section"])
    if loc["row_key"]:
        parts.append(f"row {loc['row_key']}")
    if loc["start_s"] is not None and loc["end_s"] is not None:
        parts.append(f"{loc['start_s']:g}-{loc['end_s']:g} s")
    return ", ".join(parts)[:300]


class JobRunner:
    def __init__(self, settings: Settings, db: Database, metrics: Metrics, providers: dict[str, Callable]):
        self.s = settings
        self.db = db
        self.metrics = metrics
        self.providers = providers
        self.pool: ThreadPoolExecutor | None = None
        self._stop = threading.Event()
        self._watchdog: threading.Thread | None = None

    # --- жизненный цикл --------------------------------------------------------
    def start(self) -> None:
        self.pool = ThreadPoolExecutor(max_workers=self.s.worker_threads, thread_name_prefix="fa-job")
        self._stop.clear()
        self.recover()
        self._watchdog = threading.Thread(target=self._watch, name="fa-watchdog", daemon=True)
        self._watchdog.start()

    def stop(self) -> None:
        self._stop.set()
        if self._watchdog:
            self._watchdog.join(5)
        if self.pool:
            self.pool.shutdown(wait=False, cancel_futures=True)

    def submit(self, job_id: str, recovered: bool = False) -> None:
        assert self.pool is not None, "JobRunner не запущен"
        self.pool.submit(self._run, job_id, recovered)

    def recover(self) -> None:
        self.sweep()
        with self.db.read() as conn:
            rows = conn.execute("SELECT id, state FROM jobs WHERE state IN ('queued','running') ORDER BY created_at").fetchall()
        for r in rows:
            log.info(json.dumps({"event": "job_recovered", "job_id": r["id"], "state": r["state"]}))
            self.submit(r["id"], recovered=r["state"] == "running")

    def _watch(self) -> None:
        while not self._stop.wait(self.s.sweep_interval_s):
            try:
                self.sweep()
            except Exception:  # watchdog не должен умирать
                log.exception("sweep_failed")

    def sweep(self) -> None:
        """Дедлайны задач, срок отчетов, очистка ключей идемпотентности."""
        now = iso(utcnow())
        with self.db.write() as conn:
            overdue = conn.execute("SELECT id, type FROM jobs WHERE state IN ('queued','running') AND deadline_at <= ?",
                                   (now,)).fetchall()
            for r in overdue:
                cur = conn.execute("UPDATE jobs SET state='expired', error=?, updated_at=? WHERE id=? AND state IN ('queued','running')",
                                   (dumps(job_error("JOB_TIMEOUT")), now, r["id"]))
                if cur.rowcount:
                    self.metrics.job_finished(r["type"], "expired", "JOB_TIMEOUT")
                    if r["type"] == "report":
                        conn.execute("UPDATE reports SET state='failed', error=? WHERE job_id=? AND state='preparing'",
                                     (dumps(job_error("JOB_TIMEOUT", "The report was not prepared before its deadline.")), r["id"]))
            expired = conn.execute("SELECT id, file_name FROM reports WHERE state='ready' AND expires_at <= ?", (now,)).fetchall()
            for r in expired:
                conn.execute("UPDATE reports SET state='expired' WHERE id=? AND state='ready'", (r["id"],))
            conn.execute("UPDATE reports SET state='expired' WHERE state IN ('preparing','failed') AND expires_at <= ?", (now,))
            cutoff = iso(plus(utcnow(), hours=-self.s.idempotency_hours))
            conn.execute("DELETE FROM idempotency_keys WHERE created_at <= ?", (cutoff,))
        for r in expired:
            if r["file_name"]:
                (self.s.reports_dir / r["file_name"]).unlink(missing_ok=True)

    # --- переходы состояний --------------------------------------------------------
    def _begin(self, job_id: str, recovered: bool) -> dict | None:
        now = iso(utcnow())
        with self.db.write() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None or row["state"] in TERMINAL:
                return None
            if row["state"] == "queued":
                conn.execute("UPDATE jobs SET state='running', updated_at=?, attempts=attempts+1 WHERE id=? AND state='queued'",
                             (now, job_id))
            elif not recovered:
                return None  # уже выполняется другим исполнителем
            else:
                conn.execute("UPDATE jobs SET attempts=attempts+1, updated_at=? WHERE id=?", (now, job_id))
            return dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def _stage(self, job: dict, stage: str) -> None:
        if utcnow() >= parse_iso(job["deadline_at"]):
            raise Abort()  # watchdog переведет в expired
        with self.db.write() as conn:
            cur = conn.execute("UPDATE jobs SET stage=?, updated_at=? WHERE id=? AND state='running'",
                               (stage, iso(utcnow()), job["id"]))
            if cur.rowcount != 1:
                raise Abort()

    def _set_fallback(self, job_id: str, ids: list[str]) -> None:
        with self.db.write() as conn:
            conn.execute("UPDATE jobs SET fallback_evidence_ids=? WHERE id=? AND state='running'", (dumps(ids[:20]), job_id))

    def _fail(self, job: dict, code: str, internal: str = "") -> None:
        now = iso(utcnow())
        with self.db.write() as conn:
            cur = conn.execute("UPDATE jobs SET state='failed', error=?, updated_at=? WHERE id=? AND state='running'",
                               (dumps(job_error(code)), now, job["id"]))
            if cur.rowcount and job["type"] == "report":
                conn.execute("UPDATE reports SET state='failed', error=? WHERE job_id=? AND state='preparing'",
                             (dumps(job_error(code)), job["id"]))
        if cur.rowcount:
            self.metrics.job_finished(job["type"], "failed", code)
        log.warning(json.dumps({"event": "job_failed", "job_id": job["id"], "code": code, "detail": internal[:500]},
                               ensure_ascii=False))

    def _timed(self, job: dict, stage: str, fn: Callable, *args):
        t0 = time.perf_counter()
        try:
            return fn(*args)
        finally:
            ms = (time.perf_counter() - t0) * 1000
            self.metrics.stage(job["type"], stage, ms)
            with self.db.write() as conn:
                row = conn.execute("SELECT timings FROM jobs WHERE id=?", (job["id"],)).fetchone()
                t = json.loads(row["timings"])
                t[stage] = round(t.get(stage, 0) + ms, 1)
                conn.execute("UPDATE jobs SET timings=? WHERE id=?", (dumps(t), job["id"]))

    def _run(self, job_id: str, recovered: bool) -> None:
        job = self._begin(job_id, recovered)
        if job is None:
            return
        try:
            if job["type"] == "analysis":
                self._run_analysis(job)
            else:
                self._run_report(job)
        except Abort:
            pass
        except ContractViolation as e:
            self._fail(job, "VALIDATION_FAILED", str(e))
        except AIError as e:
            self._fail(job, e.code, str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("job_crashed job_id=%s", job_id)
            self._fail(job, "EXPORT_FAILED" if job["type"] == "report" else "INTERNAL_ERROR", repr(e))

    # --- анализ ----------------------------------------------------------------------
    def _run_analysis(self, job: dict) -> None:
        inp = json.loads(job["input"])
        rq = inp["request"]
        rev = inp["input_context"]["data_revision"]
        scenario = inp["scenario_snapshot"]
        attempt_tag = f"{job['id'][4:]}_{job['attempts']}"

        self._stage(job, "retrieving")
        rreq = {"request_id": f"req_{attempt_tag}", "question": rq["question"], "locale": rq.get("locale", "en"), "scenario": scenario,
                "filters": EMPTY_FILTERS, "selected_investigation_ids": rq["selected_investigation_ids"],
                "data_revision": rev, "top_k": 12, "deadline_at": job["deadline_at"], "include_related": False}
        c.validate("InternalRetrievalRequest", rreq)
        rres = self._timed(job, "retrieving", self.providers["retriever"], rreq)
        bundle = check_retrieval(rres, rreq, self.db)
        self._set_fallback(job["id"], bundle["allowed_evidence_ids"])

        self._stage(job, "reasoning")
        qreq = {"request_id": f"req_{attempt_tag}r", "evidence_bundle": bundle, "locale": rq.get("locale", "en"), "output_limits": OUTPUT_LIMITS,
                "deadline_at": job["deadline_at"], "reasoning_revision": self.s.reasoning_revision}
        c.validate("InternalReasoningRequest", qreq)
        resp = self._timed(job, "reasoning", self.providers["reasoner"], qreq)

        self._stage(job, "validating")
        problems = check_reasoning(resp, bundle, scenario, OUTPUT_LIMITS)
        if problems and utcnow() < parse_iso(job["deadline_at"]):
            # Один исправляющий проход в пределах общего дедлайна (13.9)
            log.info(json.dumps({"event": "reasoning_retry", "job_id": job["id"], "problems": problems[:5]}, ensure_ascii=False))
            self._stage(job, "reasoning")
            resp = self._timed(job, "reasoning", self.providers["reasoner"], qreq)
            self._stage(job, "validating")
            problems = check_reasoning(resp, bundle, scenario, OUTPUT_LIMITS)
        if problems:
            raise ContractViolation("; ".join(problems[:5]))

        applicability = resp["applicability"]
        if applicability is None and scenario is not None:
            inv_ids = rq["selected_investigation_ids"] or bundle["coverage"]["matching_investigation_ids"]
            invs = list(self.db.get_entities(rev, "investigation", inv_ids).values())
            runs = list(self.db.get_entities(rev, "run", bundle["coverage"]["matching_run_ids"]).values())
            evs = [i["evidence"] for i in bundle["items"]]
            applicability = self._timed(job, "validating", self.providers["applicability"], scenario, invs, runs, evs)
            check_applicability(applicability, scenario, rev, runs)

        answer = self._build_answer(job, inp, resp, bundle, applicability, rres["mode"])
        self._publish_answer(job, inp["workspace_id"], answer)

    def _build_answer(self, job, inp, resp, bundle, applicability, mode) -> dict:
        rev = inp["input_context"]["data_revision"]
        by_ev = {i["evidence"]["id"]: i for i in bundle["items"]}
        order: list[str] = []
        for b in resp["answer_blocks"]:
            order += b["evidence_ids"] + [e for q in b["quantities"] for e in q["evidence_ids"]]
        order += [cit["evidence_id"] for cit in resp["citations"]]
        if applicability:
            order += [e for f in applicability["factors"] for e in f["evidence_ids"]]
        citations = []
        for e in dict.fromkeys(order):
            item = by_ev[e]
            loc = item["evidence"]["locator"]
            citations.append({"evidence_id": e, "source_id": item["source_metadata"]["id"],
                              "label": citation_label(item["source_metadata"], loc), "locator": loc})
        answer = {
            "id": "ans_" + secrets.token_hex(12), "data_revision": rev,
            "workspace_revision": inp["input_context"]["workspace_revision"], "scenario_snapshot": inp["scenario_snapshot"],
            "question": inp["request"]["question"], "status": resp["status"], "answer_blocks": resp["answer_blocks"],
            "applicability": applicability, "citations": citations[:20], "limitations": resp["limitations"],
            "follow_up_questions": resp["follow_up_questions"], "retrieval_mode": mode,
            "reasoning_revision": resp["reasoning_revision"],
            "validation_summary": {"schema_valid": True, "references_valid": True, "quantities_valid": True, "scope_valid": True},
            "created_at": iso(utcnow()),
        }
        viol = c.errors_for("AnalysisResult", answer)
        if viol:
            raise ContractViolation(f"AnalysisResult: {viol[0]['field']}: {viol[0]['reason']}")
        return answer

    def _publish_answer(self, job: dict, workspace_id: str, answer: dict) -> None:
        now = utcnow()
        with self.db.write() as conn:
            if now >= parse_iso(job["deadline_at"]):
                raise Abort()
            cur = conn.execute("UPDATE jobs SET state='succeeded', stage=NULL, result_id=?, updated_at=? WHERE id=? AND state='running'",
                               (answer["id"], iso(now), job["id"]))
            if cur.rowcount != 1:
                raise Abort()  # отмена или дедлайн уже зафиксированы: поздний ответ не публикуется
            conn.execute("INSERT INTO answers (id, workspace_id, data_revision, body, created_at) VALUES (?, ?, ?, ?, ?)",
                         (answer["id"], workspace_id, answer["data_revision"], dumps(answer), answer["created_at"]))
        self.metrics.job_finished("analysis", "succeeded", None)

    # --- отчет -----------------------------------------------------------------------
    def _run_report(self, job: dict) -> None:
        from .report_pdf import render_report

        inp = json.loads(job["input"])
        report_id = inp["report_id"]
        self._stage(job, "exporting")
        tmp_dir = self.s.reports_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tmp_dir / f"{report_id}.{secrets.token_hex(4)}.pdf"
        try:
            self._timed(job, "exporting", render_report, inp["snapshot"], tmp, self.s.font_dir)
            raw = tmp.read_bytes()
            if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-1024:] or len(raw) < 500:
                raise RuntimeError("PDF не прошел проверку")
            sha = hashlib.sha256(raw).hexdigest()
            final = self.s.reports_dir / f"{report_id}.pdf"
            os.replace(tmp, final)
            now = utcnow()
            with self.db.write() as conn:
                if now >= parse_iso(job["deadline_at"]):
                    raise Abort()
                cur = conn.execute("UPDATE jobs SET state='succeeded', stage=NULL, result_id=?, updated_at=? WHERE id=? AND state='running'",
                                   (report_id, iso(now), job["id"]))
                if cur.rowcount != 1:
                    raise Abort()
                conn.execute("UPDATE reports SET state='ready', sha256=?, file_name=? WHERE id=? AND state='preparing'",
                             (sha, final.name, report_id))
            self.metrics.job_finished("report", "succeeded", None)
        except Abort:
            (self.s.reports_dir / f"{report_id}.pdf").unlink(missing_ok=True)
            raise
        finally:
            tmp.unlink(missing_ok=True)


def body_hash(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def new_job_id() -> str:
    return "job_" + secrets.token_hex(12)


def report_path(settings: Settings, file_name: str) -> Path:
    return settings.reports_dir / file_name
