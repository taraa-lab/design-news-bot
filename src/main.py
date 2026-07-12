"""
main.py — Daily orchestrator: collect -> dedup -> enrich (fa+en) -> send personalized digests.
"""
import logging, sys, os, copy
from datetime import datetime, timezone, timedelta

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR    = os.path.join(BASE_DIR, "logs")
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
from sheets     import SheetsDB


def main():
    logger.info("=== Design News Bot starting ===")

    logger.info("Step 1/5 — Collecting...")
    articles_raw = collect_all()
    if not articles_raw:
        logger.warning("No articles found")
        return

    logger.info("Step 2/5 — Deduplicating...")
    articles_raw = deduplicate(articles_raw)
    logger.info("%d unique articles", len(articles_raw))

    logger.info("Step 3/5 — Enriching (fa + en)...")
    articles_fa = enrich_articles(copy.deepcopy(articles_raw), lang="fa")
    articles_en = enrich_articles(copy.deepcopy(articles_raw), lang="en")

    logger.info("Step 4/5 — Sending personalized digests...")
    users = SheetsDB().get_all_users()
    logger.info("Found %d registered users", len(users))
    send_to_all_users(articles_fa, articles_en)

    logger.info("Step 5/5 — Saving archive report...")
    markdown = build_markdown(articles_fa)
    save_report(markdown, output_dir=REPORTS_DIR)

    logger.info("=== Done. ===")


if __name__ == "__main__":
    main()
