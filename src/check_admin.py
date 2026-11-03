"""check_admin.py — is the admin registered in the Sheet? Writes booleans/counts only (no IDs)."""
import os, json
from datetime import datetime, timezone
from sheets import _get_service

ADMIN = os.environ.get("ADMIN_USERNAME", "widd_iran_admin").lower()
svc = _get_service()
sid = os.environ["GOOGLE_SHEET_ID"]
out = {"checked_at": datetime.now(timezone.utc).isoformat(), "admins_tab_exists": False,
       "admin_rows": 0, "admin_username_registered": False}
try:
    rows = svc.values().get(spreadsheetId=sid, range="admins!A:C").execute().get("values", [])
    out["admins_tab_exists"] = True
    out["admin_rows"] = max(0, len(rows) - 1)
    out["admin_username_registered"] = any(len(r) > 1 and str(r[1]).lower() == ADMIN for r in rows[1:])
except Exception as e:
    out["note"] = "admins tab missing or unreadable: " + str(e)[:80]
try:
    users = svc.values().get(spreadsheetId=sid, range="users!A:D").execute().get("values", [])
    out["users_rows"] = max(0, len(users) - 1)
except Exception:
    pass
print(json.dumps(out, ensure_ascii=False))
os.makedirs("../data", exist_ok=True)
json.dump(out, open("../data/admin_status.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
