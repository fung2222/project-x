"""open job (ET 09:35): plain-language opening note — market mood, Roy's REAL positions first (today's move,
since buy, trend word, one-line reason), 資金, alerts, paper book one line, site link. Paper SL/TP auto execution.
Always 1 Telegram message (once per session). Yahoo rate-limited -> data_wait (no push with holes)."""
import json

from .. import clock, guard, ledger, marketdata, telegram
from ..config import load_settings, path
from ..engine import market_context
from ..messages import OPEN_TEACH, esc, f2, pct, footer, money, real_section, real_alerts, paper_brief, REAL_NOTE
from .common import (Ctx, gate_run, refresh_positions, write_json, write_text, report_path, real_snapshot, paper_bench,
                     paper_max_positions, real_context, data_wait, save_reasons)

JOB = "open"


def build_message(ctx, mkt, rows, executed, alerts, teach, acct, real_ev=None, real_al=None, paper_bench_=(None, None),
                  reasons=None, trends=None):
    """Plain: market mood -> REAL positions (+ alerts) -> 資金 -> paper one line -> site link."""
    from .. import plain, realpos
    real_ev = real_ev or realpos.evaluate(realpos.empty_book(), {}, acct.get("fx_usdhkd"))
    dw = plain.day_word(mkt.get("session_date"), ctx.now)
    L = [f"<b>🔔 美股開市報告</b>（{plain.session_label(ctx.now)}，{ctx.now.strftime('%m-%d %H:%M')} HKT）",
         "🌍 " + " ".join(plain.market_lines(mkt.get("spy_chg_pct"), mkt.get("qqq_chg_pct"), mkt.get("vix"),
                                            when="開市" if dw == "今日" else dw)), ""]
    L += plain.real_block(real_ev, reasons, trends, dw)
    if real_al:
        L += ["<b>⚠️ 要留意</b>"] + [f"• {esc(a)}" for a in real_al] + [REAL_NOTE]
    elif real_ev.get("rows"):
        L.append("📍 照預設止蝕／止賺做，唔好頭半個鐘用感覺加倉。")
    L.append(plain.capital_line(real_ev, mkt.get("fx_live", True)))
    notes = []
    for tr in executed:
        kind = "止損" if tr["reason"] == "STOP_LOSS" else "止盈"
        notes.append(f"紙上已{kind} {tr['ticker']}（淨 {tr['net_pnl_usd']:+.2f} 美元）")
    for r in rows:
        if not r["action"].endswith("_EXECUTED") and r.get("dist_sl_pct") is not None and r["dist_sl_pct"] < 2:
            notes.append(f"{r['ticker']} 距止損 {f2(r['dist_sl_pct'], 1)}%")
    notes += [a.split(" ", 1)[1] for a in alerts if a.startswith("QUOTE ")]
    L += ["", plain.paper_line(acct, len([r for r in rows if not r["action"].endswith("_EXECUTED")]),
                               paper_max_positions(mkt.get("regime")), paper_bench_[0], paper_bench_[1], notes)]
    L += ["", plain.footer_line()]
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
    real_book, real_ev, rsn, trends = real_context(ctx, mkt.get("fx_usdhkd") or acct.get("fx_usdhkd"))
    real_al, _ = real_alerts(real_ev, reasons=rsn)
    wait = data_wait(JOB)
    if wait:
        return wait
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
    msg = build_message(ctx, mkt, rows, executed, alerts, teach, acct, real_ev, real_al, paper_bench(), rsn, trends)
    save_reasons(rsn) if not dry_run else None
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
