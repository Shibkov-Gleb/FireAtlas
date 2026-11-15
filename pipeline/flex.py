"""Normalise the FLEX (PSI-69) experimental table into contract records."""
import csv
import io
from collections import Counter

from common import RAW, absent, clean, quantity, sha256_file, slug

PSI_ID = "PSI-69"
INV_ID = "inv_psi69_flex"
TABLE = RAW / "PSI-69" / "PSI-69_Experimental table_FLEX.csv"
SRC_TABLE = "src_psi69_experimental_table"
SRC_REPO = "src_psi69_repository"
DOI = "10.60555/mbq8-0451"
URL = "https://doi.org/" + DOI

# Column names exactly as in the source file. The file lost its subscripts:
# "O" is O2, "N" is N2 and "CO" is CO2 (the table has no carbon monoxide).
C_NUM, C_ID, C_DATE, C_GMT, C_FUEL = "FLEX Test #", "FLEX Identifier", "Test Date", "Test GMT", "Fuel"
C_P = "Ambient pressure; mmHg"
C_O2 = "O initial ambient composition; mole fraction"
C_N2 = "N initial ambient composition; mole fraction"
C_CO2 = "CO initial ambient composition; mole fraction"
C_HE = "He initial ambient composition; mole fraction"
C_D0 = "Droplet initial diameter; mm"
C_DEXT = "Visible flame extinction diameter; mm"
C_K = "Burning rate; mm"
C_T = "Burn time; s"
C_END = "Test end"
RAW_UNITS = {C_P: "mmHg", C_O2: "mole fraction", C_N2: "mole fraction", C_CO2: "mole fraction",
             C_HE: "mole fraction", C_D0: "mm", C_DEXT: "mm", C_K: None, C_T: "s"}

OUTCOMES = {"Extinction": "extinction", "Disruption": "disruption", "Completion": "burn_to_completion"}
MATERIALS = {
    "Methanol": {"id": "mat_methanol", "label": "Methanol", "state": "liquid", "composition": None,
                 "aliases": ["methanol"]},
    "Heptane": {"id": "mat_heptane", "label": "Heptane", "state": "liquid", "composition": None,
                "aliases": ["heptane", "n-heptane"]},
}


def read_table():
    # The file is Windows-1252 (it contains en dashes), not UTF-8.
    text = TABLE.read_bytes().decode("cp1252")
    return list(csv.DictReader(io.StringIO(text)))


def build(revision, retrieved_at):
    rows = read_table()
    id_counts = Counter(clean(r[C_ID]) for r in rows)
    runs, evidence, quarantine = [], [], []

    for r in rows:
        ident, num = clean(r[C_ID]), clean(r[C_NUM])
        key = slug(ident)
        ev_id, run_id = f"ev_psi69_{key}", f"run_psi69_{key}"
        problems = []
        if id_counts[ident] > 1:
            problems.append(f"source identifier {ident} occurs {id_counts[ident]} times with different values")
        try:
            if float(r[C_P]) <= 0:
                problems.append(f"ambient pressure {clean(r[C_P])} mmHg is not physical")
        except ValueError:
            problems.append("ambient pressure is not numeric")
        if clean(r[C_END]) not in OUTCOMES:
            problems.append(f"unmapped outcome label {clean(r[C_END])!r}")
        if clean(r[C_FUEL]) not in MATERIALS:
            problems.append(f"unknown fuel {clean(r[C_FUEL])!r}")
        if problems:
            quarantine.append({"investigation": PSI_ID, "row_key": f"FLEX Test # {num}",
                               "source_test_id": ident, "reasons": problems,
                               "raw": {k: clean(v) for k, v in r.items()}})
            continue

        notes = ["Chamber gas is nominally quiescent; the source table does not say whether the droplet "
                 "was free or fiber-supported or whether it was translated near the end of the test.",
                 "Source column 'Burning rate; mm' (average burning-rate constant, mm2/s) is kept as a raw value in "
                 "the evidence row; the contract has no metric key for it."]
        ev = [ev_id]
        q = {}
        for name, col, unit in [("pressure", C_P, "Pa"), ("o2", C_O2, "fraction"), ("n2", C_N2, "fraction"),
                                ("co2", C_CO2, "fraction"), ("he", C_HE, "fraction"), ("d0", C_D0, "m"),
                                ("dext", C_DEXT, "m"), ("t", C_T, "s")]:
            q[name], note = quantity(r[col], RAW_UNITS[col], unit, ev)
            if note:
                notes.append(f"{col}: {note}; not used as a number.")
        tags = []
        if (clean(r[C_CO2]) or "0") not in {"0", "0.0"}:
            tags.append("co2_diluted")
        if (clean(r[C_HE]) or "0") not in {"0", "0.0"}:
            tags.append("he_diluted")

        evidence.append({
            "id": ev_id, "data_revision": revision, "source_id": SRC_TABLE, "kind": "table_row",
            "locator": {"page": None, "section": None, "row_key": f"FLEX Test # {num} ({ident})",
                        "start_s": None, "end_s": None},
            "excerpt": None,
            "table_values": [{"field": c, "raw_value": clean(v) or None, "raw_unit": RAW_UNITS.get(c)}
                             for c, v in r.items()],
            "verified": True,
            "verification_note": "Row parsed from the original PSI-69 experimental table CSV "
                                 "(sha256 in sources.jsonl); raw values copied without change.",
        })
        metrics = [{"metric_key": "burn_duration", "quantity": q["t"]}]
        if q["dext"]["status"] != "not_reported":
            metrics.append({"metric_key": "visible_extinction_diameter", "quantity": q["dext"]})
        runs.append({
            "id": run_id, "data_revision": revision, "investigation_id": INV_ID,
            "source_test_id": ident, "material_id": MATERIALS[clean(r[C_FUEL])]["id"],
            "sample": {"geometry": "droplet", "thickness": absent("m", ev, "not_applicable"),
                       "initial_diameter": q["d0"]},
            "conditions": {
                "gravity_regime": "microgravity",
                "gravity_level": absent("g_fraction", ev),
                "oxygen_fraction": q["o2"], "nitrogen_fraction": q["n2"], "co2_fraction": q["co2"],
                "helium_fraction": q["he"], "pressure": q["pressure"],
                "airflow_speed": absent("m_s", ev),
                "flow_configuration": "quiescent",
                "ambient_temperature": absent("K", ev),
            },
            "metrics": metrics,
            "terminal_outcome": {"category": OUTCOMES[clean(r[C_END])], "raw_label": clean(r[C_END]),
                                 "interpretation_status": "source_explicit", "evidence_ids": ev},
            "regime_tags": tags, "evidence_ids": ev, "quality_notes": notes,
        })

    sources = [
        {"id": SRC_REPO, "data_revision": revision,
         "title": "Flame Extinguishment Experiment (FLEX), PSI-69, version 5",
         "kind": "repository", "canonical_url": URL, "doi": DOI, "publication_date": "2016-07-31",
         "retrieved_at": retrieved_at, "license": "CC0-1.0", "availability": "metadata_only",
         "local_asset_id": None, "sha256": None},
        {"id": SRC_TABLE, "data_revision": revision,
         "title": "PSI-69 Experimental table, FLEX (CSV)",
         "kind": "experimental_table", "canonical_url": URL, "doi": DOI, "publication_date": "2016-07-31",
         "retrieved_at": retrieved_at, "license": "CC0-1.0", "availability": "available",
         "local_asset_id": None, "sha256": sha256_file(TABLE)},
        {"id": "src_psi69_test_plan", "data_revision": revision, "title": "FLEX Test Plan (PSI-69 science document)",
         "kind": "report", "canonical_url": URL, "doi": DOI, "publication_date": None,
         "retrieved_at": retrieved_at, "license": "CC0-1.0", "availability": "available",
         "local_asset_id": None, "sha256": sha256_file(RAW / "PSI-69" / "FLEX_Test_Plan.pdf")},
        {"id": "src_psi69_dod", "data_revision": revision, "title": "FLEX data documentation, DoD (PSI-69 science document)",
         "kind": "report", "canonical_url": URL, "doi": DOI, "publication_date": None,
         "retrieved_at": retrieved_at, "license": "CC0-1.0", "availability": "available",
         "local_asset_id": None, "sha256": sha256_file(RAW / "PSI-69" / "FLEX DoD.docx")},
    ]
    meta_ev = "ev_psi69_metadata"
    evidence.append({
        "id": meta_ev, "data_revision": revision, "source_id": SRC_REPO, "kind": "metadata",
        "locator": {"page": None, "section": "Description: Objectives, Approach, Hardware",
                    "row_key": None, "start_s": None, "end_s": None},
        "excerpt": "The FLEX (Flame Extinguishment Experiment) investigation aims to map the flammability "
                   "limits of liquid fuels in microgravity environments, measure the effectiveness of various "
                   "gaseous fire suppressants such as CO2, He, and SF6, and develop reliable predictive models "
                   "for combustion limits under reduced gravity conditions.",
        "table_values": [], "verified": True,
        "verification_note": "Copied from the PSI-69 investigation page as displayed on 2026-11-14.",
    })
    investigation = {
        "id": INV_ID, "data_revision": revision, "psi_id": PSI_ID, "acronym": "FLEX",
        "title": "Flame Extinguishment Experiment",
        "objectives": [
            "Map the flammability limits of liquid fuels in microgravity.",
            "Measure the effectiveness of gaseous fire suppressants such as CO2, He and SF6.",
            "Develop predictive models for combustion limits under reduced gravity.",
        ],
        "setup_summary": "Isolated liquid-fuel droplets ignited in a sealed chamber of the Multi-user Droplet "
                         "Combustion Apparatus (MDCA) inside the Combustion Integrated Rack (CIR) on the ISS. "
                         "Ambient pressure, oxygen fraction and diluent (N2, CO2, He) were varied between tests.",
        "scopes": ["suppression"], "fuel_states": ["liquid"], "gravity_regimes": ["microgravity"],
        "material_ids": sorted({r["material_id"] for r in runs}),
        "source_ids": [SRC_REPO, SRC_TABLE, "src_psi69_test_plan", "src_psi69_dod"], "claim_ids": [],
        "conditions_coverage": coverage(runs, meta_ev, ("co2_fraction", "helium_fraction")),
        "available_assets": [SRC_TABLE, "src_psi69_test_plan", "src_psi69_dod"],
    }
    return {"investigations": [investigation], "materials": list(MATERIALS.values()), "runs": runs,
            "sources": sources, "evidence": evidence, "claims": [], "quarantine": quarantine}


def coverage(runs, meta_ev, extra=()):
    """Observed ranges; field is the full path of the run field (backend D-037)."""
    out = []
    fields = [("conditions.oxygen_fraction", lambda r: r["conditions"]["oxygen_fraction"]),
              ("conditions.pressure", lambda r: r["conditions"]["pressure"]),
              ("conditions.airflow_speed", lambda r: r["conditions"]["airflow_speed"]),
              ("sample.initial_diameter", lambda r: r["sample"]["initial_diameter"])]
    fields += [(f"conditions.{k}", (lambda k: lambda r: r["conditions"][k])(k)) for k in extra]
    for name, get in fields:
        qs = [get(r) for r in runs]
        vals = [x["value"] for x in qs if x["value"] is not None]
        out.append({"field": name, "min_value": min(vals) if vals else None,
                    "max_value": max(vals) if vals else None, "unit": qs[0]["unit"],
                    "known_count": len(vals), "unknown_count": len(qs) - len(vals),
                    "derivation_evidence_ids": [meta_ev]})
    return out
