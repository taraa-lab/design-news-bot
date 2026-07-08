"""
main.py — Orchestrator (GitHub Actions daily run)
collect → dedup → enrich → send personalized digests to all users
"""

import logging
import sys
import os
from datetime import datetime, timezone, timedelta

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR  = os.path.join(BASE_DIR, "logs")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOGS_DIR, f"run-{datetime.now().strftime('%Y%m%d')}.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

from collector  import collect_all
from dedup      import deduplicate
from summarizer import enrich_articles
from report     import build_markdown, save_report
from sender     import send_to_all_users


def main():
    logger.info("=== Design News Bot starting ===")

    logger.info("Step 1/4 — Collecting...")
    articles = collect_all()
    if not articles:
        logger.warning("No articles found")
        return

    logger.info("Step 2/4 — Deduplicating...")
    articles = deduplicate(articles)

    logger.info("Step 3/4 — Enriching (%d articles)...", len(articles))
    articles = enrich_articles(articles)

    logger.info("Step 4/4 — Sending personalized digests...")
    send_to_all_users(articles)

    markdown = build_markdown(articles)
    save_report(markdown, output_dir=REPORTS_DIR)
    logger.info("=== Done. ===")


if __name__ == "__main__":
    main()
