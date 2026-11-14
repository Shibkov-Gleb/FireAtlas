"""CLI бэкенда.

    python3 -m fire_atlas_api.cli migrate
    python3 -m fire_atlas_api.cli import data/releases/<rev> [--profile p0|dev] [--no-activate]
    python3 -m fire_atlas_api.cli validate data/releases/<rev> [--profile p0]   # проверка без записи (для AI 1)
    python3 -m fire_atlas_api.cli serve [--host 127.0.0.1] [--port 8000]
    python3 -m fire_atlas_api.cli backup                       # онлайн-копия БД + manifest (BE-13)
    python3 -m fire_atlas_api.cli restore <backup.sqlite3>     # только при остановленном сервере
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import logging
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .db import Database
from .importer import import_release, validate_release
from .settings import Settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fire_atlas_api")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    imp = sub.add_parser("import")
    imp.add_argument("release_dir", type=Path)
    imp.add_argument("--profile", choices=["dev", "p0"])
    imp.add_argument("--no-activate", action="store_true")
    val = sub.add_parser("validate")
    val.add_argument("release_dir", type=Path)
    val.add_argument("--profile", choices=["dev", "p0"], default="p0")
    stg = sub.add_parser("stage-assets", help="D-038: разложить файлы источников по sha256 в FA_ASSETS_DIR")
    stg.add_argument("release_dir", type=Path)
    stg.add_argument("raw_dir", type=Path)
    sub.add_parser("backup")
    rst = sub.add_parser("restore")
    rst.add_argument("backup_file", type=Path)
    srv = sub.add_parser("serve")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings.from_env()
    if a.cmd == "migrate":
        n = Database(settings.db_path).migrate()
        print(json.dumps({"applied_migrations": n, "db": str(settings.db_path)}))
        return 0
    if a.cmd == "validate":
        rep, manifest, entities, _ = validate_release(a.release_dir, a.profile)
        out = {"accepted": not rep.errors, "data_revision": (manifest or {}).get("data_revision"),
               "entity_counts": {t: len(v) for t, v in entities.items()}, "errors": rep.errors, "warnings": rep.warnings}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["accepted"] else 1
    if a.cmd == "stage-assets":
        from .importer import stage_assets

        out = stage_assets(a.release_dir, a.raw_dir, settings.assets_dir)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "import":
        db = Database(settings.db_path)
        db.migrate()
        report = import_release(db, a.release_dir, a.profile or settings.import_profile, activate=not a.no_activate,
                                assets_dir=settings.assets_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["accepted"] else 1
    if a.cmd == "backup":
        out = backup(settings)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "restore":
        out = restore(settings, a.backup_file)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["restored"] else 1
    if a.cmd == "serve":
        import uvicorn

        from .app import build_app

        # Адрес клиента (лимит поиска на адрес) берется из X-Forwarded-For только от доверенного прокси.
        # В compose это nginx в соседнем контейнере: FA_FORWARDED_ALLOW_IPS=* (API наружу не опубликован).
        trusted = os.environ.get("FA_FORWARDED_ALLOW_IPS", "127.0.0.1")
        uvicorn.run(build_app(settings), host=a.host, port=a.port, proxy_headers=True, forwarded_allow_ips=trusted,
                    log_config=None)
        return 0
    return 2


def _check(path: Path) -> dict:
    conn = sqlite3.connect(path)
    try:
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        mig = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        active = conn.execute("SELECT data_revision FROM active_release WHERE singleton=1").fetchone()
        counts = dict(conn.execute("SELECT data_revision, COUNT(*) FROM entities GROUP BY data_revision").fetchall())
        return {"integrity_ok": ok, "schema_version": mig, "active_revision": active[0] if active else None,
                "entities_by_revision": counts}
    finally:
        conn.close()


def backup(settings: Settings) -> dict:
    """Онлайн-копия через SQLite backup API: безопасна при работающем сервере (WAL)."""
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = settings.backups_dir / f"fire_atlas-{stamp}.sqlite3"
    src = sqlite3.connect(settings.db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    info = _check(target)
    if not info["integrity_ok"]:
        target.unlink(missing_ok=True)
        raise SystemExit("backup failed integrity_check")
    info.update({"file": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "created_at": stamp})
    target.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def restore(settings: Settings, backup_file: Path) -> dict:
    """Заменяет БД проверенной копией. Сервер должен быть остановлен (см. docs/runbook.md)."""
    info = _check(backup_file)
    if not info["integrity_ok"] or info["active_revision"] is None:
        return {"restored": False, "reason": "копия повреждена или в ней нет активной ревизии", **info}
    meta = backup_file.with_suffix(".json")
    if meta.exists():
        expected = json.loads(meta.read_text(encoding="utf-8"))["sha256"]
        if hashlib.sha256(backup_file.read_bytes()).hexdigest() != expected:
            return {"restored": False, "reason": "sha256 копии не совпадает с manifest", **info}
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(settings.db_path) + suffix)
        if p.exists():
            shutil.move(p, str(p) + ".before-restore")
    shutil.copy2(backup_file, settings.db_path)
    Database(settings.db_path).migrate()
    return {"restored": True, "db": str(settings.db_path), **info}


if __name__ == "__main__":
    sys.exit(main())
