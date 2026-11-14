#!/usr/bin/env python3
"""Build and validate a Fire Atlas data release (spec section 12, CT-09).

Usage (from the repository root):
    python3 pipeline/build_release.py [data_revision]
Writes data/releases/<data_revision>/ with manifest.json, six JSONL files and
quarantine.json. Exits with code 1 if any blocking error is found.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bass2  # noqa: E402
import flex  # noqa: E402
import samer  # noqa: E402
from common import (ID_RE, RAW, ROOT, SCHEMA_VERSION, check_quantity,  # noqa: E402
                    sha256_file, write_jsonl)

ENTITIES = ["investigations", "materials", "runs", "sources", "evidence", "claims"]
OUTCOME_CATEGORIES = {"no_ignition", "extinction", "burn_to_completion", "disruption",
                      "ongoing_at_stop", "smoke_measurement", "unknown"}


def validate(data, revision):
    """Blocking checks from spec section 21.3. Returns (errors, warnings)."""
    errors, warnings = [], 0
    ids = {}
    for entity in ENTITIES:
        for rec in data[entity]:
            if not ID_RE.match(rec["id"]):
                errors.append(f"{entity}: bad id {rec['id']!r}")
            if rec["id"] in ids:
                errors.append(f"duplicate id {rec['id']}")
            ids[rec["id"]] = entity
            if "data_revision" in rec and rec["data_revision"] != revision:
                errors.append(f"{rec['id']}: revision mismatch")

    def ref(owner, target, kind):
        if ids.get(target) != kind:
            errors.append(f"{owner}: dangling {kind} reference {target}")

    for ev in data["evidence"]:
        ref(ev["id"], ev["source_id"], "sources")
        if not ev["verified"]:
            errors.append(f"{ev['id']}: unverified evidence in release")
        if ev["kind"] == "table_row" and not (ev["locator"]["row_key"] and ev["table_values"]):
            errors.append(f"{ev['id']}: table_row without row_key/table_values")
    for src in data["sources"]:
        if not src["canonical_url"].startswith("https://"):
            errors.append(f"{src['id']}: canonical_url is not HTTPS")
    for inv in data["investigations"]:
        for m in inv["material_ids"]:
            ref(inv["id"], m, "materials")
        for s in inv["source_ids"] + inv["available_assets"]:
            ref(inv["id"], s, "sources")
    for run in data["runs"]:
        ref(run["id"], run["investigation_id"], "investigations")
        ref(run["id"], run["material_id"], "materials")
        for e in run["evidence_ids"] + run["terminal_outcome"]["evidence_ids"]:
            ref(run["id"], e, "evidence")
        if run["terminal_outcome"]["category"] not in OUTCOME_CATEGORIES:
            errors.append(f"{run['id']}: bad outcome category")
        quantities = [("thickness", run["sample"]["thickness"]),
                      ("initial_diameter", run["sample"]["initial_diameter"])]
        quantities += [(k, v) for k, v in run["conditions"].items() if isinstance(v, dict)]
        quantities += [(m["metric_key"], m["quantity"]) for m in run["metrics"]]
        for name, q in quantities:
            check_quantity(q, f"{run['id']}.{name}", errors)
            for e in q["evidence_ids"]:
                ref(run["id"], e, "evidence")
            if q["status"] in {"not_reported", "unusable"}:
                warnings += 1
    return errors, warnings


def control_check(data):
    """Appendix A of the spec: five FLEX methanol rows must normalise exactly."""
    expected = {"20CAL08": (1.69e-3, 4.3, "disruption", 757.7), "20CAL10": (1.86e-3, 5.0, "extinction", 762.0),
                "20CAL12": (1.61e-3, 3.2, "extinction", 764.2), "30CAL02": (2.06e-3, 7.64, "extinction", 760.0),
                "30CAL03": (1.92e-3, 6.34, "extinction", 760.0)}
    runs = {r["source_test_id"]: r for r in data["runs"]}
    errors = []
    for ident, (d0, t, outcome, mmhg) in expected.items():
        r = runs.get(ident)
        if r is None:
            errors.append(f"control row {ident} missing")
            continue
        burn = next(m["quantity"]["value"] for m in r["metrics"] if m["metric_key"] == "burn_duration")
        ok = (abs(r["sample"]["initial_diameter"]["value"] / d0 - 1) <= 1e-6 and abs(burn - t) <= 1e-9
              and r["terminal_outcome"]["category"] == outcome
              and abs(r["conditions"]["pressure"]["value"] - mmhg * 133.322387) <= 1.0
              and abs(r["conditions"]["oxygen_fraction"]["value"] - 0.21) <= 1e-9)
        if not ok:
            errors.append(f"control row {ident} does not match Appendix A")
    return errors


def main():
    revision = sys.argv[1] if len(sys.argv) > 1 else "psi-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-r1"
    log = json.loads((RAW / "download_log.json").read_text())
    retrieved = {v["source"]: v["retrieved_at"] for v in log.values()}

    data = {e: [] for e in ENTITIES + ["quarantine"]}
    for module in (bass2, flex, samer):
        part = module.build(revision, retrieved[module.PSI_ID])
        for k in data:
            data[k].extend(part[k])

    errors, warnings = validate(data, revision)
    errors += control_check(data)
    out = ROOT / "data" / "releases" / revision
    files = []
    for entity in ENTITIES:
        path = out / f"{entity}.jsonl"
        write_jsonl(path, data[entity])
        files.append({"path": path.name, "entity_type": entity, "sha256": sha256_file(path),
                      "record_count": len(data[entity])})
    (out / "quarantine.json").write_text(json.dumps(data["quarantine"], indent=2, ensure_ascii=False) + "\n")
    checked = sum(f["record_count"] for f in files) + len(data["quarantine"])
    manifest = {"schema_version": SCHEMA_VERSION, "data_revision": revision,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "producer": "fire-atlas pipeline (AI 1)", "files": files,
                "quality_summary": {"checked_records": checked, "quarantined_records": len(data["quarantine"]),
                                    "blocking_errors": len(errors), "warning_count": warnings}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    for f in files:
        print(f"{f['record_count']:>5}  {f['path']}")
    per_inv = {}
    for run in data["runs"]:
        per_inv[run["investigation_id"]] = per_inv.get(run["investigation_id"], 0) + 1
    for inv, n in sorted(per_inv.items()):
        print(f"{n:>5}  runs in {inv}" + ("" if n >= 10 else "  (below the P0 minimum of 10)"))
    print(f"{len(data['quarantine']):>5}  quarantined (see quarantine.json)")
    print(f"warnings: {warnings}, blocking errors: {len(errors)}")
    for e in errors[:30]:
        print("  ERROR", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
