"""
send_one.py — Collect, enrich, and send news to ONE user immediately.
Triggered by workflow_dispatch (from the Cloudflare Worker) with inputs:
  CHAT_ID, LANG, INTERESTS (comma-separated)
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("send_one")

from collector  import collect_all
from dedup      import deduplicate
from summarizer import enrich_articles
from sender     import build_personal_digest
import requests


def send_message(token, chat_id, text):
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk,
                      "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=30
            )
        except Exception as e:
            logger.error("Send error: %s", e)


def main():
    chat_id   = os.environ["CHAT_ID"]
    lang      = os.environ.get("LANG_CODE", "fa")
    interests = [i for i in os.environ.get("INTERESTS", "").split(",") if i]
    token     = os.environ["TELEGRAM_BOT_TOKEN"]

    no_news_msg = {
        "fa": "امروز خبری در حوزه‌های انتخابی تو پیدا نشد.",
        "en": "No news found for your selected areas today.",
    }

    logger.info("Sending personal news to %s (lang=%s, interests=%s)", chat_id, lang, interests)

    articles = collect_all()
    if not articles:
        send_message(token, chat_id, no_news_msg.get(lang, no_news_msg["fa"]))
        return

    articles = deduplicate(articles)
    articles = enrich_articles(articles, lang=lang)

    msg = build_personal_digest(articles, interests, lang)
    if not msg:
        send_message(token, chat_id, no_news_msg.get(lang, no_news_msg["fa"]))
        return

    send_message(token, chat_id, msg)
    logger.info("Done sending to %s", chat_id)


if __name__ == "__main__":
    main()
