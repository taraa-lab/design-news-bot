"""
summarizer.py — Categorize, summarize, translate and rate news importance.

- Claude path (if ANTHROPIC_API_KEY is set): parallel batches.
- OpenRouter free path: model list is DISCOVERED at runtime (free model slugs
  rotate and 404 without warning), dead models are skipped, requests are
  sequential with a fixed delay, results are matched back by article id.
"""
import os, re, json, time, logging
import requests
import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed
from collector import Article

logger = logging.getLogger(__name__)

BATCH_SIZE = 12                    # Persian output is token-heavy; keep batches small
MAX_WORKERS_CLAUDE = 5
OPENROUTER_DELAY_SECONDS = 3
OPENROUTER_MAX_TOKENS = 5000
OPENROUTER_BUDGET_SECONDS = 600    # per enrich_articles() call; after that -> fallback
MAX_MODEL_CANDIDATES = 6

CATEGORIES_FA = [
    "طراحی محصول", "طراحی صنعتی", "جوایز طراحی", "مسابقات طراحی",
    "همایش‌ها و رویدادها", "آموزش طراحی", "پایداری و محیط زیست",
    "تکنولوژی", "مواد و متریال", "هوش مصنوعی در طراحی",
    "کسب‌وکار", "استارتاپ", "خودرو", "مبلمان",
    "لوازم الکترونیکی", "طراحی پزشکی", "بسته‌بندی", "UX و طراحی خدمات",
    "طراحی جواهرات", "طراحی اکسسوری", "سایر",
]

CATEGORIES_EN = [
    "Product Design", "Industrial Design", "Design Awards", "Design Competitions",
    "Conferences & Events", "Design Education", "Sustainability",
    "Technology", "Materials", "AI in Design", "Business", "Startups",
    "Automotive", "Furniture", "Consumer Electronics", "Medical Design",
    "Packaging", "UX / Service Design", "Jewelry Design", "Accessory Design", "Other",
]

SYSTEM_PROMPT_FA = f"""تو یک ویراستار متخصص حوزه طراحی صنعتی و طراحی محصول هستی.
ورودی: چند خبر انگلیسی که هر کدام شماره‌ی id دارد. برای هر خبر یک شیء JSON بساز با این فیلدها:
- id: همان شماره‌ی ورودی، بدون تغییر
- title_fa: عنوان خبر را خلاصه کن (حداکثر ۱۰ کلمه) و به فارسی روان و طبیعی ترجمه کن. نام برندها و محصولات را به لاتین نگه دار.
- summary: خلاصه‌ی حداکثر ۳ جمله‌ی کوتاه به فارسی روان (ترجمه‌ی تحت‌اللفظی نکن)
- keywords: ۳ تا ۵ کلیدواژه‌ی فارسی
- category: دقیقاً یکی از این موارد: {json.dumps(CATEGORIES_FA, ensure_ascii=False)}
- importance: یکی از «بالا»، «متوسط»، «پایین»

معیار اهمیت:
بالا = جایزه یا مسابقه‌ی بین‌المللی مهم، محصول واقعاً نوآورانه، تحول بزرگ در صنعت (معمولاً ۱ تا ۲ خبر از هر ۱۰ خبر)
متوسط = رونمایی قابل توجه، رویداد منطقه‌ای، پروژه‌ی جالب
پایین = خبر جزئی، یادداشت نظری، اطلاعیه‌ی معمول

خروجی فقط یک آرایه‌ی JSON باشد، بدون هیچ توضیح اضافه و بدون markdown."""

SYSTEM_PROMPT_EN = f"""You are an expert industrial design editor.
Input: several news items, each with an id number. For each item return one JSON object with:
- id: the input id, unchanged
- title: a concise, clear English headline (max 10 words)
- summary: a clear English summary of at most 3 short sentences
- keywords: 3-5 English keywords
- category: exactly one of {json.dumps(CATEGORIES_EN)}
- importance: "High", "Medium" or "Low"

High = major international award/competition, genuinely innovative product, big industry shift (usually 1-2 of every 10 items)
Medium = notable release, regional event, interesting project
Low = minor news, opinion piece, routine announcement

Return ONLY a JSON array. No extra text, no markdown."""

_IMPORTANCE_FA = {"بالا": "بالا", "high": "بالا", "متوسط": "متوسط", "medium": "متوسط",
                  "پایین": "پایین", "low": "پایین"}
_IMPORTANCE_EN = {"high": "High", "بالا": "High", "medium": "Medium", "متوسط": "Medium",
                  "low": "Low", "پایین": "Low"}


# ──────────────────────────────────────────────
# Prompt / parsing helpers
# ──────────────────────────────────────────────
def _build_user_message(batch):
    parts = []
    for i, a in enumerate(batch, 1):
        parts.append(f"id={i}\nTITLE: {a.title}\nSOURCE: {a.source}\n"
                     f"SNIPPET: {(a.summary or '(none)')[:300]}")
    return "\n\n".join(parts)


def _salvage_objects(raw):
    """Recover complete JSON objects from truncated / messy model output."""
    dec = json.JSONDecoder()
    out, i = [], raw.find("{")
    while i != -1 and i < len(raw):
        try:
            obj, end = dec.raw_decode(raw, i)
            if isinstance(obj, dict):
                out.append(obj)
            i = raw.find("{", end)
        except json.JSONDecodeError:
            i = raw.find("{", i + 1)
    return out


def _parse_results(raw):
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except json.JSONDecodeError:
            pass
    return _salvage_objects(raw)


def _norm_importance(val, lang):
    table = _IMPORTANCE_FA if lang == "fa" else _IMPORTANCE_EN
    return table.get(str(val or "").strip().lower(), "متوسط" if lang == "fa" else "Medium")


def _norm_category(val, lang):
    cats = CATEGORIES_FA if lang == "fa" else CATEGORIES_EN
    other = "سایر" if lang == "fa" else "Other"
    v = str(val or "").strip()
    if v in cats:
        return v
    for c in cats:
        if v and (c in v or v in c):
            return c
    return other


def _fallback(article, lang):
    t = article.title.lower()
    cat_map_fa = {"award": "جوایز طراحی", "competition": "مسابقات طراحی", "ai ": "هوش مصنوعی در طراحی",
                  "automotive": "خودرو", "furniture": "مبلمان", "packaging": "بسته‌بندی",
                  "medical": "طراحی پزشکی"}
    cat_map_en = {"award": "Design Awards", "competition": "Design Competitions", "ai ": "AI in Design",
                  "automotive": "Automotive", "furniture": "Furniture", "packaging": "Packaging",
                  "medical": "Medical Design"}
    cat_map = cat_map_fa if lang == "fa" else cat_map_en
    for kw, cat in cat_map.items():
        if kw in t:
            return {"title_fa": article.title, "category": cat, "summary": article.summary,
                    "keywords": [], "importance": "متوسط" if lang == "fa" else "Medium"}
    return {"title_fa": article.title, "category": "سایر" if lang == "fa" else "Other",
            "summary": article.summary, "keywords": [],
            "importance": "پایین" if lang == "fa" else "Low"}


def _apply_results(batch, results, lang):
    """Match AI results to articles by id (never by position unless ids are absent)."""
    by_id = {}
    for r in results:
        try:
            by_id[int(r.get("id"))] = r
        except (TypeError, ValueError):
            pass
    positional_ok = (not by_id) and len(results) == len(batch)

    enriched, matched = [], 0
    for idx, article in enumerate(batch, 1):
        r = by_id.get(idx)
        if r is None and positional_ok:
            r = results[idx - 1]
        if r is None:
            r = _fallback(article, lang)
        else:
            matched += 1
        article.title = str(r.get("title_fa") or r.get("title") or article.title).strip()
        article.summary = str(r.get("summary") or article.summary or "").strip()
        article.keywords = r.get("keywords") or []
        article.category = _norm_category(r.get("category"), lang)
        article.importance = _norm_importance(r.get("importance"), lang)
        enriched.append(article)
    return enriched, matched


# ──────────────────────────────────────────────
# Claude
# ──────────────────────────────────────────────
def _call_claude(user_msg, lang):
    system = SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    response = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=6000, system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return _parse_results(response.content[0].text)


def _process_batch_claude(batch, lang):
    results = []
    try:
        results = _call_claude(_build_user_message(batch), lang)
    except Exception as e:
        logger.error("Claude batch error: %s", e)
    return _apply_results(batch, results, lang)[0]


def _enrich_claude(articles, lang):
    batches = [articles[i:i + BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
    done = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_CLAUDE) as ex:
        futures = {ex.submit(_process_batch_claude, b, lang): i for i, b in enumerate(batches)}
        for f in as_completed(futures):
            i = futures[f]
            try:
                done[i] = f.result()
            except Exception as e:
                logger.error("Batch %d failed: %s", i, e)
                done[i] = batches[i]
    out = []
    for i in range(len(batches)):
        out.extend(done.get(i, batches[i]))
    return out


# ──────────────────────────────────────────────
# OpenRouter (free tier) — self-healing model selection
# ──────────────────────────────────────────────
_PREFERRED = (
    "meta-llama/llama-3.3-70b-instruct", "google/gemma-4-31b-it",
    "qwen/qwen3-next-80b-a3b-instruct", "openai/gpt-oss-120b", "openai/gpt-oss-20b",
    "nousresearch/hermes-3-llama-3.1-405b", "google/gemma-4-26b-a4b-it",
    "nvidia/nemotron-3-super-120b-a12b",
)
_EXCLUDE_WORDS = ("lyria", "safety", "guard", "code", "coder", "-vl", "embed", "image",
                  "audio", "tts", "whisper", "omni", "vision", "moderation")

_state = {"models": None, "dead": set(), "last_good": None}


class _ModelGone(Exception):
    pass


class _RateLimited(Exception):
    pass


def _discover_free_models():
    ids = []
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=20)
        r.raise_for_status()
        for m in r.json().get("data", []):
            mid = m.get("id", "")
            pr = m.get("pricing") or {}
            if not mid.endswith(":free"):
                continue
            if str(pr.get("prompt", "0")) not in ("0", "0.0", "0.00"):
                continue
            if str(pr.get("completion", "0")) not in ("0", "0.0", "0.00"):
                continue
            if any(w in mid.lower() for w in _EXCLUDE_WORDS):
                continue
            ids.append(mid)
    except Exception as e:
        logger.warning("Could not list OpenRouter models: %s", e)

    if ids:
        ordered = [p + ":free" for p in _PREFERRED if p + ":free" in ids]
        ordered += [m for m in ids if m not in ordered]
        ordered = ordered[:MAX_MODEL_CANDIDATES]
    else:
        ordered = [p + ":free" for p in _PREFERRED[:4]]
    ordered.append("openrouter/free")
    logger.info("OpenRouter candidate models: %s", ordered)
    return ordered


def _candidate_models():
    if _state["models"] is None:
        _state["models"] = _discover_free_models()
    models = [m for m in _state["models"] if m not in _state["dead"]]
    good = _state["last_good"]
    if good in models:
        models.remove(good)
        models.insert(0, good)
    return models


def _call_openrouter_model(model, user_msg, lang):
    system = SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
                 "Content-Type": "application/json"},
        json={"model": model, "max_tokens": OPENROUTER_MAX_TOKENS,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user_msg}]},
        timeout=90)
    if resp.status_code == 429:
        raise _RateLimited()
    if resp.status_code in (400, 401, 402, 403, 404):
        raise _ModelGone(f"{resp.status_code}: {resp.text[:160]}")
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"].get("content") or ""
    results = _parse_results(content)
    if not results:
        raise ValueError("no parsable JSON in model output")
    return results


def _openrouter_batch(user_msg, lang):
    """Try candidate models in order until one returns usable results."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        return []
    for model in _candidate_models():
        for attempt in range(2):
            try:
                results = _call_openrouter_model(model, user_msg, lang)
                _state["last_good"] = model
                logger.info("OpenRouter OK via %s (%d items)", model, len(results))
                return results
            except _ModelGone as e:
                logger.warning("Model %s unavailable, skipping (%s)", model, e)
                _state["dead"].add(model)
                break
            except _RateLimited:
                wait = 8 * (attempt + 1)
                logger.warning("Model %s rate-limited, waiting %ds", model, wait)
                time.sleep(wait)
            except Exception as e:
                logger.warning("Model %s failed: %s", model, e)
                break
    logger.error("All OpenRouter models failed for this batch")
    return []


def _call_api(user_msg, lang):
    """Compatibility shim (used by debug scripts)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _call_claude(user_msg, lang)
    return _openrouter_batch(user_msg, lang)


def _enrich_openrouter_sequential(articles, lang):
    batches = [articles[i:i + BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
    started = time.time()
    out = []
    for i, batch in enumerate(batches):
        results = []
        if time.time() - started < OPENROUTER_BUDGET_SECONDS:
            results = _openrouter_batch(_build_user_message(batch), lang)
        else:
            logger.warning("Time budget exhausted — using fallback for batch %d", i)
        enriched, matched = _apply_results(batch, results, lang)
        logger.info("Batch %d/%d: %d/%d articles enriched by AI", i + 1, len(batches),
                    matched, len(batch))
        out.extend(enriched)
        if i < len(batches) - 1:
            time.sleep(OPENROUTER_DELAY_SECONDS)
    return out


def enrich_articles(articles, lang="fa"):
    if not articles:
        return []
    if os.environ.get("ANTHROPIC_API_KEY"):
        enriched, provider = _enrich_claude(articles, lang), "Claude"
    else:
        enriched, provider = _enrich_openrouter_sequential(articles, lang), "OpenRouter"

    other = ("سایر", "Other")
    imp = {}
    for a in enriched:
        imp[a.importance] = imp.get(a.importance, 0) + 1
    logger.info("Enriched %d articles via %s. Non-Other: %d/%d. Importance: %s",
                len(enriched), provider,
                sum(1 for a in enriched if a.category not in other), len(enriched), imp)
    return enriched
