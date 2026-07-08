"""
sheets.py — Google Sheets as user database.
Each row: chat_id | name | lang | interests | created_at
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_NAME = "users"
HEADER = ["chat_id", "name", "lang", "interests", "created_at", "updated_at"]


def _get_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON env var not set")

    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds).spreadsheets()


class SheetsDB:
    def __init__(self):
        self.sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
        self._svc = None

    def _service(self):
        if not self._svc:
            self._svc = _get_service()
        return self._svc

    def _get_all_rows(self):
        try:
            result = self._service().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{SHEET_NAME}!A:F"
            ).execute()
            return result.get("values", [])
        except Exception as e:
            logger.error("Sheets read error: %s", e)
            return []

    def _ensure_header(self):
        rows = self._get_all_rows()
        if not rows or rows[0] != HEADER:
            self._service().values().update(
                spreadsheetId=self.sheet_id,
                range=f"{SHEET_NAME}!A1",
                valueInputOption="RAW",
                body={"values": [HEADER]}
            ).execute()

    def get_all_users(self) -> list[dict]:
        rows = self._get_all_rows()
        if not rows or len(rows) < 2:
            return []
        header = rows[0]
        return [dict(zip(header, row)) for row in rows[1:] if row]

    def get_user(self, chat_id: str) -> dict | None:
        for user in self.get_all_users():
            if user.get("chat_id") == str(chat_id):
                return user
        return None

    def save_user(self, chat_id: str, name: str, lang: str, interests: str):
        self._ensure_header()
        now = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)).strftime("%Y-%m-%d %H:%M")
        rows = self._get_all_rows()

        # Find existing row
        for i, row in enumerate(rows[1:], start=2):
            if row and row[0] == str(chat_id):
                # Update existing
                self._service().values().update(
                    spreadsheetId=self.sheet_id,
                    range=f"{SHEET_NAME}!A{i}:F{i}",
                    valueInputOption="RAW",
                    body={"values": [[chat_id, name, lang, interests, row[4] if len(row)>4 else now, now]]}
                ).execute()
                logger.info("Updated user %s", chat_id)
                return

        # Append new
        created = now
        self._service().values().append(
            spreadsheetId=self.sheet_id,
            range=f"{SHEET_NAME}!A:F",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [[chat_id, name, lang, interests, created, now]]}
        ).execute()
        logger.info("New user %s saved", chat_id)
