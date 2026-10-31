"""
manual.py — admin-curated news (data/manual_news.json) merged into digests.

Item: {id, title_fa, summary_fa, title_en?, summary_en?, category (fa name), importance
       ("high"|"medium"|"low"), url, source, created_at, expires_at?, mode ("digest"|"instant")}
Only mode == "digest" items that have not expired are merged. They bypass interest filtering.
"""
import os, json, logging
from datetime import datetime, timezone, timedelta
from collector import Article
from categories import FA_TO_EN

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_PATH = os.path.join(BASE_DIR, "data", "manual_news.json")
DEFAULT_TTL_HOURS = 30
_IMP = {"high": ("بالا", "High"), "medium": ("متوسط", "Medium"), "low": ("پایین", "Low")}


def _parse(ts):
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def load_items(path=None) -> list:
    path = path or MANUAL_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", []) if isinstance(data, dict) else []
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.error("manual_news.json unreadable: %s", e)
        return []


def item_to_article(it: dict, lang: str) -> Article:
    fa = lang == "fa"
    title = (it.get("title_fa") if fa else (it.get("title_en") or it.get("title_fa"))) or ""
    summary = (it.get("summary_fa") if fa else (it.get("summary_en") or it.get("summary_fa"))) or ""
    cat_fa = it.get("category") or "سایر"
    created = _parse(it.get("created_at")) or datetime.now(timezone.utc)
    imp = _IMP.get(str(it.get("importance", "medium")).lower(), _IMP["medium"])[0 if fa else 1]
    a = Article(title=title.strip(), url=it.get("url", "").strip(), source=(it.get("source") or "WIDD Iran"),
                published=created, summary=summary.strip(),
                category=cat_fa if fa else FA_TO_EN.get(cat_fa, "Other"), importance=imp)
    a.force_all = True
    return a


def load_manual_articles(lang: str, now=None, path=None) -> list:
    now = now or datetime.now(timezone.utc)
    out = []
    for it in load_items(path):
        if it.get("mode", "digest") != "digest" or not it.get("url") or not (it.get("title_fa") or it.get("title_en")):
            continue
        created = _parse(it.get("created_at")) or now
        expires = _parse(it.get("expires_at")) or (created + timedelta(hours=DEFAULT_TTL_HOURS))
        if expires < now:
            continue
        out.append(item_to_article(it, lang))
    if out:
        logger.info("Merged %d manual news item(s) (%s)", len(out), lang)
    return out
