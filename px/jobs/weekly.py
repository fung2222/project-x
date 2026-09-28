"""weekly job (Monday HKT morning): plain 7-day review (Roy 2026-09-28) — market week in words, REAL positions first,
three-way comparison (real vs paper vs QQQ/SPY), 資金, this week's real trades, next week's 潛力股 with plain reasons,
one takeaway, paper one line, site link. Signal hit-rate sample stays in the JSON / website. 1 Telegram message.
Guard key = the HKT Monday date (weekly runs regardless of US holidays)."""
import datetime as dt
import json

from .. import archive, clock, guard, ledger, marketdata, telegram, engine
from ..config import load_settings, path
from ..messages import f2, pct, usd_s, hkd_s
from .common import Ctx, write_json, write_text, report_path, strip_html, real_snapshot, paper_max_positions, data_wait
from .daily import spy_return_since_rebase

JOB = "weekly"


def three_way(book, ev, acct):
    """Since real-trading start: real account vs paper book vs QQQ / SPY (None where not computable)."""
    d0 = book.get("real_start_date")
    if not d0:
        return {"since": None}
    hist = archive.load_pnl()
    base = next((h for h in reversed(hist) if h.get("date", "") < d0 and h.get("equity_usd")), None)
    base_eq = float(base["equity_usd"]) if base else float(acct.get("start_equity_usd") or 0)
    paper = round((float(acct["equity_usd"]) / base_eq - 1) * 100, 2) if base_eq else None
    return {"since": d0, "real_pct": ev.get("return_pct"), "real_usd": ev.get("return_usd"), "paper_pct": paper,
            "paper_base_date": base.get("date") if base else None,
            "qqq_pct": marketdata.return_since("QQQ", d0), "spy_pct": marketdata.return_since("SPY", d0),
            "n_closed": ev.get("n_closed"), "n_wins": ev.get("n_wins"), "win_rate_pct": ev.get("win_rate_pct")}


def three_way_lines(tw, book, ev, start, today):
    if not tw.get("since"):
        return ["<b>⚖️ 三方比較</b>：真倉未開始（第一次買入之後開始計：真倉 vs 紙上倉 vs 納指／標普）"]
    L = [f"<b>⚖️ 三方比較（真倉 {tw['since']} 起）</b>",
         f"真倉 {pct(tw['real_pct'])}（{usd_s(tw['real_usd'])} / {hkd_s((tw['real_usd'] or 0) * ev['fx'])}）· 紙上倉 {pct(tw['paper_pct'])}"
         f" · 納指(QQQ) {pct(tw['qqq_pct'])} · 標普(SPY) {pct(tw['spy_pct'])}"]
    wr = f"勝率 {f2(tw['win_rate_pct'], 0)}%（贏 {tw['n_wins']}／輸 {tw['n_closed'] - tw['n_wins']}）" if tw.get("n_closed") else "勝率 —"
    wk = [t for t in book.get("closed_trades", []) if str(start) <= str(t.get("exit_date", "")) <= str(today)]
    wk_buys = [p for p in book.get("positions", []) if str(start) <= str(p.get("entry_date", "")) <= str(today)]
    L.append(f"真倉交易：已賣出 {tw.get('n_closed') or 0} 筆 · {wr} · 持倉中 {ev['n_open']} 隻（要 20–30 筆先睇得出系統好唔好）")
    for t in wk:
        L.append(f"· {t['exit_date'][5:]} 真倉賣 {t['ticker']} {t['shares']}股 @{f2(t['exit_price'])} 淨 {usd_s(t['net_pnl_usd'])}（{pct(t.get('net_pnl_pct'))}，{t.get('exit_reason')}）")
    for p in wk_buys:
        L.append(f"· {p['entry_date'][5:]} 真倉買 {p['ticker']} {p['shares']}股 @{f2(p['entry_price'])}")
    return L


def week_change(t):
    """% change of the last completed close vs 5 trading days earlier (None if history is missing)."""
    try:
        c = marketdata.history(t, period="3mo")["Close"].dropna()
        return round((float(c.iloc[-1]) / float(c.iloc[-6]) - 1) * 100, 2)
    except Exception:
        return None


def run(dry_run=False, force=False, legacy=False, now=None):
    ctx = Ctx(JOB, dry_run, force, legacy, now)
    today = ctx.now.date()
    week_key = (today - dt.timedelta(days=today.weekday())).isoformat()  # HKT Monday
    if guard.was_sent(week_key, JOB, "main") and not force:
        msg = f"[weekly] already sent for week {week_key} — not sending again (use --force)"
        print(msg)
        return {"status": "duplicate", "reason": msg}
    start = today - dt.timedelta(days=7)
    pf = ledger.load()
    quotes = {p["ticker"]: marketdata.quote(p["ticker"]) for p in pf.get("positions", [])}
    ledger.mark(pf, {t: q["price"] for t, q in quotes.items() if q.get("ok")}, ctx.now)
    acct = ledger.recompute(pf)
    vix = marketdata.vix()
    regime = marketdata.regime_for(vix)
    reg = load_settings()["regimes"][regime]
    spy = marketdata.quote("SPY").get("price")
    qqq = marketdata.quote("QQQ").get("price")
    spy_ret = spy_return_since_rebase()
    trades = [t for t in pf.get("trade_log", []) if start.isoformat() <= str(t.get("date", "")) <= today.isoformat()]
    sig = engine.load_json(engine.SIGNALS_PATH, {})
    perf = sig.get("performance", {})
    by_day = {}
    for x in sig.get("signals", []):
        if start.isoformat() <= x.get("date", "") <= today.isoformat():
            by_day.setdefault(x["date"], []).append(x)
    n_buy = sum(1 for d in by_day.values() for x in d if x["signal"] == "BUY")
    n_hold = sum(1 for d in by_day.values() for x in d if x["signal"] == "HOLD")
    n_sell = sum(1 for d in by_day.values() for x in d if x["signal"] == "SELL")
    rep = engine.load_json(engine.REPORT_PATH, {})
    watch = sorted(rep.get("opportunity_signals", []) + rep.get("signals", []), key=lambda y: y.get("confidence", 0), reverse=True)
    watch = [x for x in watch if x.get("raw_signal") == "BUY"][:3]
    real_book, real_ev = real_snapshot(ctx, acct.get("fx_usdhkd"))
    tw = three_way(real_book, real_ev, acct)
    from .. import plain
    wk_spy, wk_qqq = week_change("SPY"), week_change("QQQ")
    mood = []
    if wk_spy is None and wk_qqq is None:
        mood.append("美股今個禮拜走勢數據暫缺。")
    else:
        mood.append(f"美股今個禮拜：標普 {plain.pct1(wk_spy)}、納指 {plain.pct1(wk_qqq)}。")
    mood.append(plain.vix_words(vix) + "。")
    L = [f"<b>📊 每週回顧</b> {start} 至 {today}", "🌍 " + " ".join(mood), ""]
    trends = {}
    for r in real_ev.get("rows", []):
        try:
            from .. import reasons as rs
            trends[r["ticker"]] = rs.trend_word(r["ticker"])
        except Exception:
            pass
    L += plain.real_block(real_ev, None, trends, "上個交易日")
    L.append(plain.capital_line(real_ev, marketdata.fx_info()["live"]))
    L += [""] + three_way_lines(tw, real_book, real_ev, start, today)
    sc = archive.load_scan() or {}
    L += [""] + plain.picks_block(sc, None, title="⭐ 下週潛力股（上個收市掃描）")
    L += ["", "<b>🎓 本週重點</b>：止蝕同止賺買之前定好，到價就照做；每次最多蝕本金 2%，唔攤平、唔追高。"]
    qqq_ret = marketdata.return_since("QQQ", load_settings()["account"]["rebase_date"])
    n_b = sum(1 for t in trades if t.get("action") == "BUY")
    n_s = sum(1 for t in trades if t.get("action") == "SELL")
    L += ["", plain.paper_line(acct, len(pf.get("positions", [])), paper_max_positions(regime), spy_ret, qqq_ret,
                               [f"本週買 {n_b}／賣 {n_s}"] if trades else None), "", plain.footer_line()]
    msg = "\n".join(L)
    wait = data_wait(JOB)
    if wait:
        return wait
    tg_ok, tg_res = telegram.send(msg, dry_run=dry_run, label="weekly")
    out = {"type": "weekly_report", "week_start": str(start), "week_end": str(today), "generated": ctx.now.isoformat(),
           "market": {"vix": vix, "regime": reg["title"], "spy_price": spy, "qqq_price": qqq},
           "real": {"summary": {k: real_ev.get(k) for k in ("n_open", "equity_usd", "cash_usd", "unrealized_usd", "realized_usd",
                                                         "return_pct", "n_closed", "n_wins", "win_rate_pct", "real_start_date")},
                    "three_way": tw},
           "account": {k: acct.get(k) for k in ("equity_usd", "cash_usd", "cash_pct", "realized_pnl_usd", "unrealized_pnl_usd",
                                                 "total_pnl_usd", "total_return_pct")}, "spy_return_since_rebase_pct": spy_ret,
           "trades": trades, "week_summary": {"days_analyzed": len(by_day), "buy_signals": n_buy, "hold_signals": n_hold,
                                              "sell_signals": n_sell}, "signal_hit_rate_sample": perf,
           "telegram_ok": tg_ok, "engine": "px v3-core"}
    if not dry_run:
        ledger.save(pf)
        write_json(report_path(f"WeeklyReport_{today}.json"), out)
        write_text(report_path(f"WeeklySummary_{today}.txt"), strip_html(msg))
        try:
            archive.save_report("weekly", str(today), [msg], summary=f"每週回顧 {start} 至 {today}")
        except Exception as e:
            print("[weekly] archive failed:", type(e).__name__)
        if tg_ok:
            guard.mark_sent(week_key, JOB, "main", tg_res)
        guard.update(week_key, JOB, status="ok" if tg_ok else "telegram_failed", _inc_runs=True,
                     finished=clock.now_hkt().isoformat(timespec="seconds"))
    out["status"] = "ok" if tg_ok else "telegram_failed"
    return out
