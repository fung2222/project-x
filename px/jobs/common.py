"""Shared job plumbing: run-window / holiday checks, position refresh + auto exits."""
import datetime as dt
import json
import os

from .. import clock, ledger, marketdata
from ..config import load_settings, path, REPORTS_DIR


class Ctx:
    def __init__(self, job, dry_run=False, force=False, legacy=False, now=None):
        self.job = job
        self.dry_run = dry_run
        self.force = force
        self.legacy = legacy
        self.now = now or clock.now_hkt()
        self.now_et = clock.to_et(self.now)
        self.session = clock.session_date(self.now).isoformat()


def gate_run(ctx, window_key):
    """Return (ok, reason). Holiday / weekend / outside window -> quiet skip unless --force."""
    d = ctx.now_et.date()
    if ctx.force:
        return True, "forced"
    if not clock.is_trading_day(d):
        name = clock.holiday_name(d) or "weekend"
        return False, f"US market closed on {d} ET ({name}) — skipping quietly"
    if os.environ.get("PX_RERUN") == "1":  # watchdog re-run: trading-day check only, window bypassed
        return True, "watchdog rerun"
    win = load_settings()["schedule_et"][window_key]["window"]
    if not clock.in_window(win, ctx.now_et):
        return False, (f"outside {window_key} window {win[0]}-{win[1]} ET (now {ctx.now_et.strftime('%H:%M')} ET)"
                       " — skipping quietly (use --force to override)")
    return True, "ok"


def refresh_positions(ctx, pf):
    """Quote every open position, mark to market, auto-execute SL/TP (paper).

    Returns (rows, executed, quotes)."""
    s = load_settings()
    quotes = {p["ticker"]: marketdata.quote(p["ticker"]) for p in pf.get("positions", [])}
    prices = {t: q["price"] for t, q in quotes.items() if q.get("ok")}
    ledger.mark(pf, prices, ctx.now)
    executed, rows = [], []
    for pos in list(pf.get("positions", [])):
        t = pos["ticker"]
        q = quotes.get(t, {})
        px = float(pos.get("current_price") or pos["entry_price"])
        hit = ledger.check_exit(pos, px) if q.get("ok") else None
        row = {"ticker": t, "shares": pos["shares"], "entry": pos["entry_price"], "px": round(px, 4),
               "prev_close": q.get("prev_close"), "chg_vs_prev": q.get("change_pct"),
               "sl": pos.get("stop_loss_price"), "tp": pos.get("take_profit_price"),
               "quote_ok": bool(q.get("ok")), "source": q.get("source"), "action": "HOLD"}
        if hit and s["rules"]["auto_execute_exits"]:
            tr = ledger.execute_exit(pf, t, px, hit, note=f"{ctx.job} check {ctx.now.strftime('%Y-%m-%d %H:%M')} HKT: "
                                     f"{px:.2f} vs {'SL' if hit == 'STOP_LOSS' else 'TP'} "
                                     f"{row['sl'] if hit == 'STOP_LOSS' else row['tp']}", now=ctx.now)
            executed.append(tr)
            row["action"] = f"{hit}_EXECUTED"
        elif hit:
            row["action"] = hit
        rows.append(row)
    acct = ledger.recompute(pf)
    for row in rows:
        p = ledger.position(pf, row["ticker"])
        src = p or {}
        e = float(row["entry"])
        row["pnl_pct"] = round((row["px"] - e) / e * 100, 2)
        row["dist_sl_pct"] = round((row["px"] - float(row["sl"])) / row["px"] * 100, 2) if row["sl"] else None
        row["risk_flag"] = src.get("risk_flag", "CLOSED" if not p else "OK")
    return rows, executed, acct


def write_text(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def write_json(p, data):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def report_path(name):
    return os.path.join(REPORTS_DIR, name)


def strip_html(t):
    import re
    return re.sub(r"<[^>]+>", "", t)


# ---------------------------------------------------------------- REAL positions (Roy's Futu account)
def real_snapshot(ctx, fx=None):
    """Load Roy's real book, quote each position, evaluate. Persists last prices (for the website)
    only on live runs. Never raises: a broken real book must not break the paper jobs."""
    from .. import realpos
    try:
        book = realpos.load()
        quotes = realpos.quotes_for(book)
        ev = realpos.evaluate(book, quotes, fx, ctx.now.date())
        if not ctx.dry_run and book.get("positions"):
            try:
                realpos.mark_prices({t: q["price"] for t, q in quotes.items() if q.get("ok")}, ctx.now)
            except Exception as e:
                print("[real] mark_prices skipped:", type(e).__name__)
        return book, ev
    except Exception as e:
        print("[real] real book unavailable:", type(e).__name__, e)
        book = realpos.empty_book()
        return book, realpos.evaluate(book, {}, fx, ctx.now.date())


def paper_bench():
    """(SPY %, QQQ %) since the paper book's rebase date (same period as the paper total return)."""
    rb = load_settings()["account"]["rebase_date"]
    return marketdata.return_since("SPY", rb), marketdata.return_since("QQQ", rb)


def paper_max_positions(regime=None):
    s = load_settings()
    mp = s["rules"]["max_positions"]
    if regime and regime in s["regimes"]:
        mp = min(mp, s["regimes"][regime]["max_positions"])
    return mp
