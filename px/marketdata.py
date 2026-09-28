"""Market data: yfinance (daily bars) with Finnhub /quote as live-price fallback.

Rules (Roy 2026-09-28: never show wrong data):
- One Yahoo history request per ticker per process: every history is fetched once with the longest
  period any job needs ("2y") and sliced for shorter periods (engine 1y and scan 2y share it).
- quote() takes the live price from that same daily history (today's in-progress bar = latest price);
  no second Yahoo request (the old fast_info path re-downloaded 1y of prices).
- Yahoo rate limit (YFRateLimitError / HTTP 429 / "Too Many Requests") -> stop immediately: no more
  Yahoo requests in this process, a 15-min cooldown in state/api_state.json, jobs defer (see yahoo_blocked()).
- Missing data stays missing (ok=False / None). VIX missing -> regime "UNKNOWN" (never NORMAL).
"""
import datetime as dt
import time

from . import apistate, clock
from .config import load_settings, network_off

_hist_cache = {}
_live_cache = {}
_state = {"yahoo_limited": False}
FETCH_PERIOD = "2y"
YAHOO_COOLDOWN_S = 15 * 60
_PERIOD_DAYS = {"5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731}


def _yf():
    import yfinance as yf  # imported lazily so offline tests don't need network
    return yf


def _is_rate_limit(e):
    name = type(e).__name__
    txt = str(e)
    return name == "YFRateLimitError" or "Too Many Requests" in txt or "429" in txt.split(":")[0] or "Rate limited" in txt


def yahoo_blocked():
    """True if Yahoo rate-limited us in this process or within the cooldown window (any process)."""
    if _state["yahoo_limited"]:
        return True
    try:
        return apistate.in_cooldown("yahoo")
    except Exception:
        return False


def _mark_yahoo_limited(ticker):
    _state["yahoo_limited"] = True
    print(f"[marketdata] Yahoo rate limit hit at {ticker}: stopping Yahoo requests (cooldown {YAHOO_COOLDOWN_S // 60} min)")
    try:
        apistate.set_cooldown("yahoo", time.time() + YAHOO_COOLDOWN_S, f"rate limit at {ticker}")
        apistate.count("yahoo_429")
    except Exception:
        pass


def _slice(df, period):
    days = _PERIOD_DAYS.get(period)
    if df is None or not days or not len(df):
        return df
    cutoff = df.index[-1] - dt.timedelta(days=days)
    return df[df.index > cutoff]


def history(ticker, period=None, retries=2):
    """Daily OHLCV (completed bars + today's in-progress bar) or None. One request per ticker per process."""
    period = period or load_settings()["indicators"]["history_period"]
    if ticker in _hist_cache:
        return _slice(_hist_cache[ticker], period)
    if network_off() or yahoo_blocked():
        return None
    last_err = None
    for i in range(retries):
        try:
            df = _yf().Ticker(ticker).history(period=FETCH_PERIOD, interval="1d", auto_adjust=False)
            if df is not None and len(df):
                _hist_cache[ticker] = df
                return _slice(df, period)
        except Exception as e:  # network / rate limit
            last_err = e
            if _is_rate_limit(e):
                _mark_yahoo_limited(ticker)
                break
        if i < retries - 1:  # no sleep after the final attempt
            time.sleep(1.5)
    _hist_cache[ticker] = None
    if last_err:
        print(f"[marketdata] history failed {ticker}: {type(last_err).__name__}")
    else:
        print(f"[marketdata] history empty {ticker}")
    return None


def finnhub_quote(ticker, max_age_s=None):
    """Finnhub /quote -> {"price", "prev_close", "change_pct", ...} or None (errors are logged in px.finnhub)."""
    if network_off():
        return None
    from . import finnhub
    q, err = finnhub.quote(ticker, max_age_s=max_age_s)
    if q is None and err and "not supported" not in err:
        print(f"[marketdata] finnhub quote {ticker} unavailable: {err}")
    return q


def quote(ticker, now=None):
    """Live-ish quote: {ticker, price, prev_close, change_pct, source, ok, stale, at}.

    - today's bar present (session open or closed today): price = today's close/in-progress price, prev = yesterday.
    - market open but Yahoo has no bar for today yet: Finnhub /quote (fresh <= 20 min); else ok=False (no stale price).
    - market closed (weekend / holiday / pre-market): last completed session: price = last close, prev = the one before
      (change_pct = that session's move; `session_date` tells which session).
    Sanity check: a move > rules.max_price_sanity_jump_pct vs prev close marks the quote invalid."""
    if ticker in _live_cache:
        return _live_cache[ticker]
    now_et = clock.to_et(now) if now else clock.now_et()
    today = now_et.date()
    price = prev = None
    source, session = None, None
    df = history(ticker)
    closes = df["Close"].dropna() if df is not None and len(df) else None
    if closes is not None and len(closes):
        last_date = closes.index[-1].date()
        if last_date == today and len(closes) >= 2:
            price, prev, source, session = float(closes.iloc[-1]), float(closes.iloc[-2]), "yfinance", today
        elif last_date < today and not clock.market_is_open(now_et):
            price = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
            source, session = "yfinance(last session)", last_date
        elif last_date < today:  # market open, no bar for today yet -> need a live source
            prev = float(closes.iloc[-1])
    if price is None:
        fq = finnhub_quote(ticker, max_age_s=20 * 60 if clock.market_is_open(now_et) else None)
        if fq:
            price, source, session = fq["price"], "finnhub", today
            prev = fq.get("prev_close") or prev
    ok = price is not None and price > 0
    chg = (price / prev - 1) * 100 if ok and prev else None
    jump = load_settings()["rules"]["max_price_sanity_jump_pct"]
    if ok and chg is not None and abs(chg) > jump:
        ok = False
        source = f"{source}(rejected:{chg:+.0f}%)"
    q = {"ticker": ticker, "price": round(price, 4) if price else None, "prev_close": round(prev, 4) if prev else None,
         "change_pct": round(chg, 2) if chg is not None else None, "source": source, "ok": ok,
         "session_date": session.isoformat() if session else None,
         "at": clock.now_hkt().isoformat(timespec="seconds")}
    _live_cache[ticker] = q
    return q


def vix():
    """VIX level or None (Yahoo ^VIX only: Finnhub's free plan has no index quotes; no proxy is substituted)."""
    q = quote("^VIX")
    return q["price"] if q.get("ok") and q.get("price") else None


def regime_for(vix_value):
    """NORMAL / CAUTION / DEFENSIVE from VIX; "UNKNOWN" when VIX is missing (never pretend NORMAL)."""
    regs = load_settings()["regimes"]
    if vix_value is None:
        return "UNKNOWN"
    for name in ("NORMAL", "CAUTION", "DEFENSIVE"):
        if vix_value < regs[name]["vix_max"]:
            return name
    return "DEFENSIVE"


def fx_usdhkd():
    """Live USD/HKD from Yahoo (HKD=X) if sane, else the configured peg rate (settings.account.fx_fallback_usdhkd).
    Use fx_info() when the caller must label an estimate."""
    return fx_info()["rate"]


def fx_info():
    q = quote(load_settings()["universe"]["fx"])
    if q.get("ok") and q.get("price") and 7.0 < q["price"] < 8.5:
        return {"rate": round(q["price"], 4), "live": True}
    return {"rate": load_settings()["account"]["fx_fallback_usdhkd"], "live": False}


def clear_cache():
    _hist_cache.clear()
    _live_cache.clear()
    _state["yahoo_limited"] = False


def return_since(ticker, date_str):
    """% return of `ticker` from the last completed close BEFORE date_str (YYYY-MM-DD) to the live price.
    None if data is missing (callers just omit the comparison)."""
    try:
        d0 = dt.date.fromisoformat(str(date_str))
        df = history(ticker)
        if df is None or not len(df):
            return None
        before = df[[i.date() < d0 for i in df.index]]["Close"].dropna()
        if not len(before):
            return None
        base = float(before.iloc[-1])
        q = quote(ticker)
        if not q.get("ok"):
            return None
        return round((float(q["price"]) / base - 1) * 100, 2)
    except Exception:
        return None
