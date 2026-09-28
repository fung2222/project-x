"""
Project X — 即時持倉追蹤 (每小時 21:00-04:00 HKT)
美股交易時段自動更新持倉價格；報價失敗唔會清零 equity
"""
import json, os, sys, datetime
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finnhub_api
import risk_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_PATH = os.path.join(BASE_DIR, "portfolio.json")
PROFILES_PATH = os.path.join(BASE_DIR, "profiles.json")


def fetch_latest_quote(ticker):
    """取得實時／最近報價：Finnhub 優先，再 yfinance"""
    try:
        q = finnhub_api.get_quote(ticker)
        if isinstance(q, dict):
            price = q.get("price") or q.get("c") or q.get("current")
            if price:
                return float(price)
    except Exception:
        pass
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price:
            return float(price)
    except Exception:
        pass
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist):
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


def update_positions():
    """更新所有持倉嘅當前價格 + 重算帳戶（px ledger；報價失敗保留舊價）。
    Mark-to-market only — SL/TP execution happens in run.py open/hourly/daily."""
    from px import ledger, marketdata
    pf = ledger.load()
    positions = pf.get("positions", [])
    if not positions:
        ledger.recompute(pf)
        ledger.save(pf)
        print(f"[{datetime.datetime.now()}] 無持倉，跳過")
        return
    prices, updates = {}, []
    for pos in positions:
        q = marketdata.quote(pos["ticker"])
        if q.get("ok"):
            prices[pos["ticker"]] = q["price"]
    ledger.mark(pf, prices)
    acct = ledger.recompute(pf)
    for pos in pf["positions"]:
        updates.append(f"{pos['ticker']} ${float(pos.get('current_price') or 0):.2f} ({pos['pnl_pct']:+.2f}%)")
    if not prices:
        print(f"[{datetime.datetime.now()}] 報價失敗，保留舊價；權益 ${acct['equity_usd']:.2f}")
    pf["last_tracker_update"] = datetime.datetime.now().isoformat()
    ledger.save(pf)
    print(f"[{datetime.datetime.now()}] 更新 {len(positions)} 持倉: {' '.join(updates)}")


if __name__ == "__main__":
    update_positions()
