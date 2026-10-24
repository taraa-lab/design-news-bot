"""
sender.py — Build the personalized digest and send it via Telegram (HTML mode).

Each news post:
    <b>short fluent Persian title</b>
    summary (max ~3 lines)
    🏷 دسته‌بندی: ...
    لینک خبر            (hyperlinked to the article)
    https://t.me/WIDD_Iran

Messages are split on post boundaries (never mid-tag) to stay under Telegram's limit.
"""
import os
import re
import html
import time
import logging
import requests
from datetime import datetime, timezone, timedelta
from sheets import SheetsDB

logger = logging.getLogger(__name__)

CHANNEL_URL = "https://t.me/WIDD_Iran"
MAX_CHUNK_CHARS = 3800
SUMMARY_MAX_CHARS = 380

INTEREST_CATEGORIES = {
    "automotive": ["خودرو", "Automotive"],
    "product":    ["طراحی محصول", "Product Design", "طراحی صنعتی", "Industrial Design"],
    "furniture":  ["مبلمان", "Furniture"],
    "jewelry":    ["جواهرات", "Jewelry", "Jewelry Design", "طراحی جواهرات"],
    "accessory":  ["اکسسوری", "Accessory", "Accessory Design", "طراحی اکسسوری"],
    "service":    ["UX و طراحی خدمات", "UX / Service Design", "طراحی خدمات"],
}

COMPETITION_CATS = ["جوایز طراحی", "مسابقات طراحی", "Design Awards", "Design Competitions"]

IMPORTANCE_ORDER = {"بالا": 0, "High": 0, "متوسط": 1, "Medium": 1, "پایین": 2, "Low": 2}


def _esc(text) -> str:
    return html.escape(str(text or ""), quote=False)


def _shorten(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(".,،؛ ") + "…"


def _filter_for_user(articles: list, interests: list) -> list:
    allowed = set()
    for interest in interests:
        allowed.update(INTEREST_CATEGORIES.get(interest, []))
    result, seen = [], set()
    for a in articles:
        if a.url in seen:
            continue
        if a.category in COMPETITION_CATS or a.category in allowed:
            result.append(a)
            seen.add(a.url)
    return result


def _item_block(a, lang: str) -> str:
    cat_label = "🏷 دسته‌بندی" if lang == "fa" else "🏷 Category"
    link_word = "لینک خبر" if lang == "fa" else "Read more"
    title = (a.title or "").strip()
    summary = (a.summary or "").strip()
    if summary == title:
        summary = ""
    lines = []
    if title:
        lines.append(f"<b>{_esc(title)}</b>")
    if summary:
        lines.append(_esc(_shorten(summary, SUMMARY_MAX_CHARS)))
    lines.append(f"{cat_label}: {_esc(a.category)}")
    lines.append(f'<a href="{html.escape(a.url, quote=True)}">{link_word}</a>')
    lines.append(CHANNEL_URL)
    return "\n".join(lines)


def _pack(blocks: list) -> list:
    chunks, cur = [], ""
    for b in blocks:
        b = b[:MAX_CHUNK_CHARS]
        if cur and len(cur) + 2 + len(b) > MAX_CHUNK_CHARS:
            chunks.append(cur)
            cur = b
        else:
            cur = f"{cur}\n\n{b}" if cur else b
    if cur:
        chunks.append(cur)
    return chunks


def build_personal_digest_chunks(articles: list, interests: list, lang: str) -> list:
    filtered = _filter_for_user(articles, interests)
    if not filtered:
        return []

    ordered = sorted(filtered, key=lambda a: (IMPORTANCE_ORDER.get(a.importance, 2),
                                              -(a.published.timestamp() if a.published else 0)))
    today = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)).strftime("%Y-%m-%d")

    if lang == "fa":
        header = f"🎨 <b>اخبار امروز دیزاین</b> — {today}\n<i>{len(filtered)} خبر برای تو</i>"
        labels = {"بالا": "🔴 اهمیت بالا", "High": "🔴 اهمیت بالا",
                  "متوسط": "🟡 اهمیت متوسط", "Medium": "🟡 اهمیت متوسط",
                  "پایین": "🟢 سایر اخبار", "Low": "🟢 سایر اخبار"}
    else:
        header = f"🎨 <b>Design News Today</b> — {today}\n<i>{len(filtered)} articles for you</i>"
        labels = {"بالا": "🔴 High Priority", "High": "🔴 High Priority",
                  "متوسط": "🟡 Medium Priority", "Medium": "🟡 Medium Priority",
                  "پایین": "🟢 Other News", "Low": "🟢 Other News"}

    blocks, current = [header], None
    for a in ordered:
        imp = a.importance or "متوسط"
        prefix = ""
        if imp != current:
            current = imp
            prefix = f"<b>{labels.get(imp, _esc(imp))}</b>\n"
        blocks.append(prefix + _item_block(a, lang))
    return _pack(blocks)


def build_personal_digest(articles: list, interests: list, lang: str) -> str:
    """Compatibility helper: whole digest as one string (use the _chunks version to send)."""
    return "\n\n".join(build_personal_digest_chunks(articles, interests, lang))


# ──────────────────────────────────────────────
# Sending
# ──────────────────────────────────────────────
def competitions_keyboard(lang: str) -> dict:
    """Inline ('glass') button shown under every digest; handled by the Cloudflare Worker."""
    label = "🏆 مسابقات طراحی" if lang == "fa" else "🏆 Design Competitions"
    return {"inline_keyboard": [[{"text": label, "callback_data": f"comp_{lang}"}]]}


def _post_message(token: str, chat_id, text: str, parse_mode=None, reply_markup=None) -> bool:
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json=payload, timeout=30)
        if r.ok:
            return True
        logger.error("Telegram send failed (%s): %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.error("Telegram send error: %s", e)
    return False


def _to_plain(chunk: str) -> str:
    chunk = re.sub(r'<a href="([^"]+)">([^<]*)</a>', r"\2: \1", chunk)
    return html.unescape(re.sub(r"<[^>]+>", "", chunk))


def send_text(token: str, chat_id, text: str) -> bool:
    return _post_message(token, chat_id, text)


def send_chunks(token: str, chat_id, chunks: list, lang=None) -> bool:
    """Send digest messages; the competitions button is attached to the LAST one."""
    ok_all = True
    for i, chunk in enumerate(chunks):
        if i:
            time.sleep(0.6)
        kb = competitions_keyboard(lang) if lang and i == len(chunks) - 1 else None
        if not _post_message(token, chat_id, chunk, "HTML", kb):
            ok_all = _post_message(token, chat_id, _to_plain(chunk), None, kb) and ok_all
    return ok_all


def send_to_all_users(articles_fa: list, articles_en: list):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN")
        return

    users = SheetsDB().get_all_users()
    logger.info("Sending to %d users", len(users))

    for user in users:
        chat_id = user.get("chat_id", "")
        lang = user.get("lang", "fa")
        interests = [i for i in user.get("interests", "").split(",") if i]
        if not chat_id or not interests:
            continue

        articles = articles_fa if lang == "fa" else articles_en
        chunks = build_personal_digest_chunks(articles, interests, lang)
        if not chunks:
            send_text(token, chat_id,
                      "امروز خبری در حوزه‌های انتخابی تو پیدا نشد." if lang == "fa"
                      else "No news found for your selected areas today.")
        else:
            send_chunks(token, chat_id, chunks, lang)
        logger.info("Sent to user %s (%s, interests=%s, %d messages)",
                    chat_id, lang, interests, len(chunks))
        time.sleep(0.5)
