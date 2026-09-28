"""close job (ET 17:00 = HKT 05:00 EDT / 06:00 EST; trading days only).

Plain-language close report (Roy 2026-09-28) — ONE text message + the equity chart photo:
  🌙 收市報告: market mood (SPY/QQQ/VIX in words) -> Roy's REAL positions first (today, since buy in % + US$ + HK$,
  trend word, one-line reason) -> 資金 -> 買賣信號 (揸住／考慮賣出／考慮買入 sized for the real account) ->
  明日潛力股 (scan on today's completed bar, plain reasons) -> 紙上倉 one line -> health line -> site link.
Writes data/pnl_history.json, data/scan.json, data/reasons.json, data/reports/close_report_<date>.*, portfolio.json.
Yahoo rate-limited during the run -> data_wait (nothing pushed; the watchdog retries)."""
import json

from .. import archive, clock, engine, guard, ledger, marketdata, scan, schedule, telegram
from ..config import load_settings
from ..messages import esc, f2, pct, real_alerts, REAL_NOTE
from .common import (Ctx, refresh_positions, paper_bench, paper_max_positions, real_context, data_wait, pick_news,
                     annotate_scan, save_reasons)

JOB = "close"
PARTS = ("report",)
LEGACY_PARTS = ("summary", "positions", "trend", "scan")  # pre-2026-09-28 parts: any sent => session already reported


def _flag(p):
    pnl = p.get("pnl_pct") or 0
    d = p.get("dist_sl_pct")
    if d is not None and d < 2:
        return "🔴"
    if pnl <= -7:
        return "🟠"
    return "🟢"


def run(dry_run=False, force=False, legacy=False, now=None):
    ctx = Ctx(JOB, dry_run, force, legacy, now)
    d = ctx.now_et.date()
    import os
    if not force:
        if not clock.is_trading_day(d):
            return {"status": "skipped", "reason": f"US market closed on {d} ET ({clock.holiday_name(d) or 'weekend'})"}
        if not clock.session_closed(ctx.now_et) and os.environ.get("PX_RERUN") != "1":
            return {"status": "skipped", "reason": "session not closed yet"}
        win = load_settings()["schedule_et"]["close"]["window"]
        if not clock.in_window(win, ctx.now_et) and os.environ.get("PX_RERUN") != "1":
            # e.g. the 05:00 HKT line during EST = 16:00 ET: too early for final prices; the 06:00 line runs it
            return {"status": "skipped", "reason": f"outside close window {win[0]}-{win[1]} ET"}
        if (all(guard.was_sent(ctx.session, JOB, p) for p in PARTS)
                or any(guard.was_sent(ctx.session, JOB, p) for p in LEGACY_PARTS)):
            return {"status": "duplicate", "reason": f"close already sent for {ctx.session}"}
    s = load_settings()
    pf = ledger.load()
    rows, executed, acct = refresh_positions(ctx, pf)
    mk = engine.market_context()
    hist = archive.load_pnl()
    prev = next((h for h in reversed(hist) if h.get("date") < ctx.session), None)
    day_chg = acct["equity_usd"] - prev["equity_usd"] if prev else None
    fx = acct.get("fx_usdhkd") or mk["fx_usdhkd"]
    real_book, real_ev, rsn, trends = real_context(ctx, fx)
    real_al, _ = real_alerts(real_ev, reasons=rsn)
    from .. import plain, reasons as rs
    res = scan.run_scan(ctx.now, acct["equity_usd"], fx)
    news = pick_news(res)
    annotate_scan(res, news)
    notes = [f"紙上{'止損' if tr['reason'] == 'STOP_LOSS' else '止盈'} {tr['ticker']}（淨 {tr['net_pnl_usd']:+.2f} 美元）"
             for tr in executed]
    open_rows = [r for r in rows if not r["action"].endswith("_EXECUTED")]
    if day_chg is not None:
        notes.append(f"權益 {day_chg:+.2f} 美元")
    spy_ret, qqq_ret = paper_bench()
    L = [f"<b>🌙 收市報告 {ctx.session}</b>（美股已收市）",
         "🌍 " + " ".join(plain.market_lines(mk.get("spy_chg_pct"), mk.get("qqq_chg_pct"), mk.get("vix"), rs.market_headline())), ""]
    L += plain.real_block(real_ev, rsn, trends, "今日")
    if real_al:
        L += ["<b>⚠️ 要留意</b>"] + [f"• {esc(a)}" for a in real_al] + [REAL_NOTE]
    L.append(plain.capital_line(real_ev, mk.get("fx_live", True)))
    L += ["", "<b>🧭 買賣信號</b>"] + plain.hold_signal_lines(real_ev, trends)
    L += plain.buy_suggestion(real_ev, res, mk.get("regime"), market_open=False)[0]
    L += [""] + plain.picks_block(res, news, title="⭐ 明日潛力股")
    L += ["", plain.paper_line(acct, len(open_rows), paper_max_positions(mk.get("regime")), spy_ret, qqq_ret, notes)]
    health = schedule.health_line(clock.to_et(ctx.now).date(), ctx.now, exclude=("close",))
    L += [health, "", plain.footer_line()]
    msgs = {"report": "\n".join(L)}
    wait = data_wait(JOB)
    if wait:
        return wait
    if not dry_run:
        ledger.save(pf)
        archive.append_pnl(ctx.session, acct, pf.get("positions", []), mk["spy"], mk["qqq"],
                           real={k: real_ev.get(k) for k in ("equity_usd", "cash_usd", "unrealized_usd", "realized_usd",
                                                             "return_pct", "n_open", "n_closed", "real_start_date")})
        archive.save_scan(res)
        save_reasons(rsn, res, news)
        archive.save_report(JOB, ctx.session, [msgs[p] for p in PARTS],
                            summary=f"收市 · 真倉 {real_ev['n_open']} 隻（{pct(real_ev['return_pct'])}）· 紙上 {pct(acct['total_return_pct'])} · VIX {f2(mk['vix'])}",
                            pnl=acct["total_return_pct"])
    results = {}
    for part in PARTS:
        if guard.was_sent(ctx.session, JOB, part) and not force:
            results[part] = "already-sent"
            continue
        ok_, r = telegram.send(msgs[part], dry_run=dry_run, label=f"close/{part}")
        results[part] = "ok" if ok_ else f"failed: {r}"
        if ok_ and not dry_run:
            guard.mark_sent(ctx.session, JOB, part, r)
    # equity chart (photo) after the text parts; config-driven, guarded once per session
    if s["telegram"].get("send_charts", True) and not guard.was_sent(ctx.session, JOB, "chart"):
        try:
            from .. import charts
            hist_now = archive.load_pnl() if not dry_run else hist
            if len(hist_now) >= 2:
                img = charts.equity_chart(hist_now, archive.path_chart(f"equity_{ctx.session}.png") if not dry_run else "/tmp/px_equity_preview.png")
                okc, rc = telegram.send_photo(img, caption=f"📈 紙上倉（對照組）同 SPY 比較（{hist_now[0]['date']} → {ctx.session}）· "
                                              f"而家 US${f2(acct['equity_usd'])}（{pct(acct['total_return_pct'])}）",
                                              dry_run=dry_run, label="close/chart")
                results["chart"] = "ok" if okc else f"failed: {rc}"
                if okc and not dry_run:
                    guard.mark_sent(ctx.session, JOB, "chart", rc)
        except Exception as e:
            results["chart"] = f"failed: {type(e).__name__}"
    if dry_run or legacy:
        for p in PARTS:
            print(archive.strip_html(msgs[p]), "\n")
    print(json.dumps({"session": ctx.session, "telegram": results, "exits": [t["id"] for t in executed]}, ensure_ascii=False))
    good = all(v in ("ok", "already-sent") for k, v in results.items() if k != "chart")
    return {"status": "ok" if good else "telegram_failed", "telegram": results, "messages": msgs}
