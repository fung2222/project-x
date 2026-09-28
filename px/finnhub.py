"""Finnhub REST client (free plan: 60 calls/min + 30 calls/s; HTTP 429 when exceeded).

Every call goes through get(): cooldown file respected (state/api_state.json), 429 -> cooldown until
X-Ratelimit-Reset (fallback 60 s), every failure is logged (never a silent "no data"), daily counter kept.
Returns (data, error_str). data is None on any failure."""
import time

import requests

from . import apistate
from .config import get_secret, network_off

BASE = "https://finnhub.io/api/v1/"
_last_call = [0.0]
rate = {"remaining": None, "reset": None, "at": 0.0}  # last X-Ratelimit-* headers seen (heatmap pacing)
MIN_GAP_S = 0.12  # stay far below the 30 calls/second cap


def get(path, params=None, timeout=10):
    if network_off():
        return None, "network off"
    key = get_secret("FINNHUB_API_KEY")
    if not key:
        return None, "no FINNHUB_API_KEY"
    if apistate.in_cooldown("finnhub"):
        err = f"finnhub cooldown active (until {apistate.cooldown_until('finnhub'):.0f})"
        print(f"[finnhub] skip {path}: {err}")
        return None, err
    gap = time.time() - _last_call[0]
    if gap < MIN_GAP_S:
        time.sleep(MIN_GAP_S - gap)
    p = dict(params or {})
    p["token"] = key
    try:
        _last_call[0] = time.time()
        r = requests.get(BASE + path.lstrip("/"), params=p, timeout=timeout)
    except Exception as e:
        print(f"[finnhub] {path} network error: {type(e).__name__}")
        return None, f"network {type(e).__name__}"
    try:
        apistate.count("finnhub")
    except Exception:
        pass
    if r.status_code == 429:
        try:
            reset = float(r.headers.get("X-Ratelimit-Reset") or 0)
        except ValueError:
            reset = 0
        until = reset if reset > time.time() else time.time() + 60
        apistate.set_cooldown("finnhub", min(until, time.time() + 900), "HTTP 429")
        return None, "HTTP 429 rate limited"
    if r.status_code in (401, 403):
        print(f"[finnhub] {path} HTTP {r.status_code} (key invalid or premium-only endpoint)")
        return None, f"HTTP {r.status_code}"
    if r.status_code != 200:
        print(f"[finnhub] {path} HTTP {r.status_code}")
        return None, f"HTTP {r.status_code}"
    try:
        rem = r.headers.get("X-Ratelimit-Remaining")
        if rem is not None:
            rate.update(remaining=int(rem), reset=float(r.headers.get("X-Ratelimit-Reset") or 0) or None, at=time.time())
        if rem is not None and int(rem) <= 2:  # about to hit the per-minute cap: pause until reset
            reset = float(r.headers.get("X-Ratelimit-Reset") or 0)
            if reset > time.time():
                apistate.set_cooldown("finnhub", min(reset, time.time() + 90), f"remaining={rem}")
    except Exception:
        pass
    try:
        return r.json(), None
    except Exception:
        print(f"[finnhub] {path} bad JSON")
        return None, "bad JSON"


def quote(symbol, max_age_s=None, now_ts=None):
    """{price, prev_close, change_pct, high, low, open, t, source} or (None, err).
    max_age_s: reject quotes whose timestamp `t` is older (stale) — used during the regular session."""
    if not symbol or symbol.startswith("^") or "=" in symbol:
        return None, "symbol not supported on Finnhub free plan"
    d, err = get("quote", {"symbol": symbol})
    if d is None:
        return None, err
    c = d.get("c")
    if not c:
        return None, "empty quote (c=0)"
    t = d.get("t") or 0
    if max_age_s is not None and t and (now_ts or time.time()) - float(t) > max_age_s:
        return None, f"stale quote ({int(((now_ts or time.time()) - float(t)) / 60)} min old)"
    pc = float(d.get("pc") or 0) or None
    chg = d.get("dp")
    if chg is None and pc:
        chg = (float(c) / pc - 1) * 100
    return {"price": float(c), "prev_close": pc, "change_pct": float(chg) if chg is not None else None,
            "high": d.get("h"), "low": d.get("l"), "open": d.get("o"), "t": t, "source": "finnhub"}, None
