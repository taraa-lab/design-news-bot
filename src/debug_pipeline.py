"""debug_pipeline.py — inspect each stage of the pipeline to find where articles are lost."""
import json, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from collector import collect_all
from dedup import deduplicate
from summarizer import enrich_articles
from sender import INTEREST_CATEGORIES, COMPETITION_CATS

report = {}

raw = collect_all()
report["1_raw_collected"] = len(raw)
report["1_by_source"] = {}
for a in raw:
    report["1_by_source"][a.source] = report["1_by_source"].get(a.source, 0) + 1

deduped = deduplicate(raw)
report["2_after_dedup"] = len(deduped)

enriched = enrich_articles(deduped, lang="fa")
report["3_after_enrich"] = len(enriched)

cat_counts = {}
for a in enriched:
    cat_counts[a.category] = cat_counts.get(a.category, 0) + 1
report["4_category_distribution"] = cat_counts

# Simulate filter for interest "product"
allowed = set()
for cat in INTEREST_CATEGORIES.get("product", []):
    allowed.add(cat)
matched = [a for a in enriched if a.category in COMPETITION_CATS or a.category in allowed]
report["5_matched_for_product_interest"] = len(matched)
report["5_matched_titles"] = [a.title for a in matched][:20]
report["6_allowed_categories_checked"] = list(allowed) + COMPETITION_CATS

with open("../pipeline_debug.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(json.dumps(report, ensure_ascii=False, indent=2))
