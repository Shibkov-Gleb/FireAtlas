#!/usr/bin/env python3
"""Fire Atlas, AI 1, task A1-01: download the original NASA source files.

Downloads the P0 source files for BASS-II (PSI-25), FLEX (PSI-69) and
SAME-R (PSI-101) from the NASA PSI repository, plus four NTRS reports,
into data/raw/. For every file it records sha256, size, URL and retrieval
time in data/raw/download_log.json (needed for Source.retrieved_at).

Usage (from the repository root):  python3 scripts/download_sources.py
Only the Python standard library is used. Existing files are skipped;
pass --force to download them again.
"""
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LOG = RAW / "download_log.json"
WS = "https://psi.nasa.gov/geode-py/ws"
UA = {"User-Agent": "FireAtlas-SpaceApps2026/1.0"}

PSI_FILES = {
    "PSI-25": [
        "PSI-25_Experimental table_BASS-II.csv",
        "PSI-25_Reference Data_Fan calibration data.xlsx",
        "PSI-25_Science Documents_BASS-II_ReadMe.docx",
        "PSI-25_Science Documents_BASS-II_Test.Matrices.xlsx",
        "PSI-25_Reports_BASS-II Summary Report.pdf",
    ],
    "PSI-69": [
        "PSI-69_Experimental table_FLEX.csv",
        "PSI-69_Science Documents_FLEX DoD.docx",
        "PSI-69_Science Documents_FLEX_Test_Plan.pdf",
    ],
    "PSI-101": [
        "PSI-101_Experimental table_SAME-R.csv",
        "PSI-101_Analyzed Data_SAME, SAME-R_Results.xlsx",
        "PSI-101_Reports_SAME-R_Final Report.pdf",
    ],
}
# NTRS citation id -> short label
NTRS = {
    "20160000593": "BASS-II results poster (Ferkul et al., 2014)",
    "20150023456": "FLEX detailed results, NASA/TP-2015-216046",
    "20130000422": "SAME-2 particle morphology and size (AIAA 2012-3536)",
    "20150010172": "SAME-R particle morphology (2012)",
}


def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def psi_download(acc, fname):
    """Return (bytes, url_used). PSI answers with a pre-signed S3 URL."""
    q = urllib.parse.urlencode({"file": fname, "redirect": "false"})
    api = f"{WS}/studies/{acc}/download?{q}"
    body = fetch(api, timeout=120)
    text = body[:4000].decode("utf-8", "replace").strip().strip('"')
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            text = next((v for v in obj.values() if isinstance(v, str) and v.startswith("http")), text)
        except ValueError:
            pass
    if text.startswith("http"):
        return fetch(text), api
    # The API returned the file itself instead of a URL.
    return body, api


def main():
    force = "--force" in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)
    log = json.loads(LOG.read_text()) if LOG.exists() else {}
    jobs = []
    for acc, names in PSI_FILES.items():
        for n in names:
            jobs.append(("psi", acc, n, RAW / acc / n))
    for cid in NTRS:
        jobs.append(("ntrs", cid, f"{cid}.pdf", RAW / "NTRS" / f"{cid}.pdf"))

    failed = []
    for kind, ident, name, dest in jobs:
        rel = str(dest.relative_to(ROOT))
        if dest.exists() and rel in log and not force:
            print(f"skip   {rel}")
            continue
        try:
            if kind == "psi":
                data, url = psi_download(ident, name)
                page = f"https://psi.nasa.gov/physci/repo/data/studies/{ident}"
            else:
                url = f"https://ntrs.nasa.gov/api/citations/{ident}/downloads/{ident}.pdf"
                data = fetch(url)
                page = f"https://ntrs.nasa.gov/citations/{ident}"
            if len(data) < 200 or data[:15].lstrip().lower().startswith((b"<!doctype", b"<html")):
                raise ValueError(f"unexpected content ({len(data)} bytes)")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            log[rel] = {
                "source": ident,
                "file": name,
                "note": NTRS.get(ident, ""),
                "landing_page": page,
                "download_url": url,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            print(f"ok     {rel}  ({len(data):,} bytes)")
        except (urllib.error.URLError, OSError, ValueError) as e:
            failed.append(rel)
            print(f"FAILED {rel}: {e}")
        LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n")

    print(f"\n{len(jobs) - len(failed)}/{len(jobs)} files present; log: {LOG.relative_to(ROOT)}")
    if failed:
        print("Not downloaded:\n  " + "\n  ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
