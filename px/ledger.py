"""Paper ledger on the root `portfolio.json` (legacy path kept on purpose so the
existing website and the Grok Bot routines keep working until cutover).

Accounting (current era = trades dated >= account.rebase_date, HKD 10k book):
  cash       = start_equity - sum(buy cost + buy fee) + sum(sell gross - sell fee)
  realized   = sum(net P&L of closed round trips, BOTH fees deducted)
  unrealized = sum((last - entry) * shares) for open positions (price only)
  open_fees  = entry fees paid on still-open positions
  total_pnl  = realized + unrealized - open_fees  == equity - start_equity
"""
import datetime as dt
import json
import math
import os
import tempfile

from . import clock
from .config import load_settings, path, theme_of, bucket_of

PORTFOLIO_PATH = path("portfolio.json")


class RuleViolation(Exception):
    pass


def load(p=None):
    with open(p or PORTFOLIO_PATH, encoding="utf-8") as f:
        return json.load(f)


def save(pf, p=None):
    p = p or PORTFOLIO_PATH
    sync_rules(pf)
    d = os.path.dirname(p)
    fd, tmp = tempfile.mkstemp(prefix=".portfolio.", suffix=".tmp", dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(pf, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def sync_rules(pf):
    """Mirror config/settings.json rules into portfolio.json (display only)."""
    s = load_settings()
    r = s["rules"]
    rules = pf.setdefault("rules", {})
    rules.update({
        "max_positions": r["max_positions"], "max_position_pct": r["max_position_pct"],
        "min_cash_pct": r["min_cash_pct"], "min_confidence": r["min_confidence"],
        "stop_loss_type": "ATR", "stop_loss_atr_mult": r["sl_atr_mult"],
        "take_profit_pct": r["tp_pct"], "risk_per_trade_pct": r["risk_per_trade_pct"],
        "max_new_entries_per_day": r["max_new_entries_per_day"],
        "one_position_per_theme": r["one_position_per_theme"],
        "allow_averaging_down": r["allow_averaging_down"],
        "cooldown_after_sl_days": r["cooldown_after_sl_days"],
        "cooldown_after_tp_days": r["cooldown_after_tp_days"],
        "source_of_truth": "config/settings.json",
    })
    rules.pop("max_trades_per_day", None)
    vg = pf.setdefault("vix_guardrails", {})
    for name, reg in s["regimes"].items():
        vg.setdefault(name, {})
        vg[name]["max_positions"] = reg["max_positions"]
        vg[name]["min_confidence"] = reg["min_confidence"]


def fee(notional, shares=None, side="buy", fcfg=None):
    """Per-order fee in USD.

    model "futu_hk_fixed" (default): Futu HK US-stock fixed plan — commission + platform fee
    (each with its per-order minimum; the 0.5%-of-notional cap never goes below the minimums),
    settlement fee per share, TAF on sells. ~US$2.00 per small order, ~US$4 per round trip.
    model "flat": the pre-2026-09-28 paper model max(min_usd, rate * notional)."""
    f = fcfg or load_settings()["rules"]["fee"]
    if f.get("model", "flat") != "futu_hk_fixed":
        return round(max(f["min_usd"], round(f["rate"] * notional, 2)), 2)
    sh = int(shares) if shares else 0
    comm = max(f["commission_min"], f["commission_per_share"] * sh)
    plat = max(f["platform_min"], f["platform_per_share"] * sh)
    both = max(f["commission_min"] + f["platform_min"], min(comm + plat, f["cap_pct_of_notional"] * notional))
    other = f["settlement_per_share"] * sh
    if side == "sell":
        other += min(f["taf_max"], max(f["taf_min"], f["taf_per_share_sell"] * sh))
    return round(both + other, 2)


def round_trip_fee(price, shares, fcfg=None):
    n = price * shares
    return round(fee(n, shares, "buy", fcfg) + fee(n, shares, "sell", fcfg), 2)


def _r2(x):
    return round(float(x) + 0.0, 2)


def rebase_date():
    return load_settings()["account"]["rebase_date"]


def era_trades(pf):
    rb = rebase_date()
    return [t for t in pf.get("trade_log", []) if str(t.get("date", "")) >= rb]


def replay_cash(pf):
    cash = float(load_settings()["account"]["start_equity_usd"])
    for t in era_trades(pf):
        if t.get("action") == "BUY":
            cash -= float(t.get("cost_usd") or t["entry_price"] * t["shares"]) + float(t.get("fee_usd") or 0)
        elif t.get("action") == "SELL":
            cash += float(t.get("gross_proceeds_usd") or t["exit_price"] * t["shares"]) - float(t.get("fee_usd") or 0)
    return _r2(cash)


def _buy_fee_for(pf, pos):
    tid = pos.get("trade_id")
    for t in pf.get("trade_log", []):
        if t.get("id") == tid:
            return float(t.get("fee_usd") or 0)
    return float(pos.get("entry_fee_usd") or 0)


def recompute(pf, fx=None, now=None):
    """Recompute position marks + account totals in place. Returns account dict."""
    s = load_settings()
    acct = pf.setdefault("account", {})
    start = float(s["account"]["start_equity_usd"])
    cash = replay_cash(pf)
    stored = acct.get("cash_usd")
    if stored is not None and abs(float(stored) - cash) > 0.011:
        acct["cash_reconcile_warning"] = f"stored cash {stored} != ledger replay {cash}; using ledger replay"
    else:
        acct.pop("cash_reconcile_warning", None)
    acct["cash_usd"] = cash
    value = unreal = open_fees = invested = 0.0
    today = clock.now_et().date()
    for pos in pf.get("positions", []):
        entry = float(pos["entry_price"])
        px = float(pos.get("current_price") or entry)
        sh = float(pos["shares"])
        pos["cost_usd"] = _r2(entry * sh)
        pos["value_usd"] = _r2(px * sh)
        pos["pnl_usd"] = _r2((px - entry) * sh)
        pos["pnl_pct"] = _r2((px - entry) / entry * 100)
        sl, tp = pos.get("stop_loss_price"), pos.get("take_profit_price")
        pos["dist_to_sl_pct"] = _r2((px - sl) / px * 100) if sl and px else None
        pos["dist_to_tp_pct"] = _r2((tp - px) / px * 100) if tp and px else None
        pos.setdefault("theme", theme_of(pos["ticker"]))
        pos.setdefault("bucket", bucket_of(pos["ticker"]))
        try:
            ed = dt.date.fromisoformat(pos.get("entry_date"))
            pos["held_trading_days"] = clock.trading_days_between(ed, today)
        except Exception:
            pass
        flag = "OK"
        near = s["rules"]["near_sl_alert_pct"]
        if pos.get("dist_to_sl_pct") is not None and pos["dist_to_sl_pct"] < near:
            flag = "NEAR_SL"
        elif pos.get("dist_to_tp_pct") is not None and pos["dist_to_tp_pct"] < near:
            flag = "NEAR_TP"
        elif pos.get("held_trading_days", 0) >= s["rules"]["time_review_days"] and abs(pos["pnl_pct"]) <= 3:
            flag = "REVIEW"
        pos["risk_flag"] = flag
        value += px * sh
        unreal += (px - entry) * sh
        invested += entry * sh
        open_fees += _buy_fee_for(pf, pos)
    realized = sum(float(t.get("net_pnl_usd") or 0) for t in era_trades(pf) if t.get("action") == "SELL")
    fees = sum(float(t.get("fee_usd") or 0) for t in era_trades(pf))
    equity = cash + value
    total = realized + unreal - open_fees
    fx = fx or acct.get("fx_usdhkd") or s["account"]["fx_fallback_usdhkd"]
    acct.update({
        "capital_hkd": s["account"]["capital_hkd"],
        "start_equity_usd": start,
        "rebase_date": s["account"]["rebase_date"],
        "cash_usd": _r2(cash),
        "cash_hkd": _r2(cash * fx),
        "equity_usd": _r2(equity),
        "equity_hkd": _r2(equity * fx),
        "fx_usdhkd": fx,
        "total_invested_usd": _r2(invested),
        "realized_pnl_usd": _r2(realized),
        "unrealized_pnl_usd": _r2(unreal),
        "open_entry_fees_usd": _r2(open_fees),
        "total_pnl_usd": _r2(total),
        "total_pnl_pct": _r2(total / start * 100),
        "total_return_usd": _r2(equity - start),
        "total_return_pct": _r2((equity - start) / start * 100),
        "total_fees_usd": _r2(fees),
        "total_fees_scope": f"trades since rebase {s['account']['rebase_date']}",
        "cash_pct": _r2(cash / equity * 100) if equity else None,
        "deployed_pct": _r2(value / equity * 100) if equity else None,
        "pnl_formula": "total_pnl = realized + unrealized - open_entry_fees = equity - start_equity",
    })
    if abs((equity - start) - total) > 0.011:
        acct["pnl_reconcile_warning"] = f"equity-start {equity-start:.2f} != total_pnl {total:.2f}"
    else:
        acct.pop("pnl_reconcile_warning", None)
    return acct


def mark(pf, prices, now=None):
    ts = (now or clock.now_hkt()).isoformat(timespec="seconds")
    for pos in pf.get("positions", []):
        p = prices.get(pos["ticker"])
        if p:
            pos["current_price"] = round(float(p), 4)
            pos["last_updated"] = ts


def next_trade_id(pf):
    n = 0
    for t in pf.get("trade_log", []):
        tid = str(t.get("id", ""))
        if tid.startswith("T") and tid[1:].isdigit():
            n = max(n, int(tid[1:]))
    return f"T{n + 1:03d}"


def position(pf, ticker):
    return next((p for p in pf.get("positions", []) if p["ticker"] == ticker), None)


def check_exit(pos, price):
    """Return 'STOP_LOSS' | 'TAKE_PROFIT' | None."""
    sl, tp = pos.get("stop_loss_price"), pos.get("take_profit_price")
    if sl and price <= float(sl):
        return "STOP_LOSS"
    if tp and price >= float(tp):
        return "TAKE_PROFIT"
    return None


def execute_exit(pf, ticker, price, reason, note="", now=None):
    now = now or clock.now_hkt()
    pos = position(pf, ticker)
    if not pos:
        raise RuleViolation(f"no open position in {ticker}")
    sh = int(pos["shares"])
    entry = float(pos["entry_price"])
    gross = _r2(price * sh)
    f = fee(gross, sh, "sell")
    buy_fee = _buy_fee_for(pf, pos)
    net = _r2(gross - f - entry * sh - buy_fee)
    cost_basis = entry * sh + buy_fee
    tid = next_trade_id(pf)
    trade = {
        "id": tid, "date": clock.session_date(now).isoformat(), "timestamp": now.isoformat(timespec="seconds"),
        "ticker": ticker, "action": "SELL", "reason": reason, "shares": sh,
        "entry_price": entry, "exit_price": round(float(price), 4),
        "entry_date": pos.get("entry_date"), "exit_date": clock.session_date(now).isoformat(),
        "open_trade_id": pos.get("trade_id"),
        "gross_proceeds_usd": gross, "fee_usd": f, "proceeds_usd": _r2(gross - f),
        "gross_pnl_usd": _r2((price - entry) * sh), "gross_pnl_pct": _r2((price - entry) / entry * 100),
        "net_pnl_usd": net, "net_pnl_pct": _r2(net / cost_basis * 100),
        "status": "closed", "decision_note": note or f"auto {reason} by px engine",
    }
    pf.setdefault("trade_log", []).append(trade)
    for t in pf["trade_log"]:
        if t.get("id") == pos.get("trade_id"):
            t.update({"status": "closed", "closed_by": tid, "exit_date": trade["exit_date"],
                      "exit_price": trade["exit_price"], "pnl_usd": net, "pnl_pct": trade["net_pnl_pct"]})
    pf["positions"] = [p for p in pf["positions"] if p["ticker"] != ticker]
    recompute(pf)
    return trade


def entries_on(pf, session):
    return [t for t in pf.get("trade_log", []) if t.get("action") == "BUY" and t.get("date") == session]


def last_exit(pf, ticker):
    ex = [t for t in pf.get("trade_log", []) if t.get("action") == "SELL" and t.get("ticker") == ticker]
    return ex[-1] if ex else None


def compute_sl_tp(entry, atr):
    r = load_settings()["rules"]
    sl = max(entry - r["sl_atr_mult"] * (atr or 0), entry * (1 - r["sl_max_pct"]))
    sl = min(sl, entry * (1 - r["sl_min_pct"]))
    return round(sl, 2), round(entry * (1 + r["tp_pct"]), 2)


def size_position(equity, cash, entry, sl, size_factor=1.0):
    r = load_settings()["rules"]
    cap_pos = r["max_position_pct"] * equity * size_factor
    cap_cash = cash - r["min_cash_pct"] * equity
    risk_ps = entry - sl
    cap_risk = r["risk_per_trade_pct"] * equity / risk_ps * entry if risk_ps > 0 else 0
    budget = min(cap_pos, cap_cash, cap_risk)
    # leave room for the entry fee
    shares = int(math.floor(max(0.0, budget) / (entry * (1 + r["fee"]["rate"]))))
    while shares > 0 and (entry * shares + fee(entry * shares, shares)) > cap_cash:
        shares -= 1
    return shares, {"cap_position": _r2(cap_pos), "cap_cash_floor": _r2(cap_cash), "cap_risk": _r2(cap_risk)}


def enforce_entry_rules(pf, ticker, price, shares, sl, regime, now=None):
    """Code-enforced portfolio rules for ANY paper entry. Raises RuleViolation."""
    s = load_settings()
    r = s["rules"]
    now = now or clock.now_hkt()
    session = clock.session_date(now).isoformat()
    acct = recompute(pf)
    eq, cash = acct["equity_usd"], acct["cash_usd"]
    if position(pf, ticker):
        raise RuleViolation(f"{ticker} already held (no averaging down / no add)")
    maxpos = min(r["max_positions"], s["regimes"][regime]["max_positions"])
    if len(pf.get("positions", [])) >= maxpos:
        raise RuleViolation(f"max positions {maxpos} reached ({regime})")
    if len(entries_on(pf, session)) >= r["max_new_entries_per_day"]:
        raise RuleViolation(f"max {r['max_new_entries_per_day']} new entry per day already used ({session})")
    th = theme_of(ticker)
    if r["one_position_per_theme"] and th != "OTHER" and any(theme_of(p["ticker"]) == th for p in pf["positions"]):
        raise RuleViolation(f"theme {th} already held")
    lx = last_exit(pf, ticker)
    if lx:
        days = clock.trading_days_between(dt.date.fromisoformat(lx["date"]), clock.session_date(now))
        cd = r["cooldown_after_sl_days"] if lx.get("reason") == "STOP_LOSS" else r["cooldown_after_tp_days"]
        if days < cd:
            raise RuleViolation(f"{ticker} cooldown: exited {lx['reason']} {days} trading day(s) ago (< {cd})")
    if shares < 1:
        raise RuleViolation("position size < 1 share")
    notional = price * shares
    f = fee(notional, shares)
    if notional > r["max_position_pct"] * eq + 0.01:
        raise RuleViolation(f"notional {notional:.2f} > {r['max_position_pct']*100:.0f}% of equity")
    if cash - notional - f < r["min_cash_pct"] * eq - 0.01:
        raise RuleViolation("cash would fall below minimum cash %")
    if (price - sl) * shares > r["risk_per_trade_pct"] * eq + 0.01:
        raise RuleViolation(f"risk {(price-sl)*shares:.2f} > {r['risk_per_trade_pct']*100:.0f}% of equity")
    if notional < r["min_notional_usd"]:
        raise RuleViolation(f"notional {notional:.2f} < min {r['min_notional_usd']}")
    return True


def execute_entry(pf, ticker, price, shares, sl, tp, regime, reason, setup=None, confidence=None, now=None):
    now = now or clock.now_hkt()
    enforce_entry_rules(pf, ticker, price, shares, sl, regime, now)
    notional = _r2(price * shares)
    f = fee(notional, shares)
    tid = next_trade_id(pf)
    session = clock.session_date(now).isoformat()
    trade = {
        "id": tid, "date": session, "timestamp": now.isoformat(timespec="seconds"), "ticker": ticker,
        "action": "BUY", "shares": int(shares), "entry_price": round(float(price), 4), "cost_usd": notional,
        "fee_usd": f, "reason": reason, "setup": setup, "confidence": confidence, "theme": theme_of(ticker),
        "stop_loss_price": sl, "take_profit_price": tp, "status": "open", "pnl_usd": None, "pnl_pct": None,
    }
    pf.setdefault("trade_log", []).append(trade)
    pf.setdefault("positions", []).append({
        "ticker": ticker, "shares": int(shares), "entry_price": round(float(price), 4), "entry_date": session,
        "trade_id": tid, "current_price": round(float(price), 4), "cost_usd": notional,
        "stop_loss_price": sl, "take_profit_price": tp, "setup": setup, "theme": theme_of(ticker),
        "bucket": bucket_of(ticker), "thesis": reason, "last_updated": now.isoformat(timespec="seconds"),
    })
    recompute(pf)
    return trade
