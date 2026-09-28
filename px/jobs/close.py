"""close job (ET 17:00 = HKT 05:00 EDT / 06:00 EST; trading days only).

Ported from Hermes's 05:00 close report, rebuilt on the px engine:
  msg 1  🌙 收市報告 — Roy's REAL Futu positions first (price/cost/qty, P&L USD+HKD, dist SL/TP, days held,
         real SL/TP/big-drop alerts; he executes manually) + SPY/QQQ/VIX
  msg 2  🧪 紙上倉（對照組）— condensed: total P&L % vs SPY/QQQ, open count, today's paper actions (SL/TP auto on paper)
  msg 3  🧭 趨勢 + 今日掃描池最強/最弱 (Mag7 observer retired by Roy 2026-09-28)
  msg 4  🚀 明日觀察 Top 5 (opportunity scan on today's completed bar) + 🩺 health line
Writes data/pnl_history.json, data/scan.json, data/reports/close_report_<date>.*, portfolio.json."""
import json

from .. import archive, clock, engine, guard, ledger, marketdata, scan, schedule, telegram
from ..config import load_settings
from ..messages import esc, f2, pct, footer, money, scan_message, real_section, real_alerts, paper_brief, REAL_NOTE
from .common import Ctx, refresh_positions, real_snapshot, paper_bench, paper_max_positions

JOB = "close"
PARTS = ("summary", "positions", "trend", "scan")


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
        if all(guard.was_sent(ctx.session, JOB, p) for p in PARTS):
            return {"status": "duplicate", "reason": f"close already sent for {ctx.session}"}
    s = load_settings()
    pf = ledger.load()
    rows, executed, acct = refresh_positions(ctx, pf)
    mk = engine.market_context()
    hist = archive.load_pnl()
    prev = next((h for h in reversed(hist) if h.get("date") < ctx.session), None)
    day_chg = acct["equity_usd"] - prev["equity_usd"] if prev else None
    fx = acct.get("fx_usdhkd") or mk["fx_usdhkd"]
    real_book, real_ev = real_snapshot(ctx, fx)
    real_al, _ = real_alerts(real_ev)
    L = [f"<b>🌙 Project X 收市報告 — {ctx.session}</b>（美東收市後）"]
    L += real_section(real_ev)
    if real_al:
        L += [f"• {esc(a)}" for a in real_al] + [REAL_NOTE]
    L.append(f"🌍 SPY ${f2(mk['spy'])}（{pct(mk['spy_chg_pct'])}）· QQQ ${f2(mk['qqq'])}（{pct(mk['qqq_chg_pct'])}）· VIX {f2(mk['vix'])} {mk['emoji']}{esc(mk['regime_zh'])} · 匯率 {f2(fx, 3)}")
    m1 = "\n".join(L)
    # paper book (control group) — condensed
    notes = []
    for tr in executed:
        notes.append(f"✅ 紙上{'止損' if tr['reason'] == 'STOP_LOSS' else '止盈'} {tr['ticker']} x{tr['shares']} @ ${f2(tr['exit_price'])}（淨 {tr['net_pnl_usd']:+.2f}）")
    open_rows = [r for r in rows if not r["action"].endswith("_EXECUTED")]
    for r in open_rows:
        notes.append(f"{_flag(r)}{r['ticker']} {pct(r['pnl_pct'], 1)}（今日 {pct(r.get('chg_vs_prev'), 1)}，距SL {f2(r.get('dist_sl_pct'), 1)}%）")
    if day_chg is not None:
        notes.append(f"紙上權益今日 {day_chg:+.2f} USD")
    spy_ret, qqq_ret = paper_bench()
    m2 = "\n".join(paper_brief(acct, len(open_rows), paper_max_positions(mk.get("regime")), spy_ret, qqq_ret, notes))
    # trend + movers (market context = SPY/QQQ/VIX only)
    T = ["<b>🧭 趨勢狀態（已收市日 bar）</b>"]
    core = [r["ticker"] for r in real_ev["rows"]]  # real positions first, then core, then paper holdings
    core += [t for t in s["universe"]["core"] + [p["ticker"] for p in pf.get("positions", [])] if t not in core]
    movers = []
    for t in core:
        sg = engine.build_signal(t, mk["regime"], ledger.position(pf, t) is not None, ctx.now)
        if "error" in sg:
            continue
        T.append(f"{t}：{sg['trend_label']}（分 {sg['trend_score']:+d}）RSI {f2(sg['rsi'], 0)} · {esc(sg['action'])}")
    res = scan.run_scan(ctx.now, acct["equity_usd"], fx)
    allx = [x for x in res.get("all", []) if x.get("close")]
    try:
        chg = []
        for x in allx:
            df = marketdata.history(x["ticker"], period=s["scan"]["history_period"])
            c = df["Close"].dropna()
            chg.append((x["ticker"], (float(c.iloc[-1]) / float(c.iloc[-2]) - 1) * 100))
        chg.sort(key=lambda y: y[1])
        if chg:
            T.append(f"\n🏆 掃描池今日最強：{', '.join(f'{t} {v:+.1f}%' for t, v in chg[-3:][::-1])}")
            T.append(f"🥶 最弱：{', '.join(f'{t} {v:+.1f}%' for t, v in chg[:3])}")
    except Exception as e:
        print("movers skipped", type(e).__name__)
    m3 = "\n".join(T)
    health = schedule.health_line(clock.to_et(ctx.now).date(), ctx.now, exclude=("close",))
    m4 = scan_message(res, title="🚀 明日觀察 Top 5") + "\n\n" + health + "\n\n" + footer()
    msgs = dict(zip(PARTS, (m1, m2, m3, m4)))
    if not dry_run:
        ledger.save(pf)
        archive.append_pnl(ctx.session, acct, pf.get("positions", []), mk["spy"], mk["qqq"],
                           real={k: real_ev.get(k) for k in ("equity_usd", "cash_usd", "unrealized_usd", "realized_usd",
                                                             "return_pct", "n_open", "n_closed", "real_start_date")})
        archive.save_scan(res)
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
                okc, rc = telegram.send_photo(img, caption=f"📈 紙上倉（對照組）權益 vs SPY（{hist_now[0]['date']} → {ctx.session}）· "
                                              f"權益 US${f2(acct['equity_usd'])}（{pct(acct['total_return_pct'])}）",
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
