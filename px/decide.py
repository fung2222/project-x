"""Professional-filter gates (MERGE_PLAN §5.4) as deterministic code.

A BUY candidate opens a paper position only if ALL gates pass:
 G1 confidence >= regime min (NORMAL 0.75 / CAUTION 0.80 / DEFENSIVE 0.85)
 G2 setup A "uptrend pullback": close >= MA50 and 30 <= RSI <= 45 (full size)
    setup B "oversold reversal": RSI <= 30, MACD hist rising, up day (half size)
    (DEFENSIVE: setup A only)
 G3 volume (completed bar): A >= 0.8x, B >= 1.0x
 G4 trend_score > -4
 G5 portfolio: < max positions, theme not held, no entry yet today, not owned
 G6 sizing: 25% cap x size, cash floor 20%, 2% risk cap -> >= 1 share & >= USD 50
 G7 earnings blackout: NOT CHECKED (no reliable free data) -> noted
 G8 cooldown: no SL exit in 5 trading days / TP exit in 3 trading days
 G9 overrides: config/overrides.json pause_new_entries / blocklist
 + no new entries after schedule_et.daily.no_new_entries_after (ET)
At most max_new_entries_per_day (1) entry: highest confidence, tie -> higher vol_ratio.
"""
import datetime as dt
import json
import os

from . import clock, ledger
from .config import load_settings, path, theme_of

GATE_ZH = {
    "G1": "信心不足", "G2": "唔符合 setup A/B", "G3": "成交量不足", "G4": "趨勢太弱",
    "G5": "組合限制", "G6": "注碼計唔到 ≥1 股 / ≥USD50", "G8": "冷靜期", "G9": "人手暫停/封鎖", "TIME": "太夜唔開新倉",
}


def load_overrides():
    p = path("config", "overrides.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"pause_new_entries": False, "blocklist": []}


def evaluate(pf, sig, regime, now=None):
    """Return dict(passed, failed[list], setup, size_factor, shares, sl, tp, notes)."""
    s = load_settings()
    r = s["rules"]
    now = now or clock.now_hkt()
    ind = sig["indicators"]
    t = sig["ticker"]
    failed, notes = [], []
    reg = s["regimes"][regime]
    min_conf = max(r["min_confidence"], reg["min_confidence"]) * 100
    if sig["confidence"] < min_conf:
        failed.append("G1")
    close, ma50, rsi = ind["close"], ind["ma50"], ind["rsi14"]
    setup, size = None, 0.0
    if close >= ma50 and 30 <= rsi <= 45:
        setup, size = "A", 1.0
    elif rsi <= 30 and ind.get("hist_rising") and ind.get("up_day"):
        setup, size = "B", 0.5
    if setup is None or (setup not in reg.get("setups", ["A", "B"])):
        failed.append("G2")
    vol = ind.get("vol_ratio") or 0
    need = 1.0 if setup == "B" else 0.8
    if vol < need:
        failed.append("G3")
    if ind.get("trend_score", 0) <= -4:
        failed.append("G4")
    acct = ledger.recompute(pf)
    session = clock.session_date(now).isoformat()
    maxpos = min(r["max_positions"], reg["max_positions"])
    g5 = []
    if ledger.position(pf, t):
        g5.append("已持有")
    if len(pf.get("positions", [])) >= maxpos:
        g5.append(f"持倉已滿 {maxpos}")
    th = theme_of(t)
    if r["one_position_per_theme"] and th != "OTHER" and any(theme_of(p["ticker"]) == th for p in pf.get("positions", [])):
        g5.append(f"同主題 {th} 已有持倉")
    if len(ledger.entries_on(pf, session)) >= r["max_new_entries_per_day"]:
        g5.append("今日已開過新倉")
    if g5:
        failed.append("G5")
        notes += g5
    price = sig["price"]
    sl, tp = ledger.compute_sl_tp(price, ind.get("atr14"))
    shares, caps = ledger.size_position(acct["equity_usd"], acct["cash_usd"], price, sl, size or 1.0)
    if shares < 1 or price * shares < r["min_notional_usd"]:
        failed.append("G6")
    notes.append("G7 業績日未檢查（冇可靠免費數據）")
    lx = ledger.last_exit(pf, t)
    if lx:
        days = clock.trading_days_between(dt.date.fromisoformat(lx["date"]), clock.session_date(now))
        cd = r["cooldown_after_sl_days"] if lx.get("reason") == "STOP_LOSS" else r["cooldown_after_tp_days"]
        if days < cd:
            failed.append("G8")
            notes.append(f"{lx['reason']} 後第 {days} 個交易日")
    ov = load_overrides()
    if ov.get("pause_new_entries") or t in (ov.get("blocklist") or []):
        failed.append("G9")
    cutoff = s["schedule_et"]["daily"].get("no_new_entries_after")
    if cutoff:
        hh, mm = map(int, cutoff.split(":"))
        if clock.to_et(now).time() >= dt.time(hh, mm):
            failed.append("TIME")
    return {"ticker": t, "passed": not failed, "failed": failed, "setup": setup, "size_factor": size,
            "shares": shares, "sl": sl, "tp": tp, "caps": caps, "notes": notes,
            "confidence": sig["confidence"], "vol_ratio": vol}


def why_text(ev):
    return "、".join(f"{g} {GATE_ZH.get(g, '')}" for g in ev["failed"])


def run_gates(pf, signals, regime, now=None):
    """Evaluate all BUY candidates; return (chosen_or_None, evaluations)."""
    evals = []
    for sig in signals:
        if sig.get("raw_signal", sig.get("signal")) != "BUY" or sig.get("is_owned"):
            continue
        evals.append(evaluate(pf, sig, regime, now))
    passed = [e for e in evals if e["passed"]]
    passed.sort(key=lambda e: (e["confidence"], e["vol_ratio"] or 0), reverse=True)
    return (passed[0] if passed else None), evals
