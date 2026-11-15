"""BE-12 / BE-13: метрики, бэкап и восстановление, запрет заглушек в production."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

import pytest

from conftest import FIX_REV, ROOT, poll, prepared_settings, start_analysis
from fire_atlas_api.cli import backup, restore
from fire_atlas_api.settings import Settings


def test_internal_metrics_requires_token(make_server):
    with make_server(internal_token="s3cret") as srv:
        cl = srv.client()
        cl.post("/api/v1/workspaces", {})
        poll(cl, start_analysis(cl)[0].data["id"])
        assert cl.get("/internal/metrics").status == 404
        assert cl.get("/internal/metrics", headers={"Authorization": "Bearer wrong"}).status == 404
        r = cl.get("/internal/metrics", headers={"Authorization": "Bearer s3cret"})
        assert r.status == 200
        m = r.json
        assert m["routes"]["POST /api/v1/analyses"]["statuses"] == {"202": 1}
        assert {"analysis.retrieving", "analysis.reasoning"} <= set(m["job_stages"])
        assert {"type": "analysis", "state": "succeeded", "error_code": "-", "count": 1} in m["job_outcomes"]
        assert "Как поток воздуха" not in r.raw.decode()  # текст вопроса не попадает в метрики


def test_backup_and_restore_roundtrip(tmp_path, release_dir):
    s = prepared_settings(tmp_path, release_dir)
    from dataclasses import replace
    s = replace(s, backups_dir=tmp_path / "backups")
    info = backup(s)
    assert info["integrity_ok"] and info["active_revision"] == FIX_REV
    assert json.loads((tmp_path / "backups" / (os.path.basename(info["file"])[:-8] + ".json")).read_text())["sha256"] == info["sha256"]
    s.db_path.unlink()
    out = restore(s, __import__("pathlib").Path(info["file"]))
    assert out["restored"] and out["entities_by_revision"] == {FIX_REV: 28}
    bad = tmp_path / "bad.sqlite3"
    bad.write_bytes(b"not a database")
    with pytest.raises(Exception):
        restore(s, bad)


def test_production_refuses_stub_analysis():
    env = {**os.environ, "FA_ENV": "production", "FA_CURSOR_SECRET": "x" * 32, "FA_FEATURE_ANALYSIS": "true",
           "FA_RETRIEVER": "stub", "FA_REASONER": "stub", "FA_APPLICABILITY": "stub",
           "PYTHONIOENCODING": "utf-8"}  # сообщение на русском читается одинаково на любой консоли (Windows: cp1251)
    code = "import fire_atlas_api.settings as s; s.Settings.from_env()"
    r = subprocess.run([sys.executable, "-c", code], env={**env, "PYTHONPATH": str(ROOT / "apps" / "api")},
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode != 0 and "заглушками" in r.stderr
    ok = subprocess.run([sys.executable, "-c", code], env={**env, "FA_FEATURE_ANALYSIS": "false",
                                                           "PYTHONPATH": str(ROOT / "apps" / "api")}, capture_output=True)
    assert ok.returncode == 0
