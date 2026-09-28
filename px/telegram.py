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


def send_photo(path, caption="", dry_run=None, label=""):
    """Send a PNG/JPG to the configured chat (group ids like -100... work the same). Returns (ok, id|error)."""
    dry = is_dry_run() if dry_run is None else dry_run
    if dry or telegram_disabled():
        print(f"----- [{'DRY-RUN' if dry else 'TELEGRAM-DISABLED'}] Telegram photo {label}: {path} ({len(caption)} chars caption) -----")
        return True, ["DRY-RUN"]
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat = get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False, "Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)"
    res = None
    for wait in (0, 3, 8):
        if wait:
            time.sleep(wait)
        try:
            with open(path, "rb") as f:
                r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                                  data={"chat_id": chat, "caption": caption[:1000], "parse_mode": "HTML"},
                                  files={"photo": (path.split("/")[-1], f, "image/png")}, timeout=30)
            d = r.json()
            if d.get("ok"):
                return True, [d.get("result", {}).get("message_id")]
            res = d.get("description", f"HTTP {r.status_code}")
            if r.status_code in (400, 401, 403):
                break
        except Exception as e:
            res = f"{type(e).__name__}: {_redact(e)}"
    return False, _redact(res)


def get_me():
    """Bot identity for cutover checks (username only; token never printed)."""
    token = get_secret("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    try:
        d = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15).json()
        r = d.get("result") or {}
        return {"ok": d.get("ok"), "username": r.get("username"), "id": r.get("id"), "name": r.get("first_name")}
    except Exception as e:
        return {"ok": False, "error": _redact(e)}


def get_chat():
    """Chat type/title of TELEGRAM_CHAT_ID (e.g. group 'Project X Nas'); id never printed."""
    token, chat = get_secret("TELEGRAM_BOT_TOKEN"), get_secret("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return None
    try:
        d = requests.get(f"https://api.telegram.org/bot{token}/getChat", params={"chat_id": chat}, timeout=15).json()
        r = d.get("result") or {}
        return {"ok": d.get("ok"), "type": r.get("type"), "title": r.get("title"), "error": None if d.get("ok") else d.get("description")}
    except Exception as e:
        return {"ok": False, "error": _redact(e)}
