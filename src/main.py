"""
main.py — Orchestrator: collect -> dedup -> enrich -> report -> deliver.
"""

import logging
import sys
import os
from datetime import datetime, timezone, timedelta

# Fix paths — run from any directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

log_file = os.path.join(LOGS_DIR, f"run-{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

from collector  import collect_all
from dedup      import deduplicate
from summarizer import enrich_articles
from report     import build_markdown, save_report, build_telegram_message
from deliver    import send_telegram_message, send_telegram_document, send_gmail


def main():
    logger.info("=== Design News Bot starting ===")

    # 1. Collect
    logger.info("Step 1/5 - Collecting articles...")
    articles = collect_all()
    if not articles:
        logger.warning("No articles found - exiting early")
        send_telegram_message("Design News Bot: No articles found today.")
        return

    # 2. Deduplicate
    logger.info("Step 2/5 - Deduplicating...")
    articles = deduplicate(articles)

    # 3. Enrich with AI
    logger.info("Step 3/5 - Enriching with AI (%d articles)...", len(articles))
    articles = enrich_articles(articles)

    # 4. Build report
    logger.info("Step 4/5 - Building report...")
    markdown = build_markdown(articles)
    report_path = save_report(markdown, output_dir=REPORTS_DIR)
    logger.info("Report saved: %s", report_path)

    tg_msg = build_telegram_message(articles)

    # 5. Deliver
    logger.info("Step 5/5 - Delivering...")
    today_str = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)).strftime("%Y-%m-%d")

    send_telegram_message(tg_msg)
    send_telegram_document(report_path, caption=f"Full report - {today_str}")
    send_gmail(
        subject=f"Industrial Design Daily - {today_str}",
        markdown_body=markdown,
        attachment_path=report_path,
    )

    logger.info("=== Done. %d articles delivered. ===", len(articles))


if __name__ == "__main__":
    main()
