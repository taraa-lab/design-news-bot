"""
main.py — Orchestrator for scheduled daily digest (multi-user).
"""
import logging, sys, os
from datetime import datetime, timezone, timedelta

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR    = os.path.join(BASE_DIR, "logs")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(LOGS_DIR,    exist_ok=True)
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

from collector   import collect_all
from dedup       import deduplicate
from summarizer  import enrich_articles
from report      import build_markdown, save_report, build_telegram_message_for_user
from deliver     import send_telegram_message, send_telegram_document, send_gmail
from user_store  import get_all_users
from bot         import poll_once, INTERESTS

# Categories always sent to everyone regardless of interests
COMPETITION_CATS = {"مسابقات طراحی", "جوایز طراحی", "Design Competitions", "Design Awards"}

INTEREST_CATEGORY_MAP = {
    "automotive": {"خودرو", "Automotive"},
    "product":    {"طراحی محصول", "طراحی صنعتی", "Product Design", "Industrial Design"},
    "furniture":  {"مبلمان", "Furniture"},
    "jewelry":    {"جواهرات", "Jewelry", "طراحی جواهر"},
    "accessory":  {"اکسسوری", "Accessory", "طراحی اکسسوری"},
    "service":    {"UX و طراحی خدمات", "UX / Service Design"},
}

def filter_articles_for_user(articles, interests):
    if not interests or "all" in interests:
        return articles
    allowed_cats = set(COMPETITION_CATS)
    for interest in interests:
        allowed_cats |= INTEREST_CATEGORY_MAP.get(interest, set())
    return [a for a in articles if a.category in allowed_cats or
            any(c in a.category for c in allowed_cats)]


def main():
    logger.info("=== Design News Bot (multi-user) starting ===")

    # Poll bot commands first (handle /news requests etc.)
    logger.info("Polling bot commands...")
    poll_once()

    # Collect + process articles once for all users
    logger.info("Step 1/4 — Collecting...")
    articles = collect_all()
    if not articles:
        logger.warning("No articles found")
        return

    logger.info("Step 2/4 — Deduplicating...")
    articles = deduplicate(articles)

    logger.info("Step 3/4 — Enriching (%d articles)...", len(articles))
    articles = enrich_articles(articles)

    # Save full report
    today_str = (datetime.now(timezone.utc) + timedelta(hours=3,minutes=30)).strftime("%Y-%m-%d")

    logger.info("Step 4/4 — Delivering to users...")
    users = get_all_users()

    if not users:
        # Fallback: send to default chat_id if no users registered
        default_chat = os.environ.get("TELEGRAM_CHAT_ID","")
        if default_chat:
            markdown = build_markdown(articles)
            path = save_report(markdown, REPORTS_DIR)
            send_telegram_message(build_telegram_message_for_user(articles, "fa", ["all"]))
            send_telegram_document(path, caption=f"📄 گزارش کامل — {today_str}")
        return

    for user_id, user_data in users.items():
        if not user_data.get("active", True):
            continue
        chat_id   = user_data.get("chat_id", user_id)
        lang      = user_data.get("lang", "fa")
        interests = user_data.get("interests", ["all"])

        user_articles = filter_articles_for_user(articles, interests)
        if not user_articles:
            continue

        markdown   = build_markdown(user_articles, lang=lang)
        report_path = save_report(markdown, REPORTS_DIR)
        tg_msg     = build_telegram_message_for_user(user_articles, lang, interests)

        send_telegram_message(tg_msg, chat_id=chat_id)
        send_telegram_document(report_path, caption=f"📄 {'گزارش کامل' if lang=='fa' else 'Full Report'} — {today_str}", chat_id=chat_id)

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
