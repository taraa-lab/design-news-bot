"""
summarizer.py — Categorize, summarize, assign keywords and importance.
Translates ALL content to the requested language (fa/en).
"""

import os, json, logging, time, anthropic
from collector import Article

logger = logging.getLogger(__name__)
BATCH_SIZE = 7

CATEGORIES_FA = [
    "طراحی محصول","طراحی صنعتی","جوایز طراحی","مسابقات طراحی",
    "همایش‌ها و رویدادها","آموزش طراحی","پایداری و محیط زیست",
    "تکنولوژی","مواد و متریال","هوش مصنوعی در طراحی",
    "کسب‌وکار","استارتاپ","خودرو","مبلمان",
    "لوازم الکترونیکی","طراحی پزشکی","بسته‌بندی","UX و طراحی خدمات","سایر"
]

CATEGORIES_EN = [
    "Product Design","Industrial Design","Design Awards","Design Competitions",
    "Conferences & Events","Design Education","Sustainability","Technology",
    "Materials","AI in Design","Business","Startups","Automotive","Furniture",
    "Consumer Electronics","Medical Design","Packaging","UX / Service Design","Other"
]

SYSTEM_FA = """تو یک ویراستار متخصص در حوزه طراحی صنعتی هستی.
اخبار را به فارسی روان و حرفه‌ای ترجمه و خلاصه کن — حتی اگر متن اصلی انگلیسی باشد.
برای هر خبر یک JSON با این فیلدها برگردان:
  - category: یکی از: """ + json.dumps(CATEGORIES_FA, ensure_ascii=False) + """
  - summary: خلاصه ۳ جمله کامل به فارسی روان
  - keywords: لیست ۴ کلیدواژه فارسی
  - importance: "بالا"، "متوسط" یا "پایین"

اهمیت بالا: جایزه بین‌المللی، محصول نوآورانه، تحول بزرگ در صنعت، رویداد جهانی
اهمیت متوسط: رونمایی قابل توجه، رویداد منطقه‌ای، پروژه جالب
اهمیت پایین: خبر جزئی، مقاله نظری، اطلاع‌رسانی معمول

فقط JSON آرایه برگردان. هیچ توضیح اضافه‌ای ندهد."""

SYSTEM_EN = """You are an expert industrial design editor.
For each article return a JSON object with:
  - category: one of """ + json.dumps(CATEGORIES_EN) + """
  - summary: 3 clear sentences in English
  - keywords: list of 4 relevant keywords
  - importance: "High", "Medium", or "Low"

High = major award, breakthrough product, global event, significant industry shift
Medium = notable release, regional event, interesting project
Low = minor news, opinion piece, routine announcement

Return only a JSON array. No extra text."""

def _build_msg(batch):
    parts = []
    for i, a in enumerate(batch, 1):
        parts.append(f"{i}. TITLE: {a.title}\n   SOURCE: {a.source}\n   SNIPPET: {a.summary[:300] or '(none)'}")
    return "\n\n".join(parts)

def _call(user_msg, lang="fa"):
    system = SYSTEM_FA if lang == "fa" else SYSTEM_EN
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if api_key:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=system,
            messages=[{"role":"user","content":user_msg}],
        )
        raw = resp.content[0].text.strip()
    else:
        import requests as req
        or_key = os.environ.get("OPENROUTER_API_KEY","")
        if not or_key: return []
        r = req.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization":f"Bearer {or_key}","Content-Type":"application/json"},
            json={"model":"mistralai/mistral-7b-instruct:free",
                  "messages":[{"role":"system","content":system},{"role":"user","content":user_msg}]},
            timeout=60)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
    raw = raw.replace("```json","").replace("```","").strip()
    return json.loads(raw)

def _fallback(article, lang):
    return {"category":"سایر" if lang=="fa" else "Other",
            "summary": article.summary, "keywords":[], "importance":"متوسط" if lang=="fa" else "Medium"}

def enrich_articles(articles, lang="fa"):
    enriched = []
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i:i+BATCH_SIZE]
        results = []
        try:
            results = _call(_build_msg(batch), lang)
        except Exception as e:
            logger.error("API error: %s", e)
        for j, article in enumerate(batch):
            if j < len(results):
                r = results[j]
                article.category   = r.get("category","سایر" if lang=="fa" else "Other")
                article.summary    = r.get("summary", article.summary)
                article.keywords   = r.get("keywords",[])
                article.importance = r.get("importance","متوسط" if lang=="fa" else "Medium")
            else:
                fb = _fallback(article, lang)
                article.category   = fb["category"]
                article.importance = fb["importance"]
            enriched.append(article)
        logger.info("Enriched batch %d/%d", min(i+BATCH_SIZE, len(articles)), len(articles))
        time.sleep(1)
    return enriched
