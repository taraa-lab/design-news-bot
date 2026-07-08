"""
report.py — Build Markdown digest. Supports fa/en output. 7 items per section.
"""

import os
from datetime import datetime, timezone, timedelta

IMPORTANCE_ORDER = {"بالا":0,"High":0,"متوسط":1,"Medium":1,"پایین":2,"Low":2}
TEHRAN_OFFSET = timedelta(hours=3, minutes=30)

def _now_tehran():
    return datetime.now(timezone.utc) + TEHRAN_OFFSET

def _fmt_date(dt):
    return dt.strftime("%Y-%m-%d")

def _fmt_pub(dt):
    if dt is None: return "—"
    return (dt + TEHRAN_OFFSET).strftime("%Y-%m-%d %H:%M")

def build_markdown(articles, lang="fa"):
    today = _now_tehran()
    sorted_arts = sorted(articles, key=lambda a:(IMPORTANCE_ORDER.get(a.importance,2),
                                                  -(a.published.timestamp() if a.published else 0)))
    if lang == "fa":
        lines = ["# 🎨 اخبار روزانه دیزاین و طراحی صنعتی",
                 f"**تاریخ:** {_fmt_date(today)}", f"**تعداد اخبار:** {len(articles)}", "", "---", ""]
        imp_map = {"بالا":"🔴 اهمیت بالا","High":"🔴 اهمیت بالا",
                   "متوسط":"🟡 اهمیت متوسط","Medium":"🟡 اهمیت متوسط",
                   "پایین":"🟢 سایر اخبار","Low":"🟢 سایر اخبار"}
        lbl = {"cat":"دسته‌بندی","src":"منبع","pub":"تاریخ","link":"لینک","kw":"کلیدواژه‌ها"}
        footer = f"_گزارش در {today.strftime(\'%Y-%m-%d %H:%M\')} به وقت تهران_"
    else:
        lines = ["# 🎨 Industrial Design Daily News",
                 f"**Date:** {_fmt_date(today)}", f"**Articles:** {len(articles)}", "", "---", ""]
        imp_map = {"بالا":"🔴 High Priority","High":"🔴 High Priority",
                   "متوسط":"🟡 Medium Priority","Medium":"🟡 Medium Priority",
                   "پایین":"🟢 Other News","Low":"🟢 Other News"}
        lbl = {"cat":"Category","src":"Source","pub":"Published","link":"Read","kw":"Keywords"}
        footer = f"_Report generated at {today.strftime(\'%Y-%m-%d %H:%M\')} Tehran time._"

    cur_imp = None
    for a in sorted_arts:
        imp = a.importance or ("متوسط" if lang=="fa" else "Medium")
        if imp != cur_imp:
            cur_imp = imp
            lines += [f"## {imp_map.get(imp,imp)}", ""]
        lines += [f"### {a.title}", "", a.summary or "—", ""]
        if a.keywords:
            lines.append(f"**{lbl[\'kw\']}:** {\', \'.join(a.keywords)}")
        lines += [f"**{lbl[\'cat\']}:** {a.category}",
                  f"**{lbl[\'src\']}:** {a.source}",
                  f"**{lbl[\'pub\']}:** {_fmt_pub(a.published)}",
                  f"**{lbl[\'link\']}:** [{a.url}]({a.url})",
                  "", "---", ""]
    lines.append(footer)
    return "\n".join(lines)

def save_report(markdown, output_dir="reports"):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"design-news-{_fmt_date(_now_tehran())}.md")
    with open(path,"w",encoding="utf-8") as f: f.write(markdown)
    return path

def build_telegram_message(articles, lang="fa"):
    today = _now_tehran()
    date_str = today.strftime("%Y-%m-%d")
    sorted_arts = sorted(articles, key=lambda a:(IMPORTANCE_ORDER.get(a.importance,2),
                                                  -(a.published.timestamp() if a.published else 0)))

    high   = [a for a in sorted_arts if a.importance in ("بالا","High")][:7]
    medium = [a for a in sorted_arts if a.importance in ("متوسط","Medium")][:7]

    if lang == "fa":
        header  = f"🎨 *اخبار روزانه دیزاین* — {date_str}\n_{len(articles)} خبر امروز_\n"
        h_label = "🔴 *اهمیت بالا*"
        m_label = "🟡 *اهمیت متوسط*"
        footer  = "📄 گزارش کامل: فایل پیوست"
    else:
        header  = f"🎨 *Design News Daily* — {date_str}\n_{len(articles)} articles today_\n"
        h_label = "🔴 *High Priority*"
        m_label = "🟡 *Medium Priority*"
        footer  = "📄 Full report: see attached file"

    parts = [header]
    if high:
        parts.append(h_label)
        for a in high:
            t = a.title.replace("_","\\_").replace("*","\\*").replace("[","\\[")
            parts += [f"• [{t}]({a.url})", f"  _{a.source}_ · {a.category}", ""]
    if medium:
        parts.append(m_label)
        for a in medium:
            t = a.title.replace("_","\\_").replace("*","\\*").replace("[","\\[")
            parts += [f"• [{t}]({a.url})", f"  _{a.source}_ · {a.category}", ""]
    parts.append(footer)
    return "\n".join(parts)
