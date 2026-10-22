"""
send_one.py — Send news to ONE user immediately.
Reads from cache (instant) if fresh; falls back to the live pipeline if the cache
is missing or stale.
"""
import os, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("send_one")

from cache  import load_cache
from sender import build_personal_digest_chunks, send_chunks, send_text


def get_articles(lang):
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
    return enrich_articles(deduplicate(raw), lang=lang)


def main():
    chat_id   = os.environ["CHAT_ID"]
    lang      = os.environ.get("LANG_CODE", "fa")
    interests = [i for i in os.environ.get("INTERESTS", "").split(",") if i]
    token     = os.environ["TELEGRAM_BOT_TOKEN"]

    no_news = {"fa": "امروز خبری در حوزه‌های انتخابی تو پیدا نشد.",
               "en": "No news found for your selected areas today."}

    logger.info("Sending personal news to %s (lang=%s, interests=%s)", chat_id, lang, interests)

    articles = get_articles(lang)
    chunks = build_personal_digest_chunks(articles, interests, lang) if articles else []
    if not chunks:
        send_text(token, chat_id, no_news.get(lang, no_news["fa"]))
        return

    send_chunks(token, chat_id, chunks)
    logger.info("Done sending to %s (%d messages)", chat_id, len(chunks))


if __name__ == "__main__":
    main()
