"""
summarizer.py — Categorize, summarize, assign keywords and importance
using Claude API (or OpenRouter as fallback).

Batch mode: sends up to BATCH_SIZE articles per API call to save tokens.
"""

import os
import json
import logging
import time
import anthropic
from collector import Article

logger = logging.getLogger(__name__)

BATCH_SIZE = 8   # articles per API call (balance cost vs latency)

CATEGORIES = [
    "Product Design", "Industrial Design", "Design Awards",
    "Design Competitions", "Conferences & Events", "Design Education",
    "Sustainability", "Technology", "Materials", "AI in Design",
    "Business", "Startups", "Automotive", "Furniture",
    "Consumer Electronics", "Medical Design", "Packaging",
    "UX / Service Design", "Other",
]

SYSTEM_PROMPT = f"""You are an expert industrial design editor.
You receive batches of news article titles and snippets.
For EACH article return a JSON object with:
  - category: one of {json.dumps(CATEGORIES)}
  - summary: 2-4 clear sentences in English describing the article
  - keywords: list of 3-6 relevant keywords
  - importance: "High", "Medium", or "Low"

High = major award, breakthrough product, global competition, significant industry shift.
Medium = notable release, regional event, interesting project.
Low = minor news, opinion piece, routine announcement.

Return a JSON array — one object per article, in the same order received.
No markdown, no extra text, just the JSON array."""


def _build_user_message(batch: list[Article]) -> str:
    parts = []
    for i, a in enumerate(batch, 1):
        parts.append(
            f"{i}. TITLE: {a.title}\n"
            f"   SOURCE: {a.source}\n"
            f"   SNIPPET: {a.summary[:300] or '(no snippet)'}"
        )
    return "\n\n".join(parts)


def _call_api(user_msg: str) -> list[dict]:
    """Call Claude API and return parsed JSON list."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key:
        # Fallback: OpenRouter (free tier with some models)
        return _call_openrouter(user_msg)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",    # cheapest Claude; swap to sonnet for quality
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = response.content[0].text.strip()
    return json.loads(raw)


def _call_openrouter(user_msg: str) -> list[dict]:
    """Fallback to OpenRouter free tier (e.g. mistral-7b-instruct)."""
    import requests
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("No API key set — using fallback categorizer")
        return []   # handled below

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/YOUR_USERNAME/design-news-bot",
            "Content-Type": "application/json",
        },
        json={
            "model": "mistralai/mistral-7b-instruct:free",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    return json.loads(raw)


def _fallback_categorize(article: Article) -> dict:
    """Simple keyword-based categorization used when no API key is available."""
    title_lower = article.title.lower()
    cat_map = {
        "award": "Design Awards",
        "competition": "Design Competitions",
        "conference": "Conferences & Events",
        "summit": "Conferences & Events",
        "ai ": "AI in Design",
        "artificial intelligence": "AI in Design",
        "sustainable": "Sustainability",
        "recycl": "Sustainability",
        "automotive": "Automotive",
        "car ": "Automotive",
        "furniture": "Furniture",
        "electric": "Consumer Electronics",
        "smartphone": "Consumer Electronics",
        "medical": "Medical Design",
        "packaging": "Packaging",
        "material": "Materials",
        "startup": "Startups",
        "ux": "UX / Service Design",
        "education": "Design Education",
    }
    for kw, cat in cat_map.items():
        if kw in title_lower:
            return {"category": cat, "summary": article.summary, "keywords": [], "importance": "Medium"}
    return {"category": "Other", "summary": article.summary, "keywords": [], "importance": "Low"}


def enrich_articles(articles: list[Article]) -> list[Article]:
    """Fill in category, summary, keywords, importance for each article."""
    enriched = []

    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i : i + BATCH_SIZE]
        user_msg = _build_user_message(batch)

        results = []
        try:
            results = _call_api(user_msg)
        except Exception as e:
            logger.error("API call failed: %s — using fallback", e)

        for j, article in enumerate(batch):
            if j < len(results):
                r = results[j]
                article.category   = r.get("category", "Other")
                article.summary    = r.get("summary", article.summary)
                article.keywords   = r.get("keywords", [])
                article.importance = r.get("importance", "Medium")
            else:
                fb = _fallback_categorize(article)
                article.category   = fb["category"]
                article.importance = fb["importance"]
            enriched.append(article)

        logger.info("Enriched batch %d/%d", min(i + BATCH_SIZE, len(articles)), len(articles))
        time.sleep(1)   # rate-limit buffer

    return enriched
