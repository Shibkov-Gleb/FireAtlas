"""BE-02 / CT-09: атомарный импорт. AT-01, AT-02."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import FIX_REV
from fire_atlas_api.db import Database
from fire_atlas_api.importer import _sha256, import_release


def _copy(release_dir: Path, tmp: Path) -> Path:
    dst = tmp / "rel"
    shutil.copytree(release_dir / "rel", dst)
    return dst


def _rewrite(rel: Path, fname: str, mutate) -> None:
    """Изменяет JSONL и честно пересчитывает sha256/record_count в manifest (проверяем семантику, а не хеш)."""
    p = rel / fname
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = mutate(rows)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    m = json.loads((rel / "manifest.json").read_text(encoding="utf-8"))
    for f in m["files"]:
        if f["path"] == fname:
            f["sha256"] = _sha256(p)
            f["record_count"] = len(rows)
    (rel / "manifest.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")


def _set_rev(rel: Path, new_rev: str) -> None:
    for p in rel.glob("*.jsonl"):
        p.write_text(p.read_text(encoding="utf-8").replace(f'"{FIX_REV}"', f'"{new_rev}"'), encoding="utf-8")
    m = json.loads((rel / "manifest.json").read_text(encoding="utf-8"))
    m["data_revision"] = new_rev
    for f in m["files"]:
        f["sha256"] = _sha256(rel / f["path"])
    (rel / "manifest.json").write_text(json.dumps(m), encoding="utf-8")


@pytest.fixture
def db(tmp_path) -> Database:
    d = Database(tmp_path / "db.sqlite3")
    d.migrate()
    return d


def test_at01_clean_import_counts_and_idempotency(db, release_dir):
    rep = import_release(db, release_dir / "rel", "dev")
    assert rep["accepted"] and rep["data_revision"] == FIX_REV
    assert rep["entity_counts"] == {"investigation": 3, "material": 2, "run": 6, "source": 5, "evidence": 9, "claim": 3}
    assert db.active_revision() == FIX_REV
    again = import_release(db, release_dir / "rel", "dev")
    assert again["accepted"] and any(w["code"] == "ALREADY_IMPORTED" for w in again["warnings"])
    with db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 28


def test_p0_profile_blocks_insufficient_corpus(db, release_dir):
    rep = import_release(db, release_dir / "rel", "p0")
    assert not rep["accepted"]
    assert {e["code"] for e in rep["errors"]} == {"P0_COUNT"}
    assert db.active_revision() is None


def test_at02_dangling_reference_rejects_whole_release(db, release_dir, tmp_path):
    assert import_release(db, release_dir / "rel", "dev")["accepted"]
    rel = _copy(release_dir, tmp_path)
    _set_rev(rel, "fixture-20261115-r2")
    _rewrite(rel, "runs.jsonl", lambda rows: [dict(r, evidence_ids=["ev_does_not_exist"]) if i == 0 else r
                                              for i, r in enumerate(rows)])
    rep = import_release(db, rel, "dev")
    assert not rep["accepted"]
    assert any(e["code"] == "DANGLING_REFERENCE" and e["file"] == "runs.jsonl" and e["line"] == 1 for e in rep["errors"])
    assert db.active_revision() == FIX_REV
    assert not db.revision_exists("fixture-20261115-r2")


def test_sha_mismatch_rejected(db, release_dir, tmp_path):
    rel = _copy(release_dir, tmp_path)
    with (rel / "claims.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("\n")  # пустая строка не меняет смысл, но меняет хеш
    rep = import_release(db, rel, "dev")
    assert not rep["accepted"] and rep["errors"][0]["code"] == "SHA256_MISMATCH"


def test_same_revision_different_content_is_immutable(db, release_dir, tmp_path):
    assert import_release(db, release_dir / "rel", "dev")["accepted"]
    rel = _copy(release_dir, tmp_path)
    _rewrite(rel, "materials.jsonl", lambda rows: [dict(r, aliases=r["aliases"] + ["x"]) for r in rows])
    rep = import_release(db, rel, "dev")
    assert not rep["accepted"] and rep["errors"][0]["code"] == "REVISION_IMMUTABLE"


@pytest.mark.parametrize("fname,mutate,code", [
    ("runs.jsonl", lambda rows: rows + [rows[0] | {"quality_notes": ["другое"]}], "DUPLICATE_ID"),
    ("evidence.jsonl", lambda rows: [dict(r, verified=False) if i == 0 else r for i, r in enumerate(rows)], "UNVERIFIED_EVIDENCE"),
    ("runs.jsonl", lambda rows: [_mut_outcome(r) for r in rows], "OUTCOME_MAPPING"),
    ("runs.jsonl", lambda rows: [_mut_oxygen(r) for r in rows], "VALUE_OUT_OF_RANGE"),
    ("runs.jsonl", lambda rows: [_mut_metric_unit(r) for r in rows], "SCHEMA_INVALID"),
    ("claims.jsonl", lambda rows: [dict(r, extra_field=1) for r in rows], "SCHEMA_INVALID"),
])
def test_blocking_errors(db, release_dir, tmp_path, fname, mutate, code):
    rel = _copy(release_dir, tmp_path)
    _rewrite(rel, fname, mutate)
    rep = import_release(db, rel, "dev")
    assert not rep["accepted"]
    assert code in {e["code"] for e in rep["errors"]}, rep["errors"]
    assert db.active_revision() is None


def test_nan_in_jsonl_rejected(db, release_dir, tmp_path):
    rel = _copy(release_dir, tmp_path)
    p = rel / "runs.jsonl"
    p.write_text(p.read_text(encoding="utf-8").replace('"value":6.34', '"value":NaN', 1), encoding="utf-8")
    m = json.loads((rel / "manifest.json").read_text())
    for f in m["files"]:
        if f["path"] == "runs.jsonl":
            f["sha256"] = _sha256(p)
    (rel / "manifest.json").write_text(json.dumps(m))
    rep = import_release(db, rel, "dev")
    assert not rep["accepted"] and rep["errors"][0]["code"] == "JSON_INVALID"


def test_path_traversal_rejected(db, release_dir, tmp_path):
    rel = _copy(release_dir, tmp_path)
    m = json.loads((rel / "manifest.json").read_text())
    m["files"][0]["path"] = "../../etc/passwd"
    (rel / "manifest.json").write_text(json.dumps(m))
    rep = import_release(db, rel, "dev")
    assert not rep["accepted"] and rep["errors"][0]["code"] == "MANIFEST_INVALID"


def _mut_outcome(r):
    if r["source_test_id"] == "20CAL08":  # Disruption нельзя переименовать в погасание (DR-05)
        r["terminal_outcome"]["category"] = "extinction"
    return r


def _mut_oxygen(r):
    if r["source_test_id"] == "30CAL03":
        r["conditions"]["oxygen_fraction"]["value"] = 21.0  # проценты вместо доли
    return r


def _mut_metric_unit(r):
    if r["metrics"]:
        r["metrics"][0]["quantity"]["unit"] = "furlong"
    return r
