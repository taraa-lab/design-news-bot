"""
sender.py (v3) — personalized digest layout + Telegram sending (HTML mode).

Layout per news item:
    <b>عنوان فارسی</b>
    <blockquote>خلاصه (حداکثر ~۳ خط)</blockquote>
    🏷 #دسته_بندی  📰 منبع
    🔗 لینک خبر                (hyperlink)
    https://t.me/WIDD_Iran

Messages are split on item boundaries only (never inside a tag).
"""
import os, re, html, time, logging, requests
from datetime import datetime, timezone, timedelta
from sheets import SheetsDB

logger = logging.getLogger(__name__)

CHANNEL_URL = "https://t.me/WIDD_Iran"
MAX_CHUNK_CHARS = 3800
SUMMARY_MAX_CHARS = 380
ITEM_SEP = "┈┈┈┈┈┈┈┈┈┈┈┈┈┈"
HEAD_SEP = "━━━━━━━━━━━━━━"

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

_JM = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
_WD_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]   # datetime.weekday() order


def gregorian_to_jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def _fa_digits(s) -> str:
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def tehran_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)


def format_date(lang: str, dt=None) -> str:
    dt = dt or tehran_now()
    if lang == "fa":
        jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
        return f"{_WD_FA[dt.weekday()]} {_fa_digits(jd)} {_JM[jm - 1]} {_fa_digits(jy)}"
    return dt.strftime("%a, %d %b %Y")


def _esc(text) -> str:
    return html.escape(str(text or ""), quote=False)


def _shorten(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(".,،؛ ") + "…"


def _hashtag(category: str) -> str:
    t = re.sub(r"[^\w\u0600-\u06FF]+", "_", category or "").strip("_")
    return f"#{t}" if t else ""


def _filter_for_user(articles: list, interests: list) -> list:
    allowed = set()
    for i in interests:
        allowed.update(INTEREST_CATEGORIES.get(i, []))
    out, seen = [], set()
    for a in articles:
        if a.url in seen:
            continue
        if getattr(a, "force_all", False) or a.category in COMPETITION_CATS or a.category in allowed:
            out.append(a)
            seen.add(a.url)
    return out


def item_block(a, lang: str) -> str:
    link_word = "لینک خبر" if lang == "fa" else "Read more"
    title, summary = (a.title or "").strip(), (a.summary or "").strip()
    if summary == title:
        summary = ""
    lines = []
    if title:
        lines.append(f"<b>{_esc(title)}</b>")
    if summary:
        lines.append(f"<blockquote>{_esc(_shorten(summary, SUMMARY_MAX_CHARS))}</blockquote>")
    meta = []
    if _hashtag(a.category):
        meta.append(f"🏷 {_hashtag(a.category)}")
    if a.source:
        meta.append(f"📰 {_esc(a.source)}")
    if meta:
        lines.append("   ".join(meta))
    lines.append(f'<a href="{html.escape(a.url, quote=True)}">🔗 {link_word}</a>')
    lines.append(CHANNEL_URL)
    return "\n".join(lines)


_item_block = item_block   # backward-compatible name


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
    date = format_date(lang)
    if lang == "fa":
        header = f"🎨 <b>اخبار روز دیزاین و طراحی صنعتی</b>\n📆 {date}  ·  {_fa_digits(len(filtered))} خبر برای شما\n{HEAD_SEP}"
        labels = {"بالا": "🔴 مهم‌ترین اخبار", "متوسط": "🟡 اخبار مهم", "پایین": "🟢 سایر اخبار"}
        labels.update({"High": labels["بالا"], "Medium": labels["متوسط"], "Low": labels["پایین"]})
    else:
        header = f"🎨 <b>Design &amp; Industrial Design News</b>\n📆 {date}  ·  {len(filtered)} stories for you\n{HEAD_SEP}"
        labels = {"High": "🔴 Top stories", "Medium": "🟡 Important", "Low": "🟢 More news"}
        labels.update({"بالا": labels["High"], "متوسط": labels["Medium"], "پایین": labels["Low"]})

    blocks, current = [header], None
    for a in ordered:
        imp = a.importance or "متوسط"
        if imp != current:
            current = imp
            blocks.append(f"<b>{labels.get(imp, _esc(imp))}</b>\n\n{item_block(a, lang)}")
        else:
            blocks.append(f"{ITEM_SEP}\n{item_block(a, lang)}")
    return _pack(blocks)


def build_personal_digest(articles: list, interests: list, lang: str) -> str:
    return "\n\n".join(build_personal_digest_chunks(articles, interests, lang))


# ───────────── keyboard + sending ─────────────
def main_keyboard(lang: str) -> dict:
    """Inline ('glass') buttons under digests; callbacks are handled by the Cloudflare Worker."""
    comp = "🏆 مسابقات طراحی" if lang == "fa" else "🏆 Design Competitions"
    sub = "📨 ارسال خبر" if lang == "fa" else "📨 Submit news"
    return {"inline_keyboard": [[{"text": comp, "callback_data": f"comp_{lang}"}],
                                [{"text": sub, "callback_data": f"submit_{lang}"}]]}


competitions_keyboard = main_keyboard   # backward-compatible name


def _post_message(token: str, chat_id, text: str, parse_mode=None, reply_markup=None) -> bool:
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=30)
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


def send_html(token: str, chat_id, text: str, reply_markup=None) -> bool:
    """HTML first; plain-text fallback if Telegram rejects the markup."""
    if _post_message(token, chat_id, text, "HTML", reply_markup):
        return True
    return _post_message(token, chat_id, _to_plain(text), None, reply_markup)


def send_chunks(token: str, chat_id, chunks: list, lang=None) -> bool:
    ok_all = True
    for i, chunk in enumerate(chunks):
        if i:
            time.sleep(0.6)
        kb = main_keyboard(lang) if lang and i == len(chunks) - 1 else None
        ok_all = send_html(token, chat_id, chunk, kb) and ok_all
    return ok_all


def send_to_all_users(articles_fa: list, articles_en: list):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN")
        return
    users = SheetsDB().get_all_users()
    logger.info("Sending to %d users", len(users))
    for user in users:
        chat_id, lang = user.get("chat_id", ""), user.get("lang", "fa")
        interests = [i for i in user.get("interests", "").split(",") if i]
        if not chat_id or not interests:
            continue
        chunks = build_personal_digest_chunks(articles_fa if lang == "fa" else articles_en, interests, lang)
        if not chunks:
            send_text(token, chat_id, "امروز خبری در حوزه‌های انتخابی تو پیدا نشد." if lang == "fa"
                      else "No news found for your selected areas today.")
        else:
            send_chunks(token, chat_id, chunks, lang)
        logger.info("Sent digest (%s, interests=%s, %d messages)", lang, interests, len(chunks))
        time.sleep(0.5)
