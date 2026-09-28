"""risk_manager.py - 模擬倉止損/止盈/距離警示（硬數據）"""
import json
from datetime import datetime
from data_fetcher import get_verified_quote

STOP_LOSS_PCT = 0.10
TAKE_PROFIT_PCT = 0.20
WARN_SL_PCT = 0.07   # -7% 預警
DANGER_SL_PCT = 0.085  # -8.5% 高危


def update_portfolio():
    with open("portfolio.json", "r", encoding="utf-8") as f:
        port = json.load(f)

    alerts = []
    total_value = port["cash_usd"]

    for pos in port.get("positions", []):
        q = get_verified_quote(pos["ticker"])
        if not q:
            alerts.append(f"⚠️ {pos['ticker']} 數據取唔到，跳過")
            continue

        cur = q["price"]
        entry = pos["entry_price"]
        pnl_pct = (cur - entry) / entry * 100
        pos_value = cur * pos["shares"]
        total_value += pos_value

        sl_price = round(entry * (1 - STOP_LOSS_PCT), 2)
        tp_price = round(entry * (1 + TAKE_PROFIT_PCT), 2)
        # 距離止損還有多少百分點（正數=安全緩衝）
        dist_to_sl_pp = round(pnl_pct - (-STOP_LOSS_PCT * 100), 2)
        dist_to_tp_pp = round((TAKE_PROFIT_PCT * 100) - pnl_pct, 2)

        pos["current_price"] = cur
        pos["pnl_pct"] = round(pnl_pct, 2)
        pos["value_usd"] = round(pos_value, 2)
        pos["stop_loss"] = sl_price
        pos["take_profit"] = tp_price
        pos["dist_to_sl_pp"] = dist_to_sl_pp
        pos["dist_to_tp_pp"] = dist_to_tp_pp
        pos["risk_flag"] = "OK"
        pos["last_updated"] = datetime.now().isoformat()

        if pnl_pct <= -STOP_LOSS_PCT * 100:
            pos["risk_flag"] = "STOP"
            alerts.append(
                f"🚨 STOP {pos['ticker']} 蝕 {pnl_pct:.1f}% 已觸/穿止損 "
                f"(入 {entry:.2f} → 止損 {sl_price:.2f} | 現價 {cur:.2f})"
            )
        elif pnl_pct <= -DANGER_SL_PCT * 100:
            pos["risk_flag"] = "DANGER"
            alerts.append(
                f"🔴 DANGER {pos['ticker']} 蝕 {pnl_pct:.1f}% · 距止損只剩 {dist_to_sl_pp:.1f}pp "
                f"(止損 {sl_price:.2f})"
            )
        elif pnl_pct <= -WARN_SL_PCT * 100:
            pos["risk_flag"] = "WARN"
            alerts.append(
                f"🟠 WARN {pos['ticker']} 蝕 {pnl_pct:.1f}% · 接近止損區 "
                f"(距止損 {dist_to_sl_pp:.1f}pp · 止損 {sl_price:.2f})"
            )
        elif pnl_pct >= TAKE_PROFIT_PCT * 100:
            pos["risk_flag"] = "TP"
            alerts.append(
                f"💰 TP {pos['ticker']} 賺 {pnl_pct:.1f}% 可考慮止盈 "
                f"(入 {entry:.2f} → 止盈 {tp_price:.2f})"
            )

    port["total_value_usd"] = round(total_value, 2)
    port["total_pnl_usd"] = round(
        total_value - port["account"]["initial_usd"], 2
    )
    port["total_pnl_pct"] = round(
        (total_value - port["account"]["initial_usd"])
        / port["account"]["initial_usd"] * 100, 2
    )
    port["last_updated"] = datetime.now().isoformat()

    with open("portfolio.json", "w", encoding="utf-8") as f:
        json.dump(port, f, ensure_ascii=False, indent=2)

    return {"alerts": alerts, "portfolio": port}


if __name__ == "__main__":
    r = update_portfolio()
    print("Alerts:", r["alerts"])
    print(f"Total: ${r['portfolio']['total_value_usd']} ({r['portfolio']['total_pnl_pct']:+.2f}%)")
