"""A1-11 draft: Recall@5 over investigations and false 'direct' matches on lunar/Mars questions.

Usage: python3 packages/retrieval/evaluate.py
The question set is a first draft by AI 1; AI 2 should review and extend it.
"""
import json
from pathlib import Path

from retrieve import ROOT, retrieve

qs = json.loads((Path(__file__).parent / "eval_questions.json").read_text(encoding="utf-8"))
rev = sorted(p.parent.name for p in (ROOT / "data" / "releases").glob("*/manifest.json"))[-1]
hits = total = false_direct = ev_hits = ev_total = 0
release = __import__("retrieve").load(ROOT / "data" / "releases" / rev)
for q in qs:
    res = retrieve({"request_id": q["id"], "question": q["question"], "locale": "ru", "data_revision": rev,
                    "filters": {}, "scenario": None, "include_related": False, "top_k": 12})
    top5 = [x["investigation_id"] for x in res["ranked_items"][:5]]
    found = sum(1 for r in q["relevant"] if r in top5)
    hits += found
    total += len(q["relevant"])
    top_ev = set(res["evidence_bundle"]["allowed_evidence_ids"][:5])
    rel_ev = {e for c in q.get("relevant_claims", []) for e in release["claims"][c]["supporting_evidence_ids"]}
    ev_ok = bool(top_ev & rel_ev) if rel_ev else None
    if ev_ok is not None:
        ev_total += 1
        ev_hits += ev_ok
    fd = q["lunar"] and any(x["relevance_category"] == "direct" for x in res["ranked_items"])
    false_direct += fd
    print(f"{q['id']} inv {found}/{len(q['relevant'])} ev {'-' if ev_ok is None else 'ok' if ev_ok else 'MISS'} {'FALSE-DIRECT ' if fd else ''}"
          f"{top5[:3]}  {q['question']}")
print(f"\nInvestigation Recall@5 = {hits / total:.2f}; evidence Recall@5 = {ev_hits / ev_total:.2f} "
      f"(target >= 0.85); false direct on lunar/Mars questions: {false_direct}")
