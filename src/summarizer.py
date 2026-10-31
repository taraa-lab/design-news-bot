"""
summarizer.py (v3) — categorize, summarize, translate and rate news.

Providers (first available wins):
  1. Claude    (ANTHROPIC_API_KEY)  — parallel
  2. Gemini    (GEMINI_API_KEY)     — sequential, free tier, strong Persian
  3. OpenRouter free models         — sequential, vetted models only, auto-discovered

Quality rules: proper nouns stay in Latin script; Persian output is validated
(language ratio + non-empty) and failed items are retried on a different model.
Results are matched to articles by id, never by position.
"""
import os, re, json, time, logging
import requests
import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed
from collector import Article
from categories import CATEGORIES_FA, CATEGORIES_EN

logger = logging.getLogger(__name__)

BATCH_SIZE_OPENROUTER = 8
BATCH_SIZE_GEMINI = 10
BATCH_SIZE_CLAUDE = 12
BATCH_SIZE = BATCH_SIZE_OPENROUTER            # kept for debug scripts
MAX_WORKERS_CLAUDE = 5
DELAY_OPENROUTER = 3
DELAY_GEMINI = 5
MAX_TOKENS = 5000
BUDGET_SECONDS = 900                          # per enrich_articles() call
MAX_MODEL_CANDIDATES = 5

_EXAMPLE_FA = ('[{"id": 1, "title_fa": "Studio Aria یک صندلی چوبی تاشوی جدید معرفی کرد", '
               '"summary": "این صندلی با چوب بازیافتی ساخته شده و بدون ابزار جمع می‌شود. '
               'طراحان آن را برای آپارتمان‌های کوچک ساخته‌اند. فروش از بهار آینده شروع می‌شود.", '
               '"keywords": ["صندلی تاشو", "چوب بازیافتی", "فضای کوچک"], '
               '"category": "مبلمان", "importance": "متوسط"}]')

SYSTEM_PROMPT_FA = (
    "تو سردبیر یک کانال خبری تخصصی «طراحی و طراحی صنعتی» هستی و برای مخاطب فارسی‌زبان می‌نویسی.\n"
    "ورودی چند خبر انگلیسی است که هر کدام شماره‌ی id دارد. برای هر خبر یک شیء JSON بساز.\n\n"
    "قوانین ترجمه و نگارش (بسیار مهم):\n"
    "1. نام‌های خاص را هرگز فارسی‌نویسی یا آوانگاری نکن؛ دقیقاً به همان شکل لاتین بنویس: برند، شرکت، استودیو، "
    "نام طراح و افراد، نام محصول و مدل، نام جایزه و مسابقه، نمایشگاه و رسانه. "
    "درست: «Dyson»، «Red Dot»، «Milan Design Week». غلط: «دایسون»، «رد دات».\n"
    "2. بقیه‌ی متن را به فارسی روان، طبیعی و خبری بنویس؛ ترجمه‌ی کلمه‌به‌کلمه نکن و ساختار جمله را فارسی کن. "
    "جمله‌ها کوتاه و روشن باشند.\n"
    "3. اصطلاح‌های عمومی را فارسی بنویس (مثلاً صندلی، نمونه‌ی اولیه، طراحی صنعتی). "
    "واژه‌ی انگلیسی را فقط برای نام‌های خاص نگه دار.\n"
    "4. عدد، تاریخ و مبلغ را دقیق منتقل کن و چیزی که در خبر نیست اضافه نکن.\n\n"
    "فیلدهای هر شیء:\n"
    "- id: همان شماره‌ی ورودی\n"
    "- title_fa: عنوان خبری کوتاه و کامل، حداکثر ۱۰ کلمه\n"
    "- summary: خلاصه در حداکثر ۳ جمله‌ی کوتاه\n"
    "- keywords: ۳ تا ۵ کلیدواژه‌ی فارسی\n"
    "- category: دقیقاً یکی از: " + json.dumps(CATEGORIES_FA, ensure_ascii=False) + "\n"
    "- importance: «بالا» یا «متوسط» یا «پایین»\n\n"
    "معیار اهمیت: بالا = جایزه یا مسابقه‌ی بین‌المللی مهم، محصول واقعاً نوآورانه، تحول بزرگ صنعت "
    "(معمولاً ۱ تا ۲ خبر از هر ۱۰ خبر). متوسط = رونمایی قابل توجه، رویداد منطقه‌ای، پروژه‌ی جالب. "
    "پایین = خبر جزئی، یادداشت نظری، اطلاعیه‌ی معمول.\n\n"
    "خروجی فقط یک آرایه‌ی JSON باشد، بدون هیچ توضیح اضافه و بدون markdown.\n"
    "نمونه‌ی قالب (فقط برای فرمت؛ محتوایش را تکرار نکن):\n" + _EXAMPLE_FA
)

SYSTEM_PROMPT_EN = (
    "You are the editor of a specialist industrial-design news channel.\n"
    "Input: several news items, each with an id. For each item return one JSON object with:\n"
    "- id: the input id, unchanged\n"
    "- title: a clear, concise English headline (max 10 words); keep all brand, company, person, "
    "product and award names exactly as written\n"
    "- summary: a clear English summary of at most 3 short sentences; do not add facts that are not in the item\n"
    "- keywords: 3-5 English keywords\n"
    "- category: exactly one of " + json.dumps(CATEGORIES_EN) + "\n"
    "- importance: \"High\", \"Medium\" or \"Low\"\n\n"
    "High = major international award/competition, genuinely innovative product, big industry shift "
    "(usually 1-2 of every 10 items). Medium = notable release, regional event, interesting project. "
    "Low = minor news, opinion piece, routine announcement.\n"
    "Return ONLY a JSON array. No extra text, no markdown."
)

_IMP_FA = {"بالا": "بالا", "high": "بالا", "متوسط": "متوسط", "medium": "متوسط", "پایین": "پایین", "low": "پایین"}
_IMP_EN = {"high": "High", "بالا": "High", "medium": "Medium", "متوسط": "Medium", "low": "Low", "پایین": "Low"}
_AR = re.compile(r"[\u0600-\u06FF]")
_LETTER = re.compile(r"[A-Za-z\u0600-\u06FF]")


# ───────────── parsing / validation helpers ─────────────
def _build_user_message(batch):
    return "\n\n".join(
        f"id={i}\nTITLE: {a.title}\nSOURCE: {a.source}\nSNIPPET: {(a.summary or '(none)')[:300]}"
        for i, a in enumerate(batch, 1))


def _salvage_objects(raw):
    dec, out, i = json.JSONDecoder(), [], raw.find("{")
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
    s, e = raw.find("["), raw.rfind("]")
    if s != -1 and e > s:
        try:
            data = json.loads(raw[s:e + 1])
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except json.JSONDecodeError:
            pass
    return _salvage_objects(raw)


def _persian_ratio(text):
    letters = _LETTER.findall(text or "")
    return (sum(1 for c in letters if _AR.match(c)) / len(letters)) if letters else 0.0


def _quality_ok(r, lang):
    title = str(r.get("title_fa") or r.get("title") or "").strip()
    summary = str(r.get("summary") or "").strip()
    if len(title) < 3 or len(summary) < 20:
        return False
    if lang == "fa":
        return _persian_ratio(title) >= 0.25 and _persian_ratio(summary) >= 0.6
    return True


def _norm_importance(v, lang):
    t = _IMP_FA if lang == "fa" else _IMP_EN
    return t.get(str(v or "").strip().lower(), "متوسط" if lang == "fa" else "Medium")


def _norm_category(v, lang):
    cats = CATEGORIES_FA if lang == "fa" else CATEGORIES_EN
    v = str(v or "").strip()
    if v in cats:
        return v
    for c in cats:
        if v and (c in v or v in c):
            return c
    return "سایر" if lang == "fa" else "Other"


def _fallback(article, lang):
    t = article.title.lower()
    fa = {"award": "جوایز طراحی", "competition": "مسابقات طراحی", "ai ": "هوش مصنوعی در طراحی",
          "automotive": "خودرو", "furniture": "مبلمان", "packaging": "بسته‌بندی", "medical": "طراحی پزشکی"}
    en = {"award": "Design Awards", "competition": "Design Competitions", "ai ": "AI in Design",
          "automotive": "Automotive", "furniture": "Furniture", "packaging": "Packaging", "medical": "Medical Design"}
    for kw, cat in (fa if lang == "fa" else en).items():
        if kw in t:
            return {"title": article.title, "category": cat, "summary": article.summary, "keywords": [],
                    "importance": "متوسط" if lang == "fa" else "Medium"}
    return {"title": article.title, "category": "سایر" if lang == "fa" else "Other",
            "summary": article.summary, "keywords": [], "importance": "پایین" if lang == "fa" else "Low"}


def _apply_results(batch, results, lang):
    """Match by id; validate quality. Returns (articles, matched_count, failed_indices)."""
    by_id = {}
    for r in results:
        try:
            by_id[int(r.get("id"))] = r
        except (TypeError, ValueError):
            pass
    positional = (not by_id) and len(results) == len(batch)

    out, matched, failed = [], 0, []
    for idx, a in enumerate(batch, 1):
        r = by_id.get(idx) or (results[idx - 1] if positional else None)
        if r is not None and _quality_ok(r, lang):
            a.title = str(r.get("title_fa") or r.get("title")).strip()
            a.summary = str(r.get("summary")).strip()
            a.keywords = r.get("keywords") or []
            a.category = _norm_category(r.get("category"), lang)
            a.importance = _norm_importance(r.get("importance"), lang)
            matched += 1
        else:
            fb = _fallback(a, lang)
            a.keywords, a.category, a.importance = [], fb["category"], fb["importance"]
            failed.append(idx - 1)
        out.append(a)
    return out, matched, failed


# ───────────── generic model-candidate loop ─────────────
class _ModelGone(Exception):
    pass


class _RateLimited(Exception):
    pass


def _try_models(models, call, dead, user_msg, lang, rate_wait):
    for model in models:
        if model in dead:
            continue
        for attempt in range(2):
            try:
                return model, call(model, user_msg, lang)
            except _ModelGone as e:
                logger.warning("Model %s unavailable, skipping (%s)", model, e)
                dead.add(model)
                break
            except _RateLimited:
                wait = rate_wait * (attempt + 1)
                logger.warning("Model %s rate-limited, waiting %ds", model, wait)
                time.sleep(wait)
            except Exception as e:
                logger.warning("Model %s failed: %s", model, e)
                break
    return None, []


# ───────────── Claude ─────────────
def _call_claude(user_msg, lang):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    r = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=6000,
        system=SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN,
        messages=[{"role": "user", "content": user_msg}])
    return _parse_results(r.content[0].text)


def _enrich_claude(articles, lang):
    batches = [articles[i:i + BATCH_SIZE_CLAUDE] for i in range(0, len(articles), BATCH_SIZE_CLAUDE)]

    def work(b):
        try:
            res = _call_claude(_build_user_message(b), lang)
        except Exception as e:
            logger.error("Claude batch error: %s", e)
            res = []
        return _apply_results(b, res, lang)[0]

    done = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_CLAUDE) as ex:
        futs = {ex.submit(work, b): i for i, b in enumerate(batches)}
        for f in as_completed(futs):
            try:
                done[futs[f]] = f.result()
            except Exception as e:
                logger.error("Batch failed: %s", e)
                done[futs[f]] = batches[futs[f]]
    return [a for i in range(len(batches)) for a in done.get(i, batches[i])]


# ───────────── Gemini (free tier) ─────────────
_gem = {"dead": set(), "last_good": None}


def _gemini_models():
    env = os.environ.get("GEMINI_MODELS", "")
    return [m.strip() for m in env.split(",") if m.strip()] or ["gemini-flash-latest", "gemini-2.5-flash"]


def _call_gemini_model(model, user_msg, lang):
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ.get("GEMINI_API_KEY", ""), "Content-Type": "application/json"},
        json={"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN}]},
              "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
              "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192,
                                   "responseMimeType": "application/json"}},
        timeout=90)
    if resp.status_code == 429:
        raise _RateLimited()
    if resp.status_code in (400, 401, 403, 404):
        raise _ModelGone(f"{resp.status_code}: {resp.text[:160]}")
    resp.raise_for_status()
    parts = resp.json()["candidates"][0]["content"]["parts"]
    results = _parse_results("".join(p.get("text", "") for p in parts))
    if not results:
        raise ValueError("no parsable JSON")
    return results


def _gemini_batch(user_msg, lang, avoid=None):
    models = [m for m in _gemini_models() if m != avoid] + ([avoid] if avoid in _gemini_models() else [])
    model, res = _try_models(models, _call_gemini_model, _gem["dead"], user_msg, lang, rate_wait=15)
    if model:
        _gem["last_good"] = model
        logger.info("Gemini OK via %s (%d items)", model, len(res))
    return res


# ───────────── OpenRouter (free tier) ─────────────
_PREFERRED = (
    "google/gemma-4-31b-it", "meta-llama/llama-3.3-70b-instruct",
    "qwen/qwen3-next-80b-a3b-instruct", "openai/gpt-oss-120b",
    "nousresearch/hermes-3-llama-3.1-405b", "google/gemma-4-26b-a4b-it",
)
_EXCLUDE = ("lyria", "safety", "guard", "code", "coder", "-vl", "embed", "image",
            "audio", "tts", "whisper", "omni", "vision", "moderation")
_or = {"models": None, "dead": set(), "last_good": None}


def _discover_free_models():
    ids = []
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=20)
        r.raise_for_status()
        for m in r.json().get("data", []):
            mid, pr = m.get("id", ""), (m.get("pricing") or {})
            if (mid.endswith(":free") and str(pr.get("prompt", "0")) in ("0", "0.0", "0.00")
                    and str(pr.get("completion", "0")) in ("0", "0.0", "0.00")
                    and not any(w in mid.lower() for w in _EXCLUDE)):
                ids.append(mid)
    except Exception as e:
        logger.warning("Could not list OpenRouter models: %s", e)
    vetted = [p + ":free" for p in _PREFERRED if p + ":free" in ids]
    ordered = vetted if len(vetted) >= 2 else vetted + [m for m in ids if m not in vetted]
    if not ordered:
        ordered = [p + ":free" for p in _PREFERRED[:4]]
    ordered = ordered[:MAX_MODEL_CANDIDATES] + ["openrouter/free"]
    logger.info("OpenRouter candidate models: %s", ordered)
    return ordered


def _call_openrouter_model(model, user_msg, lang):
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
                 "Content-Type": "application/json"},
        json={"model": model, "max_tokens": MAX_TOKENS, "temperature": 0.2,
              "messages": [{"role": "system", "content": SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN},
                           {"role": "user", "content": user_msg}]},
        timeout=90)
    if resp.status_code == 429:
        raise _RateLimited()
    if resp.status_code in (400, 401, 402, 403, 404):
        raise _ModelGone(f"{resp.status_code}: {resp.text[:160]}")
    resp.raise_for_status()
    results = _parse_results(resp.json()["choices"][0]["message"].get("content") or "")
    if not results:
        raise ValueError("no parsable JSON")
    return results


def _candidate_models(avoid=None):
    if _or["models"] is None:
        _or["models"] = _discover_free_models()
    models = [m for m in _or["models"] if m not in _or["dead"]]
    good = _or["last_good"]
    if good in models and good != avoid:
        models.remove(good)
        models.insert(0, good)
    if avoid in models:
        models.remove(avoid)
        models.append(avoid)
    return models


def _openrouter_batch(user_msg, lang, avoid=None):
    if not os.environ.get("OPENROUTER_API_KEY"):
        return []
    model, res = _try_models(_candidate_models(avoid), _call_openrouter_model, _or["dead"], user_msg, lang, rate_wait=8)
    if model:
        _or["last_good"] = model
        logger.info("OpenRouter OK via %s (%d items)", model, len(res))
    else:
        logger.error("All OpenRouter models failed for this batch")
    return res


def _call_api(user_msg, lang):
    """Compatibility shim for debug scripts."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _call_claude(user_msg, lang)
    if os.environ.get("GEMINI_API_KEY"):
        return _gemini_batch(user_msg, lang)
    return _openrouter_batch(user_msg, lang)


# ───────────── sequential driver with quality retry ─────────────
def _enrich_sequential(articles, lang, batch_fn, size, delay, last_good_fn):
    batches = [articles[i:i + size] for i in range(0, len(articles), size)]
    started, out = time.time(), []
    for i, batch in enumerate(batches):
        within = time.time() - started < BUDGET_SECONDS
        results = batch_fn(_build_user_message(batch), lang, None) if within else []
        enriched, matched, failed = _apply_results(batch, results, lang)
        if failed and within and time.time() - started < BUDGET_SECONDS:
            retry = [batch[j] for j in failed]
            time.sleep(delay)
            res2 = batch_fn(_build_user_message(retry), lang, last_good_fn())
            _, m2, _ = _apply_results(retry, res2, lang)
            matched += m2
        logger.info("Batch %d/%d: %d/%d enriched with valid output", i + 1, len(batches), matched, len(batch))
        out.extend(enriched)
        if i < len(batches) - 1:
            time.sleep(delay)
    return out


def enrich_articles(articles, lang="fa"):
    if not articles:
        return []
    if os.environ.get("ANTHROPIC_API_KEY"):
        provider, enriched = "Claude", _enrich_claude(articles, lang)
    elif os.environ.get("GEMINI_API_KEY"):
        provider = "Gemini"
        enriched = _enrich_sequential(articles, lang, _gemini_batch, BATCH_SIZE_GEMINI, DELAY_GEMINI,
                                      lambda: _gem["last_good"])
    else:
        provider = "OpenRouter"
        enriched = _enrich_sequential(articles, lang, _openrouter_batch, BATCH_SIZE_OPENROUTER, DELAY_OPENROUTER,
                                      lambda: _or["last_good"])
    imp = {}
    for a in enriched:
        imp[a.importance] = imp.get(a.importance, 0) + 1
    other = ("سایر", "Other")
    logger.info("Enriched %d articles via %s. Non-Other: %d/%d. Importance: %s", len(enriched), provider,
                sum(1 for a in enriched if a.category not in other), len(enriched), imp)
    return enriched
