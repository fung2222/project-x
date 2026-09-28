#!/usr/bin/env python3
"""Hourly position check for Project X automation."""
import json, os, datetime
from zoneinfo import ZoneInfo
import yfinance as yf
import position_tracker
import vix_guardrail
import telegram_push

HKT = ZoneInfo("Asia/Hong_Kong")
now = datetime.datetime.now(HKT)
today = now.date().isoformat()
BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = "/home/box/sand-data/agents/5ae81f5d-f7a3-4247-9353-f342b925b25b/automations/position_tracker_state.json"

position_tracker.update_positions()

with open(os.path.join(BASE, "portfolio.json"), encoding="utf-8") as f:
    pf = json.load(f)

prev = {}
prev_path = os.path.join(BASE, "_last_hourly_check.json")
try:
    with open(prev_path, encoding="utf-8") as f:
        prev = json.load(f)
except Exception:
    pass
prev_px = {p["ticker"]: p["px"] for p in prev.get("positions", [])}

quiet_path = os.path.join(BASE, ".last_hourly_quiet_hkt")
first_today = True
if os.path.exists(quiet_path):
    with open(quiet_path) as f:
        first_today = f.read().strip() != today

vix = None
try:
    hist = yf.Ticker("^VIX").history(period="5d")
    if len(hist):
        vix = float(hist["Close"].iloc[-1])
except Exception as e:
    print("VIX err", e)
regime_info = vix_guardrail.check_guardrail(vix_value=vix)
regime = regime_info["regime"]

alerts = []
positions_out = []
NEAR_SL = 2.0
BIG_MOVE = 3.0

for pos in pf.get("positions", []):
    ticker = pos["ticker"]
    px = float(pos.get("current_price") or pos["entry_price"])
    entry = float(pos["entry_price"])
    sl = float(pos.get("stop_loss_price") or entry * 0.92)
    tp = float(pos.get("take_profit_price") or entry * 1.10)
    pnl_pct = float(pos.get("pnl_pct") or (px - entry) / entry * 100)
    dist_sl = (px - sl) / px * 100 if px else 0
    action = "HOLD"
    if px <= sl:
        action = "STOP_LOSS"
        alerts.append(f"STOP_LOSS {ticker} @ {px:.2f} (SL {sl:.2f})")
    elif px >= tp:
        action = "TAKE_PROFIT"
        alerts.append(f"TAKE_PROFIT {ticker} @ {px:.2f} (TP {tp:.2f})")
    near = dist_sl < NEAR_SL and action == "HOLD"
    if near:
        alerts.append(f"NEAR_SL {ticker} dist {dist_sl:.1f}% (px {px:.2f} SL {sl:.2f})")
    if ticker in prev_px and prev_px[ticker]:
        chg = (px - prev_px[ticker]) / prev_px[ticker] * 100
        if abs(chg) >= BIG_MOVE:
            alerts.append(f"BIG_MOVE {ticker} {prev_px[ticker]:.2f}->{px:.2f} ({chg:+.1f}%)")
    positions_out.append({
        "ticker": ticker,
        "shares": pos["shares"],
        "px": round(px, 2),
        "pnl_pct": round(pnl_pct, 2),
        "sl": sl,
        "tp": tp,
        "dist_sl_pct": round(dist_sl, 2),
        "action": action,
        "near_stop": near,
    })

prev_regime = prev.get("regime")
if prev_regime and prev_regime != regime:
    alerts.append(f"VIX_REGIME {prev_regime}->{regime} (VIX {vix})")

need_push = bool(alerts) or first_today
push_reason = "alerts" if alerts else ("first_today" if first_today else "none")
pushed = False
push_err = None

if need_push:
    lines = [
        f"📊 Project X 持倉監控 {now.strftime('%Y-%m-%d %H:%M')} HKT",
        f"VIX {vix:.2f} {regime}" if vix is not None else f"VIX n/a {regime}",
        f"Equity ~USD {pf['account'].get('equity_usd')}",
        "",
    ]
    for p in positions_out:
        lines.append(
            f"{p['ticker']} x{p['shares']} @ {p['px']:.2f} ({p['pnl_pct']:+.2f}%) "
            f"SL {p['sl']:.2f} / TP {p['tp']:.2f} distSL {p['dist_sl_pct']:.1f}% → {p['action']}"
        )
    if alerts:
        lines.append("")
        lines.append("⚠️ Alerts:")
        for a in alerts:
            lines.append(f"• {a}")
    elif first_today:
        lines.append("")
        lines.append("✅ 持倉監控正常（今日首次）")
    text = "\n".join(lines)
    cfg = telegram_push.load_config()
    token = cfg.get("bot_token") or cfg.get("token")
    chat_id = cfg.get("chat_id")
    ok, result = telegram_push.send_telegram_message(token, chat_id, text)
    pushed = bool(ok)
    if not ok:
        push_err = str(result)
    print("TELEGRAM", ok, result)

# mark quiet date once we ran (first_today only once per HKT day)
with open(quiet_path, "w") as f:
    f.write(today)

out = {
    "hkt": now.isoformat(),
    "vix": vix,
    "regime": regime,
    "positions": positions_out,
    "equity_usd": pf["account"].get("equity_usd"),
    "cash_usd": pf["account"].get("cash_usd"),
    "alerts": alerts,
    "need_push": need_push,
    "first_today": first_today,
    "push_reason": push_reason,
    "pushed": pushed,
    "push_err": push_err,
}
with open(prev_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

state = {
    "last_check_hkt_date": today,
    "last_check_iso": now.isoformat(),
    "last_vix": vix,
    "last_regime": regime,
    "last_alerts": alerts,
    "last_near_stop": [p["ticker"] for p in positions_out if p.get("near_stop")],
    "sig_changes": [],
    "telegram_sent": pushed,
    "prices": {p["ticker"]: p["px"] for p in positions_out},
    "equity_usd": pf["account"].get("equity_usd"),
    "cash_usd": pf["account"].get("cash_usd"),
    "eval": [
        {
            "ticker": p["ticker"],
            "shares": p["shares"],
            "entry": next(x["entry_price"] for x in pf["positions"] if x["ticker"] == p["ticker"]),
            "current": p["px"],
            "pnl_pct": p["pnl_pct"],
            "stop": p["sl"],
            "take_profit": p["tp"],
            "dist_to_sl_pct": p["dist_sl_pct"],
            "triggered_sl": p["action"] == "STOP_LOSS",
            "triggered_tp": p["action"] == "TAKE_PROFIT",
            "near_stop": p["near_stop"],
        }
        for p in positions_out
    ],
    "quote_note": "hourly tracker",
    "push_reason": push_reason,
    "need_wake_parent": bool(alerts),
}
os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
with open(STATE_PATH, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

print(json.dumps(out, ensure_ascii=False, indent=2))
