"""
broadcast.py — send an admin message (or one manual news item) to bot users.
Driven by the "Broadcast" workflow; inputs arrive through environment variables:
  BROADCAST_KIND  message | manual_item
  BROADCAST_TEXT  Telegram-HTML text (kind=message)
  ITEM_ID         manual item id (kind=manual_item)
  AUDIENCE        test | all
  LANG_FILTER     all | fa | en
  TEST_CHAT_ID    recipient when AUDIENCE=test
Chat IDs are never printed (logs are public-ish); only counts are reported.
"""
import os, sys, json, time, logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("broadcast")

from sender import send_html, item_block, main_keyboard
from manual import load_items, item_to_article

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "data", "broadcast_log.json")
MAX_LEN = 4000


def recipients(audience, lang_filter, test_chat):
    if audience == "test":
        return [(str(test_chat), "fa")] if test_chat else []
    from sheets import SheetsDB
    out = []
    for u in SheetsDB().get_all_users():
        cid, lang = u.get("chat_id", ""), u.get("lang", "fa") or "fa"
        if cid and (lang_filter == "all" or lang == lang_filter):
            out.append((cid, lang))
    return out


def write_log(entry):
    try:
        data = {"entries": []}
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["entries"] = ([entry] + data.get("entries", []))[:50]
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("could not write broadcast log: %s", e)


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    kind = os.environ.get("BROADCAST_KIND", "message")
    audience = os.environ.get("AUDIENCE", "test")
    lang_filter = os.environ.get("LANG_FILTER", "all")
    to = recipients(audience, lang_filter, os.environ.get("TEST_CHAT_ID", "").strip())
    if not to:
        log.error("No recipients (audience=%s)", audience)
        sys.exit(1)

    def message_for(lang):
        if kind == "manual_item":
            item = next((i for i in load_items() if i.get("id") == os.environ.get("ITEM_ID")), None)
            if not item:
                log.error("manual item not found")
                sys.exit(1)
            return item_block(item_to_article(item, lang), lang), main_keyboard(lang)
        text = os.environ.get("BROADCAST_TEXT", "").strip()
        if not text:
            log.error("empty message")
            sys.exit(1)
        return text[:MAX_LEN], None

    sent = failed = 0
    for cid, lang in to:
        text, kb = message_for(lang)
        if send_html(token, cid, text, kb):
            sent += 1
        else:
            failed += 1
        time.sleep(0.1)
    log.info("kind=%s audience=%s lang=%s -> sent=%d failed=%d", kind, audience, lang_filter, sent, failed)
    write_log({"at": datetime.now(timezone.utc).isoformat(), "kind": kind, "audience": audience,
               "lang": lang_filter, "sent": sent, "failed": failed,
               "preview": (os.environ.get("BROADCAST_TEXT", "") or os.environ.get("ITEM_ID", ""))[:80]})


if __name__ == "__main__":
    main()
