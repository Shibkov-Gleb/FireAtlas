"""Normalise the BASS-II (PSI-25) experimental table into contract records.

The table is a crew operations log, not a results table: it has no outcome,
no flame spread rate and no pressure column. Nothing is inferred for them.
"""
import csv
import io
import re

from common import RAW, absent, clean, quantity, sha256_file, slug
from flex import coverage

PSI_ID = "PSI-25"
INV_ID = "inv_psi25_bass2"
DIR = RAW / "PSI-25"
TABLE = DIR / "PSI-25_Experimental table_BASS-II.csv"
FAQ = DIR / "BASS-II data FAQ.docx"
FANCAL = DIR / "Fan calibration data.xlsx"
POSTER = RAW / "NTRS" / "20160000593.pdf"
DOI = "10.60555/4qc4-de67"
URL = "https://doi.org/" + DOI
SRC_REPO, SRC_TABLE = "src_psi25_repository", "src_psi25_experimental_table"
SRC_FAQ, SRC_FANCAL, SRC_POSTER = "src_psi25_data_faq", "src_psi25_fan_calibration", "src_ntrs_20160000593"

C_O2 = "Calibrated  initial O2 % by vol "   # spelled exactly as in the file
C_O2_END = "Calibrated final O2 % by vol"
C_MAT, C_AIR, C_FAN = "Fuel Sample Material", "Air display", "Fan display"
RAW_UNITS = {C_AIR: "cm/s", C_O2: "%", C_O2_END: "%", "Initial CO2 % by vol": "%", "Final CO2 % by vol": "%",
             "Initial CO (ppm)": "ppm", "Final CO (ppm)": "ppm"}

MATERIALS = {
    "mat_pmma": {"id": "mat_pmma", "label": "PMMA (colour not stated)", "state": "solid", "composition": None,
                 "aliases": ["PMMA", "polymethyl methacrylate", "acrylic"]},
    "mat_pmma_clear": {"id": "mat_pmma_clear", "label": "PMMA, clear", "state": "solid", "composition": None,
                       "aliases": ["clear PMMA", "clear rod"]},
    "mat_pmma_black": {"id": "mat_pmma_black", "label": "PMMA, black", "state": "solid", "composition": None,
                       "aliases": ["black PMMA", "black rod"]},
    "mat_sibal": {"id": "mat_sibal", "label": "SIBAL fabric", "state": "solid",
                  "composition": "75/25 cotton/fiberglass blend", "aliases": ["SIBAL", "Sibal"]},
    "mat_nomex_iii": {"id": "mat_nomex_iii", "label": "Nomex III (natural)", "state": "solid", "composition": None,
                      "aliases": ["Nomex", "Nomex natural"]},
    "mat_japan_wax": {"id": "mat_japan_wax", "label": "Japan wax candle", "state": "solid", "composition": None,
                      "aliases": ["candle", "Japan Wax"]},
}
# Flow geometry per principal investigator, each backed by a text excerpt.
FLOW = {
    "Olson": ("concurrent", "ev_psi25_faq_test_matrix"),
    "Fernandez-Pello": ("opposed", "ev_psi25_faq_test_matrix"),
    "Bhattacharjee": ("opposed", "ev_psi25_poster_bhattacharjee"),
    "Miller": ("opposed", "ev_psi25_poster_narrow_channel"),
    "T'ien": ("concurrent", "ev_psi25_poster_tien"),
}
ROD_INCH = {"1/4": 0.25, "3/8": 0.375, "1/2": 0.5, "0.5": 0.5}


def parse_sample(pi, text, ev):
    """Reviewed mapping of the free-text sample description. Returns (material_id, sample, notes)."""
    low = text.lower()
    notes = []
    thickness, diameter = absent("m", ev), absent("m", ev, "not_applicable")
    if "rod" in low:
        geometry = "rod"
        material = "mat_pmma_clear" if "clear" in low else "mat_pmma_black" if "blac" in low else "mat_pmma"
        thickness = absent("m", ev, "not_applicable")
        m = re.search(r"(1/4|3/8|1/2|0\.5)", low)
        diameter = absent("m", ev)
        if m:
            diameter.update(value=ROD_INCH[m.group(1)] * 0.0254, status="reported", qualifier="eq",
                            raw_value=m.group(1), raw_unit="in")
    elif "sibal" in low:
        geometry, material = "fabric", "mat_sibal"
    elif "nomex" in low:
        geometry, material = "fabric", "mat_nomex_iii"
    elif "candle" in low:
        geometry, material = "other", "mat_japan_wax"
    elif "spherical" in low:
        geometry, material = "sphere", "mat_pmma"
        notes.append("Sample is a 4 cm PMMA spherical section (material per the BASS-II data FAQ).")
    elif pi == "Bhattacharjee":
        geometry, material = "film", "mat_pmma"
    elif pi == "Miller":
        geometry, material = "slab", "mat_pmma"
    else:
        return None, None, [f"sample description {text!r} could not be mapped"]
    if geometry in {"film", "slab"}:
        if "pmma" not in low:
            notes.append("Material is not named in this row; PMMA is taken from the BASS-II data FAQ "
                         "(this investigator burned PMMA films).")
        m = re.search(r"(\d+(?:\.\d+)?)\s*micron", low)
        if m:
            thickness, _ = quantity(m.group(1), "micron", "m", ev)
        else:
            m = re.search(r"(\d+(?:\.\d+)?)\s*mm", low)
            if m:
                thickness, _ = quantity(m.group(1), "mm", "m", ev)
        if "1 sided" in low or "2 sided" in low:
            notes.append("One-sided or two-sided burning is stated in the sample description (see evidence row).")
    if re.search(r"\d\s*cm", low):
        notes.append("Sample width is given in the description but the contract has no width field.")
    return material, {"geometry": geometry, "thickness": thickness, "initial_diameter": diameter}, notes


def text_evidence(ev_id, revision, source, section, excerpt, note):
    return {"id": ev_id, "data_revision": revision, "source_id": source, "kind": "text_excerpt",
            "locator": {"page": None, "section": section, "row_key": None, "start_s": None, "end_s": None},
            "excerpt": excerpt, "table_values": [], "verified": True, "verification_note": note}


def build(revision, retrieved_at):
    text = TABLE.read_bytes().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    runs, quarantine = [], []
    faq_note = "Excerpt copied from the original 'BASS-II data FAQ.docx' downloaded from PSI-25."
    poster_note = "Excerpt copied from the text layer of NTRS 20160000593 (pdftotext), section heading as printed."
    evidence = [
        text_evidence("ev_psi25_faq_test_matrix", revision, SRC_FAQ, "Test Matrix explanation",
                      "Sandra Olson burned three sizes of pmma rods (mostly clear), igniting the upstream end for "
                      "a stagnation flame / concurrent flow geometry. Carlos Fernandez-Pello burned three sizes of "
                      "pmma rods (mostly black), igniting the downstream end for an opposed flow flame spread "
                      "geometry. James T'ien burned mostly SIBAL fabric (75/25 cotton/fiberglass blend).", faq_note),
        text_evidence("ev_psi25_faq_air_display", revision, SRC_FAQ, "Columns in test matrix",
                      "Air display: flow speed measured in the duct in cm/s on the video display. Response time is "
                      "very slow (~ 1 min), so reading is only steady for long times at the same flow setting.",
                      faq_note),
        text_evidence("ev_psi25_faq_o2", revision, SRC_FAQ, "Columns in test matrix",
                      "Calibrated initial and final O2: The O2 sensor was out of calibration, so the MCA ISS reading "
                      "was used to correct the initial ISS 'air' reading of the sensor for the day via a constant "
                      "offset.", faq_note),
        text_evidence("ev_psi25_poster_bhattacharjee", revision, SRC_POSTER, "Residence Time Driven Flame Spread",
                      "Comparison of flame extinction at low opposing flow velocity (radiative quenching) vs. at "
                      "high flow velocities (blow off extinction) for 0.1 mm thick sample.", poster_note),
        text_evidence("ev_psi25_poster_narrow_channel", revision, SRC_POSTER, "Narrow Channel Validation",
                      "All tests were opposed-flow flame spread. The flow speed was varied one or more times "
                      "throughout each test to see the effect on the flame.", poster_note),
        text_evidence("ev_psi25_poster_tien", revision, SRC_POSTER, "Growth and Extinction Limit",
                      "Flame spread and extinction were studied in purely forced concurrent flow in zero-gravity "
                      "under various oxygen percentages for narrow SIBAL fabric samples.", poster_note),
    ]

    for r in rows:
        test, pi = clean(r["Test #"]), clean(r["PI"])
        key = slug(test)
        ev_id, run_id = f"ev_psi25_{key}", f"run_psi25_{key}"
        ev = [ev_id]
        desc = re.sub(r"\s+", " ", clean(r[C_MAT]))
        material, sample, notes = parse_sample(pi, desc, ev)
        if material is None:
            quarantine.append({"investigation": PSI_ID, "row_key": f"Test # {test}", "source_test_id": test,
                               "reasons": notes, "raw": {k: clean(v) for k, v in r.items()}})
            continue

        air_raw = clean(r[C_AIR])
        tags = []
        if re.fullmatch(r"\d+(\.\d+)?", air_raw or ""):
            airflow, _ = quantity(air_raw, "cm/s", "m_s", ev + ["ev_psi25_faq_air_display"])
            notes.append("Airflow speed is the duct reading shown on the video display (cm/s), which responds "
                         "slowly (about 1 min); the fan-calibration file estimates test-section speed as "
                         "1.0066 x this reading.")
        elif not air_raw:
            airflow = absent("m_s", ev)
        else:
            airflow = absent("m_s", ev + ["ev_psi25_faq_air_display"], "unusable")
            airflow.update(raw_value=air_raw, raw_unit="cm/s")
            tags.append("flow_stepped")
            notes.append(f"Air display holds several flow settings or operator remarks ({air_raw!r}); the flow "
                         "was changed during the test, so no single airflow speed is assigned.")
        o2, o2_note = quantity(r[C_O2], "%", "fraction", ev + ["ev_psi25_faq_o2"])
        if o2_note:
            notes.append(f"Initial O2: {o2_note}.")
        try:
            o2_end = float(r[C_O2_END])
            if o2["value"] is not None and (o2_end > o2["value"] * 100 + 1 or o2_end < 5):
                notes.append(f"Final O2 reading {clean(r[C_O2_END])} % is anomalous against the initial "
                             f"{clean(r[C_O2])} %; it is kept as a raw value only and is not interpreted.")
        except ValueError:
            pass
        remark = f"{air_raw or ''} {clean(r[C_FAN]) or ''}".lower()
        if "ext" in remark or "blow" in remark:
            notes.append("Operator remarks in the display columns mention extinction or blowoff; this is not a "
                         "reviewed outcome, so the terminal outcome stays unknown.")
        if not clean(r["Date"]).endswith("2014"):
            notes.append(f"Source date {clean(r['Date'])} is outside the 2014 campaign; not verified.")
        flow_cfg, flow_ev = FLOW.get(pi, ("unknown", None))
        if sample["geometry"] == "sphere":
            flow_cfg, flow_ev = "unknown", None
        notes.append("Pressure, ambient temperature, flame spread rate and test outcome are not in the source table.")

        evidence.append({
            "id": ev_id, "data_revision": revision, "source_id": SRC_TABLE, "kind": "table_row",
            "locator": {"page": None, "section": None, "row_key": f"Test # {test}", "start_s": None, "end_s": None},
            "excerpt": None,
            "table_values": [{"field": c.strip(), "raw_value": clean(v) or None, "raw_unit": RAW_UNITS.get(c)}
                             for c, v in r.items()],
            "verified": True,
            "verification_note": "Row parsed from the original PSI-25 experimental table CSV "
                                 "(sha256 in sources.jsonl); raw values copied without change.",
        })
        runs.append({
            "id": run_id, "data_revision": revision, "investigation_id": INV_ID, "source_test_id": test,
            "material_id": material, "sample": sample,
            "conditions": {"gravity_regime": "microgravity", "gravity_level": absent("g_fraction", ev),
                           "oxygen_fraction": o2, "pressure": absent("Pa", ev), "airflow_speed": airflow,
                           "flow_configuration": flow_cfg, "ambient_temperature": absent("K", ev)},
            "metrics": [],
            "terminal_outcome": {"category": "unknown", "raw_label": None, "interpretation_status": "unmapped",
                                 "evidence_ids": ev},
            "regime_tags": tags, "evidence_ids": ev + ([flow_ev] if flow_ev else []), "quality_notes": notes,
        })

    def src(sid, title, kind, path, url=URL, doi=DOI, date="2016-07-31", lic="CC0-1.0", avail="available"):
        return {"id": sid, "data_revision": revision, "title": title, "kind": kind, "canonical_url": url,
                "doi": doi, "publication_date": date, "retrieved_at": retrieved_at, "license": lic,
                "availability": avail, "local_asset_id": None, "sha256": sha256_file(path) if path else None}
    sources = [
        src(SRC_REPO, "Burning and Suppression of Solids - II (BASS-II), PSI-25", "repository", None,
            date=None, avail="metadata_only"),
        src(SRC_TABLE, "PSI-25 Experimental table, BASS-II (CSV)", "experimental_table", TABLE, date=None),
        src(SRC_FAQ, "BASS-II data FAQ (PSI-25 science document)", "report", FAQ, date=None),
        src(SRC_FANCAL, "BASS-II fan calibration data (PSI-25 reference data)", "calibration", FANCAL, date=None),
        src(SRC_POSTER, "Combustion of Solids in Microgravity: Results from the BASS-II Experiment "
            "(Ferkul et al., NTRS 20160000593)", "publication", POSTER,
            url="https://ntrs.nasa.gov/citations/20160000593", doi=None, date="2014-10-23", lic=None),
    ]
    meta_ev = "ev_psi25_faq_test_matrix"
    investigation = {
        "id": INV_ID, "data_revision": revision, "psi_id": PSI_ID, "acronym": "BASS-II",
        "title": "Burning and Suppression of Solids - II",
        "objectives": ["Study how airflow speed, fuel thickness and geometry, and oxygen concentration affect "
                       "flame growth, spread and extinction over solid fuels in microgravity."],
        "setup_summary": "Small solid samples (PMMA films, slabs, rods and a spherical section, SIBAL and Nomex "
                         "fabric) burned in a fan-driven flow duct inside the Microgravity Science Glovebox on the "
                         "ISS, in opposed or concurrent flow, with oxygen at or below cabin level.",
        "scopes": ["prevention"], "fuel_states": ["solid"], "gravity_regimes": ["microgravity"],
        "material_ids": sorted({r["material_id"] for r in runs}),
        "source_ids": [s["id"] for s in sources], "claim_ids": [],
        "conditions_coverage": coverage(runs, meta_ev),
        "available_assets": [SRC_TABLE, SRC_FAQ, SRC_FANCAL, SRC_POSTER],
    }
    return {"investigations": [investigation], "materials": list(MATERIALS.values()), "runs": runs,
            "sources": sources, "evidence": evidence, "claims": [], "quarantine": quarantine}
