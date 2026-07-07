# ============================================================
# SOURCES CONFIG
# Add or remove sources here — no other file needs to change.
# ============================================================

RSS_SOURCES = [
    {
        "name": "Core77",
        "url": "https://www.core77.com/rss.xml",
        "enabled": True,
    },
    {
        "name": "Dezeen",
        "url": "https://www.dezeen.com/feed/",
        "enabled": True,
    },
    {
        "name": "Designboom",
        "url": "https://www.designboom.com/feed/",
        "enabled": True,
    },
    {
        "name": "Yanko Design",
        "url": "https://www.yankodesign.com/feed/",
        "enabled": True,
    },
    {
        "name": "Dexigner",
        "url": "https://www.dexigner.com/rss/news.xml",
        "enabled": True,
    },
    {
        "name": "Design Milk",
        "url": "https://design-milk.com/feed/",
        "enabled": True,
    },
    {
        "name": "Fast Company Design",
        "url": "https://www.fastcompany.com/section/design/rss",
        "enabled": True,
    },
    {
        "name": "ArchDaily",
        "url": "https://www.archdaily.com/feed",
        "enabled": True,
    },
    {
        "name": "Creative Boom",
        "url": "https://www.creativeboom.com/feed/",
        "enabled": True,
    },
    {
        "name": "Dezeen Jobs",
        "url": "https://www.dezeen.com/jobs/feed/",
        "enabled": False,  # optional — set True to enable
    },
]

# Sources without RSS — scraped with requests + BeautifulSoup
SCRAPE_SOURCES = [
    {
        "name": "IDSA",
        "url": "https://www.idsa.org/news",
        "article_selector": "article",          # CSS selector for article containers
        "title_selector": "h2,h3",
        "link_selector": "a",
        "date_selector": "time",
        "enabled": True,
    },
    {
        "name": "WDO",
        "url": "https://wdo.org/news/",
        "article_selector": ".entry-content article, .news-item, article",
        "title_selector": "h2,h3",
        "link_selector": "a",
        "date_selector": "time,.date",
        "enabled": True,
    },
    {
        "name": "Red Dot",
        "url": "https://www.red-dot.org/press",
        "article_selector": "article,.press-item",
        "title_selector": "h2,h3",
        "link_selector": "a",
        "date_selector": "time,.date",
        "enabled": True,
    },
    {
        "name": "iF Design",
        "url": "https://ifdesign.com/en/news",
        "article_selector": "article,.news-card",
        "title_selector": "h2,h3",
        "link_selector": "a",
        "date_selector": "time,.date",
        "enabled": True,
    },
]

# Google News RSS queries
GOOGLE_NEWS_QUERIES = [
    "industrial design",
    "product design award",
    "design competition 2025",
]

GOOGLE_NEWS_BASE = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
