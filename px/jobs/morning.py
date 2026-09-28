"""morning job (HKT 08:30 Tue–Sat, after a completed US session).

Ported from Hermes's 08:30 '隔夜複盤' (overnight review — NOT pre-market).
One message: equity + overnight index moves, positions with flags, tonight's
Top 5 (from data/scan.json written by the close job; recomputed if missing/stale),
upcoming earnings for held + Top 5 names, tonight's schedule in HKT."""
import datetime as dt
import json
import os

from .. import archive, clock, engine, guard, ledger, marketdata, scan, telegram
from ..config import load_settings
from ..messages import esc, f2, pct, footer, money
from .common import Ctx, refresh_positions

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
    L = [f"<b>🌅 Project X 隔夜複盤 — 美股 {session} 收市後</b>（香港早晨；唔係盤前）",
         f"💼 權益 {money(acct['equity_usd'], fx)}（{pct(acct['total_return_pct'])}）· 現金 {f2(acct['cash_pct'], 1)}%",
         f"🌍 SPY {pct(mk['spy_chg_pct'])} · QQQ {pct(mk['qqq_chg_pct'])} · VIX {f2(mk['vix'])} {mk['emoji']}{esc(mk['regime_zh'])}", "",
         "<b>💼 持倉快睇</b>"]
    for r in rows:
        L.append(f"{'🔴' if (r.get('dist_sl_pct') or 99) < 2 else '🟢'} {r['ticker']} ${f2(r['px'])}（{pct(r['pnl_pct'])}）· SL ${f2(r['sl'])}（距 {f2(r.get('dist_sl_pct'), 1)}%）· TP ${f2(r['tp'])}")
    if not rows:
        L.append("空倉")
    top = sc.get("top", [])
    L += ["", f"<b>🚀 今晚觀察 Top {len(top)}</b>（詳情晚上每日分析）"]
    for i, x in enumerate(top, 1):
        L.append(f"{i}. {x['ticker']} 入場區 ${f2(x['entry_zone'][0])}–{f2(x['entry_zone'][1])} · SL ${f2(x['stop'])} · 目標 ${f2(x['target'])} · R:R {f2(x['rr'], 1)} · {x['shares']} 股")
    cats = []
    held = [p["ticker"] for p in pf.get("positions", [])]
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
        archive.save_report(JOB, session.isoformat(), [msg], summary=f"隔夜複盤 · 權益 US${f2(acct['equity_usd'])}", pnl=acct["total_return_pct"])
    ok_, r = telegram.send(msg, dry_run=dry_run, label="morning")
    if ok_ and not dry_run:
        guard.mark_sent(session.isoformat(), JOB, "main", r)
    if dry_run or legacy:
        print(archive.strip_html(msg))
    return {"status": "ok" if ok_ else "telegram_failed", "messages": {"main": msg}}
