"""
bot.py — Telegram Bot: /start, /lang, /news, /help
When user picks a language, news is sent immediately.
"""

import os, json, logging
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

USERS_FILE = Path(__file__).parent.parent / "users.json"

TEXTS = {
    "fa": {
        "start":    "سلام! 👋 زبان مورد نظرت را انتخاب کن:",
        "saved":    "✅ زبان فارسی انتخاب شد.\n⏳ در حال آماده‌سازی اخبار امروز برات...",
        "saved2":   "از فردا هر روز ساعت ۸ صبح اخبار می‌رسد.\n\n/news — اخبار همین الان\n/lang — تغییر زبان\n/help — راهنما",
        "news_wait":"⏳ در حال جمع‌آوری اخبار... چند دقیقه صبر کن.",
        "no_news":  "امروز خبری پیدا نشد.",
        "error":    "❌ خطا در دریافت اخبار. دوباره امتحان کن.",
        "help":     "📚 راهنما\n/news — اخبار همین الان\n/lang — تغییر زبان\n/help — این پیام\n\nهر روز ۸ صبح تهران اخبار ارسال می‌شه.",
    },
    "en": {
        "start":    "Hello! 👋 Choose your language:",
        "saved":    "✅ English selected.\n⏳ Preparing today's news for you...",
        "saved2":   "From tomorrow you'll get news every morning at 8AM Tehran time.\n\n/news — Get news now\n/lang — Change language\n/help — Help",
        "news_wait":"⏳ Collecting news... please wait.",
        "no_news":  "No news found today.",
        "error":    "❌ Error fetching news. Please try again.",
        "help":     "📚 Help\n/news — Get news now\n/lang — Change language\n/help — This message\n\nNews is sent daily at 8AM Tehran time.",
    }
}

def load_users():
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}

def save_users(data):
    USERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def get_lang(chat_id):
    users = load_users()
    return users.get(str(chat_id), {}).get("lang", "fa")

def set_lang(chat_id, lang):
    users = load_users()
    users.setdefault(str(chat_id), {})["lang"] = lang
    save_users(users)

def lang_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇮🇷 فارسی", callback_data="setlang_fa"),
        InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en"),
    ]])

async def _send_news(update_or_query, lang, is_callback=False):
    """Fetch & send fresh news immediately. Works for both /news and post-lang-select."""
    reply_fn = update_or_query.message.reply_text if not is_callback else update_or_query.message.reply_text

    await reply_fn(TEXTS[lang]["news_wait"])
    try:
        from collector  import collect_all
        from dedup      import deduplicate
        from summarizer import enrich_articles
        from report     import build_telegram_message

        articles = collect_all()
        articles = deduplicate(articles)
        articles = enrich_articles(articles, lang=lang)
        msg = build_telegram_message(articles, lang=lang)
        if not msg:
            await reply_fn(TEXTS[lang]["no_news"])
            return
        for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
            await reply_fn(chunk, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        logger.error("news error: %s", e)
        await reply_fn(TEXTS[lang]["error"])

async def start(update, ctx):
    await update.message.reply_text(TEXTS["fa"]["start"], reply_markup=lang_keyboard())

async def lang_cmd(update, ctx):
    await update.message.reply_text(TEXTS["fa"]["start"], reply_markup=lang_keyboard())

async def lang_callback(update, ctx):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_")[1]
    set_lang(query.from_user.id, lang)

    # Confirm language choice
    await query.edit_message_text(TEXTS[lang]["saved"])

    # Immediately fetch and send today's news
    await _send_news(query, lang, is_callback=True)

    # Final info message
    await query.message.reply_text(TEXTS[lang]["saved2"])

async def news_now(update, ctx):
    lang = get_lang(update.effective_user.id)
    await _send_news(update, lang)

async def help_cmd(update, ctx):
    lang = get_lang(update.effective_user.id)
    await update.message.reply_text(TEXTS[lang]["help"])

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lang",  lang_cmd))
    app.add_handler(CommandHandler("news",  news_now))
    app.add_handler(CommandHandler("help",  help_cmd))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern="^setlang_"))
    logger.info("Bot polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
