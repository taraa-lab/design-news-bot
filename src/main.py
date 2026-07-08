"""
main.py — Orchestrator. Sends FA digest by default; lang detected from env.
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
        logging.FileHandler(os.path.join(LOGS_DIR, f"run-{datetime.now().strftime(\'%Y%m%d\')}.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

from collector  import collect_all
from dedup      import deduplicate
from summarizer import enrich_articles
from report     import build_markdown, save_report, build_telegram_message
from deliver    import send_telegram_message, send_telegram_document, send_gmail

def main():
    lang = os.environ.get("OUTPUT_LANG", "fa")   # fa or en
    logger.info("=== Design News Bot | lang=%s ===", lang)

    logger.info("Step 1/4 — Collecting...")
    articles = collect_all()
    if not articles:
        logger.warning("No articles found")
        send_telegram_message("⚠️ Design News Bot: خبری امروز پیدا نشد.")
        return

    logger.info("Step 2/4 — Deduplicating (%d)...", len(articles))
    articles = deduplicate(articles)

    logger.info("Step 3/4 — Enriching in lang=%s (%d articles)...", lang, len(articles))
    articles = enrich_articles(articles, lang=lang)

    logger.info("Step 4/4 — Delivering...")
    markdown    = build_markdown(articles, lang=lang)
    report_path = save_report(markdown, output_dir=REPORTS_DIR)
    tg_msg      = build_telegram_message(articles, lang=lang)
    today_str   = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)).strftime("%Y-%m-%d")

    send_telegram_message(tg_msg)
    send_telegram_document(report_path, caption=f"📄 {'گزارش کامل' if lang=='fa' else 'Full Report'} — {today_str}")
    send_gmail(
        subject=f"{'🎨 اخبار دیزاین' if lang=='fa' else '🎨 Design News'} — {today_str}",
        markdown_body=markdown,
        attachment_path=report_path,
    )
    logger.info("=== Done. %d articles. ===", len(articles))

if __name__ == "__main__":
    main()
