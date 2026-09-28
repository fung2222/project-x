"""morning job (HKT 08:30 Tue–Sat, after a completed US session).

Plain-language overnight review (Roy 2026-09-28; NOT pre-market). One message: market mood overnight ->
Roy's REAL positions first (overnight move, since buy, trend word, one-line reason) -> 資金 -> tonight's 買賣信號 ->
tonight's 潛力股 (data/scan.json from the close job; recomputed if missing/stale) -> upcoming earnings for held/picks ->
tonight's open time in HKT -> paper one line -> site link."""
import datetime as dt
import json
import os

from .. import archive, clock, engine, guard, ledger, scan, telegram
from ..config import load_settings
from ..messages import esc, pct, real_alerts, REAL_NOTE
from .common import (Ctx, refresh_positions, paper_bench, paper_max_positions, real_context, data_wait, pick_news,
                     annotate_scan)

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
    real_book, real_ev, rsn, trends = real_context(ctx, fx)
    real_al, _ = real_alerts(real_ev, reasons=rsn)
    from .. import plain
    news = pick_news(sc)
    annotate_scan(sc, news)
    L = [f"<b>🌅 早晨｜美股 {session} 收市回顧</b>",
         "🌍 " + " ".join(plain.market_lines(mk.get("spy_chg_pct"), mk.get("qqq_chg_pct"), mk.get("vix"), when="隔晚")), ""]
    L += plain.real_block(real_ev, rsn, trends, "隔晚")
    if real_al:
        L += ["<b>⚠️ 要留意</b>"] + [f"• {esc(a)}" for a in real_al] + [REAL_NOTE]
    L.append(plain.capital_line(real_ev, mk.get("fx_live", True)))
    L += ["", "<b>🧭 今晚買賣信號</b>"] + plain.hold_signal_lines(real_ev, trends)
    L += plain.buy_suggestion(real_ev, sc, mk.get("regime"), market_open=False)[0]
    L += [""] + plain.picks_block(sc, news, title="⭐ 今晚潛力股")
    cats = []
    held = [r["ticker"] for r in real_ev["rows"]]
    for x in (sc.get("top") or [])[:3]:
        if x.get("earnings_days") is not None and x["earnings_days"] <= 10:
            cats.append(f"{x['ticker']} {x['earnings_date'][5:]}")
    try:
        cal = scan.earnings_calendar(held, session, horizon_days=14) if held else {}
        cats += [f"{t}（你持有）{d[5:]}" for t, d in cal.items()]
    except Exception:
        pass
    if cats:
        L += ["", "📅 快出業績（股價可能大上大落）：" + "、".join(cats)]
    L += ["", f"🕘 今晚美股 {open_hkt} 開市（香港時間）。先諗定買咩、買幾多、止蝕位，唔好臨場 FOMO。"]
    spy_ret, qqq_ret = paper_bench()
    L += ["", plain.paper_line(acct, len(rows), paper_max_positions(mk.get("regime")), spy_ret, qqq_ret), "",
          plain.footer_line()]
    wait = data_wait(JOB)
    if wait:
        return wait
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
