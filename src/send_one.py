"""
send_one.py — Send news to ONE user immediately.
Cache first (instant); live pipeline only if the cache is missing/stale.
Admin-curated manual news is merged in.
"""
import os, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("send_one")

from cache  import load_cache
from manual import load_manual_articles
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
    return enrich_articles(deduplicate(raw), lang=lang) if raw else []


def main():
    chat_id   = os.environ["CHAT_ID"]
    lang      = os.environ.get("LANG_CODE", "fa")
    interests = [i for i in os.environ.get("INTERESTS", "").split(",") if i]
    token     = os.environ["TELEGRAM_BOT_TOKEN"]
    no_news = {"fa": "امروز خبری در حوزه‌های انتخابی تو پیدا نشد.",
               "en": "No news found for your selected areas today."}

    articles = list(get_articles(lang) or []) + load_manual_articles(lang)
    chunks = build_personal_digest_chunks(articles, interests, lang) if articles else []
    if not chunks:
        send_text(token, chat_id, no_news.get(lang, no_news["fa"]))
        return
    send_chunks(token, chat_id, chunks, lang)
    logger.info("Done sending (%d messages)", len(chunks))


if __name__ == "__main__":
    main()
