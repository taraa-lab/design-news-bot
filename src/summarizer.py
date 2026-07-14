"""
summarizer.py — Categorize, summarize, translate, assign importance.
- Claude path: parallel batches (generous rate limits).
- OpenRouter free path: SEQUENTIAL with a fixed delay between calls, larger
  batches (fewer total requests) to stay safely under free-tier rate limits.
"""
import os, json, time, logging, anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed
from collector import Article

logger = logging.getLogger(__name__)

BATCH_SIZE = 30                 # fewer, larger batches = fewer API calls
MAX_WORKERS_CLAUDE = 5
OPENROUTER_MODEL = "openai/gpt-oss-20b:free"
OPENROUTER_DELAY_SECONDS = 4    # fixed spacing between sequential OpenRouter calls

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

فقط JSON آرایه برگردان با این فیلدها برای هر خبر، بدون هیچ توضیح یا متن اضافه، بدون markdown fence:
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

Return only a JSON array, no extra text, no markdown fence."""


def _build_user_message(batch):
    parts = []
    for i, a in enumerate(batch, 1):
        parts.append(f"{i}. TITLE: {a.title}\n   SOURCE: {a.source}\n   SNIPPET: {a.summary[:300] or '(none)'}")
    return "\n\n".join(parts)


def _extract_json_array(raw: str):
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end+1]
    return json.loads(raw)


def _call_claude(user_msg, lang):
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    system  = SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=6000,
        system=system,
        messages=[{"role":"user","content":user_msg}],
    )
    return _extract_json_array(response.content[0].text)


def _call_openrouter_once(user_msg, lang):
    import requests as req
    api_key = os.environ.get("OPENROUTER_API_KEY","")
    if not api_key:
        return []
    system = SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN
    resp = req.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": OPENROUTER_MODEL,
              "messages":[{"role":"system","content":system},{"role":"user","content":user_msg}],
              "max_tokens": 6000},
        timeout=60)
    if resp.status_code == 429:
        raise RuntimeError("rate_limited")
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    return _extract_json_array(raw)


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


def _apply_results(batch, results, lang):
    enriched = []
    for j, article in enumerate(batch):
        r = results[j] if j < len(results) else _fallback(article, lang)
        article.title      = r.get("title_fa", article.title)
        article.category   = r.get("category", "سایر" if lang=="fa" else "Other")
        article.summary    = r.get("summary",  article.summary)
        article.keywords   = r.get("keywords", [])
        article.importance = r.get("importance","متوسط" if lang=="fa" else "Medium")
        enriched.append(article)
    return enriched


def _process_batch_claude(batch, lang):
    results = []
    try:
        results = _call_claude(_build_user_message(batch), lang)
    except Exception as e:
        logger.error("Claude batch error: %s", e)
    return _apply_results(batch, results, lang)


def _enrich_claude(articles, lang):
    batches = [articles[i:i+BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
    results_by_idx = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_CLAUDE) as executor:
        futures = {executor.submit(_process_batch_claude, b, lang): i for i, b in enumerate(batches)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results_by_idx[idx] = future.result()
            except Exception as e:
                logger.error("Batch %d failed: %s", idx, e)
                results_by_idx[idx] = batches[idx]
    out = []
    for i in range(len(batches)):
        out.extend(results_by_idx.get(i, batches[i]))
    return out


def _enrich_openrouter_sequential(articles, lang):
    """One request at a time, fixed delay between each — avoids free-tier rate limits."""
    batches = [articles[i:i+BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
    out = []
    for i, batch in enumerate(batches):
        results = []
        max_retries = 3
        delay = OPENROUTER_DELAY_SECONDS
        for attempt in range(max_retries):
            try:
                results = _call_openrouter_once(_build_user_message(batch), lang)
                break
            except Exception as e:
                logger.warning("OpenRouter batch %d attempt %d failed: %s", i, attempt+1, e)
                time.sleep(delay)
                delay *= 2
        out.extend(_apply_results(batch, results, lang))

        if i < len(batches) - 1:
            time.sleep(OPENROUTER_DELAY_SECONDS)   # fixed spacing before next request

    return out


def enrich_articles(articles, lang="fa"):
    if not articles:
        return []

    using_claude = bool(os.environ.get("ANTHROPIC_API_KEY",""))
    if using_claude:
        enriched = _enrich_claude(articles, lang)
        provider = "Claude"
    else:
        enriched = _enrich_openrouter_sequential(articles, lang)
        provider = "OpenRouter (sequential)"

    ai_success = sum(1 for a in enriched if a.category not in ("سایر","Other"))
    logger.info("Enriched %d articles via %s. Non-Other categories: %d/%d",
                len(enriched), provider, ai_success, len(enriched))
    return enriched
