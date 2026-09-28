"""open job (ET 09:35): regime, positions vs prev close, SL/TP check+auto execution,
levels to watch, one teaching line. Always 1 Telegram message (once per session)."""
import json

from .. import clock, guard, ledger, marketdata, telegram
from ..config import load_settings, path
from ..engine import market_context
from ..messages import OPEN_TEACH, esc, f2, pct, footer, money, real_section, real_alerts, paper_brief, REAL_NOTE
from .common import (Ctx, gate_run, refresh_positions, write_json, write_text, report_path, real_snapshot, paper_bench,
                     paper_max_positions)

JOB = "open"


def build_message(ctx, mkt, rows, executed, alerts, teach, acct, real_ev=None, real_al=None, paper_bench_=(None, None)):
    """Roy's REAL positions first (+ real alerts), then the paper book (control group) condensed."""
    from .. import realpos
    real_ev = real_ev or realpos.evaluate(realpos.empty_book(), {}, acct.get("fx_usdhkd"))
    L = [f"<b>🔔 開市監控</b> {ctx.now.strftime('%Y-%m-%d %H:%M')} HKT（ET {ctx.now_et.strftime('%H:%M')}）",
         f"{mkt['emoji']} 市況：<b>{esc(mkt['regime_zh'])}</b>（VIX {f2(mkt['vix'])} / {mkt['regime']}）· "
         f"SPY {f2(mkt['spy'])} ({pct(mkt['spy_chg_pct'])}) · QQQ {f2(mkt['qqq'])} ({pct(mkt['qqq_chg_pct'])})", ""]
    L += real_section(real_ev)
    if real_al:
        L += ["<b>⚠️ 真倉預警</b>"] + [f"• {esc(a)}" for a in real_al] + [REAL_NOTE]
    elif real_ev.get("rows"):
        L.append("📍 今晚照預設止蝕／止賺做，唔好頭半個鐘用感覺加倉攤平。")
    notes = []
    for tr in executed:
        kind = "止損" if tr["reason"] == "STOP_LOSS" else "止盈"
        notes.append(f"✅ 紙上已{kind} {tr['ticker']} x{tr['shares']} @ ${f2(tr['exit_price'])}（淨 {tr['net_pnl_usd']:+.2f}）")
    for r in rows:
        if not r["action"].endswith("_EXECUTED"):
            notes.append(f"{r['ticker']} {pct(r['pnl_pct'], 1)}（vs昨收 {pct(r.get('chg_vs_prev'), 1)}，距SL {f2(r['dist_sl_pct'], 1)}%）")
    notes += [a.split(" ", 1)[1] for a in alerts if a.startswith("QUOTE ")]
    L += [""] + paper_brief(acct, len([r for r in rows if not r["action"].endswith("_EXECUTED")]),
                            paper_max_positions(mkt.get("regime")), paper_bench_[0], paper_bench_[1], notes)
    L += ["", f"📚 {esc(teach)}", "", footer()]
    return "\n".join(L)


def run(dry_run=False, force=False, legacy=False, now=None):
    ctx = Ctx(JOB, dry_run, force, legacy, now)
    ok, why = gate_run(ctx, "open")
    if not ok:
        print(f"[open] {why}")
        return {"status": "skipped", "reason": why}
    if guard.was_sent(ctx.session, JOB, "main") and not force:
        msg = f"[open] already sent for session {ctx.session} — not sending again (use --force)"
        print(msg)
        return {"status": "duplicate", "reason": msg}
    s = load_settings()
    pf = ledger.load()
    mkt = market_context()
    rows, executed, acct = refresh_positions(ctx, pf)
    alerts = []
    for r in rows:
        if r["action"].endswith("_EXECUTED"):
            continue
        if r.get("dist_sl_pct") is not None and r["dist_sl_pct"] < s["rules"]["near_sl_alert_pct"]:
            alerts.append(f"NEAR_SL {r['ticker']} 距止損 {r['dist_sl_pct']:.1f}%（{f2(r['px'])} vs SL {f2(r['sl'])}）")
        if r.get("chg_vs_prev") is not None and abs(r["chg_vs_prev"]) >= s["rules"]["open_move_alert_pct"]:
            alerts.append(f"OPEN_MOVE {r['ticker']} {'急升' if r['chg_vs_prev'] > 0 else '急跌'} {r['chg_vs_prev']:+.1f}% vs 昨收")
        if not r["quote_ok"]:
            alerts.append(f"QUOTE {r['ticker']} 報價異常（{r.get('source')}），今次唔執行 SL/TP")
    real_book, real_ev = real_snapshot(ctx, acct.get("fx_usdhkd") or mkt.get("fx_usdhkd"))
    real_al, _ = real_alerts(real_ev, day_move_pct=s["rules"]["open_move_alert_pct"], downside_only=False)
    teach = OPEN_TEACH.get(mkt["regime"], OPEN_TEACH["NORMAL"])
    real_status = {r["status"] for r in real_ev["rows"]}
    if "SL_HIT" in real_status or "NEAR_SL" in real_status:
        teach = OPEN_TEACH["NEAR_SL"]
    elif "TP_HIT" in real_status:
        teach = OPEN_TEACH["EXIT_TP"]
    elif any(r.get("chg_vs_prev") is not None and r["chg_vs_prev"] <= -s["rules"]["open_move_alert_pct"] for r in real_ev["rows"]):
        teach = OPEN_TEACH["GAP_DOWN"]
    elif any(t["reason"] == "STOP_LOSS" for t in executed):
        teach = OPEN_TEACH["EXIT_SL"]
    elif executed:
        teach = OPEN_TEACH["EXIT_TP"]
    elif any(a.startswith("NEAR_SL") for a in alerts):
        teach = OPEN_TEACH["NEAR_SL"]
    elif any(a.startswith("OPEN_MOVE") and "急跌" in a for a in alerts):
        teach = OPEN_TEACH["GAP_DOWN"]
    msg = build_message(ctx, mkt, rows, executed, alerts, teach, acct, real_ev, real_al, paper_bench())
    if not dry_run:
        ledger.save(pf)
    tg_ok, tg_res = telegram.send(msg, dry_run=dry_run, label="open")
    if tg_ok and not dry_run:
        guard.mark_sent(ctx.session, JOB, "main", tg_res)
    if not dry_run:
        guard.update(ctx.session, JOB, status="ok" if tg_ok else "telegram_failed", _inc_runs=True,
                     finished=clock.now_hkt().isoformat(timespec="seconds"),
                     executed=[t["id"] for t in executed])
    out = {"hkt": ctx.now.isoformat(), "session_date": ctx.session, "vix": mkt["vix"], "regime": mkt["regime"],
           "title": mkt["regime_zh"], "emoji": mkt["emoji"], "teach": teach,
           "price_watch": [f"{r['ticker']} 睇住 ${f2(r['sl'])} 止損、${f2(r['tp'])} 止盈（而家 ${f2(r['px'])}）" for r in rows],
           "alerts": alerts, "real_alerts": real_al, "positions": rows, "executed": executed, "equity_usd": acct["equity_usd"],
           "cash_usd": acct["cash_usd"], "telegram_ok": tg_ok,
           "telegram_result": str(tg_res), "dry_run": dry_run, "engine": "px v3-core"}
    if not dry_run:
        write_json(path("_last_open_monitor.json"), out)
        write_text(report_path(f"OpenMonitor_{ctx.now.date().isoformat()}.txt"), msg)
        try:
            from .. import archive
            archive.save_report("open", ctx.session, [msg], summary=f"開市監控 · {mkt['regime_zh']}（VIX {mkt['vix']}）")
        except Exception as e:
            print("[open] archive failed:", type(e).__name__)
    if legacy:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        print("---MSG---")
        print(msg)
        print("---TG---", tg_ok, tg_res)
    out["status"] = "ok" if tg_ok else "telegram_failed"
    return out
