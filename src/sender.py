"""
sender.py — Build personalized digest per user and send to all users.
Message format: 3-line Persian summary, then "لینک خبر" as the clickable link
(saves space vs. long titles-as-links, fits more news per Telegram message).
"""

import os
import logging
import requests
from sheets import SheetsDB

logger = logging.getLogger(__name__)

INTEREST_CATEGORIES = {
    "automotive": ["خودرو", "Automotive"],
    "product":    ["طراحی محصول", "Product Design", "طراحی صنعتی", "Industrial Design"],
    "furniture":  ["مبلمان", "Furniture"],
    "jewelry":    ["جواهرات", "Jewelry", "Jewelry Design", "طراحی جواهرات"],
    "accessory":  ["اکسسوری", "Accessory", "Accessory Design", "طراحی اکسسوری"],
    "service":    ["UX و طراحی خدمات", "UX / Service Design", "طراحی خدمات"],
}

COMPETITION_CATS = ["جوایز طراحی", "مسابقات طراحی", "Design Awards", "Design Competitions"]


def _escape_md(text: str) -> str:
    """Escape Telegram Markdown special characters in AI-generated text."""
    for ch in ("_", "*", "[", "]"):
        text = text.replace(ch, "\\" + ch)
    return text


def _filter_for_user(articles: list, interests: list) -> list:
    allowed_cats = set()
    for interest in interests:
        for cat in INTEREST_CATEGORIES.get(interest, []):
            allowed_cats.add(cat)

    result, seen = [], set()
    for a in articles:
        if a.url in seen:
            continue
        if a.category in COMPETITION_CATS or a.category in allowed_cats:
            result.append(a)
            seen.add(a.url)
    return result


def build_personal_digest(articles: list, interests: list, lang: str) -> str:
    filtered = _filter_for_user(articles, interests)
    if not filtered:
        return ""

    IMPORTANCE_ORDER = {"بالا": 0, "High": 0, "متوسط": 1, "Medium": 1, "پایین": 2, "Low": 2}
    sorted_arts = sorted(filtered, key=lambda a: (IMPORTANCE_ORDER.get(a.importance, 2),
                                                   -(a.published.timestamp() if a.published else 0)))

    from datetime import datetime, timezone, timedelta
    today = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)).strftime("%Y-%m-%d")

    if lang == "fa":
        header = f"🎨 *اخبار امروز دیزاین* — {today}\n_{len(filtered)} خبر برای تو_\n"
        imp_labels = {"بالا": "🔴 اهمیت بالا", "High": "🔴 اهمیت بالا",
                      "متوسط": "🟡 اهمیت متوسط", "Medium": "🟡 اهمیت متوسط",
                      "پایین": "🟢 سایر اخبار", "Low": "🟢 سایر اخبار"}
        link_word = "لینک خبر"
    else:
        header = f"🎨 *Design News Today* — {today}\n_{len(filtered)} articles for you_\n"
        imp_labels = {"بالا": "🔴 High Priority", "High": "🔴 High Priority",
                      "متوسط": "🟡 Medium Priority", "Medium": "🟡 Medium Priority",
                      "پایین": "🟢 Other News", "Low": "🟢 Other News"}
        link_word = "Read more"

    parts = [header]
    current_imp = None
    for a in sorted_arts:
        imp = a.importance or "متوسط"
        if imp != current_imp:
            current_imp = imp
            parts.append(f"*{imp_labels.get(imp, imp)}*")

        summary = _escape_md((a.summary or a.title).strip())
        parts.append(summary)
        parts.append(f"[{link_word}]({a.url})")
        parts.append("")   # blank line between items

    return "\n".join(parts)


def send_to_all_users(articles_fa: list, articles_en: list):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN")
        return

    db = SheetsDB()
    users = db.get_all_users()
    logger.info("Sending to %d users", len(users))

    for user in users:
        chat_id   = user.get("chat_id", "")
        lang      = user.get("lang", "fa")
        interests = [i for i in user.get("interests", "").split(",") if i]

        if not chat_id or not interests:
            continue

        articles = articles_fa if lang == "fa" else articles_en
        msg = build_personal_digest(articles, interests, lang)
        if not msg:
            no_news = "امروز خبری در حوزه‌های انتخابی تو پیدا نشد." if lang=="fa" else "No news found for your selected areas today."
            msg = no_news

        for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk,
                          "parse_mode": "Markdown", "disable_web_page_preview": True},
                    timeout=30
                )
            except Exception as e:
                logger.error("Send error to %s: %s", chat_id, e)

        logger.info("Sent to user %s (%s, interests=%s)", chat_id, lang, interests)
