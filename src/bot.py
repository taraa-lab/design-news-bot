"""
bot.py — Telegram Bot with inline menu, multi-user, multi-language.
Stores user preferences in Google Sheets.
Run with: python bot.py
"""

import os
import json
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)
from sheets import SheetsDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Conversation states
LANG, INTERESTS = range(2)

INTERESTS_FA = {
    "automotive":   "🚗 طراحی خودرو",
    "product":      "📦 طراحی محصول",
    "furniture":    "🛋️ طراحی مبلمان",
    "jewelry":      "💍 طراحی جواهرات",
    "accessory":    "👜 طراحی اکسسوری",
    "service":      "🔧 طراحی خدمات",
}

INTERESTS_EN = {
    "automotive":   "🚗 Automotive Design",
    "product":      "📦 Product Design",
    "furniture":    "🛋️ Furniture Design",
    "jewelry":      "💍 Jewelry Design",
    "accessory":    "👜 Accessory Design",
    "service":      "🔧 Service Design",
}

TEXTS = {
    "fa": {
        "welcome":      "سلام! 👋\nبه ربات اخبار دیزاین خوش اومدی.\n\nزبان مورد نظرت را انتخاب کن:",
        "choose_lang":  "زبان / Language:",
        "choose_int":   "حوزه‌های علاقه‌مندیت را انتخاب کن:\n(می‌تونی چند تا انتخاب کنی)",
        "done_btn":     "✅ تأیید و ذخیره",
        "saved":        "✅ تنظیماتت ذخیره شد!\nهر روز ساعت ۸ صبح اخبار مرتبط با علاقه‌مندی‌هات برات می‌رسه.\n\nدستورات:\n/news — اخبار همین الان\n/settings — تغییر تنظیمات\n/help — راهنما",
        "no_interest":  "⚠️ حداقل یک حوزه انتخاب کن!",
        "news_wait":    "⏳ در حال جمع‌آوری اخبار... چند دقیقه صبر کن.",
        "no_news":      "امروز خبری در حوزه‌های انتخابی تو پیدا نشد.",
        "settings":     "تنظیمات فعلی:\n🌐 زبان: فارسی\n📌 حوزه‌ها: {interests}\n\nبرای تغییر /start بزن",
        "help":         "📚 راهنما\n\n/start — شروع و تنظیم اولیه\n/news — دریافت اخبار همین الان\n/settings — مشاهده تنظیمات\n/help — این پیام\n\nهر روز ساعت ۸ صبح به وقت تهران اخبار برات ارسال می‌شه.",
    },
    "en": {
        "welcome":      "Hello! 👋\nWelcome to the Design News Bot.\n\nChoose your language:",
        "choose_lang":  "Language:",
        "choose_int":   "Select your areas of interest:\n(You can choose multiple)",
        "done_btn":     "✅ Save & Continue",
        "saved":        "✅ Settings saved!\nYou'll receive relevant news every morning at 8AM Tehran time.\n\nCommands:\n/news — Get news now\n/settings — Change settings\n/help — Help",
        "no_interest":  "⚠️ Please select at least one area!",
        "news_wait":    "⏳ Collecting news... please wait a moment.",
        "no_news":      "No news found for your selected areas today.",
        "settings":     "Current settings:\n🌐 Language: English\n📌 Areas: {interests}\n\nUse /start to change settings",
        "help":         "📚 Help\n\n/start — Initial setup\n/news — Get news now\n/settings — View settings\n/help — This message\n\nNews is sent daily at 8AM Tehran time.",
    }
}

db = SheetsDB()


# ── /start ──────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
    ]]
    await update.message.reply_text(
        TEXTS["fa"]["welcome"],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return LANG


async def lang_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_")[1]   # "fa" or "en"
    ctx.user_data["lang"] = lang
    ctx.user_data["selected"] = []

    interests = INTERESTS_FA if lang == "fa" else INTERESTS_EN
    keyboard = []
    for key, label in interests.items():
        keyboard.append([InlineKeyboardButton(label, callback_data=f"int_{key}")])
    keyboard.append([InlineKeyboardButton(TEXTS[lang]["done_btn"], callback_data="int_done")])

    await query.edit_message_text(
        TEXTS[lang]["choose_int"],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return INTERESTS


async def interest_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = ctx.user_data.get("lang", "fa")

    if query.data == "int_done":
        selected = ctx.user_data.get("selected", [])
        if not selected:
            await query.answer(TEXTS[lang]["no_interest"], show_alert=True)
            return INTERESTS

        # Save to Google Sheets
        user = update.effective_user
        interests = INTERESTS_FA if lang == "fa" else INTERESTS_EN
        interest_labels = [interests[k] for k in selected if k in interests]
        db.save_user(
            chat_id=str(user.id),
            name=user.full_name or "Unknown",
            lang=lang,
            interests=",".join(selected)
        )
        await query.edit_message_text(TEXTS[lang]["saved"])
        return ConversationHandler.END

    # Toggle interest
    key = query.data.replace("int_", "")
    selected = ctx.user_data.get("selected", [])
    if key in selected:
        selected.remove(key)
    else:
        selected.append(key)
    ctx.user_data["selected"] = selected

    # Rebuild keyboard with checkmarks
    interests = INTERESTS_FA if lang == "fa" else INTERESTS_EN
    keyboard = []
    for k, label in interests.items():
        tick = "✓ " if k in selected else ""
        keyboard.append([InlineKeyboardButton(tick + label, callback_data=f"int_{k}")])
    keyboard.append([InlineKeyboardButton(TEXTS[lang]["done_btn"], callback_data="int_done")])

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    return INTERESTS


# ── /news ────────────────────────────────────
async def news_now(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = db.get_user(user_id)
    lang = user.get("lang", "fa") if user else "fa"

    await update.message.reply_text(TEXTS[lang]["news_wait"])

    from collector  import collect_all
    from dedup      import deduplicate
    from summarizer import enrich_articles
    from sender     import build_personal_digest

    articles = collect_all()
    articles = deduplicate(articles)
    articles = enrich_articles(articles)

    interests = user.get("interests", "").split(",") if user else []
    msg = build_personal_digest(articles, interests, lang)

    if not msg:
        await update.message.reply_text(TEXTS[lang]["no_news"])
        return

    # Split long messages
    for chunk in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
        await update.message.reply_text(chunk, parse_mode="Markdown",
                                        disable_web_page_preview=True)


# ── /settings ────────────────────────────────
async def settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("ابتدا /start بزن تا تنظیمات را وارد کنی.")
        return
    lang = user.get("lang","fa")
    interests_raw = user.get("interests","").split(",")
    int_map = INTERESTS_FA if lang=="fa" else INTERESTS_EN
    labels = [int_map.get(i, i) for i in interests_raw if i]
    text = TEXTS[lang]["settings"].format(interests=", ".join(labels) or "—")
    await update.message.reply_text(text)


# ── /help ─────────────────────────────────────
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user = db.get_user(user_id)
    lang = user.get("lang","fa") if user else "fa"
    await update.message.reply_text(TEXTS[lang]["help"])


# ── main ──────────────────────────────────────
def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG:      [CallbackQueryHandler(lang_chosen,      pattern="^lang_")],
            INTERESTS: [CallbackQueryHandler(interest_chosen,  pattern="^int_")],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("news",     news_now))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("help",     help_cmd))

    logger.info("Bot started — polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
