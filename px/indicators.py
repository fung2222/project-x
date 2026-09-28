"""Technical indicators on COMPLETED daily bars (pure pandas; unit-tested).

Fixes vs. the old finnhub_api.get_tech_indicators:
- >= 1y of daily history (min 120 bars) so MA20/MA50/MACD are real
- Wilder RSI(14) and Wilder ATR(14)
- MACD 12/26/9 on full series (no degenerate fallback)
- volume ratio = last COMPLETED bar volume / previous 20-bar average
- the in-progress bar of today's session is dropped before computing
"""
import datetime as dt
import math

import pandas as pd

from . import clock


def drop_incomplete_bar(df, now=None):
    """Drop today's still-forming daily bar (ET session not yet closed)."""
    if df is None or len(df) == 0:
        return df
    now_et = clock.to_et(now or clock.now_et())
    last = df.index[-1]
    last_date = last.date() if hasattr(last, "date") else pd.Timestamp(last).date()
    if last_date == now_et.date() and not clock.session_closed(now_et):
        return df.iloc[:-1]
    return df


def wilder_rsi(closes, period=14):
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.where(avg_loss != 0, 100.0)
    return rsi


def wilder_atr(high, low, close, period=14):
    prev = close.shift(1)
    tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def macd(closes, fast=12, slow=26, signal=9):
    ema_f = closes.ewm(span=fast, adjust=False).mean()
    ema_s = closes.ewm(span=slow, adjust=False).mean()
    line = ema_f - ema_s
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def _r(x, n=2):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return round(float(x), n)
    except Exception:
        return None


def trend_score(price, ma20, ma50, rsi, chg5):
    s = 0
    if ma50:
        p50 = (price - ma50) / ma50 * 100
        s += 2 if p50 > 0 else (-1 if p50 >= -10 else -2)
    if ma20:
        s += 1 if price > ma20 else -1
    if ma20 and ma50:
        m = (ma20 - ma50) / ma50 * 100
        s += 1 if m > 1 else (-1 if m < -1 else 0)
    if rsi is not None:
        s += 1 if 50 <= rsi <= 70 else (-1 if rsi < 35 else 0)
    if chg5 is not None:
        s += 1 if chg5 > 3 else (-1 if chg5 < -3 else 0)
    return s


def trend_label(score):
    if score >= 3:
        return "上升趨勢"
    if score <= -3:
        return "下降趨勢"
    return "中性震盪"


def compute(df, now=None, min_bars=120):
    """Compute indicators from a daily OHLCV DataFrame (index = dates).

    Returns dict (with key "error" if not enough data).
    """
    if df is None or len(df) == 0:
        return {"error": "no data"}
    df = drop_incomplete_bar(df, now)
    df = df.dropna(subset=["Close"])
    if len(df) < min_bars:
        return {"error": f"only {len(df)} completed bars (< {min_bars})", "bars": len(df)}
    c, h, l = df["Close"].astype(float), df["High"].astype(float), df["Low"].astype(float)
    v = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series([0.0] * len(df), index=df.index)

    rsi_s = wilder_rsi(c)
    atr_s = wilder_atr(h, l, c)
    m_line, m_sig, m_hist = macd(c)
    price = float(c.iloc[-1])
    ma20 = float(c.iloc[-20:].mean())
    ma50 = float(c.iloc[-50:].mean())
    ma200 = float(c.iloc[-200:].mean()) if len(c) >= 200 else None
    prev_vol_avg = float(v.iloc[-21:-1].mean()) if len(v) >= 21 else float(v.iloc[:-1].mean() or 0)
    vol_ratio = float(v.iloc[-1]) / prev_vol_avg if prev_vol_avg > 0 else None
    chg1 = (price / float(c.iloc[-2]) - 1) * 100 if len(c) >= 2 else 0.0
    chg5 = (price / float(c.iloc[-6]) - 1) * 100 if len(c) >= 6 else None
    chg20 = (price / float(c.iloc[-21]) - 1) * 100 if len(c) >= 21 else None
    rsi = float(rsi_s.iloc[-1])
    hist = float(m_hist.iloc[-1])
    hist_prev = float(m_hist.iloc[-2])
    ts = trend_score(price, ma20, ma50, rsi, chg5)
    last_idx = df.index[-1]
    return {
        "bar_date": str(last_idx.date() if hasattr(last_idx, "date") else last_idx),
        "bars": int(len(df)),
        "close": _r(price, 4),
        "prev_close": _r(c.iloc[-2], 4),
        "change_pct": _r(chg1),
        "rsi14": _r(rsi, 1),
        "ma20": _r(ma20),
        "ma50": _r(ma50),
        "ma200": _r(ma200),
        "price_vs_ma20_pct": _r((price - ma20) / ma20 * 100),
        "price_vs_ma50_pct": _r((price - ma50) / ma50 * 100),
        "ma20_vs_ma50_pct": _r((ma20 - ma50) / ma50 * 100),
        "macd": _r(m_line.iloc[-1], 4),
        "macd_signal": _r(m_sig.iloc[-1], 4),
        "macd_hist": _r(hist, 4),
        "hist_rising": bool(hist > hist_prev),
        "atr14": _r(atr_s.iloc[-1], 4),
        "vol_ratio": _r(vol_ratio),
        "vol_last": int(v.iloc[-1]) if not math.isnan(float(v.iloc[-1])) else None,
        "chg_5d_pct": _r(chg5),
        "chg_20d_pct": _r(chg20),
        "trend_score": ts,
        "trend_label": trend_label(ts),
        "up_day": bool(chg1 > 0),
    }
