"""
Project X — 開市預警 (21:35 HKT 觸發)
美股開市後 5 分鐘，檢查持倉異動
- 持倉波動 >2% → 推送預警
- 觸發止損/止盈 → 自動執行
"""
import json, os, sys, datetime
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finnhub_api
import risk_manager
import telegram_push

PORTFOLIO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.json")
ALERT_THRESHOLD_PCT = 2.0


def send_alert(message):
    """發送 Telegram 預警 (legacy; superseded by `python run.py open`). Credentials env-first."""
    try:
        from px import telegram as _tg
        ok, _ = _tg.send(message, label="market_open_alert (legacy)")
        return ok
    except Exception:
        return False


def check_positions_movement():
    """檢查持倉開市後嘅波動"""
    with open(PORTFOLIO_PATH, encoding="utf-8") as f:
        pf = json.load(f)
    positions = pf.get("positions", [])
    if not positions:
        return "📊 開市預警：目前無持倉，繼續觀望。"

    alerts = ["<b>🔔 開市預警 (21:35 HKT)</b>\n"]
    actions_taken = []
    for pos in positions:
        ticker = pos["ticker"]
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="1d", interval="5m")
            if hist.empty or len(hist) < 1:
                continue
            current = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[0]) if len(hist) == 1 else pos["current_price"]
            change_pct = (current - prev_close) / prev_close * 100
            entry_pct = (current - pos["entry_price"]) / pos["entry_price"] * 100
            alerts.append(f"\n<b>{ticker}</b> ${current:.2f}")
            alerts.append(f"  開市變動：{change_pct:+.2f}%")
            alerts.append(f"  vs 持倉：{entry_pct:+.2f}%")
            # 觸發預警
            if abs(change_pct) >= ALERT_THRESHOLD_PCT:
                direction = "📈 急升" if change_pct > 0 else "📉 急跌"
                alerts.append(f"  ⚠️ <b>{direction} {abs(change_pct):.1f}%</b>")
            # 風險評估
            res = risk_manager.evaluate_all_positions({ticker: current})
            if res and res[0]["recommended_action"]:
                action = res[0]["recommended_action"]
                alerts.append(f"  🎯 <b>建議動作：{action}</b>")
                ok, trade = risk_manager.execute_action(ticker, action, current)
                if ok:
                    actions_taken.append(trade)
                    alerts.append(f"  ✅ 已自動執行")
        except Exception as e:
            alerts.append(f"\n<b>{ticker}</b>: 數據獲取失敗")
    if actions_taken:
        alerts.append("\n<b>📋 今日已執行交易</b>")
        for t in actions_taken:
            alerts.append(f"  • {t.get('action')} {t.get('ticker')} PnL: {t.get('pnl_pct', 0):+.2f}%")
    return "\n".join(alerts)


if __name__ == "__main__":
    msg = check_positions_movement()
    print(msg)
    send_alert(msg)