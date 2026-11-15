"""Normalise SAME-R (PSI-101) into contract records.

Runs come from the PSI-101 experimental table. Particle diameter comes from
the 'Reduced data sheet' of the analysed-results workbook, joined on
(sample type, SAME test number) for flight 2 (SAME-R) rows only.
These are smoke measurements from heated (not flaming) samples.
"""
import csv
from collections import Counter

import openpyxl

from common import RAW, absent, clean, quantity, sha256_file, slug
from flex import coverage

PSI_ID = "PSI-101"
INV_ID = "inv_psi101_samer"
DIR = RAW / "PSI-101"
TABLE = DIR / "PSI-101_Experimental table_SAME-R.csv"
RESULTS = DIR / "Combined SAMER Results 06 02 14.xlsx"
SHEET = "Reduced data sheet"
DOI = "10.60555/2np7-jv14"
URL = "https://doi.org/" + DOI
SRC_REPO, SRC_TABLE, SRC_RESULTS = "src_psi101_repository", "src_psi101_experimental_table", "src_psi101_results"
C_AMD = "M1/M0 (micro-m)--AMD"
RAW_UNITS = {"Inlet velocity (cm/s)": "cm/s", "Duration (sec)": "s", "Primary aging time (sec)": "s",
             "Primary mixing time (sec)": "s", "Net aging time (sec)": "s"}
MATERIALS = {
    "Kapton": {"id": "mat_kapton", "label": "Kapton", "state": "solid", "composition": None,
               "aliases": ["Kapton", "polyimide"]},
    "Silicone": {"id": "mat_silicone_rubber", "label": "Silicone rubber", "state": "solid", "composition": None,
                 "aliases": ["Silicone", "silicone rubber"]},
    "Lampwick": {"id": "mat_lampwick", "label": "Lamp wick (cotton)", "state": "solid", "composition": None,
                 "aliases": ["Lampwick", "lamp wick", "cotton", "cellulose"]},
    "Teflon": {"id": "mat_teflon", "label": "Teflon", "state": "solid", "composition": None,
               "aliases": ["Teflon", "PTFE"]},
    "Pyrell": {"id": "mat_pyrell", "label": "Pyrell foam", "state": "solid", "composition": None,
               "aliases": ["Pyrell"]},
}


def read_results():
    """Flight-2 rows of the reduced data sheet keyed by (sample type, test number)."""
    wb = openpyxl.load_workbook(RESULTS, data_only=True, read_only=True)
    it = wb[SHEET].iter_rows(values_only=True)
    next(it)
    header = [clean(h) if h is not None else None for h in next(it)]
    out = {}
    for row in it:
        if str(row[0]) != "2":
            continue
        rec = {h: v for h, v in zip(header, row) if h}
        out[(str(rec["Sample Type"]).strip().lower(), str(rec["SAME #"]).strip().lower())] = rec
    return out


def build(revision, retrieved_at):
    rows = list(csv.DictReader(open(TABLE, encoding="ascii")))
    results = read_results()
    counts = Counter(clean(r["SAME Test #"]) for r in rows)
    runs, evidence, quarantine = [], [], []

    for r in rows:
        mat, test = clean(r["Sample Type"]), clean(r["SAME Test #"])
        res = results.get((mat.lower(), test.lower()))
        if counts[test] > 1 and res is None:
            quarantine.append({"investigation": PSI_ID, "row_key": f"{mat} test {test}", "source_test_id": test,
                               "reasons": [f"test number {test} is listed for more than one sample type and this "
                                           "row has no match in the analysed results; its identity is unclear"],
                               "raw": {k: clean(v) for k, v in r.items()}})
            continue
        key = f"{slug(mat)}_{slug(test)}"
        ev_id, run_id = f"ev_psi101_{key}", f"run_psi101_{key}"
        ev = [ev_id]
        notes = ["Smoke from a heated sample (oxidative pyrolysis), not a flaming test.",
                 "Oxygen fraction and pressure are not in the source table (ISS cabin atmosphere, not recorded "
                 "per test).",
                 "Rt/R0 and the heating, mixing and aging times are kept as raw values in the evidence row; "
                 "Rt/R0 is not interpreted."]
        tags = []
        if test.lower().endswith("a"):
            tags.append("aged_remeasurement")
            notes.append("Test number with suffix 'a' is a repeat measurement of the same smoke after aging, "
                         "not a new smoke generation.")
        airflow, note = quantity(r["Inlet velocity (cm/s)"], "cm/s", "m_s", ev)
        if note:
            notes.append(f"Inlet velocity: {note}.")
        notes.append("Airflow speed is the inlet velocity of the smoke-generation section.")

        evidence.append({
            "id": ev_id, "data_revision": revision, "source_id": SRC_TABLE, "kind": "table_row",
            "locator": {"page": None, "section": None, "row_key": f"{mat} test {test}", "start_s": None,
                        "end_s": None},
            "excerpt": None,
            "table_values": [{"field": c, "raw_value": clean(v) or None, "raw_unit": RAW_UNITS.get(c)}
                             for c, v in r.items()],
            "verified": True,
            "verification_note": "Row parsed from the original PSI-101 experimental table CSV "
                                 "(sha256 in sources.jsonl); raw values copied without change.",
        })
        metrics = []
        if res is not None:
            res_ev = f"ev_psi101_{key}_results"
            keep = [C_AMD, "Diameter of Average mass (micro-m)", "Hatch Choate Sigma g", "Hatch Choate Dg",
                    "Sample Temperature C", "Mass Loss (mg)", "Net Aging  Duration", "Description"]
            units = {C_AMD: "micron", "Diameter of Average mass (micro-m)": "micron", "Hatch Choate Dg": "micron",
                     "Sample Temperature C": "degC", "Mass Loss (mg)": "mg", "Net Aging  Duration": "s"}
            evidence.append({
                "id": res_ev, "data_revision": revision, "source_id": SRC_RESULTS, "kind": "table_row",
                "locator": {"page": None, "section": f"sheet '{SHEET}'", "row_key": f"flight 2, {mat} test {test}",
                            "start_s": None, "end_s": None},
                "excerpt": None,
                "table_values": [{"field": k, "raw_value": None if res.get(k) is None else str(res[k]),
                                  "raw_unit": units.get(k)} for k in keep],
                "verified": True,
                "verification_note": "Row read from the original analysed-results workbook downloaded from "
                                     "PSI-101 (cached cell values, sha256 in sources.jsonl).",
            })
            amd = res.get(C_AMD)
            if isinstance(amd, (int, float)) and amd > 0:
                q, _ = quantity(repr(float(amd)), "micron", "m", [res_ev])
                notes.append("particle_diameter is the arithmetic mean diameter M1/M0 (ratio of the first to the "
                             "zeroth moment) from the analysed results; other diameter definitions are in the "
                             "evidence row.")
            else:
                q = absent("m", [res_ev], "unusable")
                q.update(raw_value=None if amd is None else str(amd), raw_unit="micron")
                notes.append("The analysed results give a zero or empty mean diameter for this test; no particle "
                             "diameter is assigned.")
            metrics.append({"metric_key": "particle_diameter", "quantity": q})
            ev = ev + [res_ev]
        else:
            notes.append("No matching row in the analysed results; particle diameter is not available.")

        runs.append({
            "id": run_id, "data_revision": revision, "investigation_id": INV_ID, "source_test_id": test,
            "material_id": MATERIALS[mat]["id"],
            "sample": {"geometry": "other", "thickness": absent("m", ev[:1]),
                       "initial_diameter": absent("m", ev[:1], "not_applicable")},
            "conditions": {"gravity_regime": "microgravity", "gravity_level": absent("g_fraction", ev[:1]),
                           "oxygen_fraction": absent("fraction", ev[:1]),
                           "nitrogen_fraction": absent("fraction", ev[:1]), "co2_fraction": absent("fraction", ev[:1]),
                           "helium_fraction": absent("fraction", ev[:1]), "pressure": absent("Pa", ev[:1]),
                           "airflow_speed": airflow,
                           "flow_configuration": "quiescent" if airflow["value"] == 0 else "other",
                           "ambient_temperature": absent("K", ev[:1])},
            "metrics": metrics,
            "terminal_outcome": {"category": "smoke_measurement", "raw_label": None,
                                 "interpretation_status": "reviewed_mapping", "evidence_ids": ev[:1]},
            "regime_tags": tags, "evidence_ids": ev, "quality_notes": notes,
        })

    def src(sid, title, kind, path, avail="available"):
        return {"id": sid, "data_revision": revision, "title": title, "kind": kind, "canonical_url": URL,
                "doi": DOI, "publication_date": None, "retrieved_at": retrieved_at, "license": "CC0-1.0",
                "availability": avail, "local_asset_id": None, "sha256": sha256_file(path) if path else None}
    sources = [
        src(SRC_REPO, "Smoke and Aerosol Measurement Experiment - Reflight (SAME-R), PSI-101", "repository", None,
            "metadata_only"),
        src(SRC_TABLE, "PSI-101 Experimental table, SAME-R (CSV)", "experimental_table", TABLE),
        src(SRC_RESULTS, "Combined SAME-R Results workbook (PSI-101 analysed data)", "experimental_table", RESULTS),
        src("src_psi101_final_report", "SAME-R Final Report (PSI-101 report)", "report", DIR / "SAMER_Final 0602 2014.pdf"),
    ]
    meta_ev = "ev_psi101_metadata"
    evidence.append({
        "id": meta_ev, "data_revision": revision, "source_id": SRC_RESULTS, "kind": "metadata",
        "locator": {"page": None, "section": f"sheet '{SHEET}', header row", "row_key": None, "start_s": None,
                    "end_s": None},
        "excerpt": "Flight 1=same 2=sameR, g=ground; Sample Type; SAME #; Description; Inlet Velocity (cm/sec); "
                   "Rt/R0; Net Aging Duration; M0 best Diameter; M1 (mm/cm^3); M1/M0 (micro-m)--AMD; "
                   "Diameter of Average mass (micro-m)",
        "table_values": [], "verified": True,
        "verification_note": "Column headers copied from the original workbook.",
    })
    investigation = {
        "id": INV_ID, "data_revision": revision, "psi_id": PSI_ID, "acronym": "SAME-R",
        "title": "Smoke and Aerosol Measurement Experiment - Reflight",
        "objectives": ["Measure the size and amount of smoke particles produced by overheated spacecraft "
                       "materials in microgravity to support the design of spacecraft smoke detectors."],
        "setup_summary": "Small samples of five spacecraft materials were heated below ignition in a controlled "
                         "air flow on the ISS; the smoke was measured directly and again after aging in a chamber.",
        "scopes": ["detection"], "fuel_states": ["solid"], "gravity_regimes": ["microgravity"],
        "material_ids": sorted({r["material_id"] for r in runs}),
        "source_ids": [s["id"] for s in sources] + ["src_ntrs_20130000422"], "claim_ids": [],
        "conditions_coverage": coverage(runs, meta_ev),
        "available_assets": [SRC_TABLE, SRC_RESULTS, "src_psi101_final_report"],
    }
    return {"investigations": [investigation], "materials": list(MATERIALS.values()), "runs": runs,
            "sources": sources, "evidence": evidence, "claims": [], "quarantine": quarantine}
