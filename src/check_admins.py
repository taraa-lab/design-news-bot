"""check_admins.py — report how many admins are registered (counts only, no ids)."""
import os, json
from sheets import SheetsDB

db = SheetsDB()
out = {"tab_exists": False, "admin_rows": 0, "users": len(db.get_all_users())}
try:
    rows = db._service().values().get(spreadsheetId=db.sheet_id, range="admins!A:C").execute().get("values", [])
    out["tab_exists"], out["admin_rows"] = True, max(0, len(rows) - 1)
except Exception as e:
    out["error"] = type(e).__name__ + ": " + str(e)[:120]
os.makedirs("../data", exist_ok=True)
json.dump(out, open("../data/admins_status.json", "w"), indent=2)
print(out)
