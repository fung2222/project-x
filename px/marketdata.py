"""Market data via yfinance (primary) with Finnhub /quote fallback for live price.
Per-process cache so each ticker's history is fetched once per run."""
import datetime as dt
import time

import requests

from . import clock
from .config import get_secret, load_settings

_hist_cache = {}
_live_cache = {}


def _yf():
    import yfinance as yf  # imported lazily so offline tests don't need network
    return yf


def history(ticker, period=None, retries=3):
    period = period or load_settings()["indicators"]["history_period"]
    key = (ticker, period)
    if key in _hist_cache:
        return _hist_cache[key]
    last_err = None
    for i in range(retries):
        try:
            df = _yf().Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
            if df is not None and len(df):
                _hist_cache[key] = df
                return df
        except Exception as e:  # network / rate limit
            last_err = e
        time.sleep(1.5 * (i + 1))
    _hist_cache[key] = None
    if last_err:
        print(f"[marketdata] history failed {ticker}: {type(last_err).__name__}")
    return None


def finnhub_quote(ticker):
    key = get_secret("FINNHUB_API_KEY")
    if not key or ticker.startswith("^") or "=" in ticker:
        return None
    try:
        r = requests.get("https://finnhub.io/api/v1/quote", params={"symbol": ticker, "token": key}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            if d.get("c"):
                return {"price": float(d["c"]), "prev_close": float(d.get("pc") or 0) or None}
    except Exception:
        pass
    return None


def quote(ticker):
    """Live-ish quote: {price, prev_close, change_pct, source, ok}.

    prev_close = previous session's close (vs. the live price). Sanity check:
    a >max_price_sanity_jump_pct move vs prev_close marks the quote invalid.
    """
    if ticker in _live_cache:
        return _live_cache[ticker]
    price = prev = None
    source = None
    df = history(ticker)
    today_et = clock.now_et().date()
    if df is not None and len(df):
        last_date = df.index[-1].date()
        closes = df["Close"].dropna()
        if last_date == today_et and len(closes) >= 2:
            prev = float(closes.iloc[-2])
        elif len(closes):
            prev = float(closes.iloc[-1]) if last_date < today_et else float(closes.iloc[-2])
    try:
        fi = _yf().Ticker(ticker).fast_info
        lp = fi.last_price
        if lp:
            price, source = float(lp), "yfinance"
    except Exception:
        pass
    if price is None and df is not None and len(df):
        price, source = float(df["Close"].dropna().iloc[-1]), "yfinance_hist"
    if price is None:
        fq = finnhub_quote(ticker)
        if fq:
            price, source = fq["price"], "finnhub"
            prev = prev or fq.get("prev_close")
    ok = price is not None and price > 0
    chg = (price / prev - 1) * 100 if ok and prev else None
    jump = load_settings()["rules"]["max_price_sanity_jump_pct"]
    if ok and chg is not None and abs(chg) > jump:
        ok = False
        source = f"{source}(rejected:{chg:+.0f}%)"
    q = {"ticker": ticker, "price": round(price, 4) if price else None, "prev_close": round(prev, 4) if prev else None,
         "change_pct": round(chg, 2) if chg is not None else None, "source": source, "ok": ok,
         "at": clock.now_hkt().isoformat(timespec="seconds")}
    _live_cache[ticker] = q
    return q


def vix():
    q = quote("^VIX")
    return q["price"] if q.get("price") else None


def regime_for(vix_value):
    regs = load_settings()["regimes"]
    if vix_value is None:
        return "NORMAL"
    for name in ("NORMAL", "CAUTION", "DEFENSIVE"):
        if vix_value < regs[name]["vix_max"]:
            return name
    return "DEFENSIVE"


def fx_usdhkd():
    q = quote(load_settings()["universe"]["fx"])
    if q.get("price") and 7.0 < q["price"] < 8.5:
        return round(q["price"], 4)
    return load_settings()["account"]["fx_fallback_usdhkd"]


def clear_cache():
    _hist_cache.clear()
    _live_cache.clear()
