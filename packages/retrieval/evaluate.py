"""A1-11 draft: Recall@5 over investigations and false 'direct' matches on lunar/Mars questions.

Usage: python3 packages/retrieval/evaluate.py
The question set is a first draft by AI 1; AI 2 should review and extend it.
"""
import json
from pathlib import Path

from retrieve import ROOT, retrieve

qs = json.loads((Path(__file__).parent / "eval_questions.json").read_text(encoding="utf-8"))
rev = json.loads(next((ROOT / "data" / "releases").glob("*/manifest.json")).read_text())["data_revision"]
hits = total = false_direct = 0
for q in qs:
    res = retrieve({"request_id": q["id"], "question": q["question"], "locale": "ru", "data_revision": rev,
                    "filters": {}, "scenario": None, "include_related": False, "top_k": 12})
    top5 = [x["investigation_id"] for x in res["ranked_items"][:5]]
    found = sum(1 for r in q["relevant"] if r in top5)
    hits += found
    total += len(q["relevant"])
    fd = q["lunar"] and any(x["relevance_category"] == "direct" for x in res["ranked_items"])
    false_direct += fd
    print(f"{q['id']} {found}/{len(q['relevant'])} {'FALSE-DIRECT ' if fd else ''}{top5[:3]}  {q['question']}")
print(f"\nRecall@5 = {hits / total:.2f} (target >= 0.85); false direct on lunar/Mars questions: {false_direct}")
