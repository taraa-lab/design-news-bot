"""
summarizer.py — Categorize, summarize, assign keywords and importance
using Claude API (or OpenRouter as fallback). Output in Persian (Farsi).
"""

import os
import json
import logging
import time
import anthropic
from collector import Article

logger = logging.getLogger(__name__)

BATCH_SIZE = 8

CATEGORIES = [
    "طراحی محصول", "طراحی صنعتی", "جوایز طراحی",
    "مسابقات طراحی", "کنفرانس‌ها و رویدادها", "آموزش طراحی",
    "پایداری و محیط زیست", "تکنولوژی", "مواد و متریال", "هوش مصنوعی در طراحی",
    "کسب و کار", "استارتاپ", "خودرو", "مبلمان",
    "لوازم الکترونیکی", "طراحی پزشکی", "بسته‌بندی",
    "تجربه کاربری", "سایر",
]

SYSTEM_PROMPT = f"""تو یک ویراستار متخصص در حوزه طراحی صنعتی هستی.
اخبار مجلات معتبر طراحی را دریافت می‌کنی و باید آن‌ها را به فارسی خلاصه و دسته‌بندی کنی.

برای هر خبر یک JSON با این فیلدها برگردان:
  - category: یکی از دسته‌بندی‌های زیر: {json.dumps(CATEGORIES, ensure_ascii=False)}
  - title_fa: عنوان خبر به فارسی روان
  - summary: خلاصه ۲ تا ۴ جمله به فارسی روان و حرفه‌ای
  - keywords: لیست ۳ تا ۶ کلیدواژه فارسی
  - importance: "بالا"، "متوسط" یا "پایین"

اهمیت بالا = جایزه مهم، محصول نوآورانه، رویداد بین‌المللی، تحول بزرگ در صنعت
اهمیت متوسط = معرفی محصول جالب، رویداد منطقه‌ای، پروژه قابل توجه
اهمیت پایین = خبر کوچک، مقاله نظری، اطلاعیه معمولی

فقط یک آرایه JSON برگردان — بدون توضیح اضافه، بدون markdown."""


def _build_user_message(batch):
    parts = []
    for i, a in enumerate(batch, 1):
        parts.append(
            f"{i}. TITLE: {a.title}\n"
            f"   SOURCE: {a.source}\n"
            f"   SNIPPET: {a.summary[:300] or '(no snippet)'}"
        )
    return "\n\n".join(parts)


def _call_api(user_msg):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _call_openrouter(user_msg)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = response.content[0].text.strip()
    return json.loads(raw)


def _call_openrouter(user_msg):
    import requests
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return []

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
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


def _fallback_categorize(article):
    title_lower = article.title.lower()
    cat_map = {
        "award": "جوایز طراحی",
        "competition": "مسابقات طراحی",
        "conference": "کنفرانس‌ها و رویدادها",
        "ai ": "هوش مصنوعی در طراحی",
        "sustainable": "پایداری و محیط زیست",
        "automotive": "خودرو",
        "furniture": "مبلمان",
        "packaging": "بسته‌بندی",
        "material": "مواد و متریال",
        "startup": "استارتاپ",
        "medical": "طراحی پزشکی",
    }
    for kw, cat in cat_map.items():
        if kw in title_lower:
            return {"category": cat, "title_fa": article.title, "summary": article.summary, "keywords": [], "importance": "متوسط"}
    return {"category": "سایر", "title_fa": article.title, "summary": article.summary, "keywords": [], "importance": "پایین"}


def enrich_articles(articles):
    enriched = []
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i: i + BATCH_SIZE]
        user_msg = _build_user_message(batch)
        results = []
        try:
            results = _call_api(user_msg)
        except Exception as e:
            logger.error("API call failed: %s - using fallback", e)

        for j, article in enumerate(batch):
            if j < len(results):
                r = results[j]
                article.category  = r.get("category", "سایر")
                article.title_fa  = r.get("title_fa", article.title)
                article.summary   = r.get("summary", article.summary)
                article.keywords  = r.get("keywords", [])
                article.importance = r.get("importance", "متوسط")
            else:
                fb = _fallback_categorize(article)
                article.category   = fb["category"]
                article.title_fa   = fb["title_fa"]
                article.importance = fb["importance"]
            enriched.append(article)

        logger.info("Enriched batch %d/%d", min(i + BATCH_SIZE, len(articles)), len(articles))
        time.sleep(1)

    return enriched
