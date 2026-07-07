"""
report.py — Build the daily Markdown digest from enriched articles. Persian version.
"""

import os
from datetime import datetime, timezone, timedelta
from collector import Article

IMPORTANCE_ORDER = {"بالا": 0, "High": 0, "متوسط": 1, "Medium": 1, "پایین": 2, "Low": 2}
TEHRAN_OFFSET = timedelta(hours=3, minutes=30)


def _now_tehran() -> datetime:
    return datetime.now(timezone.utc) + TEHRAN_OFFSET


def _format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _format_published(dt) -> str:
    if dt is None:
        return "نامشخص"
    local = dt + TEHRAN_OFFSET
    return local.strftime("%Y-%m-%d %H:%M")


def build_markdown(articles: list) -> str:
    today = _now_tehran()
    date_str = _format_date(today)

    sorted_articles = sorted(
        articles,
        key=lambda a: (
            IMPORTANCE_ORDER.get(a.importance, 2),
            -(a.published.timestamp() if a.published else 0),
        ),
    )

    lines = [
        "# 🎨 اخبار روزانه دیزاین و طراحی صنعتی",
        f"**تاریخ:** {date_str}",
        f"**تعداد اخبار:** {len(articles)}",
        "",
        "---",
        "",
    ]

    current_importance = None
    for article in sorted_articles:
        imp = article.importance or "متوسط"
        if imp != current_importance:
            current_importance = imp
            emoji = {"بالا": "🔴", "High": "🔴", "متوسط": "🟡", "Medium": "🟡", "پایین": "🟢", "Low": "🟢"}.get(imp, "⚪")
            label = {"بالا": "اهمیت بالا", "High": "اهمیت بالا", "متوسط": "اهمیت متوسط", "Medium": "اهمیت متوسط", "پایین": "اهمیت پایین", "Low": "اهمیت پایین"}.get(imp, imp)
            lines.append(f"## {emoji} {label}")
            lines.append("")

        lines.append(f"### {article.title}")
        lines.append("")
        lines.append(article.summary or "_خلاصه‌ای موجود نیست._")
        lines.append("")
        if article.keywords:
            lines.append(f"**کلیدواژه‌ها:** {', '.join(article.keywords)}")
        lines.append(f"**دسته‌بندی:** {article.category}")
        lines.append(f"**منبع:** {article.source}")
        lines.append(f"**تاریخ انتشار:** {_format_published(article.published)}")
        lines.append(f"**لینک:** [{article.url}]({article.url})")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"_گزارش در {today.strftime('%Y-%m-%d %H:%M')} به وقت تهران تهیه شد._")
    return "\n".join(lines)


def save_report(markdown: str, output_dir: str = "reports") -> str:
    os.makedirs(output_dir, exist_ok=True)
    date_str = _format_date(_now_tehran())
    path = os.path.join(output_dir, f"design-news-{date_str}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    return path


def build_telegram_message(articles: list) -> str:
    today = _now_tehran()
    date_str = today.strftime("%Y-%m-%d")

    high   = [a for a in articles if a.importance in ("بالا", "High")][:5]
    medium = [a for a in articles if a.importance in ("متوسط", "Medium")][:5]

    parts = [
        f"🎨 *اخبار روزانه دیزاین* — {date_str}",
        f"_{len(articles)} خبر · {len(high)} خبر مهم_",
        "",
    ]

    if high:
        parts.append("🔴 *اهمیت بالا*")
        for a in high:
            title = a.title.replace("_", "\_").replace("*", "\*").replace("[", "\[")
            parts.append(f"• [{title}]({a.url})")
            parts.append(f"  _{a.source}_ · {a.category}")
            parts.append("")

    if medium:
        parts.append("🟡 *اهمیت متوسط*")
        for a in medium:
            title = a.title.replace("_", "\_").replace("*", "\*").replace("[", "\[")
            parts.append(f"• [{title}]({a.url})")
            parts.append(f"  _{a.source}_ · {a.category}")
            parts.append("")

    parts.append("📄 گزارش کامل: فایل پیوست")
    return "\n".join(parts)
