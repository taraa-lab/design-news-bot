"""
report.py — Build the daily Markdown digest from enriched articles.
"""

import os
from datetime import datetime, timezone, timedelta
from collector import Article

IMPORTANCE_ORDER = {"High": 0, "Medium": 1, "Low": 2}

TEHRAN_OFFSET = timedelta(hours=3, minutes=30)


def _now_tehran() -> datetime:
    return datetime.now(timezone.utc) + TEHRAN_OFFSET


def _format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _format_published(dt) -> str:
    if dt is None:
        return "Unknown"
    local = dt + TEHRAN_OFFSET
    return local.strftime("%Y-%m-%d %H:%M")


def build_markdown(articles: list[Article]) -> str:
    today = _now_tehran()
    date_str = _format_date(today)

    # Sort: importance first, then by published time (newest first)
    sorted_articles = sorted(
        articles,
        key=lambda a: (
            IMPORTANCE_ORDER.get(a.importance, 2),
            -(a.published.timestamp() if a.published else 0),
        ),
    )

    lines = [
        "# 🎨 Industrial Design Daily News",
        f"**Date:** {date_str}",
        f"**Articles:** {len(articles)}",
        "",
        "---",
        "",
    ]

    current_importance = None
    for article in sorted_articles:
        imp = article.importance or "Medium"
        if imp != current_importance:
            current_importance = imp
            emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(imp, "⚪")
            lines.append(f"## {emoji} {imp} Priority")
            lines.append("")

        lines.append(f"### {article.title}")
        lines.append("")
        lines.append(article.summary or "_No summary available._")
        lines.append("")
        if article.keywords:
            lines.append(f"**Keywords:** {', '.join(article.keywords)}")
        lines.append(f"**Category:** {article.category}")
        lines.append(f"**Source:** {article.source}")
        lines.append(f"**Published:** {_format_published(article.published)}")
        lines.append(f"**Read:** [{article.url}]({article.url})")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"_Report generated at {today.strftime('%Y-%m-%d %H:%M')} Tehran time._")
    return "\n".join(lines)


def save_report(markdown: str, output_dir: str = "reports") -> str:
    os.makedirs(output_dir, exist_ok=True)
    date_str = _format_date(_now_tehran())
    path = os.path.join(output_dir, f"design-news-{date_str}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    return path


def build_telegram_message(articles: list[Article]) -> str:
    """
    Telegram has a 4096-char limit per message.
    This builds a short digest of High + Medium priority items.
    """
    today = _now_tehran()
    date_str = today.strftime("%Y-%m-%d")

    high   = [a for a in articles if a.importance == "High"][:5]
    medium = [a for a in articles if a.importance == "Medium"][:5]

    parts = [
        f"🎨 *Industrial Design Daily* — {date_str}",
        f"_{len(articles)} articles · {len(high)} high priority_",
        "",
    ]

    if high:
        parts.append("🔴 *High Priority*")
        for a in high:
            # Escape markdown special chars for Telegram MarkdownV2
            title = a.title.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[")
            parts.append(f"• [{title}]({a.url})")
            parts.append(f"  _{a.source}_ · {a.category}")
            parts.append("")

    if medium:
        parts.append("🟡 *Medium Priority*")
        for a in medium:
            title = a.title.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[")
            parts.append(f"• [{title}]({a.url})")
            parts.append(f"  _{a.source}_ · {a.category}")
            parts.append("")

    parts.append(f"📄 Full report: see attached file")
    return "\n".join(parts)
