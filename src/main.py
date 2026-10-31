"""
main.py — Daily orchestrator: collect -> dedup -> enrich (fa+en) -> cache -> send digests.
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
from cache      import save_cache
from manual     import load_manual_articles


def main():
    logger.info("=== Design News Bot starting ===")

    logger.info("Step 1/6 — Collecting...")
    articles_raw = collect_all()
    if not articles_raw:
        logger.warning("No articles found")
        return

    logger.info("Step 2/6 — Deduplicating...")
    articles_raw = deduplicate(articles_raw)
    logger.info("%d unique articles", len(articles_raw))

    users = SheetsDB().get_all_users()
    langs = {(u.get("lang") or "fa") for u in users} | {"fa"}
    logger.info("Registered users: %d | languages needed: %s", len(users), sorted(langs))

    logger.info("Step 3/6 — Enriching (fa)...")
    articles_fa = enrich_articles(copy.deepcopy(articles_raw), lang="fa")
    articles_en = []
    if "en" in langs:
        logger.info("Step 4/6 — Enriching (en)...")
        articles_en = enrich_articles(copy.deepcopy(articles_raw), lang="en")
    else:
        logger.info("Step 4/6 — No English users: skipping English enrichment (saves AI quota).")

    logger.info("Step 5/6 — Saving cache for instant on-demand responses...")
    save_cache("fa", articles_fa)
    if articles_en:
        save_cache("en", articles_en)

    # Admin-curated news is merged AFTER caching so the cache stays "automatic news only".
    articles_fa = articles_fa + load_manual_articles("fa")
    articles_en = articles_en + load_manual_articles("en")

    if os.environ.get("SKIP_SEND", "").lower() == "true":
        logger.info("Step 6/6 — SKIP_SEND=true: cache refreshed, not sending to users.")
    else:
        logger.info("Step 6/6 — Sending personalized digests...")
        send_to_all_users(articles_fa, articles_en)

    markdown = build_markdown(articles_fa)
    save_report(markdown, output_dir=REPORTS_DIR)

    logger.info("=== Done. ===")


if __name__ == "__main__":
    main()
