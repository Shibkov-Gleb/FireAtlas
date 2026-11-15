"""SQLite-хранилище: неизменяемые ревизии корпуса и гостевые пространства.

* WAL + busy_timeout: параллельные чтения, сериализованные записи.
* Запись - только через `write()` (BEGIN IMMEDIATE), чтобы условные обновления
  (revision пространства, состояние Job) были атомарными.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

MIGRATIONS: list[str] = [
    # 001 - корпус и пространства
    """
    CREATE TABLE releases (
        data_revision   TEXT PRIMARY KEY,
        manifest_sha256 TEXT NOT NULL,
        schema_version  TEXT NOT NULL,
        producer        TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        imported_at     TEXT NOT NULL,
        entity_counts   TEXT NOT NULL
    );
    CREATE TABLE active_release (
        singleton     INTEGER PRIMARY KEY CHECK (singleton = 1),
        data_revision TEXT NOT NULL REFERENCES releases(data_revision),
        activated_at  TEXT NOT NULL
    );
    CREATE TABLE entities (
        data_revision    TEXT NOT NULL REFERENCES releases(data_revision),
        entity_type      TEXT NOT NULL,
        id               TEXT NOT NULL,
        investigation_id TEXT,
        sort_key         TEXT NOT NULL,
        body             TEXT NOT NULL,
        PRIMARY KEY (data_revision, entity_type, id)
    );
    CREATE INDEX entities_by_inv ON entities (data_revision, entity_type, investigation_id, sort_key, id);
    CREATE TABLE workspaces (
        id            TEXT PRIMARY KEY,
        session_hash  TEXT NOT NULL UNIQUE,
        revision      INTEGER NOT NULL CHECK (revision >= 1),
        data_revision TEXT NOT NULL,
        state         TEXT NOT NULL,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        expires_at    TEXT NOT NULL
    );
    CREATE TABLE answers (
        id            TEXT PRIMARY KEY,
        workspace_id  TEXT NOT NULL REFERENCES workspaces(id),
        data_revision TEXT NOT NULL,
        body          TEXT NOT NULL,
        created_at    TEXT NOT NULL
    );
    CREATE INDEX answers_by_ws ON answers (workspace_id);
    """,
    # 002 - фоновые задачи, идемпотентность, отчеты (BE-08, BE-09, BE-10)
    """
    CREATE TABLE jobs (
        id                    TEXT PRIMARY KEY,
        workspace_id          TEXT NOT NULL REFERENCES workspaces(id),
        type                  TEXT NOT NULL CHECK (type IN ('analysis', 'report')),
        state                 TEXT NOT NULL CHECK (state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'expired')),
        stage                 TEXT,
        created_at            TEXT NOT NULL,
        updated_at            TEXT NOT NULL,
        deadline_at           TEXT NOT NULL,
        result_id             TEXT,
        error                 TEXT,
        input                 TEXT NOT NULL,
        fallback_evidence_ids TEXT NOT NULL DEFAULT '[]',
        timings               TEXT NOT NULL DEFAULT '{}',
        attempts              INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX jobs_by_ws ON jobs (workspace_id, type, state, created_at);
    CREATE INDEX jobs_active ON jobs (state, deadline_at);
    CREATE TABLE idempotency_keys (
        workspace_id TEXT NOT NULL,
        operation    TEXT NOT NULL,
        key          TEXT NOT NULL,
        body_hash    TEXT NOT NULL,
        job_id       TEXT NOT NULL REFERENCES jobs(id),
        created_at   TEXT NOT NULL,
        PRIMARY KEY (workspace_id, operation, key)
    );
    CREATE TABLE reports (
        id                        TEXT PRIMARY KEY,
        workspace_id              TEXT NOT NULL REFERENCES workspaces(id),
        job_id                    TEXT NOT NULL REFERENCES jobs(id),
        state                     TEXT NOT NULL CHECK (state IN ('preparing', 'ready', 'failed', 'expired')),
        title                     TEXT NOT NULL,
        source_workspace_revision INTEGER NOT NULL,
        data_revision             TEXT NOT NULL,
        created_at                TEXT NOT NULL,
        expires_at                TEXT NOT NULL,
        sha256                    TEXT,
        error                     TEXT,
        file_name                 TEXT
    );
    CREATE INDEX reports_by_ws ON reports (workspace_id)
    """,
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def plus(dt: datetime, **kw) -> datetime:
    return dt + timedelta(**kw)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False, sort_keys=True)


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextlib.contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")
        finally:
            conn.close()

    def migrate(self) -> int:
        with self.write() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
            applied = 0
            for i, sql in enumerate(MIGRATIONS, start=1):
                if i in done:
                    continue
                for stmt in filter(None, (s.strip() for s in sql.split(";"))):
                    conn.execute(stmt)
                conn.execute("INSERT INTO schema_migrations VALUES (?, ?)", (i, iso(utcnow())))
                applied += 1
            return applied

    def ping(self) -> bool:
        try:
            with self.read() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    # --- корпус ---------------------------------------------------------
    def active_revision(self) -> str | None:
        with self.read() as conn:
            row = conn.execute("SELECT data_revision FROM active_release WHERE singleton = 1").fetchone()
            return row[0] if row else None

    def revision_exists(self, rev: str) -> bool:
        with self.read() as conn:
            return conn.execute("SELECT 1 FROM releases WHERE data_revision = ?", (rev,)).fetchone() is not None

    def get_entity(self, rev: str, etype: str, id_: str) -> dict | None:
        with self.read() as conn:
            row = conn.execute(
                "SELECT body FROM entities WHERE data_revision = ? AND entity_type = ? AND id = ?", (rev, etype, id_)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def get_entities(self, rev: str, etype: str, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        with self.read() as conn:
            qmarks = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT id, body FROM entities WHERE data_revision = ? AND entity_type = ? AND id IN ({qmarks})",
                (rev, etype, *ids),
            ).fetchall()
            return {r["id"]: json.loads(r["body"]) for r in rows}

    def existing_ids(self, rev: str, etype: str, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        with self.read() as conn:
            qmarks = ",".join("?" * len(ids))
            return {row[0] for row in conn.execute(
                f"SELECT id FROM entities WHERE data_revision = ? AND entity_type = ? AND id IN ({qmarks})",
                (rev, etype, *ids),
            )}

    def runs_for(self, rev: str, inv_ids: list[str]) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {i: [] for i in inv_ids}
        if not inv_ids:
            return out
        with self.read() as conn:
            q = ",".join("?" * len(inv_ids))
            for r in conn.execute(f"SELECT investigation_id, body FROM entities WHERE data_revision = ? AND entity_type = 'run' "
                                  f"AND investigation_id IN ({q}) ORDER BY sort_key, id", (rev, *inv_ids)):
                out[r["investigation_id"]].append(json.loads(r["body"]))
        return out
