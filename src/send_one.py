"""
send_one.py — Send news to ONE user immediately.
Reads from cache (instant) if fresh; falls back to live pipeline if cache is
missing or stale (e.g. first-ever run before any daily cycle has completed).
"""
import os, logging, requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("send_one")

from cache  import load_cache
from sender import build_personal_digest


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


def get_articles(lang):
    """Try cache first (instant). Fall back to a full live pipeline run if needed."""
    articles, is_fresh = load_cache(lang)
    if articles and is_fresh:
        logger.info("Using fresh cache (%d articles)", len(articles))
        return articles

    logger.info("Cache missing/stale — running live pipeline (slower)...")
    from collector  import collect_all
    from dedup      import deduplicate
    from summarizer import enrich_articles

    raw = collect_all()
    if not raw:
        return []
    raw = deduplicate(raw)
    return enrich_articles(raw, lang=lang)


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

    articles = get_articles(lang)
    if not articles:
        send_message(token, chat_id, no_news_msg.get(lang, no_news_msg["fa"]))
        return

    msg = build_personal_digest(articles, interests, lang)
    if not msg:
        send_message(token, chat_id, no_news_msg.get(lang, no_news_msg["fa"]))
        return

    send_message(token, chat_id, msg)
    logger.info("Done sending to %s", chat_id)


if __name__ == "__main__":
    main()
