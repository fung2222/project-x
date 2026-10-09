"""Company fundamentals for the opportunity scan (rule-based, NO LLM).

Fetches yfinance .info for a ticker at most once per day (cached 24h in
state/fundamental_cache.json). Never raises: a failed/rate-limited fetch returns
{} and the caller just omits those lines. Fields: revenue, net income (negative =
loss), gross margin, market cap, and P/S (price-to-sales).

Why a separate cache: fundamentals barely change intra-day, but .info is an extra
Yahoo request per ticker. Caching 24h keeps the daily scan to a handful of extra
calls instead of re-fetching every job.
"""
import json
import os
import time

from .config import STATE_DIR, network_off

CACHE_NAME = "fundamental_cache.json"
CACHE_HOURS = 24


def _cpath():
    return os.path.join(STATE_DIR, CACHE_NAME)


def _load():
    try:
        with open(_cpath(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _cpath() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, _cpath())
    except Exception as e:
        print(f"[fundamental] cache write failed: {type(e).__name__}")


def _num(x):
    """None-safe float; returns None for None/NaN/0-like-invalid."""
    try:
        if x is None:
            return None
        v = float(x)
        if v != v:  # NaN
            return None
        return v
    except Exception:
        return None


def _fetch_yf(ticker):
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception as e:
        print(f"[fundamental] {ticker} info failed: {type(e).__name__}")
        return {}
    rev = _num(info.get("totalRevenue"))
    ni = _num(info.get("netIncomeToCommon"))
    mc = _num(info.get("marketCap"))
    gm = _num(info.get("grossMargins"))
    rg = _num(info.get("revenueGrowth"))
    ps = (mc / rev) if (mc and rev) else None
    return {
        "revenue_usd": rev,
        "revenue_growth": rg,  # fraction (0.15 = +15%) or None
        "net_income_usd": ni,
        "gross_margin": gm,  # fraction (0.29 = 29%) or None
        "market_cap_usd": mc,
        "ps_ratio": ps,
    }


def fetch(ticker):
    """Fundamental dict for `ticker` (cached 24h). {} when unavailable."""
    if network_off():
        return {}
    c = _load()
    e = c.get(ticker)
    if e and time.time() - float(e.get("ts", 0)) < CACHE_HOURS * 3600:
        return e.get("fund") or {}
    fund = _fetch_yf(ticker)
    c[ticker] = {"ts": time.time(), "fund": fund}
    _save(c)
    return fund
