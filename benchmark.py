"""
Project X — 基準對比
計算你嘅模擬組合 vs SPY 同時段回報
"""
import json, os, datetime
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_spy_return_since(start_date):
    """SPY 由開始日期到今日嘅回報率"""
    try:
        spy = yf.Ticker("SPY")
        # 用 5d 而唔係 start_date，避免同日問題
        hist = spy.history(period="5d")
        if hist.empty or len(hist) < 2:
            return None
        start_price = float(hist["Close"].iloc[0])
        end_price = float(hist["Close"].iloc[-1])
        return round((end_price - start_price) / start_price * 100, 2)
    except Exception:
        return None


def calculate_portfolio_return():
    """計算組合總回報（vs start_equity_usd in config/settings.json, HKD 10k book）"""
    import sys
    sys.path.insert(0, BASE_DIR)
    from px import config as _pxconfig
    portfolio_path = os.path.join(BASE_DIR, "portfolio.json")
    with open(portfolio_path, encoding="utf-8") as f:
        pf = json.load(f)
    account = pf.get("account", {})
    initial = float(_pxconfig.load_settings()["account"]["start_equity_usd"])
    current = account.get("equity_usd", initial)
    return round((current - initial) / initial * 100, 2), current


def benchmark_comparison():
    """組合 vs SPY 比較"""
    portfolio_path = os.path.join(BASE_DIR, "portfolio.json")
    with open(portfolio_path, encoding="utf-8") as f:
        pf = json.load(f)
    start_date = pf.get("account", {}).get("rebase_date", "2026-09-13")
    portfolio_return, equity = calculate_portfolio_return()
    try:
        import sys
        sys.path.insert(0, BASE_DIR)
        from px.jobs.daily import spy_return_since_rebase
        spy_return = spy_return_since_rebase()
    except Exception:
        spy_return = get_spy_return_since(start_date)
    alpha = round(portfolio_return - spy_return, 2) if spy_return is not None else None
    verdict = "✅ 跑贏大市" if alpha and alpha > 0 else "❌ 跑輸大市" if alpha else "無法比較"
    return {
        "start_date": start_date,
        "portfolio_return_pct": portfolio_return,
        "spy_return_pct": spy_return,
        "alpha": alpha,
        "verdict": verdict,
        "current_equity_usd": equity
    }


if __name__ == "__main__":
    res = benchmark_comparison()
    print(json.dumps(res, ensure_ascii=False, indent=2))