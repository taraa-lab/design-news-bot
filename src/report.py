"""
report.py — Build daily digest. lang param controls output language.
"""
import os
from datetime import datetime, timezone, timedelta

IMPORTANCE_ORDER = {"بالا":0,"High":0,"متوسط":1,"Medium":1,"پایین":2,"Low":2}
TEHRAN_OFFSET = timedelta(hours=3, minutes=30)
TG_HIGH_COUNT = 7
TG_MED_COUNT  = 7

def _now_tehran():
    return datetime.now(timezone.utc) + TEHRAN_OFFSET

def _fmt_date(dt):
    return dt.strftime("%Y-%m-%d")

def _fmt_pub(dt):
    if dt is None: return "نامشخص"
    return (dt + TEHRAN_OFFSET).strftime("%Y-%m-%d %H:%M")

def build_markdown(articles):
    today = _now_tehran()
    sorted_arts = sorted(articles, key=lambda a:(IMPORTANCE_ORDER.get(a.importance,2),-(a.published.timestamp() if a.published else 0)))
    lines = ["# 🎨 اخبار روزانه دیزاین", f"**تاریخ:** {_fmt_date(today)}", f"**تعداد:** {len(articles)}", "", "---", ""]
    cur = None
    for a in sorted_arts:
        imp = a.importance or "متوسط"
        if imp != cur:
            cur = imp
            emoji = {"بالا":"🔴","High":"🔴","متوسط":"🟡","Medium":"🟡","پایین":"🟢","Low":"🟢"}.get(imp,"⚪")
            label = {"بالا":"اهمیت بالا","High":"High Priority","متوسط":"اهمیت متوسط","Medium":"Medium Priority","پایین":"اهمیت پایین","Low":"Low Priority"}.get(imp,imp)
            lines += [f"## {emoji} {label}", ""]
        lines += [f"### {a.title}", "", a.summary or "", ""]
        if a.keywords: lines.append(f"**کلیدواژه‌ها:** {', '.join(a.keywords)}")
        lines += [f"**منبع:** {a.source}", f"**لینک:** [{a.url}]({a.url})", "", "---", ""]
    lines.append(f"_گزارش در {today.strftime('%Y-%m-%d %H:%M')} تهران._")
    return "\n".join(lines)

def save_report(markdown, output_dir="reports"):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"design-news-{_fmt_date(_now_tehran())}.md")
    with open(path,"w",encoding="utf-8") as f: f.write(markdown)
    return path

def build_telegram_message(articles, lang="fa"):
    """lang param overrides env var so each user gets their own language."""
    today = _now_tehran()
    high   = [a for a in articles if a.importance in ("بالا","High")][:TG_HIGH_COUNT]
    medium = [a for a in articles if a.importance in ("متوسط","Medium")][:TG_MED_COUNT]

    if lang == "fa":
        header   = f"🎨 *اخبار روزانه دیزاین* — {today.strftime('%Y-%m-%d')}\n_{len(articles)} خبر · {len(high)} خبر مهم_\n"
        lbl_high = "🔴 *اهمیت بالا*"
        lbl_med  = "🟡 *اهمیت متوسط*"
        footer   = "📄 گزارش کامل: فایل پیوست"
    else:
        header   = f"🎨 *Daily Design News* — {today.strftime('%Y-%m-%d')}\n_{len(articles)} articles · {len(high)} high priority_\n"
        lbl_high = "🔴 *High Priority*"
        lbl_med  = "🟡 *Medium Priority*"
        footer   = "📄 Full report: see attached file"

    parts = [header]
    if high:
        parts.append(lbl_high)
        for a in high:
            t = a.title.replace("_","\\_").replace("*","\\*").replace("[","\\[")
            parts += [f"• [{t}]({a.url})", f"  _{a.source}_ · {a.category}", ""]
    if medium:
        parts.append(lbl_med)
        for a in medium:
            t = a.title.replace("_","\\_").replace("*","\\*").replace("[","\\[")
            parts += [f"• [{t}]({a.url})", f"  _{a.source}_ · {a.category}", ""]
    parts.append(footer)
    return "\n".join(parts)
