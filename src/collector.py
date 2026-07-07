"""
collector.py — Fetch articles from RSS feeds and scraped pages.
Returns only articles published in the last 24 hours.
"""

import feedparser
import requests
import logging
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import Optional

from sources import RSS_SOURCES, SCRAPE_SOURCES, GOOGLE_NEWS_QUERIES, GOOGLE_NEWS_BASE

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DesignNewsBot/1.0; "
        "+https://github.com/YOUR_USERNAME/design-news-bot)"
    )
}
TIMEOUT = 15
LOOKBACK_HOURS = 24


@dataclass
class Article:
    title: str
    url: str
    source: str
    published: Optional[datetime] = None
    summary: str = ""
    keywords: list = field(default_factory=list)
    category: str = "Other"
    importance: str = "Medium"
    title_fa: str = ""


def _is_recent(dt: Optional[datetime]) -> bool:
    """Return True if the article was published within LOOKBACK_HOURS."""
    if dt is None:
        return True  # include if date unknown
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= cutoff


def _parse_date(entry) -> Optional[datetime]:
    """Try to extract a timezone-aware datetime from a feedparser entry."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


# ──────────────────────────────────────────────
# RSS / Atom
# ──────────────────────────────────────────────

def fetch_rss(source: dict) -> list[Article]:
    articles = []
    try:
        feed = feedparser.parse(source["url"])
        if feed.bozo and not feed.entries:
            logger.warning("Bozo feed: %s", source["name"])
            return []

        for entry in feed.entries:
            published = _parse_date(entry)
            if not _is_recent(published):
                continue

            summary = ""
            for attr in ("summary", "description", "content"):
                val = getattr(entry, attr, None)
                if isinstance(val, list):
                    val = val[0].get("value", "") if val else ""
                if val:
                    soup = BeautifulSoup(val, "html.parser")
                    summary = soup.get_text(" ", strip=True)[:600]
                    break

            articles.append(Article(
                title=entry.get("title", "").strip(),
                url=entry.get("link", "").strip(),
                source=source["name"],
                published=published,
                summary=summary,
            ))

        logger.info("RSS %s → %d recent articles", source["name"], len(articles))
    except Exception as e:
        logger.error("RSS error [%s]: %s", source["name"], e)
    return articles


# ──────────────────────────────────────────────
# Web scraping (fallback for non-RSS sites)
# ──────────────────────────────────────────────

def fetch_scraped(source: dict) -> list[Article]:
    articles = []
    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for container in soup.select(source["article_selector"])[:20]:
            title_el = container.select_one(source["title_selector"])
            link_el  = container.select_one(source["link_selector"])
            date_el  = container.select_one(source["date_selector"])

            if not title_el or not link_el:
                continue

            title = title_el.get_text(strip=True)
            href  = link_el.get("href", "")
            if not href.startswith("http"):
                href = urllib.parse.urljoin(source["url"], href)

            published = None
            if date_el:
                dt_str = date_el.get("datetime") or date_el.get_text(strip=True)
                try:
                    from dateutil import parser as dparser
                    published = dparser.parse(dt_str, fuzzy=True).replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            if not _is_recent(published):
                continue

            articles.append(Article(
                title=title,
                url=href,
                source=source["name"],
                published=published,
            ))

        logger.info("Scraped %s → %d recent articles", source["name"], len(articles))
    except Exception as e:
        logger.error("Scrape error [%s]: %s", source["name"], e)
    return articles


# ──────────────────────────────────────────────
# Google News RSS
# ──────────────────────────────────────────────

def fetch_google_news(query: str) -> list[Article]:
    url = GOOGLE_NEWS_BASE.format(query=urllib.parse.quote(query))
    source = {"name": f"Google News: {query}", "url": url}
    return fetch_rss(source)


# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────

def collect_all() -> list[Article]:
    all_articles: list[Article] = []

    # RSS feeds
    for src in RSS_SOURCES:
        if src.get("enabled", True):
            all_articles.extend(fetch_rss(src))
            time.sleep(0.5)  # be polite

    # Scraped sources
    for src in SCRAPE_SOURCES:
        if src.get("enabled", True):
            all_articles.extend(fetch_scraped(src))
            time.sleep(1)

    # Google News
    for query in GOOGLE_NEWS_QUERIES:
        all_articles.extend(fetch_google_news(query))
        time.sleep(0.5)

    logger.info("Total collected (before dedup): %d", len(all_articles))
    return all_articles
