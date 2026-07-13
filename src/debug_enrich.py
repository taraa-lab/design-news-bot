"""debug_enrich.py — directly test AI batch calls to see WHY they fail."""
import os, json, logging
logging.basicConfig(level=logging.INFO)

from collector import collect_all, Article
from dedup import deduplicate
from summarizer import _build_user_message, _call_api, BATCH_SIZE

raw = collect_all()
deduped = deduplicate(raw)

batches = [deduped[i:i+BATCH_SIZE] for i in range(0, len(deduped), BATCH_SIZE)]
report = {"total_batches": len(batches), "results": []}

for idx, batch in enumerate(batches):
    entry = {"batch_idx": idx, "size": len(batch)}
    try:
        msg = _build_user_message(batch)
        results = _call_api(msg, "fa")
        entry["status"] = "success"
        entry["results_count"] = len(results)
        entry["expected_count"] = len(batch)
        entry["sample"] = results[0] if results else None
    except Exception as e:
        entry["status"] = "FAILED"
        entry["error"] = str(e)
        entry["error_type"] = type(e).__name__
    report["results"].append(entry)

with open("../enrich_debug.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(json.dumps(report, ensure_ascii=False, indent=2))
