#!/usr/bin/env python3
"""Project X open-monitor (21:35 HKT) — always Telegram push."""
import json, os, datetime
from zoneinfo import ZoneInfo
import yfinance as yf
import position_tracker
import vix_guardrail
import telegram_push

HKT = ZoneInfo("Asia/Hong_Kong")
now = datetime.datetime.now(HKT)
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "_last_open_monitor.json")
OPEN_MOVE_PCT = 2.0
NEAR_SL_PCT = 2.0

# 1) refresh quotes
position_tracker.update_positions()

with open(os.path.join(BASE, "portfolio.json"), encoding="utf-8") as f:
    pf = json.load(f)

# 2) VIX
vix = None
try:
    hist = yf.Ticker("^VIX").history(period="5d")
    if len(hist):
        vix = float(hist["Close"].iloc[-1])
except Exception as e:
    print("VIX err", e)
regime_info = vix_guardrail.check_guardrail(vix_value=vix)
regime = regime_info["regime"]
emoji = regime_info["emoji"]
title = regime_info["title"]

# 3) positions vs prev close
alerts = []
positions_out = []
price_watch = []
for pos in pf.get("positions", []):
    ticker = pos["ticker"]
    px = float(pos.get("current_price") or pos["entry_price"])
    entry = float(pos["entry_price"])
    sl = float(pos.get("stop_loss_price") or entry * 0.92)
    tp = float(pos.get("take_profit_price") or entry * 1.10)
    pnl_pct = float(pos.get("pnl_pct") or (px - entry) / entry * 100)
    dist_sl = (px - sl) / px * 100 if px else 0

    prev_close = None
    chg_vs_prev = None
    try:
        h = yf.Ticker(ticker).history(period="5d")
        if len(h) >= 2:
            prev_close = float(h["Close"].iloc[-2])
            chg_vs_prev = (px - prev_close) / prev_close * 100
        elif len(h) == 1:
            # same-day only; try info
            info = yf.Ticker(ticker).info or {}
            prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
            if prev_close:
                prev_close = float(prev_close)
                chg_vs_prev = (px - prev_close) / prev_close * 100
    except Exception as e:
        print(f"prev close err {ticker}", e)

    action = "HOLD"
    if px <= sl:
        action = "STOP_LOSS"
        alerts.append(f"STOP_LOSS {ticker} @ {px:.2f} (SL {sl:.2f})")
    elif px >= tp:
        action = "TAKE_PROFIT"
        alerts.append(f"TAKE_PROFIT {ticker} @ {px:.2f} (TP {tp:.2f})")
    if dist_sl < NEAR_SL_PCT and action == "HOLD":
        alerts.append(f"NEAR_SL {ticker} dist {dist_sl:.1f}% (px {px:.2f} SL {sl:.2f})")
    if chg_vs_prev is not None and abs(chg_vs_prev) >= OPEN_MOVE_PCT:
        direction = "急升" if chg_vs_prev > 0 else "急跌"
        alerts.append(f"OPEN_MOVE {ticker} {direction} {chg_vs_prev:+.1f}% vs prev close")

    positions_out.append({
        "ticker": ticker,
        "shares": pos["shares"],
        "px": round(px, 2),
        "pnl_pct": round(pnl_pct, 2),
        "chg_vs_prev": round(chg_vs_prev, 2) if chg_vs_prev is not None else None,
        "prev_close": round(prev_close, 2) if prev_close is not None else None,
        "sl": sl,
        "tp": tp,
        "dist_sl_pct": round(dist_sl, 2),
        "action": action,
    })
    price_watch.append(
        f"{ticker} 睇住 ${sl:.2f} 止損、${tp:.2f} 止盈（而家 ${px:.2f}）"
    )

# teaching tip (one sentence, open-session focused)
teach_by_regime = {
    "NORMAL": "開市唔使急：先睇 VIX 同大盤方向，持倉只跟預設止損／止盈，唔好喺頭半小時用感覺加倉攤平。",
    "CAUTION": "VIX 已入謹慎區：開市波動會放大，優先守住止損線，新倉等確認訊號先動手。",
    "DEFENSIVE": "高波動防禦日：現金係倉位，開市只容許止損／止盈執行，唔追缺口、唔攤平。",
}
teach = teach_by_regime.get(regime, teach_by_regime["NORMAL"])
if any(a.startswith("NEAR_SL") for a in alerts):
    teach = "開市近止損最危險：唔好加倉攤平；價一收穿預設止損就執行，情緒留畀下一個訊號。"
elif any(a.startswith("OPEN_MOVE") and "急跌" in a for a in alerts):
    teach = "開市急跌先分清缺口定趨勢：未穿止損就忍住唔抄底，等頭半小時波動收斂再決定。"
elif any(a.startswith("TAKE_PROFIT") for a in alerts):
    teach = "開市觸及止盈：鎖利優先於貪多，紙上獲利唔等於落袋，執行預設規則最穩陣。"

action_stance = "HOLD both (observation; no ADD on open)"
if any(p["action"] == "STOP_LOSS" for p in positions_out):
    action_stance = "EXECUTE stop-loss on hit names; no ADD"
elif any(p["action"] == "TAKE_PROFIT" for p in positions_out):
    action_stance = "EXECUTE take-profit on hit names; no ADD"

equity = pf["account"].get("equity_usd")

# 4) Telegram (always)
vix_str = f"{vix:.2f}" if vix is not None else "n/a"
lines = [
    f"<b>🔔 開市監控</b> {now.strftime('%Y-%m-%d %H:%M')} HKT",
    f"{emoji} 市況：<b>{title}</b>（VIX {vix_str} / {regime}）",
    f"Equity ~USD {equity}",
    "",
    "<b>📍 要睇嘅價位</b>",
]
for w in price_watch:
    lines.append(f"• {w}")
lines.append("")
lines.append("<b>📦 持倉</b>")
for p in positions_out:
    chg = f"{p['chg_vs_prev']:+.1f}% vs昨收" if p.get("chg_vs_prev") is not None else "vs昨收 n/a"
    lines.append(
        f"• <b>{p['ticker']}</b> x{p['shares']} @ ${p['px']:.2f} "
        f"（{p['pnl_pct']:+.2f}%｜{chg}｜{p['action']}｜距SL {p['dist_sl_pct']:.1f}%）"
    )
lines.append("")
lines.append(f"<b>stance</b>：{action_stance}")
if alerts:
    lines.append("")
    lines.append("<b>⚠️ 風險預警</b>")
    for a in alerts:
        lines.append(f"• <b>{a}</b>")
lines.append("")
lines.append(f"📚 開市教學：{teach}")
lines.append("")
lines.append("紙上模擬；真錢落單仍由你喺富途執行。")

msg = "\n".join(lines)

with open(os.path.join(BASE, "telegram_config.json"), encoding="utf-8") as f:
    tg = json.load(f)
token, chat_id = tg.get("bot_token"), tg.get("chat_id")
tg_ok = False
tg_result = None
try:
    ok = telegram_push.send_telegram_message(token, chat_id, msg)
    # send_telegram_message may return bool or response
    if isinstance(ok, dict):
        tg_ok = bool(ok.get("ok"))
        tg_result = str(ok.get("result", {}).get("message_id", ok))
    else:
        tg_ok = bool(ok)
        tg_result = str(ok)
except Exception as e:
    tg_result = f"err:{e}"
    print("telegram err", e)

# fallback raw requests if helper failed
if not tg_ok:
    try:
        import requests
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )
        data = resp.json()
        tg_ok = bool(data.get("ok"))
        tg_result = str(data.get("result", {}).get("message_id", data))
    except Exception as e:
        tg_result = f"err2:{e}"

out = {
    "hkt": now.isoformat(),
    "vix": vix,
    "regime": regime,
    "title": title,
    "emoji": emoji,
    "teach": teach,
    "price_watch": price_watch,
    "alerts": alerts,
    "positions": positions_out,
    "action_stance": action_stance,
    "equity_usd": equity,
    "telegram_ok": tg_ok,
    "followup_sent": False,
    "telegram_result": tg_result,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

# also save a text copy for Reports
rep_dir = os.path.join(BASE, "Reports")
os.makedirs(rep_dir, exist_ok=True)
with open(os.path.join(rep_dir, f"OpenMonitor_{now.date().isoformat()}.txt"), "w", encoding="utf-8") as f:
    f.write(msg)

print(json.dumps(out, ensure_ascii=False, indent=2))
print("---MSG---")
print(msg)
print("---TG---", tg_ok, tg_result)
