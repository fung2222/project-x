"""Telegram sender. Bot token / chat id are purely config-driven:
env TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (or local telegram_config.json fallback).
Dry-run (PX_DRY_RUN=1 or --dry-run) or PX_TELEGRAM_DISABLED=1 -> print only.
Errors are redacted so the token never appears in logs."""
import re
import time

import requests

from .config import get_secret, is_dry_run, telegram_disabled

MAX_LEN = 3500


def _redact(text):
    tok = get_secret("TELEGRAM_BOT_TOKEN")
    s = str(text)
    if tok:
        s = s.replace(tok, "<TOKEN>")
    return re.sub(r"bot\d{6,12}:[A-Za-z0-9_-]{20,}", "bot<TOKEN>", s)


def split_message(text, limit=MAX_LEN):
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            parts.append(cur)
            cur = ""
        while len(line) > limit:
            parts.append(line[:limit])
            line = line[limit:]
        cur = (cur + "\n" + line) if cur else line
    if cur:
        parts.append(cur)
    return parts


def send(text, silent=False, dry_run=None, label=""):
    """Send one logical message (auto-split). Returns (ok, [message_ids] | error)."""
    dry = is_dry_run() if dry_run is None else dry_run
    if dry or telegram_disabled():
        mode = "DRY-RUN" if dry else "TELEGRAM-DISABLED"
        print(f"----- [{mode}] Telegram {label} ({len(text)} chars) -----")
        print(text)
        print("----- end -----")
        return True, [mode]
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat = get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False, "Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)"
    ids = []
    for part in split_message(text):
        ok, res = False, None
        for wait in (0, 2, 5, 10):
            if wait:
                time.sleep(wait)
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat, "text": part, "parse_mode": "HTML",
                          "disable_web_page_preview": True, "disable_notification": bool(silent)},
                    timeout=15,
                )
                d = r.json()
                if d.get("ok"):
                    ok, res = True, d.get("result", {}).get("message_id")
                    break
                res = d.get("description", f"HTTP {r.status_code}")
                if r.status_code in (400, 401, 403):
                    break  # not retryable
            except Exception as e:
                res = f"{type(e).__name__}: {_redact(e)}"
        if not ok:
            return False, _redact(res)
        ids.append(res)
    return True, ids
