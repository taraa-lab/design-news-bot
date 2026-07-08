"""
main.py — Orchestrator
"""
import logging, sys, os
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
from report     import build_markdown, save_report, build_telegram_message
from deliver    import send_telegram_message, send_telegram_document, send_gmail

def main():
    lang = os.environ.get("OUTPUT_LANG", "fa")
    logger.info("=== Design News Bot starting (lang=%s) ===", lang)

    logger.info("Step 1/5 — Collecting...")
    articles = collect_all()
    if not articles:
        logger.warning("No articles found")
        send_telegram_message("⚠️ Design News Bot: No articles found today.")
        return

    logger.info("Step 2/5 — Deduplicating...")
    articles = deduplicate(articles)

    logger.info("Step 3/5 — Enriching (%d articles, lang=%s)...", len(articles), lang)
    articles = enrich_articles(articles, lang=lang)

    logger.info("Step 4/5 — Building report...")
    markdown    = build_markdown(articles)
    report_path = save_report(markdown, output_dir=REPORTS_DIR)
    tg_msg      = build_telegram_message(articles)

    logger.info("Step 5/5 — Delivering...")
    today_str = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)).strftime("%Y-%m-%d")
    send_telegram_message(tg_msg)
    send_telegram_document(report_path, caption=f"📄 گزارش کامل — {today_str}")
    send_gmail(subject=f"🎨 اخبار دیزاین — {today_str}", markdown_body=markdown, attachment_path=report_path)
    logger.info("=== Done. %d articles delivered. ===", len(articles))

if __name__ == "__main__":
    main()
