"""
deliver.py — Send the daily digest via Telegram and/or Gmail.
"""

import os
import smtplib
import logging
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text   import MIMEText
from email.mime.base   import MIMEBase
from email             import encoders

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Telegram
# ──────────────────────────────────────────────

def send_telegram_message(text: str) -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("Telegram credentials not set — skipping")
        return False

    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }, timeout=30)

    if resp.ok:
        logger.info("Telegram message sent ✓")
        return True
    logger.error("Telegram send failed: %s", resp.text)
    return False


def send_telegram_document(file_path: str, caption: str = "") -> bool:
    """Send the full Markdown report as a file attachment."""
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, "rb") as f:
        resp = requests.post(url, data={
            "chat_id": chat_id,
            "caption": caption[:1024],
            "parse_mode": "Markdown",
        }, files={"document": f}, timeout=60)

    if resp.ok:
        logger.info("Telegram document sent ✓")
        return True
    logger.error("Telegram doc failed: %s", resp.text)
    return False


# ──────────────────────────────────────────────
# Gmail (via SMTP with App Password)
# ──────────────────────────────────────────────

def _markdown_to_simple_html(md: str) -> str:
    """Very lightweight Markdown → HTML conversion (no library needed)."""
    import re
    html = md
    html = re.sub(r"^# (.+)$",    r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$",   r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$",  r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)
    html = re.sub(r"^---$", r"<hr>", html, flags=re.MULTILINE)
    html = html.replace("\n\n", "</p><p>")
    return f"<html><body style='font-family:sans-serif;max-width:720px;margin:auto'><p>{html}</p></body></html>"


def send_gmail(subject: str, markdown_body: str, attachment_path: str = "") -> bool:
    smtp_user = os.environ.get("GMAIL_USER", "")
    smtp_pass = os.environ.get("GMAIL_APP_PASSWORD", "")
    to_addr   = os.environ.get("GMAIL_TO", smtp_user)

    if not smtp_user or not smtp_pass:
        logger.warning("Gmail credentials not set — skipping")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = to_addr

    msg.attach(MIMEText(markdown_body, "plain", "utf-8"))
    msg.attach(MIMEText(_markdown_to_simple_html(markdown_body), "html", "utf-8"))

    if attachment_path and os.path.exists(attachment_path):
        outer = MIMEMultipart("mixed")
        outer["Subject"] = msg["Subject"]
        outer["From"]    = msg["From"]
        outer["To"]      = msg["To"]
        outer.attach(msg)

        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        fname = os.path.basename(attachment_path)
        part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
        outer.attach(part)
        msg = outer

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_addr, msg.as_string())
        logger.info("Gmail sent ✓")
        return True
    except Exception as e:
        logger.error("Gmail error: %s", e)
        return False
