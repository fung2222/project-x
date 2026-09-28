"""open job (ET 09:35): regime, positions vs prev close, SL/TP check+auto execution,
levels to watch, one teaching line. Always 1 Telegram message (once per session)."""
import json

from .. import clock, guard, ledger, marketdata, telegram
from ..config import load_settings, path
from ..engine import market_context
from ..messages import OPEN_TEACH, esc, f2, pct, footer, money
from .common import Ctx, gate_run, refresh_positions, write_json, write_text, report_path

JOB = "open"


def build_message(ctx, mkt, rows, executed, alerts, teach, acct):
    s = load_settings()
    L = [f"<b>🔔 開市監控</b> {ctx.now.strftime('%Y-%m-%d %H:%M')} HKT（ET {ctx.now_et.strftime('%H:%M')}）",
         f"{mkt['emoji']} 市況：<b>{esc(mkt['regime_zh'])}</b>（VIX {f2(mkt['vix'])} / {mkt['regime']}）",
         f"SPY {f2(mkt['spy'])} ({pct(mkt['spy_chg_pct'])}) · QQQ {f2(mkt['qqq'])} ({pct(mkt['qqq_chg_pct'])})",
         f"權益 {money(acct['equity_usd'], acct['fx_usdhkd'])} · 現金 {f2(acct['cash_pct'],1)}%"]
    open_rows = [r for r in rows if not r["action"].endswith("_EXECUTED")]
    if open_rows:
        L += ["", "<b>📍 今晚要睇嘅價位</b>"]
        for r in open_rows:
            L.append(f"• {r['ticker']} 止損 ${f2(r['sl'])} / 止盈 ${f2(r['tp'])}（而家 ${f2(r['px'])}，距SL {f2(r['dist_sl_pct'],1)}%）")
    if rows:
        L += ["", "<b>📦 持倉</b>"]
        for r in rows:
            chg = f"vs昨收 {pct(r['chg_vs_prev'],1)}" if r.get("chg_vs_prev") is not None else "vs昨收 n/a"
            L.append(f"• <b>{r['ticker']}</b> x{r['shares']} @ ${f2(r['px'])}（{pct(r['pnl_pct'])}｜{chg}｜{r['action']}）")
    else:
        L += ["", "📦 持倉：空倉"]
    for tr in executed:
        kind = "止損" if tr["reason"] == "STOP_LOSS" else "止盈"
        L.append(f"✅ 紙上已{kind}：{tr['ticker']} x{tr['shares']} @ ${f2(tr['exit_price'])}，淨 {tr['net_pnl_usd']:+.2f}")
    if alerts:
        L += ["", "<b>⚠️ 風險預警</b>"] + [f"• {esc(a)}" for a in alerts]
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
    teach = OPEN_TEACH.get(mkt["regime"], OPEN_TEACH["NORMAL"])
    if any(t["reason"] == "STOP_LOSS" for t in executed):
        teach = OPEN_TEACH["EXIT_SL"]
    elif executed:
        teach = OPEN_TEACH["EXIT_TP"]
    elif any(a.startswith("NEAR_SL") for a in alerts):
        teach = OPEN_TEACH["NEAR_SL"]
    elif any(a.startswith("OPEN_MOVE") and "急跌" in a for a in alerts):
        teach = OPEN_TEACH["GAP_DOWN"]
    msg = build_message(ctx, mkt, rows, executed, alerts, teach, acct)
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
           "alerts": alerts, "positions": rows, "executed": executed, "equity_usd": acct["equity_usd"],
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
