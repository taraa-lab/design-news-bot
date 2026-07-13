"""debug_dump.py — dump all sheet users as JSON for inspection."""
from sheets import SheetsDB
import json

db = SheetsDB()
users = db.get_all_users()
print("=== SHEET USERS ===")
print(json.dumps(users, ensure_ascii=False, indent=2))
with open("../sheet_dump.json", "w", encoding="utf-8") as f:
    json.dump(users, f, ensure_ascii=False, indent=2)
