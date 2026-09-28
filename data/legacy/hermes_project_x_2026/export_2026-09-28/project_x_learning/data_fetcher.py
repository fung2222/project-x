"""data_fetcher.py - 真實數據獲取 + 驗證"""
import yfinance as yf
import requests
import pandas as pd
from datetime import datetime, timedelta
import time

WATCH_LIST = ["NVDA", "TSLA", "RKLB"]
WATCH_SECONDARY = ["AMD", "MSFT"]
BENCHMARK = ["SPY"]
FINNHUB_API_KEY = None  # PHASE 1 暫用 yfinance


def safe_request(url, retries=3, timeout=10):
    for i in range(retries):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 429:
                time.sleep(2 ** i)
                continue
            if r.status_code == 200:
                return r
        except requests.exceptions.RequestException:
            time.sleep(1)
    return None


def get_verified_quote(ticker):
    try:
        s = yf.Ticker(ticker)
        # 10d buffer: yfinance sometimes appends an empty/NaN session row
        h = s.history(period="10d")
        if h.empty:
            return None
        h = h.dropna(subset=["Close"])
        if h.empty:
            return None
        price = float(h["Close"].iloc[-1])
        prev = float(h["Close"].iloc[-2]) if len(h) >= 2 else price
        vol_raw = h["Volume"].iloc[-1]
        volume = int(vol_raw) if pd.notna(vol_raw) else 0
        if prev == 0:
            return None
        return {
            "ticker": ticker,
            "price": round(price, 2),
            "prev_close": round(prev, 2),
            "change_pct": round((price - prev) / prev * 100, 2),
            "volume": volume,
            "verified": True,
            "source": "yfinance",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"[ERR] {ticker}: {e}")
        return None


def get_indicators(ticker, period="6mo"):
    try:
        s = yf.Ticker(ticker)
        h = s.history(period=period)
        if h.empty:
            return None
        closes = h['Close'].dropna()
        current = float(closes.iloc[-1])
        ma50 = float(closes.rolling(50).mean().iloc[-1])
        ma20 = float(closes.rolling(20).mean().iloc[-1])

        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        rsi_now = float(rsi.iloc[-1])

        # align volume to last valid close row (avoid empty session NaN bar)
        h_valid = h.dropna(subset=["Close"])
        vol_today = float(h_valid["Volume"].iloc[-1]) if not h_valid.empty else 0.0
        vol_avg20 = float(h_valid["Volume"].rolling(20).mean().iloc[-1]) if len(h_valid) >= 20 else vol_today
        vol_ratio = vol_today / vol_avg20 if vol_avg20 > 0 else 1

        # 5日/20日動能
        chg_5d = 0.0
        chg_20d = 0.0
        if len(closes) >= 6:
            chg_5d = (current / float(closes.iloc[-6]) - 1) * 100
        if len(closes) >= 21:
            chg_20d = (current / float(closes.iloc[-21]) - 1) * 100
        ma20_vs_ma50 = (ma20 - ma50) / ma50 * 100 if ma50 else 0

        return {
            "price": round(current, 2),
            "ma50": round(ma50, 2),
            "ma20": round(ma20, 2),
            "price_vs_ma50_pct": round((current - ma50) / ma50 * 100, 2),
            "price_vs_ma20_pct": round((current - ma20) / ma20 * 100, 2),
            "ma20_vs_ma50_pct": round(ma20_vs_ma50, 2),
            "chg_5d_pct": round(chg_5d, 2),
            "chg_20d_pct": round(chg_20d, 2),
            "rsi14": round(rsi_now, 1),
            "volume_ratio": round(vol_ratio, 2),
            "trend": "高於" if current > ma50 else "低於",
            "rsi_zone": (
                "超賣 (<35)" if rsi_now < 35
                else "超買 (>65)" if rsi_now > 65
                else "中性"
            )
        }
    except Exception as e:
        print(f"[ERR] indicators {ticker}: {e}")
        return None


def get_vix():
    try:
        v = yf.Ticker("^VIX")
        h = v.history(period="5d")
        if h.empty:
            return 20.0
        return round(float(h['Close'].iloc[-1]), 2)
    except:
        return 20.0


def get_fx_usdhkd():
    try:
        f = yf.Ticker("USDHKD=X")
        h = f.history(period="5d")
        if h.empty:
            return 7.80
        return round(float(h['Close'].iloc[-1]), 4)
    except:
        return 7.80


def get_spy():
    q = get_verified_quote("SPY")
    return q['price'] if q else None