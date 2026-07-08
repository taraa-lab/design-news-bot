"""
main.py — Orchestrator: collects news twice (fa+en) and sends each user in their language.
"""
import logging, sys, os, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR    = os.path.join(BASE_DIR, "logs")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
USERS_FILE  = Path(BASE_DIR) / "users.json"

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

def load_users():
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}

def send_to_user(chat_id, msg, token):
    import requests as req
    for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
        try:
            req.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk,
                      "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=30
            )
        except Exception as e:
            logger.error("Send error to %s: %s", chat_id, e)

def main():
    logger.info("=== Design News Bot starting ===")
    token = os.environ.get("TELEGRAM_BOT_TOKEN","")

    # 1. Collect & dedup once
    logger.info("Step 1/4 — Collecting...")
    articles_raw = collect_all()
    if not articles_raw:
        logger.warning("No articles found")
        send_telegram_message("⚠️ No articles found today.")
        return

    logger.info("Step 2/4 — Deduplicating...")
    articles_raw = deduplicate(articles_raw)
    logger.info("%d unique articles", len(articles_raw))

    # 2. Enrich in both languages (cache results)
    logger.info("Step 3/4 — Enriching...")
    import copy
    articles_fa = enrich_articles(copy.deepcopy(articles_raw), lang="fa")
    articles_en = enrich_articles(copy.deepcopy(articles_raw), lang="en")

    # 3. Send per-user in their language
    logger.info("Step 4/4 — Sending...")
    users = load_users()
    today_str = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)).strftime("%Y-%m-%d")

    if users:
        for chat_id, prefs in users.items():
            lang = prefs.get("lang", "fa")
            articles = articles_fa if lang == "fa" else articles_en
            msg = build_telegram_message(articles, lang=lang)
            send_to_user(chat_id, msg, token)
            logger.info("Sent to %s (lang=%s)", chat_id, lang)
    else:
        # Fallback: send to TELEGRAM_CHAT_ID with default lang
        default_lang = os.environ.get("OUTPUT_LANG","fa")
        articles = articles_fa if default_lang == "fa" else articles_en
        msg = build_telegram_message(articles, lang=default_lang)
        send_telegram_message(msg)
        # Save markdown report & send as file
        markdown = build_markdown(articles)
        report_path = save_report(markdown, output_dir=REPORTS_DIR)
        send_telegram_document(report_path, caption=f"📄 گزارش کامل — {today_str}")
        send_gmail(subject=f"🎨 اخبار دیزاین — {today_str}", markdown_body=markdown, attachment_path=report_path)

    logger.info("=== Done. ===")

if __name__ == "__main__":
    main()
