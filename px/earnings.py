"""Earnings calendar with a once-per-day cache (Roy: real dates, never guessed).

Finnhub's free /calendar/earnings returns at most 1500 rows per query: a single 60-day query silently drops
the nearest weeks (verified 2026-09-28: weeks 0-5 missing). So we query in `window_days` (7) windows over
`horizon_days` (~9 calls, once per HKT day), cache the whole US calendar in state/earnings_cache.json and
look names up locally. yfinance .calendar is only a fallback for names Finnhub doesn't list (cached too).

lookup(tickers) -> {ticker: {"date": "YYYY-MM-DD" | None, "source": "finnhub"|"yfinance"|None, "known": bool}}
A name with known=False is shown as 業績日未知; where the blackout rule applies it is treated conservatively
(settings.earnings.unknown_blocks_entry: no new scan entry)."""
import datetime as dt
import json
import os
import tempfile

from . import clock
from .config import STATE_DIR, load_settings, network_off

CACHE_NAME = "earnings_cache.json"


def cfg():
    c = {"horizon_days": 63, "window_days": 7, "unknown_blocks_entry": True}
    c.update({k: v for k, v in load_settings().get("earnings", {}).items() if not k.startswith("_")})
    return c


def _path():
    return os.path.join(STATE_DIR, CACHE_NAME)


def _load():
    try:
        with open(_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".earnings.", dir=STATE_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, _path())


def _query(start, stop):
    from . import finnhub
    d, err = finnhub.get("calendar/earnings", {"from": start.isoformat(), "to": stop.isoformat()}, timeout=20)
    if d is None:
        print(f"[earnings] finnhub window {start}..{stop} failed: {err}")
        return None
    return d.get("earningsCalendar") or []


def _fetch_finnhub(today, horizon, window):
    """{symbol: earliest date >= today} over the horizon in `window`-day chunks; a chunk that hits the
    1500-row cap is re-queried day by day. Returns (calendar, complete_bool)."""
    cal, complete = {}, True
    start, end = today, today + dt.timedelta(days=horizon)

    def add(rows):
        for e in rows:
            sym, day = e.get("symbol"), e.get("date")
            if sym and day and day >= today.isoformat() and (sym not in cal or day < cal[sym]):
                cal[sym] = day

    while start <= end:
        stop = min(start + dt.timedelta(days=window - 1), end)
        rows = _query(start, stop)
        if rows is None:
            complete = False
        elif len(rows) >= 1500 and stop > start:
            day = start
            while day <= stop:
                r1 = _query(day, day)
                if r1 is None or len(r1) >= 1500:
                    complete = False
                add(r1 or [])
                day += dt.timedelta(days=1)
        else:
            if len(rows) >= 1500:
                complete = False
            add(rows)
        start = stop + dt.timedelta(days=1)
    return cal, complete


def _yf_date(ticker, today, horizon):
    import yfinance as yf
    cal = yf.Ticker(ticker).calendar
    ds = cal.get("Earnings Date") if isinstance(cal, dict) else None
    if not ds:
        return None
    fut = sorted(d for d in ds if d >= today)
    if fut and (fut[0] - today).days <= horizon:
        return fut[0].isoformat()
    return None


def lookup(tickers, today=None, refresh=False):
    c = cfg()
    today = today or clock.now_et().date()
    key = clock.now_hkt().date().isoformat()
    d = _load()
    if d.get("day") != key or refresh:
        d = {"day": key, "today_et": today.isoformat(), "finnhub": {}, "finnhub_ok": False, "yf": {}, "yf_tried": []}
        if not network_off():
            cal, complete = _fetch_finnhub(today, int(c["horizon_days"]), int(c["window_days"]))
            d["finnhub"], d["finnhub_ok"] = cal, bool(cal) and complete
        _save(d)
    out, dirty = {}, False
    for t in tickers:
        if t in d["finnhub"]:
            out[t] = {"date": d["finnhub"][t], "source": "finnhub", "known": True}
            continue
        if t in d["yf"]:
            v = d["yf"][t]
            out[t] = {"date": v, "source": "yfinance" if v else None, "known": bool(v) or d.get("finnhub_ok", False)}
            continue
        if t not in d["yf_tried"] and not network_off():
            v = None
            try:
                from . import marketdata
                if not marketdata.yahoo_blocked():
                    v = _yf_date(t, today, int(c["horizon_days"]))
            except Exception as e:
                print(f"[earnings] yfinance calendar {t} failed: {type(e).__name__}")
            d["yf"][t] = v
            d["yf_tried"].append(t)
            dirty = True
            out[t] = {"date": v, "source": "yfinance" if v else None,
                      # a complete Finnhub horizon that doesn't list the name = no earnings inside the horizon (known)
                      "known": bool(v) or d.get("finnhub_ok", False)}
        else:
            out[t] = {"date": None, "source": None, "known": d.get("finnhub_ok", False)}
    if dirty:
        _save(d)
    return out


def dates(tickers, today=None):
    """Back-compat {ticker: 'YYYY-MM-DD'} for names with a known upcoming date."""
    return {t: v["date"] for t, v in lookup(tickers, today).items() if v.get("date")}
