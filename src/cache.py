"""
cache.py — Persist enriched articles to JSON files in the repo so on-demand
requests (bot /news, onboarding) can respond instantly without calling AI again.
"""
import os, json, logging
from datetime import datetime, timezone
from collector import Article

logger = logging.getLogger(__name__)

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "data")
MAX_AGE_HOURS = 20   # cache considered fresh if newer than this


def _cache_path(lang: str) -> str:
    return os.path.join(CACHE_DIR, f"cache_{lang}.json")


def save_cache(lang: str, articles: list[Article]):
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(articles),
        "articles": [a.to_dict() for a in articles],
    }
    with open(_cache_path(lang), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("Cache saved: %s (%d articles)", lang, len(articles))


def load_cache(lang: str):
    """Returns (articles, is_fresh) or (None, False) if cache missing/unreadable."""
    path = _cache_path(lang)
    if not os.path.exists(path):
        return None, False
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        generated_at = datetime.fromisoformat(payload["generated_at"])
        age_hours = (datetime.now(timezone.utc) - generated_at).total_seconds() / 3600
        articles = [Article.from_dict(d) for d in payload["articles"]]
        is_fresh = age_hours <= MAX_AGE_HOURS
        logger.info("Cache loaded: %s (%d articles, %.1fh old, fresh=%s)",
                    lang, len(articles), age_hours, is_fresh)
        return articles, is_fresh
    except Exception as e:
        logger.error("Cache load error [%s]: %s", lang, e)
        return None, False
