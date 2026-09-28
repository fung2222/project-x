"""Backfill data/pnl_history.json for the HKD 10k era (rebase 2026-09-13) from the trade log
and daily closes (yfinance). Rows are marked "backfilled": true. Existing live rows are kept.
Usage: python scripts/backfill_pnl_history.py"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from px import archive, clock, ledger, marketdata  # noqa: E402
from px.config import load_settings  # noqa: E402


def main():
    s = load_settings()
    pf = ledger.load()
    start = float(s["account"]["start_equity_usd"])
    rb = dt.date.fromisoformat(s["account"]["rebase_date"])
    trades = ledger.era_trades(pf)
    last = clock.previous_trading_day(clock.now_et().date() + dt.timedelta(days=1))
    if not clock.session_closed():
        last = clock.previous_trading_day(clock.now_et().date())
    tickers = sorted({t["ticker"] for t in trades} | {"SPY", "QQQ"})
    closes = {}
    for t in tickers:
        df = marketdata.history(t, period="3mo")
        closes[t] = {i.date(): float(v) for i, v in df["Close"].dropna().items()}
    fx = s["account"]["fx_fallback_usdhkd"]
    hist = {h["date"]: h for h in archive.load_pnl()}
    d = rb
    while d <= last:
        if clock.is_trading_day(d) and d.isoformat() not in hist:
            cash, pos, realized, fees_open = start, {}, 0.0, {}
            for t in trades:
                if dt.date.fromisoformat(t["date"]) > d:
                    continue
                if t["action"] == "BUY":
                    cash -= float(t.get("cost_usd") or t["entry_price"] * t["shares"]) + float(t.get("fee_usd") or 0)
                    pos[t["ticker"]] = pos.get(t["ticker"], 0) + t["shares"]
                    fees_open[t["ticker"]] = float(t.get("fee_usd") or 0)
                elif t["action"] == "SELL":
                    cash += float(t.get("gross_proceeds_usd") or t["exit_price"] * t["shares"]) - float(t.get("fee_usd") or 0)
                    pos[t["ticker"]] = pos.get(t["ticker"], 0) - t["shares"]
                    realized += float(t.get("net_pnl_usd") or 0)
            pos = {k: v for k, v in pos.items() if v}
            mv = sum(v * closes[k].get(d, 0) for k, v in pos.items())
            eq = round(cash + mv, 2)
            hist[d.isoformat()] = {
                "date": d.isoformat(), "equity_usd": eq, "cash_usd": round(cash, 2), "total_pnl_usd": round(eq - start, 2),
                "total_return_pct": round((eq / start - 1) * 100, 2), "realized_pnl_usd": round(realized, 2),
                "unrealized_pnl_usd": None, "fx_usdhkd": fx, "equity_hkd": round(eq * fx, 2),
                "spy_close": closes["SPY"].get(d), "qqq_close": closes["QQQ"].get(d),
                "positions": [{"ticker": k, "shares": v, "price": closes[k].get(d)} for k, v in pos.items()],
                "backfilled": True}
        d += dt.timedelta(days=1)
    rows = [hist[k] for k in sorted(hist)]
    archive._save(archive.PNL, rows)
    for r in rows:
        print(r["date"], r["equity_usd"], r["total_return_pct"], [p["ticker"] for p in r["positions"]])


if __name__ == "__main__":
    main()
