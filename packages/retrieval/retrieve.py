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
from pathlib import Path

RETRIEVAL_REVISION = "lexical-1"
ROOT = Path(__file__).resolve().parents[2]
MAX_EVIDENCE, MAX_EXCERPT_CHARS = 20, 24000

# Russian and English query words -> canonical index terms. Outcome words stay
# distinct: extinction (погасание) is never merged with suppression (тушение).
SYNONYMS = {
    "вентиляц": ["airflow", "flow"], "поток": ["airflow", "flow"], "обдув": ["airflow", "flow"],
    "скорост": ["airflow", "speed"], "ventilation": ["airflow", "flow"], "air": ["airflow"],
    "кислород": ["oxygen"], "o2": ["oxygen"], "давлен": ["pressure"],
    "туш": ["suppression"], "станци": ["iss", "station"], "корабл": ["spacecraft"], "подавлен": ["suppression"], "огнетуш": ["suppression"],
    "suppressant": ["suppression"], "extinguish": ["suppression", "extinction"],
    "погас": ["extinction"], "гашен": ["extinction"], "затух": ["extinction"],
    "срыв": ["blowoff"], "blow": ["blowoff"],
    "обнаруж": ["detection"], "тлен": ["smoke", "detection", "pyrolysis"], "тле": ["smoke", "detection"], "изоляц": ["kapton", "teflon", "insulation"], "провод": ["kapton", "teflon", "wire"], "электр": ["kapton", "teflon"], "горен": ["flame", "burn", "combustion"], "горит": ["flame", "burn"], "burn": ["burn"], "combust": ["combustion"], "детектор": ["detection", "detector"], "датчик": ["detection", "detector"],
    "дым": ["smoke", "detection"], "частиц": ["particle", "smoke"], "аэрозол": ["aerosol", "smoke"],
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
    checks = [("oxygen_range", run["conditions"]["oxygen_fraction"]), ("pressure_range", run["conditions"]["pressure"]),
              ("airflow_range", run["conditions"]["airflow_speed"])]
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


RU_FIELD = {"oxygen_range": "кислород", "pressure_range": "давление", "airflow_range": "скорость потока",
            "material_ids": "материал", "has_measurements": "наличие измерений", "scopes": "задача безопасности",
            "fuel_states": "состояние топлива", "gravity_regimes": "режим гравитации",
            "investigation_ids": "выбранные исследования"}
RU_SCOPE = {"prevention": "предотвращение", "detection": "обнаружение", "suppression": "тушение"}
COND_FIELDS = [("oxygen_range", "oxygen_fraction", "кислород"), ("pressure_range", "pressure", "давление"),
               ("airflow_range", "airflow_speed", "скорость потока")]


def retrieve(request, release_dir=None):
    release_dir = Path(release_dir) if release_dir else ROOT / "data" / "releases" / request["data_revision"]
    if not release_dir.exists():
        raise FileNotFoundError(f"data revision {request['data_revision']} not found")
    data = load(release_dir)
    if data["manifest"]["data_revision"] != request["data_revision"]:
        raise ValueError("release directory does not match the requested data_revision")
    docs, idf = index(data)
    f = request.get("filters") or {}
    scenario = request.get("scenario")
    qterms = expand(request.get("question") or request.get("query") or "")
    selected = request.get("selected_investigation_ids") or []
    top_k = min(int(request.get("top_k") or 12), 20)
    include_related = bool(request.get("include_related"))

    target_partial = bool(qterms & PARTIAL_WORDS) or (scenario or {}).get("gravity_regime") in {"partial",
                                                                                              "simulated_partial"}
    task = (scenario or {}).get("safety_task")
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
            reasons.append("совпадение терминов: " + ", ".join(hit[:8]))
        if scope_ok:
            reasons.append("задача безопасности: " + ", ".join(RU_SCOPE[s] for s in inv["scopes"]))
        if matching:
            reasons.append(f"{len(matching)} из {len(runs)} опытов удовлетворяют фильтрам")
        if unknown_used:
            reasons.append(f"{unknown_used} опытов включены с неизвестным значением параметра (include_unknown)")
        for key, field, ru in COND_FIELDS:
            unknown = sum(1 for r in runs if r["conditions"][field]["value"] is None)
            if unknown and (f.get(key) or (scenario or {}).get(field)):
                missing.append(field)
                differences.append(f"{ru}: нет значения у {unknown} из {len(runs)} опытов")
        if target_partial:
            differences.append("гравитация: в исследовании только " + ", ".join(inv["gravity_regimes"])
                               + "; данных частичной гравитации (Луна, Марс) в корпусе нет")

        if failed is not None:
            if include_related:
                related.append({"investigation_id": inv["id"], "rank_score": score, "relevance_category": "related",
                                "match_reasons": reasons, "differences": differences
                                + [f"не проходит фильтр: {RU_FIELD.get(failed, failed)}"],
                                "missing_fields": missing, "matching_run_ids": []})
            continue
        if qterms and not hit and not scope_ok:
            continue
        direct = (text >= 0.25 or not qterms or scope_ok) and not target_partial
        items.append({"investigation_id": inv["id"], "rank_score": score,
                      "relevance_category": "direct" if direct else "contextual",
                      "match_reasons": reasons, "differences": differences, "missing_fields": missing,
                      "matching_run_ids": matching})

    order = lambda x: (-x["rank_score"], x["investigation_id"])  # noqa: E731
    ranked = sorted(items, key=order)[:top_k] + sorted(related, key=order)
    bundle, coverage = build_bundle(data, request, ranked, qterms, target_partial, idf)
    warnings = ["SEMANTIC_SEARCH_UNAVAILABLE"]
    return {"request_id": request.get("request_id"), "data_revision": request["data_revision"],
            "retrieval_revision": RETRIEVAL_REVISION, "mode": "lexical", "ranked_items": ranked,
            "evidence_bundle": bundle, "coverage": coverage, "warnings": warnings}


def facts(run, ev_ids):
    out = [{"field": "material_id", "quantity": None, "text_value": run["material_id"], "evidence_ids": ev_ids},
           {"field": "terminal_outcome", "quantity": None, "text_value": run["terminal_outcome"]["category"],
            "evidence_ids": run["terminal_outcome"]["evidence_ids"]}]
    for k in ["oxygen_fraction", "pressure", "airflow_speed"]:
        q = run["conditions"][k]
        if q["value"] is not None:
            out.append({"field": k, "quantity": q, "text_value": None, "evidence_ids": q["evidence_ids"]})
    for m in run["metrics"]:
        if m["quantity"]["value"] is not None:
            out.append({"field": m["metric_key"], "quantity": m["quantity"], "text_value": None,
                        "evidence_ids": m["quantity"]["evidence_ids"]})
    return out


def build_bundle(data, request, ranked, qterms, target_partial, idf):
    direct = [x for x in ranked if x["relevance_category"] in {"direct", "contextual"}]
    inv_ids = [x["investigation_id"] for x in direct]
    claims = [c for c in data["claims"].values() if set(c["investigation_ids"]) & set(inv_ids)
              and c["review_status"] == "reviewed"]
    claims.sort(key=lambda c: (-sum(idf.get(t, 0) for t in qterms & expand(c["text"])),
                              -len(qterms & expand(c["text"])), c["id"]))
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
        items.append({"evidence": ev, "source_metadata": {k: src[k] for k in
                      ["id", "title", "kind", "canonical_url", "doi", "license", "availability"]},
                      "investigation_ids": sorted(invs),
                      "run_ids": run_ids, "normalized_facts": nfacts})

    for c in claims[:8]:                           # reviewed findings first
        for e in c["supporting_evidence_ids"][:2]:
            run_ids = [r for r in c["applicable_run_ids"] if e in data["runs"][r]["evidence_ids"]][:1]
            nf = facts(data["runs"][run_ids[0]], [e]) if run_ids else \
                [{"field": "claim_text", "quantity": None, "text_value": c["text"], "evidence_ids": [e]}]
            add(e, run_ids, nf, c["investigation_ids"])
    for x in direct:                               # then up to 3 example measurement rows each
        rows = [data["runs"][r] for r in x["matching_run_ids"]]
        rows = [r for r in rows if any(m["quantity"]["value"] is not None for m in r["metrics"])
                or r["conditions"]["airflow_speed"]["value"] is not None][:3]
        for run in rows:
            add(run["evidence_ids"][0], [run["id"]], facts(run, run["evidence_ids"][:1]), [x["investigation_id"]])

    matching_runs = sorted({r for x in direct for r in x["matching_run_ids"]})
    direct_available = any(x["relevance_category"] == "direct" for x in ranked)
    reasons = []
    if target_partial:
        reasons.append("Целевой режим — частичная гравитация (Луна/Марс); в корпусе только микрогравитация, "
                       "прямых наблюдений нет.")
    if not direct:
        reasons.append("Нет исследований, удовлетворяющих жёстким фильтрам.")
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
    q = sys.argv[1] if len(sys.argv) > 1 else "влияние вентиляции на твердые материалы"
    rev = json.loads(next((ROOT / "data" / "releases").glob("*/manifest.json")).read_text())["data_revision"]
    res = retrieve({"request_id": "cli", "question": q, "locale": "ru", "data_revision": rev,
                    "filters": {}, "scenario": None, "include_related": True, "top_k": 12})
    for it in res["ranked_items"]:
        print(f"{it['relevance_category']:<10} {it['rank_score']:.3f}  {it['investigation_id']}")
        for r in it["match_reasons"] + it["differences"]:
            print("            -", r)
    print("evidence in bundle:", len(res["evidence_bundle"]["items"]), "| coverage:", res["coverage"]["reasons"])
