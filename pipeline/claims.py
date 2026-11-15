"""Reviewed findings (Claim, CT-07) for the P0 corpus.

Text claims quote NASA documents with page numbers (NASA works, public
domain). Data claims are computed from the normalised runs at build time,
so their numbers always match the published rows.
"""
from collections import Counter

from common import RAW, sha256_file

POSTER, SAME2 = "src_ntrs_20160000593", "src_ntrs_20130000422"
SAME2_PDF = RAW / "NTRS" / "20130000422.pdf"
NOTE = "Sentence copied from the text layer of the original PDF (pdftotext); page number as printed by the reader."

TEXT_EVIDENCE = [
    ("ev_poster_p18_o2_margin", POSTER, 18, "The 1g blowoff for the 1/4\" rod is at 16% oxygen, whereas we obtained "
     "steady spreading at 13.6% oxygen in BASS-II. Thus the material has a negative Oxygen Margin of Safety of 2.4% "
     "O2, and the normal gravity flammability limits should be de-rated by at least that much."),
    ("ev_poster_p18_boundary", POSTER, 18, "The minimum in the flammability boundary is at low speed, on the order "
     "of diffusive flows."),
    ("ev_poster_p18_blowoff_o2", POSTER, 18, "Thus the flow needed to blow off the flame becomes slower as oxygen "
     "decreases and the flame temperature is reduced."),
    ("ev_poster_p13_quench", POSTER, 13, "Comparison of flame extinction at low opposing flow velocity (radiative "
     "quenching) vs. at high flow velocities (blow off extinction) for 0.1 mm thick sample. Sequence of top views "
     "showing radiative quenching when flow velocity goes below 2 cm/s. Flame nearing blow off extinction as the "
     "flow velocity crosses 40 cm/s."),
    ("ev_poster_p20_sibal", POSTER, 20, "29 tests were conducted in total mostly with cotton-fiberglass fabric "
     "(SIBAL) and two with a plastic (PMMA; polymethyl methacrylate) spherical section. 6 quenching cases (reducing "
     "flow) and 1 blow-off case (increasing flow, 1.2-cm wide sample)."),
    ("ev_same2_p1_sizes", SAME2, 1, "The majority of the average smoke particle sizes were found to be in the "
     "200 nm to 400 nm range with the quiescent cases producing some cases with substantially larger particles."),
    ("ev_same2_p7_aging", SAME2, 7, "The aging results show a substantial increase in the observed diameters."),
    ("ev_same2_p8_lowflow", SAME2, 8, "These figures show a strong trend of increased particle size at low flow "
     "rates."),
    ("ev_same2_p12_detection", SAME2, 12, "So the larger particle diameters observed in these zero-flow conditions "
     "are important to consider in the development of improved fire detection equipment for space vehicles."),
]
COOL_FLAME_EXCERPT = ("Additionally, the study of ''cool flames'' and low-temperature combustion processes observed "
                      "in microgravity can inform the design of advanced combustion engines")


def claim(cid, rev, inv, kind, text, support, limits, runs=()):
    return {"id": cid, "data_revision": rev, "investigation_ids": inv, "kind": kind, "text": text,
            "supporting_evidence_ids": list(support), "contradicting_evidence_ids": [],
            "applicable_run_ids": list(runs), "limitations": limits, "review_status": "reviewed"}


def build(revision, retrieved_at, data):
    ev = [{"id": i, "data_revision": revision, "source_id": s, "kind": "text_excerpt",
           "locator": {"page": p, "section": None, "row_key": None, "start_s": None, "end_s": None},
           "excerpt": t, "table_values": [], "verified": True, "verification_note": NOTE}
          for i, s, p, t in TEXT_EVIDENCE]
    ev.append({"id": "ev_psi69_metadata_cool_flames", "data_revision": revision, "source_id": "src_psi69_repository",
               "kind": "metadata", "locator": {"page": None, "section": "Research Impacts/Earth Benefits",
                                               "row_key": None, "start_s": None, "end_s": None},
               "excerpt": COOL_FLAME_EXCERPT, "table_values": [], "verified": True,
               "verification_note": "Copied from the PSI-69 investigation page as displayed on 2026-11-14."})
    sources = [{"id": SAME2, "data_revision": revision,
                "title": "Particle Morphology and Size Results from the Smoke Aerosol Measurement Experiment-2 "
                         "(Urban et al., AIAA 2012-3536, NTRS 20130000422)",
                "kind": "publication", "canonical_url": "https://ntrs.nasa.gov/citations/20130000422", "doi": None,
                "publication_date": "2012-07-15", "retrieved_at": retrieved_at, "license": None,
                "availability": "available", "local_asset_id": None, "sha256": sha256_file(SAME2_PDF)},
               {"id": "src_track_flame_in_freefall", "data_revision": revision,
                "title": "Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data "
                         "(NASA Space Apps Challenge 2026)",
                "kind": "publication", "canonical_url": "https://www.spaceappschallenge.org/2026/challenges/flame-in-freefall/",
                "doi": None, "publication_date": None, "retrieved_at": "2026-10-30T14:29:00Z", "license": None,
                "availability": "metadata_only", "local_asset_id": None, "sha256": None}]

    runs = data["runs"]
    flex = [r for r in runs if r["investigation_id"] == "inv_psi69_flex"]
    samer = [r for r in runs if r["investigation_id"] == "inv_psi101_samer"]
    o2 = lambda r: r["conditions"]["oxygen_fraction"]["value"]  # noqa: E731
    pa = lambda r: r["conditions"]["pressure"]["value"]  # noqa: E731
    diam = lambda r: next((m["quantity"]["value"] for m in r["metrics"] if m["quantity"]["value"]), None)  # noqa

    # FLEX: lunar-base-like atmosphere (>=30 % O2, about 0.7 atm).
    lunar = [r for r in flex if o2(r) >= 0.30 and 68000 < pa(r) < 75000]
    lc = Counter(r["terminal_outcome"]["category"] for r in lunar)
    # FLEX: lowest initial O2 tested per fuel and diluent.
    groups = []
    for fuel, name in [("mat_methanol", "methanol"), ("mat_heptane", "heptane")]:
        for tag, dil in [((), "N2 only"), (("co2_diluted",), "with CO2"), (("he_diluted",), "with He")]:
            g = [r for r in flex if r["material_id"] == fuel and tuple(r["regime_tags"]) == tag]
            low = min(g, key=o2)
            groups.append((name, dil, o2(low), low))
    # SAME-R: aged re-measurements vs. first measurement of the same smoke.
    by_test = {r["source_test_id"]: r for r in samer}
    pairs = [(by_test[t], by_test[t + "a"]) for t in by_test
             if t + "a" in by_test and diam(by_test[t]) and diam(by_test[t + "a"])]
    larger = sum(1 for a, b in pairs if diam(b) > diam(a))
    # SAME-R: median mean diameter of fresh smoke per material.
    fresh = [r for r in samer if diam(r) and "aged_remeasurement" not in r["regime_tags"]]
    med = {}
    for m in sorted({r["material_id"] for r in fresh}):
        v = sorted(diam(r) for r in fresh if r["material_id"] == m)
        med[m] = (v[len(v) // 2] * 1e9, len(v))
    label = {"mat_kapton": "Kapton", "mat_teflon": "Teflon", "mat_lampwick": "lamp wick (cotton)",
             "mat_silicone_rubber": "silicone rubber", "mat_pyrell": "Pyrell foam"}
    med_text = ", ".join(f"{label[m]} {round(v)} nm (n={n})" for m, (v, n) in sorted(med.items(), key=lambda x: x[1]))
    rev_ev = lambda rs: [e for r in rs for e in r["evidence_ids"] if e.startswith("ev_psi")]  # noqa: E731

    claims = [
        claim("clm_bass2_o2_margin", revision, ["inv_psi25_bass2"], "observation",
              "A 1/4-inch PMMA rod kept spreading steadily in microgravity at 13.6 % O2, while in normal gravity "
              "the flame blew off at 16 % O2: a negative oxygen margin of safety of 2.4 % O2. Normal-gravity "
              "flammability limits should be de-rated by at least that much.",
              ["ev_poster_p18_o2_margin"],
              ["One material and rod size, concurrent (stagnation-point) flow.",
               "Microgravity on the ISS; no partial-gravity data."]),
        claim("clm_bass2_film_quench_blowoff", revision, ["inv_psi25_bass2"], "observation",
              "A 0.1 mm PMMA film in opposed flow was extinguished in two ways: radiative quenching when the flow "
              "dropped below about 2 cm/s, and blowoff when it rose above about 40 cm/s.",
              ["ev_poster_p13_quench"],
              ["Thin film in opposed flow only; thresholds read from a poster summary."]),
        claim("clm_bass2_boundary_low_flow", revision, ["inv_psi25_bass2"], "observation",
              "For PMMA rods the flammability boundary has its minimum at very low airflow, on the order of "
              "diffusive flows, and the flow needed to blow the flame off becomes slower as oxygen decreases.",
              ["ev_poster_p18_boundary", "ev_poster_p18_blowoff_o2"],
              ["PMMA rods in concurrent flow; oxygen at or below cabin air."]),
        claim("clm_bass2_sibal_quenching", revision, ["inv_psi25_bass2"], "observation",
              "Of 29 tests on SIBAL cotton-fiberglass fabric and a PMMA spherical section in purely forced concurrent "
              "flow, 6 ended in quenching while the flow was reduced and 1 in blowoff while it was increased.",
              ["ev_poster_p20_sibal"],
              ["Counts from the investigator summary; per-test outcomes are not in the PSI-25 table."]),
        claim("clm_flex_lunar_like_atmosphere", revision, ["inv_psi69_flex"], "observation",
              f"In the {len(lunar)} FLEX tests at 30-34 % O2 and about 0.7 atm (close to the planned Moon-base "
              f"atmosphere), {lc['disruption']} droplets ended in disruption and {lc['burn_to_completion']} burned "
              f"to completion; none extinguished on its own.",
              rev_ev(lunar),
              ["Liquid fuel droplets (methanol, heptane) in quiescent microgravity, not cabin materials.",
               "Lunar gravity is not represented; disruption is not extinguishment."],
              [r["id"] for r in lunar]),
        claim("clm_flex_lowest_o2_tested", revision, ["inv_psi69_flex"], "synthesis",
              "Lowest initial O2 among FLEX tests in the table: "
              + "; ".join(f"{n} {d} {v:.2f}" for n, d, v, _ in groups)
              + ". Adding CO2 or helium raised the lowest oxygen level at which tests were run.",
              rev_ev([g[3] for g in groups]),
              ["These are the lowest levels tested, not measured flammability limits.",
               "Test levels were chosen by the investigators, so the comparison is indicative only."],
              [g[3]["id"] for g in groups]),
        claim("clm_flex_cool_flames", revision, ["inv_psi69_flex"], "observation",
              "FLEX observed 'cool flames': low-temperature combustion processes in microgravity.",
              ["ev_psi69_metadata_cool_flames"],
              ["Stated in the PSI-69 summary; the detailed evidence is in the FLEX publications.",
               "Whether burning continues after the visible flame goes out needs a FLEX publication as evidence."]),
        claim("clm_samer_size_range", revision, ["inv_psi101_samer"], "observation",
              "Most average smoke particle sizes from heated spacecraft materials were 200-400 nm; quiescent "
              "(no-flow) cases produced some substantially larger particles.",
              ["ev_same2_p1_sizes"],
              ["Smoke from heating below ignition, not from flaming fires."]),
        claim("clm_samer_aging_growth", revision, ["inv_psi101_samer"], "observation",
              f"Aging the smoke before measurement increased its mean particle diameter in {larger} of {len(pairs)} "
              "paired re-measurements.",
              ["ev_same2_p7_aging"] + [e for a, b in pairs for e in b["evidence_ids"] if e.endswith("_results")],
              ["Mean diameter M1/M0 from the analysed results; other diameter definitions behave differently."],
              [b["id"] for a, b in pairs]),
        claim("clm_samer_material_sizes", revision, ["inv_psi101_samer"], "observation",
              f"Median mean particle diameter of fresh smoke by material: {med_text}.",
              [e for r in fresh for e in r["evidence_ids"] if e.endswith("_results")],
              ["Mixed flow and heating conditions within each material.",
               "Arithmetic mean diameter M1/M0 only."],
              [r["id"] for r in fresh]),
        claim("clm_samer_low_flow_larger", revision, ["inv_psi101_samer"], "observation",
              "Smoke particles were larger at low flow rates.",
              ["ev_same2_p8_lowflow"],
              ["Trend stated by the investigators; see figures on page 8."]),
        claim("clm_samer_detector_design", revision, ["inv_psi101_samer"], "synthesis",
              "Because microgravity smoke can stay in still air and particles grow at low flow, spacecraft smoke "
              "detectors should be designed and tested for larger particles than in flowing air.",
              ["ev_same2_p8_lowflow", "ev_same2_p12_detection"],
              ["Design implication drawn by the investigators, not a detector test result."]),
    ]
    for inv in data["investigations"]:
        inv["claim_ids"] = [c["id"] for c in claims if inv["id"] in c["investigation_ids"]]
    return {"sources": sources, "evidence": ev, "claims": claims}
