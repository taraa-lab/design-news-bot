"""
summarizer.py — Categorize, summarize, translate, assign importance.
Supports fa (Persian) and en (English) output.
"""
import os, json, logging, time, anthropic
from collector import Article

logger = logging.getLogger(__name__)
BATCH_SIZE = 8
OUTPUT_LANG = os.environ.get("OUTPUT_LANG", "fa")  # fa or en

CATEGORIES_FA = [
    "طراحی محصول","طراحی صنعتی","جوایز طراحی","مسابقات طراحی",
    "همایش‌ها و رویدادها","آموزش طراحی","پایداری و محیط زیست",
    "تکنولوژی","مواد و متریال","هوش مصنوعی در طراحی",
    "کسب‌وکار","استارتاپ","خودرو","مبلمان",
    "لوازم الکترونیکی","طراحی پزشکی","بسته‌بندی","UX و طراحی خدمات","سایر"
]

CATEGORIES_EN = [
    "Product Design","Industrial Design","Design Awards","Design Competitions",
    "Conferences & Events","Design Education","Sustainability",
    "Technology","Materials","AI in Design","Business","Startups",
    "Automotive","Furniture","Consumer Electronics","Medical Design",
    "Packaging","UX / Service Design","Other"
]

SYSTEM_PROMPT_FA = f"""تو یک ویراستار متخصص در حوزه طراحی صنعتی هستی.
اخبار زیر به انگلیسی هستند. برای هر خبر:
1. عنوان را به فارسی روان ترجمه کن
2. یک خلاصه 3 جمله‌ای کامل به فارسی بنویس (نه ترجمه تحت‌اللفظی — روان و حرفه‌ای)
3. کلیدواژه‌های فارسی بده
4. دسته‌بندی و اهمیت تعیین کن

دسته‌بندی‌ها: {json.dumps(CATEGORIES_FA, ensure_ascii=False)}

اهمیت بالا: جایزه بین‌المللی، محصول نوآورانه، تحول بزرگ در صنعت
اهمیت متوسط: رونمایی قابل توجه، رویداد منطقه‌ای، پروژه جالب
اهمیت پایین: خبر جزئی، مقاله نظری، اطلاع‌رسانی معمول

فقط JSON آرایه برگردان با این فیلدها برای هر خبر:
{{"title_fa": "عنوان فارسی", "summary": "خلاصه فارسی", "keywords": ["کلیدواژه"], "category": "دسته", "importance": "بالا|متوسط|پایین"}}"""

SYSTEM_PROMPT_EN = f"""You are an expert industrial design editor.
For each article provide a JSON object with:
- title_fa: keep the original English title (no translation needed)
- summary: 3-sentence clear English summary
- keywords: 3-6 relevant English keywords
- category: one of {json.dumps(CATEGORIES_EN)}
- importance: "High", "Medium", or "Low"

High: major international award, breakthrough product, industry shift
Medium: notable release, regional event, interesting project
Low: minor news, opinion piece, routine announcement

Return only a JSON array, no extra text."""

def _build_user_message(batch):
    parts = []
    for i, a in enumerate(batch, 1):
        parts.append(f"{i}. TITLE: {a.title}\n   SOURCE: {a.source}\n   SNIPPET: {a.summary[:300] or '(none)'}")
    return "\n\n".join(parts)

def _call_api(user_msg, lang):
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    system  = SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN
    if not api_key:
        return _call_openrouter(user_msg, system)
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=system,
        messages=[{"role":"user","content":user_msg}],
    )
    raw = response.content[0].text.strip()
    # strip possible markdown fences
    raw = raw.replace("```json","").replace("```","").strip()
    return json.loads(raw)

def _call_openrouter(user_msg, system):
    import requests as req
    api_key = os.environ.get("OPENROUTER_API_KEY","")
    if not api_key: return []
    resp = req.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
        json={"model":"mistralai/mistral-7b-instruct:free",
              "messages":[{"role":"system","content":system},{"role":"user","content":user_msg}]},
        timeout=60)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    raw = raw.replace("```json","").replace("```","").strip()
    return json.loads(raw)

def _fallback(article, lang):
    title_lower = article.title.lower()
    cat_map_fa = {"award":"جوایز طراحی","competition":"مسابقات طراحی","ai ":"هوش مصنوعی در طراحی",
                  "automotive":"خودرو","furniture":"مبلمان","packaging":"بسته‌بندی","medical":"طراحی پزشکی"}
    cat_map_en = {"award":"Design Awards","competition":"Design Competitions","ai ":"AI in Design",
                  "automotive":"Automotive","furniture":"Furniture","packaging":"Packaging","medical":"Medical Design"}
    cat_map = cat_map_fa if lang == "fa" else cat_map_en
    for kw, cat in cat_map.items():
        if kw in title_lower:
            return {"title_fa": article.title, "category": cat, "summary": article.summary, "keywords": [], "importance": "متوسط" if lang=="fa" else "Medium"}
    return {"title_fa": article.title, "category": "سایر" if lang=="fa" else "Other", "summary": article.summary, "keywords": [], "importance": "پایین" if lang=="fa" else "Low"}

def enrich_articles(articles, lang=None):
    if lang is None:
        lang = OUTPUT_LANG
    enriched = []
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i:i+BATCH_SIZE]
        results = []
        try:
            results = _call_api(_build_user_message(batch), lang)
        except Exception as e:
            logger.error("API error: %s", e)
        for j, article in enumerate(batch):
            r = results[j] if j < len(results) else _fallback(article, lang)
            article.title      = r.get("title_fa", article.title)
            article.category   = r.get("category", "سایر" if lang=="fa" else "Other")
            article.summary    = r.get("summary",  article.summary)
            article.keywords   = r.get("keywords", [])
            article.importance = r.get("importance","متوسط" if lang=="fa" else "Medium")
            enriched.append(article)
        logger.info("Enriched batch %d/%d", min(i+BATCH_SIZE, len(articles)), len(articles))
        time.sleep(1)
    return enriched
