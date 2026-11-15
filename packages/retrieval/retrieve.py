"""Fire Atlas lexical retrieval (AI 1, spec sections 13.4, 15 and 15.1).

retrieve(request, release_dir) -> RetrievalResult with ranked investigations,
an EvidenceBundle and coverage. Pure standard library and deterministic: the
same request and data release always give the same result.

CLI:  python3 packages/retrieval/retrieve.py "влияние вентиляции на твердые материалы"
"""
import json
import math
import re
import sys
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

RETRIEVAL_REVISION = "lexical-2"
ROOT = Path(__file__).resolve().parents[2]
MAX_EVIDENCE, MAX_EXCERPT_CHARS = 20, 24000

# Russian and English query words -> canonical index terms. Outcome words stay
# distinct: extinction (погасание) is never merged with suppression (тушение).
SYNONYMS = {
    "ventilat": ["airflow", "flow"], "extinguish": ["extinction"], "suppress": ["suppression"],
    "вентиляц": ["airflow", "flow"], "поток": ["airflow", "flow"], "обдув": ["airflow", "flow"],
    "скорост": ["airflow", "speed"], "ventilation": ["airflow", "flow"], "air": ["airflow"],
    "кислород": ["oxygen"], "o2": ["oxygen"], "давлен": ["pressure"],
    "туш": ["suppression"], "станци": ["iss", "station"], "корабл": ["spacecraft"], "подавлен": ["suppression"], "огнетуш": ["suppression"],
    "suppressant": ["suppression"], "extinguish": ["suppression", "extinction"],
    "погас": ["extinction"], "гашен": ["extinction"], "затух": ["extinction"],
    "срыв": ["blowoff"], "blow": ["blowoff"],
    "обнаруж": ["detection"], "тлен": ["smoke", "detection", "pyrolysis"], "тле": ["smoke", "detection"], "изоляц": ["kapton", "teflon", "insulation"], "провод": ["kapton", "teflon", "wire"], "электр": ["kapton", "teflon"], "горен": ["flame", "burn", "combustion"], "горит": ["flame", "burn"], "burn": ["burn"], "combust": ["combustion"], "детектор": ["detection", "detector"], "датчик": ["detection", "detector"],
    "дым": ["smoke", "detection"], "задымл": ["smoke", "detection"], "дыма": ["smoke"], "частиц": ["particle", "smoke"], "аэрозол": ["aerosol", "smoke"],
    "предотвращ": ["prevention"], "горюч": ["flammability", "prevention"], "загора": ["ignition", "flammability"], "воспламен": ["ignition"],
    "распростран": ["spread"], "твёрд": ["solid"], "тверд": ["solid"],
    "пластик": ["pmma", "solid"], "оргстекл": ["pmma"], "акрил": ["pmma"], "ткан": ["fabric", "sibal", "nomex"],
    "капл": ["droplet", "liquid"], "жидк": ["liquid", "droplet"], "топлив": ["fuel"],
    "метанол": ["methanol"], "гептан": ["heptane"], "углекисл": ["co2"], "гели": ["helium", "he"],
    "разбавит": ["diluent", "co2", "helium"], "каптон": ["kapton"], "тефлон": ["teflon"],
    "силикон": ["silicone"], "фитил": ["lampwick", "cotton"], "хлоп": ["cotton"],
    "невесом": ["microgravity"], "микрогравитац": ["microgravity"], "мкс": ["iss", "microgravity"],
    "луна": ["moon"], "лунн": ["moon"], "марс": ["mars"], "ровер": ["rover"], "база": ["base"],
    "холодн": ["cool"], "пламен": ["flame"], "пожар": ["fire"],
}
STOP = {"и", "в", "на", "по", "для", "с", "о", "об", "при", "как", "что", "the", "of", "in", "on", "and", "a",
        "to", "for", "at", "is", "влияние", "какие", "какой", "как"}
PARTIAL_WORDS = {"moon", "mars"}
# Topics the corpus has no experiments on. A query about them can still find
# related investigations, but never as a direct match.
UNSUPPORTED = {"туман": "water mist", "mist": "water mist", "аккумулят": "batteries",
               "батаре": "batteries", "лити": "lithium", "hydrogen": "hydrogen", "hydrogen": "hydrogen",
               "металл": "metal combustion", "алюмини": "metal combustion", "скафандр": "spacesuits",
               "spacesuit": "spacesuits", "sf6": "SF6"}
O2_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


def unsupported_topics(text):
    found = []
    for t in tokens(text):
        for stem, name in UNSUPPORTED.items():
            if t.startswith(stem) and name not in found:
                found.append(name)
    return found


def query_oxygen(text):
    """Oxygen fractions named in the question (only when oxygen is mentioned)."""
    low = (text or "").lower()
    if not re.search(r"кислор|oxygen|o2", low):
        return []
    return [float(v.replace(",", ".")) / 100 for v in O2_RE.findall(low)]


def reason(code, text, field=None, evidence_ids=()):
    """Reason object (backend D-011)."""
    return {"code": code, "text": text[:300], "field": field, "evidence_ids": list(evidence_ids)[:20]}


def tokens(text):
    return [t for t in re.findall(r"[a-zа-яё0-9]+", (text or "").lower()) if t not in STOP]


def expand_counts(text):
    """Text -> {canonical term: count}. Word forms are kept as they are."""
    out = {}
    for t in tokens(text):
        for term in [t] + [x for stem, terms in SYNONYMS.items() if t.startswith(stem) for x in terms]:
            out[term] = out.get(term, 0) + 1
    return out


def expand(text):
    return set(expand_counts(text))


# Query words that name the safety task (scope) the user is asking about.
TASK_TERMS = {"suppression": "suppression", "extinction": "suppression", "detection": "detection",
              "smoke": "detection", "detector": "detection", "flammability": "prevention",
              "ignition": "prevention", "spread": "prevention", "prevention": "prevention"}


def load(release_dir):
    data = {}
    for name in ["investigations", "materials", "runs", "sources", "evidence", "claims"]:
        with open(Path(release_dir) / f"{name}.jsonl", encoding="utf-8") as f:
            data[name] = {r["id"]: r for r in map(json.loads, f)}
    data["manifest"] = json.loads((Path(release_dir) / "manifest.json").read_text())
    return data


def index(data):
    """One bag of terms per investigation: description, materials, claims, conditions."""
    docs = {}
    for inv in data["investigations"].values():
        parts = [inv["title"], inv["acronym"], inv["setup_summary"], " ".join(inv["objectives"]),
                 " ".join(inv["scopes"]), " ".join(inv["fuel_states"]), " ".join(inv["gravity_regimes"])]
        for m in inv["material_ids"]:
            mat = data["materials"][m]
            parts += [mat["label"], " ".join(mat["aliases"]), mat["composition"] or ""]
        for c in inv["claim_ids"]:
            parts.append(data["claims"][c]["text"])
        docs[inv["id"]] = expand_counts(" ".join(parts))
    n = len(docs)
    df = {}
    for terms in docs.values():
        for t in terms:
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log(1 + n / d) for t, d in df.items()}
    return docs, idf


def in_range(q, rng):
    v = q["value"]
    return v is not None and (rng.get("min") is None or v >= rng["min"]) and (rng.get("max") is None or v <= rng["max"])


def run_filter(run, f):
    """(passes, used_unknown, failed_field) for the run-level hard filters."""
    used_unknown = False
    checks = [(k, run["conditions"][field]) for k, field, _ in COND_FIELDS]
    for key, q in checks:
        rng = f.get(key)
        if not rng:
            continue
        if q["value"] is None:
            if not f.get("include_unknown"):
                return False, False, key
            used_unknown = True
        elif not in_range(q, rng):
            return False, False, key
    if f.get("material_ids") and run["material_id"] not in f["material_ids"]:
        return False, False, "material_ids"
    if f.get("has_measurements") is not None:
        has = any(m["quantity"]["value"] is not None for m in run["metrics"])
        if has != f["has_measurements"]:
            return False, False, "has_measurements"
    return True, used_unknown, None


def inv_filter(inv, f):
    for key, field in [("scopes", "scopes"), ("fuel_states", "fuel_states"), ("gravity_regimes", "gravity_regimes")]:
        if f.get(key) and not set(f[key]) & set(inv[field]):
            return key
    if f.get("investigation_ids") and inv["id"] not in f["investigation_ids"]:
        return "investigation_ids"
    return None


RU_FIELD = {"oxygen_range": "oxygen", "pressure_range": "pressure", "airflow_range": "airflow speed",
            "material_ids": "material", "has_measurements": "measurement availability", "scopes": "safety task",
            "fuel_states": "fuel state", "gravity_regimes": "gravity regime",
            "investigation_ids": "selected investigations"}
FILTER_PATH = {"oxygen_range": "conditions.oxygen_fraction", "pressure_range": "conditions.pressure",
               "airflow_range": "conditions.airflow_speed", "co2_range": "conditions.co2_fraction",
               "helium_range": "conditions.helium_fraction", "material_ids": "material_id", "scopes": "scopes",
               "fuel_states": "fuel_states", "gravity_regimes": "gravity_regimes", "has_measurements": "metrics",
               "investigation_ids": None}
RU_FIELD.update({"co2_range": "доля CO2", "helium_range": "helium fraction"})
RU_SCOPE = {"prevention": "prevention", "detection": "detection", "suppression": "suppression"}
COND_FIELDS = [("oxygen_range", "oxygen_fraction", "oxygen"), ("pressure_range", "pressure", "pressure"),
               ("airflow_range", "airflow_speed", "airflow speed"), ("co2_range", "co2_fraction", "доля CO2"),
               ("helium_range", "helium_fraction", "helium fraction")]


@lru_cache(maxsize=4)
def _release_index(release_path):
    """Release directories are immutable; cache is private to this module."""
    data = load(release_path)
    docs, idf = index(data)
    return data, docs, idf


def retrieve(request, release_dir=None):
    release_dir = Path(release_dir) if release_dir else ROOT / "data" / "releases" / request["data_revision"]
    if not release_dir.exists():
        raise FileNotFoundError(f"data revision {request['data_revision']} not found")
    data, docs, idf = _release_index(str(release_dir.resolve()))
    if data["manifest"]["data_revision"] != request["data_revision"]:
        raise ValueError("release directory does not match the requested data_revision")
    f = request.get("filters") or {}
    scenario = request.get("scenario")
    qterms = expand(request.get("question") or request.get("query") or "")
    selected = request.get("selected_investigation_ids") or []
    top_k = min(int(request.get("top_k") or 12), 20)
    include_related = bool(request.get("include_related"))

    target_partial = bool(qterms & PARTIAL_WORDS) or (scenario or {}).get("gravity_regime") in {"partial",
                                                                                              "simulated_partial"}
    task = (scenario or {}).get("safety_task")
    qtext = request.get("question") or request.get("query") or ""
    off_topic = unsupported_topics(qtext)
    q_o2 = query_oxygen(qtext)
    query_tasks = {TASK_TERMS[t] for t in qterms if t in TASK_TERMS}
    default_idf = math.log(1 + len(docs))
    max_idf = sum(idf.get(t, default_idf) for t in qterms) or 1.0

    items, related = [], []
    for inv in sorted(data["investigations"].values(), key=lambda x: x["id"]):
        if selected and inv["id"] not in selected:
            continue
        runs = [r for r in data["runs"].values() if r["investigation_id"] == inv["id"]]
        failed = inv_filter(inv, f)
        matching, unknown_used, fails = [], 0, {}
        for r in runs:
            ok, unk, why = run_filter(r, f)
            if ok:
                matching.append(r["id"])
                unknown_used += unk
            else:
                fails[why] = fails.get(why, 0) + 1
        if failed is None and not matching and runs:
            failed = max(fails, key=fails.get)

        doc = docs[inv["id"]]
        hit = sorted(qterms & set(doc))
        # Saturated term frequency (BM25-style, k=1.2) times inverse document frequency.
        text = sum(idf[t] * doc[t] / (doc[t] + 1.2) for t in hit) / max_idf if qterms else 0.0
        wanted = {task} if task else set(f.get("scopes") or []) | query_tasks
        scope_ok = bool(wanted & set(inv["scopes"]))
        run_share = len(matching) / len(runs) if runs else 0.0
        score = round(0.6 * text + 0.25 * scope_ok + 0.15 * run_share, 6)

        reasons, differences, missing = [], [], []
        if hit:
            reasons.append(reason("term_match", "matching terms: " + ", ".join(hit[:8])))
        if scope_ok:
            reasons.append(reason("safety_task_match", "safety task: "
                                  + ", ".join(RU_SCOPE[s] for s in inv["scopes"]), "scopes"))
        if matching:
            reasons.append(reason("runs_match_filters", f"{len(matching)} of {len(runs)} test runs match the filters"))
        if unknown_used:
            reasons.append(reason("unknown_values_included",
                                  f"{unknown_used} test runs include unknown parameter values (include_unknown)"))
        for key, field, ru in COND_FIELDS:
            unknown = sum(1 for r in runs if r["conditions"][field]["value"] is None)
            if unknown and (f.get(key) or (scenario or {}).get(field)):
                missing.append(f"conditions.{field}")
                differences.append(reason("field_not_reported", f"{ru}: missing in {unknown} of {len(runs)} test runs",
                                          f"conditions.{field}"))
        if target_partial:
            differences.append(reason("gravity_not_covered", "gravity: the investigation includes only "
                                      + ", ".join(inv["gravity_regimes"])
                                      + "; the corpus has no partial-gravity data for the Moon or Mars",
                                      "conditions.gravity_regime"))

        o2cov = next((c for c in inv["conditions_coverage"] if c["field"] == "conditions.oxygen_fraction"), None)
        o2_out = [v for v in q_o2 if o2cov and o2cov["max_value"] is not None
                  and not (o2cov["min_value"] - 1e-9 <= v <= o2cov["max_value"] + 1e-9)]
        if o2_out:
            differences.append(reason("oxygen_outside_tested_range",
                                      f"oxygen {round(o2_out[0] * 100)} % outside the tested range "
                                      f"({round(o2cov['min_value'] * 100, 1)}–{round(o2cov['max_value'] * 100, 1)} %)",
                                      "conditions.oxygen_fraction"))
        if off_topic:
            differences.append(reason("topic_not_in_corpus", "the corpus has no test runs for this topic: " + ", ".join(off_topic)))
        if failed is not None:
            if include_related:
                related.append({"investigation_id": inv["id"], "rank_score": score, "relevance_category": "related",
                                "match_reasons": reasons, "differences": differences
                                + [reason("hard_filter_failed", f"does not pass filter: {RU_FIELD.get(failed, failed)}",
                                          FILTER_PATH.get(failed))],
                                "missing_fields": missing, "matching_run_ids": []})
            continue
        if qterms and not hit and not scope_ok:
            continue
        direct = (text >= 0.25 or not qterms or scope_ok) and not target_partial and not off_topic and not o2_out
        items.append({"investigation_id": inv["id"], "rank_score": score,
                      "relevance_category": "direct" if direct else "contextual",
                      "match_reasons": reasons, "differences": differences, "missing_fields": missing,
                      "matching_run_ids": matching})

    order = lambda x: (-x["rank_score"], x["investigation_id"])  # noqa: E731
    ranked = sorted(items, key=order)[:top_k] + sorted(related, key=order)
    bundle, coverage = build_bundle(data, request, ranked, qterms, target_partial, idf)
    warnings = [{"code": "SEMANTIC_SEARCH_UNAVAILABLE",
                 "message": "P0 uses lexical search; semantic search is not enabled.", "field": None}]
    return deepcopy({"request_id": request.get("request_id"), "data_revision": request["data_revision"],
            "retrieval_revision": RETRIEVAL_REVISION, "mode": "lexical", "ranked_items": ranked,
            "evidence_bundle": bundle, "coverage": coverage, "warnings": warnings})


def facts(run, ev_ids):
    out = [{"field": "material_id", "quantity": None, "text_value": run["material_id"], "evidence_ids": ev_ids},
           {"field": "terminal_outcome.category", "quantity": None, "text_value": run["terminal_outcome"]["category"],
            "evidence_ids": run["terminal_outcome"]["evidence_ids"]}]
    for k in ["oxygen_fraction", "nitrogen_fraction", "co2_fraction", "helium_fraction", "pressure", "airflow_speed"]:
        q = run["conditions"][k]
        if q["value"] is not None:
            out.append({"field": f"conditions.{k}", "quantity": q, "text_value": None, "evidence_ids": q["evidence_ids"]})
    for m in run["metrics"]:
        if m["quantity"]["value"] is not None:
            out.append({"field": f"metrics.{m['metric_key']}", "quantity": m["quantity"], "text_value": None,
                        "evidence_ids": m["quantity"]["evidence_ids"]})
    return out


def build_bundle(data, request, ranked, qterms, target_partial, idf):
    direct = [x for x in ranked if x["relevance_category"] in {"direct", "contextual"}]
    inv_ids = [x["investigation_id"] for x in direct]
    claims = [c for c in data["claims"].values() if set(c["investigation_ids"]) & set(inv_ids)
              and c["review_status"] == "reviewed"]
    claims.sort(key=lambda c: (-sum(idf.get(t, 0) for t in qterms & expand(c["text"])),
                              -len(qterms & expand(c["text"])), c["id"]))
    # Round robin over the found investigations in rank order, best claim of each first;
    # direct matches before contextual ones.
    def rr(ids):
        queues = [[c for c in claims if c["investigation_ids"][0] == i] for i in ids]
        return [q[k] for k in range(max(map(len, queues), default=0)) for q in queues if k < len(q)]
    claims = rr([x["investigation_id"] for x in direct if x["relevance_category"] == "direct"]) + \
        rr([x["investigation_id"] for x in direct if x["relevance_category"] == "contextual"])
    chosen, items, chars = [], [], 0

    def add(ev_id, run_ids, nfacts, invs):
        nonlocal chars
        if ev_id in chosen or len(chosen) >= MAX_EVIDENCE:
            return
        ev = data["evidence"][ev_id]
        size = len(ev["excerpt"] or "")
        if chars + size > MAX_EXCERPT_CHARS:
            return
        src = data["sources"][ev["source_id"]]
        chosen.append(ev_id)
        chars += size
        items.append({"evidence": ev, "source_metadata": src,
                      "investigation_ids": sorted(invs),
                      "run_ids": run_ids, "normalized_facts": nfacts})

    for c in claims[:8]:                           # reviewed findings first
        for e in c["supporting_evidence_ids"][:2]:
            run_ids = [r for r in c["applicable_run_ids"] if e in data["runs"][r]["evidence_ids"]][:1]
            nf = facts(data["runs"][run_ids[0]], [e]) if run_ids else \
                [{"field": "claim.text", "quantity": None, "text_value": c["text"][:1000], "evidence_ids": [e]}]
            add(e, run_ids, nf, c["investigation_ids"])
    for x in direct:                               # then up to 3 example measurement rows each
        rows = [data["runs"][r] for r in x["matching_run_ids"]]
        rows = [r for r in rows if any(m["quantity"]["value"] is not None for m in r["metrics"])
                or r["conditions"]["airflow_speed"]["value"] is not None][:3]
        for run in rows:
            add(run["evidence_ids"][0], [run["id"]], facts(run, run["evidence_ids"][:1]), [x["investigation_id"]])

    allowed = set(chosen)                          # facts may cite only evidence inside this bundle
    for it in items:
        kept = []
        for fact in it["normalized_facts"]:
            ids = [e for e in fact["evidence_ids"] if e in allowed]
            if ids:
                kept.append({**fact, "evidence_ids": ids})
        it["normalized_facts"] = kept
    matching_runs = sorted({r for x in direct for r in x["matching_run_ids"]})
    direct_available = any(x["relevance_category"] == "direct" for x in ranked)
    reasons = []
    if target_partial:
        reasons.append(reason("target_gravity_not_covered", "The target regime is partial gravity (Moon/Mars); "
                              "the corpus contains only microgravity tests, with no direct observations.", "conditions.gravity_regime"))
    if not direct:
        reasons.append(reason("no_matching_investigations", "No investigations pass the hard filters."))
    off = unsupported_topics(request.get("question") or request.get("query") or "")
    if off:
        reasons.append(reason("topic_not_in_corpus", "The corpus has no test runs for this topic: " + ", ".join(off)
                              + "; the retrieved investigations are only related to the question."))
    missing = sorted({m for x in direct for m in x["missing_fields"]})
    coverage = {"matching_investigation_ids": inv_ids, "matching_run_ids": matching_runs, "missing_fields": missing,
                "target_gravity_covered": not target_partial, "direct_evidence_available": direct_available,
                "reasons": reasons}
    sel = [c for c in claims if c["id"] in {cc["id"] for cc in claims[:8]}]
    bundle = {"bundle_id": "bnd_" + (re.sub(r"[^A-Za-z0-9_-]", "", str(request.get("request_id") or "")) or "local")[:120],
              "data_revision": request["data_revision"],
              "question": request.get("question") or request.get("query") or "",
              "scenario": request.get("scenario"), "items": items, "allowed_evidence_ids": chosen,
              "allowed_source_ids": sorted({i["evidence"]["source_id"] for i in items}),
              "selected_claims": sel, "coverage": coverage, "retrieval_revision": RETRIEVAL_REVISION}
    return bundle, coverage


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "влияние вентиляции на твердые materials"
    rev = sorted(p.parent.name for p in (ROOT / "data" / "releases").glob("*/manifest.json"))[-1]
    res = retrieve({"request_id": "cli", "question": q, "locale": "ru", "data_revision": rev,
                    "filters": {}, "scenario": None, "include_related": True, "top_k": 12})
    for it in res["ranked_items"]:
        print(f"{it['relevance_category']:<10} {it['rank_score']:.3f}  {it['investigation_id']}")
        for r in it["match_reasons"] + it["differences"]:
            print("            -", r["text"])
    print("evidence in bundle:", len(res["evidence_bundle"]["items"]), "| coverage:",
          [x["text"] for x in res["coverage"]["reasons"]])
