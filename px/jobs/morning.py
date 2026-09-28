"""morning job (HKT 08:30 Tue–Sat, after a completed US session).

Ported from Hermes's 08:30 '隔夜複盤' (overnight review — NOT pre-market).
One message: equity + overnight index moves, positions with flags, tonight's
Top 5 (from data/scan.json written by the close job; recomputed if missing/stale),
upcoming earnings for held + Top 5 names, tonight's schedule in HKT."""
import datetime as dt
import json
import os

from .. import archive, clock, engine, guard, ledger, marketdata, realpos, scan, telegram
from ..config import load_settings
from ..messages import esc, f2, pct, footer, money, real_section, real_alerts, paper_brief, REAL_NOTE
from .common import Ctx, refresh_positions, real_snapshot, paper_bench, paper_max_positions

JOB = "morning"


def run(dry_run=False, force=False, legacy=False, now=None):
    ctx = Ctx(JOB, dry_run, force, legacy, now)
    et = ctx.now_et
    session = et.date()  # 08:30 HKT = previous evening ET -> the session being reviewed
    if not force:
        if not clock.is_trading_day(session):
            return {"status": "skipped", "reason": f"no US session on {session} ET ({clock.holiday_name(session) or 'weekend'})"}
        if not clock.session_closed(et):
            return {"status": "skipped", "reason": "US session not closed yet"}
        win = load_settings()["schedule_hkt"]["morning"]["window"]
        if not clock.in_window_hkt(win, ctx.now) and os.environ.get("PX_RERUN") != "1":
            return {"status": "skipped", "reason": f"outside morning window {win} HKT"}
        if guard.was_sent(session.isoformat(), JOB, "main"):
            return {"status": "duplicate", "reason": f"morning already sent for {session}"}
    s = load_settings()
    pf = ledger.load()
    rows, executed, acct = refresh_positions(ctx, pf)
    mk = engine.market_context()
    fx = acct.get("fx_usdhkd") or mk["fx_usdhkd"]
    sc = archive.load_scan()
    if not sc or (sc.get("bar_date") or "") < session.isoformat():
        sc = scan.run_scan(ctx.now, acct["equity_usd"], fx)
        if not dry_run:
            archive.save_scan(sc)
    nxt = clock.session_date(ctx.now)  # ET date now (evening before) -> tonight's session is next trading day
    tonight = session + dt.timedelta(days=1)
    while not clock.is_trading_day(tonight):
        tonight += dt.timedelta(days=1)
    open_hkt = clock.et_to_hkt_str("09:30", tonight)
    real_book, real_ev = real_snapshot(ctx, fx)
    real_al, _ = real_alerts(real_ev)
    L = [f"<b>🌅 Project X 隔夜複盤 — 美股 {session} 收市後</b>（香港早晨；唔係盤前）",
         f"🌍 SPY {pct(mk['spy_chg_pct'])} · QQQ {pct(mk['qqq_chg_pct'])} · VIX {f2(mk['vix'])} {mk['emoji']}{esc(mk['regime_zh'])}", ""]
    L += real_section(real_ev)
    if real_al:
        L += [f"• {esc(a)}" for a in real_al] + [REAL_NOTE]
    notes = [f"{'🔴' if (r.get('dist_sl_pct') or 99) < 2 else ''}{r['ticker']} {pct(r['pnl_pct'], 1)}（距SL {f2(r.get('dist_sl_pct'), 1)}%）" for r in rows]
    spy_ret, qqq_ret = paper_bench()
    L += [""] + paper_brief(acct, len(rows), paper_max_positions(mk.get("regime")), spy_ret, qqq_ret, notes, label="紙上隔夜")
    top = sc.get("top", [])
    L += ["", f"<b>🚀 今晚觀察 Top {len(top)}</b>（真倉建議；注碼按本金 ≈US${real_ev['equity_usd']:,.0f}、每隻 ≤25%、現金 ≥20%；詳情晚上每日分析）"]
    for i, x in enumerate(top, 1):
        sh, _b, why = realpos.suggest_shares(real_ev, float(x.get("live_price") or x["entry_zone"][1]), x.get("stop"))
        L.append(f"{i}. {x['ticker']} 入場區 ${f2(x['entry_zone'][0])}–{f2(x['entry_zone'][1])} · 止蝕 ${f2(x['stop'])} · 止賺 ${f2(x['target'])} · R:R {f2(x['rr'], 1)} · "
                 + ("已持有真倉，唔加倉" if x["ticker"] in {r["ticker"] for r in real_ev["rows"]} else (f"建議 {sh} 股" if sh else f"唔建議（{why}）")))
    cats = []
    held = [r["ticker"] for r in real_ev["rows"]] + [p["ticker"] for p in pf.get("positions", []) if p["ticker"] not in {r["ticker"] for r in real_ev["rows"]}]
    for x in top:
        if x.get("earnings_days") is not None and x["earnings_days"] <= 10:
            cats.append(f"{x['ticker']} {x['earnings_date']}")
    try:
        cal = scan.earnings_calendar(held, session, horizon_days=14) if held else {}
        cats += [f"{t}（持倉）{d}" for t, d in cal.items()]
    except Exception:
        pass
    L += ["", "<b>📅 未來兩星期催化劑</b>：" + ("、".join(cats) if cats else "持倉／Top 5 暫無已知業績日")]
    L += ["", f"🕘 今晚時間表（HKT）：開市 {open_hkt} · 開市監控 {clock.et_to_hkt_str('09:35', tonight)} · "
              f"每日分析 {clock.et_to_hkt_str('10:00', tonight)} · 收市報告 {clock.et_to_hkt_str('17:00', tonight)}", "",
          "今日任務：先寫低計劃（入場區／止損／注碼），晚上照計劃做，唔好 FOMO。", footer()]
    msg = "\n".join(L)
    if not dry_run:
        ledger.save(pf)
        archive.save_report(JOB, session.isoformat(), [msg], summary=f"隔夜複盤 · 真倉 {real_ev['n_open']} 隻（{pct(real_ev['return_pct'])}）· 紙上 {pct(acct['total_return_pct'])}", pnl=acct["total_return_pct"])
    ok_, r = telegram.send(msg, dry_run=dry_run, label="morning")
    if ok_ and not dry_run:
        guard.mark_sent(session.isoformat(), JOB, "main", r)
    if dry_run or legacy:
        print(archive.strip_html(msg))
    return {"status": "ok" if ok_ else "telegram_failed", "messages": {"main": msg}}
