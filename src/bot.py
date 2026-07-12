"""
bot.py — Stateless Telegram bot, driven by GitHub Actions cron (every minute).
Flow: /start -> choose language -> choose interests (multi-select) -> done -> 
      saves to Google Sheets -> sends personalized news immediately.
/news -> sends personalized news using saved preferences.
"""

import os, json, base64, logging, requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "taraa-lab/design-news-bot")
OFFSET_PATH  = "data/offset.json"
GH_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

INTERESTS_FA = {
    "automotive": "🚗 طراحی خودرو",
    "product":    "📦 طراحی محصول",
    "furniture":  "🛋️ طراحی مبلمان",
    "jewelry":    "💍 طراحی جواهرات",
    "accessory":  "👜 طراحی اکسسوری",
    "service":    "🔧 طراحی خدمات",
}
INTERESTS_EN = {
    "automotive": "🚗 Automotive Design",
    "product":    "📦 Product Design",
    "furniture":  "🛋️ Furniture Design",
    "jewelry":    "💍 Jewelry Design",
    "accessory":  "👜 Accessory Design",
    "service":    "🔧 Service Design",
}

TEXTS = {
    "fa": {
        "welcome":     "سلام! 👋 زبان مورد نظرت را انتخاب کن:",
        "choose_int":  "حوزه‌های علاقه‌مندیت را انتخاب کن (چند تا هم می‌شه):",
        "done_btn":    "✅ تأیید و دریافت اخبار",
        "no_interest": "⚠️ حداقل یک حوزه انتخاب کن!",
        "saved":       "✅ تنظیمات ذخیره شد!\n⏳ در حال آماده‌سازی اخبار امروز برات...",
        "saved2":      "از فردا هر روز ساعت ۸ صبح اخبار مرتبط با علاقه‌مندی‌هات می‌رسه.\n\n/news — اخبار همین الان\n/start — تغییر تنظیمات\n/help — راهنما",
        "news_wait":   "⏳ در حال جمع‌آوری اخبار... چند دقیقه صبر کن.",
        "no_news":     "امروز خبری در حوزه‌های انتخابی تو پیدا نشد.",
        "not_reg":     "ابتدا /start بزن تا زبان و علاقه‌مندی‌هات را انتخاب کنی.",
        "error":       "❌ خطا در دریافت اخبار. دوباره امتحان کن.",
        "help":        "📚 راهنما\n/news — اخبار همین الان\n/start — تغییر زبان یا علاقه‌مندی\n/help — این پیام\n\nهر روز ۸ صبح تهران اخبار می‌رسد.",
    },
    "en": {
        "welcome":     "Hello! 👋 Choose your language:",
        "choose_int":  "Select your areas of interest (multiple allowed):",
        "done_btn":    "✅ Confirm & Get News",
        "no_interest": "⚠️ Select at least one area!",
        "saved":       "✅ Settings saved!\n⏳ Preparing today's news for you...",
        "saved2":      "From tomorrow you'll get relevant news every morning at 8AM Tehran time.\n\n/news — Get news now\n/start — Change settings\n/help — Help",
        "news_wait":   "⏳ Collecting news... please wait.",
        "no_news":     "No news found for your selected areas today.",
        "not_reg":     "Please /start first to set your language and interests.",
        "error":       "❌ Error fetching news. Please try again.",
        "help":        "📚 Help\n/news — Get news now\n/start — Change language/interests\n/help — This message\n\nNews sent daily at 8AM Tehran time.",
    }
}

# ─────────────────────────────────────────────
# Raw Telegram API helpers
# ─────────────────────────────────────────────
def tg(method, **params):
    try:
        r = requests.post(f"{API}/{method}", json=params, timeout=20)
        return r.json()
    except Exception as e:
        logger.error("tg %s error: %s", method, e)
        return {}

def send_message(chat_id, text, keyboard=None, parse_mode="Markdown"):
    kwargs = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
              "disable_web_page_preview": True}
    if keyboard:
        kwargs["reply_markup"] = keyboard
    return tg("sendMessage", **kwargs)

def edit_message_text(chat_id, message_id, text, keyboard=None, parse_mode="Markdown"):
    kwargs = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
    if keyboard:
        kwargs["reply_markup"] = keyboard
    return tg("editMessageText", **kwargs)

def edit_message_reply_markup(chat_id, message_id, keyboard):
    return tg("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id, reply_markup=keyboard)

def answer_callback(callback_id, text=None, alert=False):
    kwargs = {"callback_query_id": callback_id}
    if text:
        kwargs["text"] = text
        kwargs["show_alert"] = alert
    return tg("answerCallbackQuery", **kwargs)

def lang_keyboard():
    return {"inline_keyboard": [[
        {"text": "🇮🇷 فارسی", "callback_data": "lang_fa"},
        {"text": "🇬🇧 English", "callback_data": "lang_en"},
    ]]}

def interests_keyboard(lang, selected):
    items = INTERESTS_FA if lang == "fa" else INTERESTS_EN
    kb = []
    for key, label in items.items():
        tick = "✓ " if key in selected else ""
        kb.append([{"text": tick + label, "callback_data": f"int_{key}"}])
    kb.append([{"text": TEXTS[lang]["done_btn"], "callback_data": "int_done"}])
    return {"inline_keyboard": kb}


# ─────────────────────────────────────────────
# Offset persistence (avoid reprocessing same updates)
# ─────────────────────────────────────────────
def _gh_get_file(path):
    r = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}", headers=GH_HEADERS)
    if r.status_code != 200:
        return None, None
    d = r.json()
    content = base64.b64decode(d["content"].replace("\n","")).decode("utf-8")
    return content, d["sha"]

def _gh_put_file(path, content, sha, msg):
    payload = {"message": msg, "content": base64.b64encode(content.encode()).decode()}
    if sha:
        payload["sha"] = sha
    r = requests.put(f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}",
                     headers=GH_HEADERS, json=payload)
    return r.status_code in (200, 201)

def get_offset():
    content, _ = _gh_get_file(OFFSET_PATH)
    if content is None:
        return 0
    try:
        return json.loads(content).get("offset", 0)
    except Exception:
        return 0

def save_offset(new_offset):
    content, sha = _gh_get_file(OFFSET_PATH)
    _gh_put_file(OFFSET_PATH, json.dumps({"offset": new_offset}), sha, "chore: update bot offset [skip ci]")


# ─────────────────────────────────────────────
# User storage (Google Sheets)
# ─────────────────────────────────────────────
def get_db():
    from sheets import SheetsDB
    return SheetsDB()


def get_user_interests(db, chat_id):
    user = db.get_user(str(chat_id))
    if not user:
        return []
    return [i for i in user.get("interests", "").split(",") if i]


# ─────────────────────────────────────────────
# Personalized news
# ─────────────────────────────────────────────
def send_personalized_news(chat_id, lang, interests):
    send_message(chat_id, TEXTS[lang]["news_wait"])
    try:
        from collector  import collect_all
        from dedup      import deduplicate
        from summarizer import enrich_articles
        from sender     import build_personal_digest

        articles = collect_all()
        articles = deduplicate(articles)
        articles = enrich_articles(articles, lang=lang)
        msg = build_personal_digest(articles, interests, lang)

        if not msg:
            send_message(chat_id, TEXTS[lang]["no_news"])
            return

        for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
            send_message(chat_id, chunk)
    except Exception as e:
        logger.error("news error: %s", e)
        send_message(chat_id, TEXTS[lang]["error"])


# ─────────────────────────────────────────────
# Update handlers
# ─────────────────────────────────────────────
def handle_command(chat_id, user, text, db):
    name = user.get("first_name", "") or user.get("username", "Unknown")
    cmd = text.split()[0].lower()

    if cmd in ("/start", "/lang"):
        send_message(chat_id, TEXTS["fa"]["welcome"], keyboard=lang_keyboard())
        return

    existing = db.get_user(str(chat_id))
    lang = existing.get("lang", "fa") if existing else "fa"

    if cmd == "/news":
        if not existing or not existing.get("interests"):
            send_message(chat_id, TEXTS[lang]["not_reg"])
            return
        interests = get_user_interests(db, chat_id)
        send_personalized_news(chat_id, lang, interests)
        return

    if cmd == "/help":
        send_message(chat_id, TEXTS[lang]["help"])
        return


def handle_callback(cq, db):
    chat_id    = cq["message"]["chat"]["id"]
    message_id = cq["message"]["message_id"]
    data       = cq["data"]
    callback_id = cq["id"]
    user       = cq["from"]
    name = user.get("first_name", "") or user.get("username", "Unknown")

    answer_callback(callback_id)

    # Language chosen
    if data.startswith("lang_"):
        lang = data.split("_")[1]
        existing = db.get_user(str(chat_id))
        interests = existing.get("interests", "") if existing else ""
        db.save_user(str(chat_id), name, lang, interests)

        edit_message_text(chat_id, message_id, TEXTS[lang]["choose_int"],
                          keyboard=interests_keyboard(lang, interests.split(",") if interests else []))
        return

    # Interest toggled
    if data.startswith("int_") and data != "int_done":
        key = data.replace("int_", "")
        existing = db.get_user(str(chat_id))
        lang = existing.get("lang", "fa") if existing else "fa"
        current = [i for i in existing.get("interests","").split(",") if i] if existing else []

        if key in current:
            current.remove(key)
        else:
            current.append(key)

        db.save_user(str(chat_id), name, lang, ",".join(current))
        edit_message_reply_markup(chat_id, message_id, interests_keyboard(lang, current))
        return

    # Done button
    if data == "int_done":
        existing = db.get_user(str(chat_id))
        lang = existing.get("lang", "fa") if existing else "fa"
        interests = [i for i in existing.get("interests","").split(",") if i] if existing else []

        if not interests:
            answer_callback(callback_id, TEXTS[lang]["no_interest"], alert=True)
            return

        edit_message_text(chat_id, message_id, TEXTS[lang]["saved"])
        send_personalized_news(chat_id, lang, interests)
        send_message(chat_id, TEXTS[lang]["saved2"])
        return


# ─────────────────────────────────────────────
# Main poll function (called by GitHub Actions every minute)
# ─────────────────────────────────────────────
def poll_once():
    if not BOT_TOKEN:
        logger.error("No TELEGRAM_BOT_TOKEN set")
        return

    offset = get_offset()
    resp = tg("getUpdates", offset=offset + 1 if offset else 0, timeout=0, limit=50)
    updates = resp.get("result", [])

    if not updates:
        logger.info("No new updates")
        return

    db = get_db()
    max_update_id = offset

    for update in updates:
        update_id = update["update_id"]
        max_update_id = max(max_update_id, update_id)

        try:
            if "message" in update and "text" in update["message"]:
                chat_id = update["message"]["chat"]["id"]
                user = update["message"]["from"]
                text = update["message"]["text"]
                handle_command(chat_id, user, text, db)

            elif "callback_query" in update:
                handle_callback(update["callback_query"], db)

        except Exception as e:
            logger.error("Error processing update %s: %s", update_id, e)

    save_offset(max_update_id)
    logger.info("Processed %d updates, new offset=%d", len(updates), max_update_id)


if __name__ == "__main__":
    poll_once()
