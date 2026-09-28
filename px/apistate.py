"""Small persistent API state: per-provider cooldowns (after HTTP 429 / rate limits) and daily call counters.

state/api_state.json
  {"cooldown": {"finnhub": <epoch>, "yahoo": <epoch>},
   "counts": {"<YYYY-MM-DD HKT>": {"finnhub": n, "marketaux": n, "yahoo_429": n}}}
Counters are informational except where a hard budget is enforced (Marketaux: settings.api_budget)."""
import datetime as dt
import json
import os
import tempfile
import time

from . import clock
from .config import STATE_DIR

PATH_NAME = "api_state.json"


def _path():
    return os.path.join(STATE_DIR, PATH_NAME)


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    cutoff = (clock.now_hkt().date() - dt.timedelta(days=10)).isoformat()
    d["counts"] = {k: v for k, v in (d.get("counts") or {}).items() if k >= cutoff}
    fd, tmp = tempfile.mkstemp(prefix=".api_state.", dir=STATE_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path())


def cooldown_until(provider):
    return float((load().get("cooldown") or {}).get(provider) or 0)


def in_cooldown(provider, now_ts=None):
    return (now_ts or time.time()) < cooldown_until(provider)


def set_cooldown(provider, until_ts, reason=""):
    d = load()
    d.setdefault("cooldown", {})[provider] = float(until_ts)
    d.setdefault("cooldown_reason", {})[provider] = f"{reason} @ {clock.now_hkt().isoformat(timespec='seconds')}"
    save(d)
    print(f"[api] {provider} cooldown until {dt.datetime.fromtimestamp(until_ts, clock.HKT):%H:%M:%S} HKT ({reason})")


def today_key():
    return clock.now_hkt().date().isoformat()


def count(provider, n=1):
    d = load()
    day = d.setdefault("counts", {}).setdefault(today_key(), {})
    day[provider] = int(day.get(provider, 0)) + n
    save(d)
    return day[provider]


def used_today(provider):
    return int(((load().get("counts") or {}).get(today_key()) or {}).get(provider, 0))
