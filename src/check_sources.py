"""
check_sources.py — health-check every configured source (and optional extra candidates).
Writes data/sources_status.json (no personal data). Run via the "Check Sources" workflow.
"""
import os, json, time, logging
from datetime import datetime, timezone, timedelta
import requests, feedparser

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("check")

from sources import RSS_SOURCES, SCRAPE_SOURCES, GOOGLE_NEWS_QUERIES, GOOGLE_NEWS_BASE

UA = {"User-Agent": "Mozilla/5.0 (compatible; DesignNewsBot/1.0; +https://github.com/taraa-lab/design-news-bot)"}
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _entry_dt(e):
    for a in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(e, a, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def check_feed(name, url, kind="rss"):
    res = {"name": name, "type": kind, "url": url, "ok": False, "http": None,
           "entries": 0, "last_24h": 0, "last_7d": 0, "newest": None, "error": ""}
    t0 = time.time()
    try:
        r = requests.get(url, headers=UA, timeout=25)
        res["http"] = r.status_code
        if r.status_code != 200:
            res["error"] = f"HTTP {r.status_code}"
            return res
        feed = feedparser.parse(r.content)
        now = datetime.now(timezone.utc)
        dts = [d for d in (_entry_dt(e) for e in feed.entries) if d]
        res["entries"] = len(feed.entries)
        res["last_24h"] = sum(1 for d in dts if now - d <= timedelta(hours=24))
        res["last_7d"] = sum(1 for d in dts if now - d <= timedelta(days=7))
        res["newest"] = max(dts).isoformat() if dts else None
        res["ok"] = res["entries"] > 0
        if not res["ok"]:
            res["error"] = "no entries parsed"
    except Exception as e:
        res["error"] = str(e)[:160]
    res["seconds"] = round(time.time() - t0, 1)
    return res


def check_scrape(src):
    from bs4 import BeautifulSoup
    res = {"name": src["name"], "type": "scrape", "url": src["url"], "ok": False,
           "http": None, "entries": 0, "error": ""}
    try:
        r = requests.get(src["url"], headers=UA, timeout=25)
        res["http"] = r.status_code
        if r.status_code != 200:
            res["error"] = f"HTTP {r.status_code}"
            return res
        soup = BeautifulSoup(r.text, "html.parser")
        res["entries"] = len(soup.select(src.get("article_selector", "article")))
        res["ok"] = res["entries"] > 0
        if not res["ok"]:
            res["error"] = "selector matched nothing"
    except Exception as e:
        res["error"] = str(e)[:160]
    return res


def main():
    results = []
    for s in RSS_SOURCES:
        r = check_feed(s["name"], s["url"]); r["enabled"] = s.get("enabled", True); results.append(r)
        log.info("%-22s http=%s entries=%s 24h=%s %s", r["name"], r["http"], r["entries"], r["last_24h"], r["error"])
    for s in SCRAPE_SOURCES:
        r = check_scrape(s); r["enabled"] = s.get("enabled", True); results.append(r)
        log.info("%-22s http=%s entries=%s %s", r["name"], r["http"], r["entries"], r["error"])

    extras = []
    for line in os.environ.get("EXTRA_FEEDS", "").replace(";", "\n").splitlines():
        if "|" in line:
            n, u = [x.strip() for x in line.split("|", 1)]
            r = check_feed(n, u); extras.append(r)
            log.info("[candidate] %-20s http=%s entries=%s 24h=%s 7d=%s %s", n, r["http"], r["entries"], r["last_24h"], r["last_7d"], r["error"])

    gn = []
    for q in GOOGLE_NEWS_QUERIES:
        import urllib.parse
        r = check_feed(f"Google News: {q}", GOOGLE_NEWS_BASE.format(query=urllib.parse.quote(q)), "google_news")
        gn.append(r)

    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "results": results,
           "google_news": gn, "candidates": extras}
    os.makedirs(os.path.join(BASE, "data"), exist_ok=True)
    with open(os.path.join(BASE, "data", "sources_status.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log.info("done")


if __name__ == "__main__":
    main()
