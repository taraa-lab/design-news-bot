"""
bot.py — Telegram bot with multi-language menu and interest selection.
Uses long-polling (run continuously or via GitHub Actions every minute).
"""
import os, logging, requests
from user_store import get_user, save_user

logger = logging.getLogger(__name__)

TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN","")
API_URL = f"https://api.telegram.org/bot{TOKEN}"

INTERESTS = {
    "automotive": {"fa":"🚗 طراحی خودرو",       "en":"🚗 Automotive Design"},
    "product":    {"fa":"📦 طراحی محصول",        "en":"📦 Product Design"},
    "furniture":  {"fa":"🪑 طراحی مبلمان",       "en":"🪑 Furniture Design"},
    "jewelry":    {"fa":"💍 طراحی جواهرات",      "en":"💍 Jewelry Design"},
    "accessory":  {"fa":"👜 طراحی اکسسوری",      "en":"👜 Accessory Design"},
    "service":    {"fa":"🔧 طراحی خدمات / UX",   "en":"🔧 Service / UX Design"},
}

STRINGS = {
    "fa": {
        "welcome":       "سلام! 👋\nخوش اومدی به ربات اخبار دیزاین.\nزبان مورد نظرت را انتخاب کن:",
        "lang_set":      "زبان فارسی تنظیم شد ✓\nحالا حوزه‌های علاقه‌ات را انتخاب کن 👇",
        "pick_interests":"حوزه‌هایی که دوست داری اخبارشون را بگیری را انتخاب کن.\n(می‌تونی چند تا انتخاب کنی)",
        "interests_set": "تنظیمات ذخیره شد ✓\nهر روز صبح اخبار انتخاب‌هایت می‌رسه 🎨",
        "news_cmd":      "در حال آماده‌سازی اخبار... لطفاً صبر کن ⏳",
        "no_news":       "امروز خبر جدیدی در حوزه‌های انتخابی تو نبود.",
        "help":          "دستورات:\n/start — شروع\n/news — دریافت اخبار همین الان\n/settings — تغییر تنظیمات\n/help — راهنما",
        "settings":      "تنظیمات فعلی تو:\nزبان: فارسی 🇮🇷\nعلاقه‌مندی‌ها:",
        "btn_done":      "✅ ذخیره",
        "btn_all":       "📰 همه اخبار",
        "competitions":  "🏆 اخبار مسابقات برای همه ارسال می‌شه",
    },
    "en": {
        "welcome":       "Hello! 👋\nWelcome to the Design News Bot.\nPlease choose your language:",
        "lang_set":      "English selected ✓\nNow pick your areas of interest 👇",
        "pick_interests":"Select the design areas you want news about.\n(You can pick multiple)",
        "interests_set": "Settings saved ✓\nYou'll receive your daily digest every morning 🎨",
        "news_cmd":      "Preparing your news... please wait ⏳",
        "no_news":       "No new articles found for your interests today.",
        "help":          "Commands:\n/start — Start\n/news — Get news now\n/settings — Change settings\n/help — Help",
        "settings":      "Your current settings:\nLanguage: English 🇬🇧\nInterests:",
        "btn_done":      "✅ Save",
        "btn_all":       "📰 All news",
        "competitions":  "🏆 Competition news is always included",
    }
}

# ─── send helpers ───────────────────────────────────────────────────
def send(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    payload = {"chat_id": chat_id, "text": text[:4096], "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{API_URL}/sendMessage", json=payload, timeout=20)

def send_doc(chat_id, file_path, caption=""):
    with open(file_path,"rb") as f:
        requests.post(f"{API_URL}/sendDocument",
                      data={"chat_id": chat_id, "caption": caption[:1024]},
                      files={"document": f}, timeout=60)

# ─── keyboards ──────────────────────────────────────────────────────
def lang_keyboard():
    return {"inline_keyboard":[[
        {"text":"🇮🇷 فارسی","callback_data":"lang_fa"},
        {"text":"🇬🇧 English","callback_data":"lang_en"},
    ]]}

def interest_keyboard(user_interests: list, lang: str):
    rows = []
    for key, labels in INTERESTS.items():
        selected = "✅ " if key in user_interests else "⬜ "
        rows.append([{"text": selected + labels[lang], "callback_data": f"int_{key}"}])
    # bottom row
    s = STRINGS[lang]
    rows.append([
        {"text": s["btn_all"],  "callback_data": "int_all"},
        {"text": s["btn_done"], "callback_data": "int_done"},
    ])
    return {"inline_keyboard": rows}

# ─── handlers ───────────────────────────────────────────────────────
def handle_start(chat_id, user_id):
    send(chat_id, STRINGS["fa"]["welcome"], lang_keyboard())

def handle_lang(chat_id, user_id, lang):
    user = get_user(user_id)
    user["lang"] = lang
    user["interests"] = []
    save_user(user_id, user)
    s = STRINGS[lang]
    send(chat_id, s["lang_set"] + "\n\n" + s["competitions"])
    send(chat_id, s["pick_interests"], interest_keyboard([], lang))

def handle_interest_toggle(chat_id, user_id, key, message_id):
    user = get_user(user_id)
    lang = user.get("lang","fa")
    interests = user.get("interests", [])

    if key == "all":
        interests = ["all"]
    elif key == "done":
        if not interests:
            interests = ["all"]
        user["interests"] = interests
        user["active"] = True
        save_user(user_id, user)
        send(chat_id, STRINGS[lang]["interests_set"])
        return
    else:
        if "all" in interests:
            interests = []
        if key in interests:
            interests.remove(key)
        else:
            interests.append(key)

    user["interests"] = interests
    save_user(user_id, user)

    # Edit the keyboard in-place
    requests.post(f"{API_URL}/editMessageReplyMarkup", json={
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": interest_keyboard(interests, lang)
    }, timeout=10)

def handle_settings(chat_id, user_id):
    user = get_user(user_id)
    lang = user.get("lang","fa")
    interests = user.get("interests",["all"])
    s = STRINGS[lang]
    interest_labels = ", ".join(INTERESTS.get(i,{}).get(lang, i) for i in interests if i!="all") or ("همه" if lang=="fa" else "All")
    send(chat_id, f"{s['settings']} {interest_labels}", interest_keyboard(interests, lang))

def handle_help(chat_id, user_id):
    user = get_user(user_id)
    lang = user.get("lang","fa")
    send(chat_id, STRINGS[lang]["help"])

# ─── main polling loop ───────────────────────────────────────────────
def poll_once(offset=0):
    r = requests.get(f"{API_URL}/getUpdates",
                     params={"offset": offset, "timeout": 10, "limit": 100},
                     timeout=20)
    if not r.ok:
        return offset
    updates = r.json().get("result", [])
    for u in updates:
        offset = u["update_id"] + 1
        try:
            process_update(u)
        except Exception as e:
            logger.error("Update error: %s", e)
    return offset

def process_update(u: dict):
    # Callback query (button press)
    if "callback_query" in u:
        cq       = u["callback_query"]
        user_id  = cq["from"]["id"]
        chat_id  = cq["message"]["chat"]["id"]
        msg_id   = cq["message"]["message_id"]
        data     = cq["data"]
        requests.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": cq["id"]}, timeout=5)

        if data.startswith("lang_"):
            handle_lang(chat_id, user_id, data[5:])
        elif data.startswith("int_"):
            handle_interest_toggle(chat_id, user_id, data[4:], msg_id)
        return

    # Text message / command
    msg     = u.get("message",{})
    if not msg: return
    user_id = msg["from"]["id"]
    chat_id = msg["chat"]["id"]
    text    = msg.get("text","").strip()

    if text.startswith("/start"):    handle_start(chat_id, user_id)
    elif text.startswith("/settings"): handle_settings(chat_id, user_id)
    elif text.startswith("/help"):   handle_help(chat_id, user_id)
    elif text.startswith("/news"):
        user = get_user(user_id)
        send(chat_id, STRINGS[user.get("lang","fa")]["news_cmd"])
        # Trigger delivery for this specific user
        deliver_to_user(user_id, chat_id, user)

def run_polling():
    """Run continuously (local or long-running server)."""
    import time
    offset = 0
    logger.info("Bot polling started")
    while True:
        offset = poll_once(offset)
        time.sleep(1)
