"""
dedup.py — Remove duplicate articles using URL normalization
and title fuzzy-similarity (no external ML libraries needed).
"""

import re
import urllib.parse
import logging
from collector import Article

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.72   # Jaccard similarity above this = duplicate


def _normalize_url(url: str) -> str:
    """Strip tracking params, trailing slashes, and normalize scheme."""
    try:
        p = urllib.parse.urlparse(url)
        # remove common UTM / tracking query params
        qs = urllib.parse.parse_qs(p.query)
        for key in list(qs):
            if key.lower().startswith(("utm_", "ref", "source", "fbclid", "gclid")):
                del qs[key]
        clean = p._replace(
            scheme="https",
            query=urllib.parse.urlencode(qs, doseq=True),
            fragment="",
            path=p.path.rstrip("/"),
        )
        return urllib.parse.urlunparse(clean).lower()
    except Exception:
        return url.lower().strip()


def _tokenize(text: str) -> set:
    """Lowercase word-token set, ignoring stopwords."""
    stopwords = {
        "a", "an", "the", "in", "of", "to", "and", "or", "for",
        "is", "at", "on", "by", "with", "new", "its", "that",
        "this", "from", "design", "designer",   # too frequent to be signal
    }
    tokens = set(re.findall(r"[a-z]+", text.lower()))
    return tokens - stopwords


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union


def deduplicate(articles: list[Article]) -> list[Article]:
    """
    Returns a deduplicated list.
    Preference: keep the article with the longer summary (more info).
    """
    seen_urls: dict[str, Article] = {}
    unique: list[Article] = []
    token_cache: dict[int, set] = {}

    def tokens(a: Article) -> set:
        key = id(a)
        if key not in token_cache:
            token_cache[key] = _tokenize(a.title)
        return token_cache[key]

    for article in articles:
        norm_url = _normalize_url(article.url)

        # ── Exact URL match ──
        if norm_url in seen_urls:
            existing = seen_urls[norm_url]
            if len(article.summary) > len(existing.summary):
                seen_urls[norm_url] = article
                idx = next(i for i, a in enumerate(unique) if a is existing)
                unique[idx] = article
            continue

        # ── Title similarity against already-kept articles ──
        is_dup = False
        for kept in unique:
            sim = _jaccard(tokens(article), tokens(kept))
            if sim >= SIMILARITY_THRESHOLD:
                is_dup = True
                # keep the one with more summary text
                if len(article.summary) > len(kept.summary):
                    idx = unique.index(kept)
                    unique[idx] = article
                    seen_urls[_normalize_url(kept.url)] = article
                break

        if not is_dup:
            seen_urls[norm_url] = article
            unique.append(article)

    removed = len(articles) - len(unique)
    logger.info("Dedup: removed %d duplicates, kept %d", removed, len(unique))
    return unique
