"""hourly job (ET :06 past 10..16, trimmed on half days; see settings.schedule): MTM, SL/TP auto execution,
alert-only Telegram (+ one status message on the first run of each session).
Alerts are de-duplicated per session in state/job_runs.json."""
import json
import os

from .. import clock, guard, ledger, marketdata, telegram
from ..config import load_settings, path
from ..messages import esc, f2, pct, footer, money
from .common import Ctx, gate_run, refresh_positions, write_json

JOB = "hourly"


def _write_quiet(day):
    with open(path(".last_hourly_quiet_hkt"), "w") as f:
        f.write(day)


def run(dry_run=False, force=False, legacy=False, now=None):
    ctx = Ctx(JOB, dry_run, force, legacy, now)
    ok, why = gate_run(ctx, "hourly")
    if not ok:
        print(f"[hourly] {why}")
        return {"status": "skipped", "reason": why}
    s = load_settings()
    st = guard.job_state(ctx.session, JOB)
    prev_px = st.get("last_prices", {})
    if not prev_px:  # fall back to legacy file from the old runner
        try:
            with open(path("_last_hourly_check.json"), encoding="utf-8") as f:
                prev = json.load(f)
            prev_px = {p["ticker"]: p["px"] for p in prev.get("positions", [])}
            st.setdefault("last_regime", prev.get("regime"))
        except Exception:
            pass
    alerted = dict(st.get("alerts", {}))
    pf = ledger.load()
    vix = marketdata.vix()
    regime = marketdata.regime_for(vix)
    rows, executed, acct = refresh_positions(ctx, pf)
    alerts = []
    for tr in executed:
        kind = "止盈" if tr["reason"] == "TAKE_PROFIT" else "止損"
        alerts.append(f"✅ 紙上{kind} {tr['ticker']} x{tr['shares']} @ ${f2(tr['exit_price'])}"
                      f"（入 {f2(tr['entry_price'])}，淨 {tr['net_pnl_usd']:+.2f} / {tr['net_pnl_pct']:+.1f}%）")
    near_pct = s["rules"]["near_sl_alert_pct"]
    for r in rows:
        if r["action"].endswith("_EXECUTED"):
            continue
        t = r["ticker"]
        d = r.get("dist_sl_pct")
        if d is not None and d < near_pct:
            last = alerted.get(f"{t}:NEAR_SL")
            if last is None or d <= float(last) - 1.0:  # re-alert only if 1pp closer
                alerts.append(f"⚠️ {t} 距止損 {d:.1f}%（${f2(r['px'])} vs SL ${f2(r['sl'])}）")
                alerted[f"{t}:NEAR_SL"] = d
        if t in prev_px and prev_px[t]:
            chg = (r["px"] - prev_px[t]) / prev_px[t] * 100
            if abs(chg) >= s["rules"]["big_move_alert_pct"]:
                alerts.append(f"📈 {t} 大波動 {f2(prev_px[t])}→{f2(r['px'])}（{chg:+.1f}%）" if chg > 0 else
                              f"📉 {t} 大波動 {f2(prev_px[t])}→{f2(r['px'])}（{chg:+.1f}%）")
        if not r["quote_ok"]:
            key = f"{t}:QUOTE"
            if key not in alerted:
                alerts.append(f"🛠 {t} 報價異常（{r.get('source')}），今次唔執行 SL/TP")
                alerted[key] = 1
    prev_regime = st.get("last_regime")
    if prev_regime and prev_regime != regime:
        alerts.append(f"🌡 VIX 市況轉變 {prev_regime} → {regime}（VIX {f2(vix)}）")
    first = s["telegram"].get("hourly_first_of_session_status", True) and not guard.was_sent(ctx.session, JOB, "status")
    need_push = bool(alerts) or first
    reason = "alerts" if alerts else ("first_of_session" if first else "none")
    msg = None
    tg_ok, tg_res = False, None
    if need_push:
        head = "<b>⚠️ 持倉警報</b>" if alerts else "<b>📊 持倉監控</b>"
        L = [f"{head} {ctx.now.strftime('%Y-%m-%d %H:%M')} HKT（ET {ctx.now_et.strftime('%H:%M')}）",
             f"VIX {f2(vix)} {regime} · 權益 {money(acct['equity_usd'], acct['fx_usdhkd'])} · 現金 {f2(acct['cash_pct'],1)}%"]
        L += [f"• {esc(a)}" for a in alerts]
        for r in rows:
            if not r["action"].endswith("_EXECUTED"):
                L.append(f"{r['ticker']} x{r['shares']} @ {f2(r['px'])}（{pct(r['pnl_pct'])}）SL {f2(r['sl'])} / TP {f2(r['tp'])} 距SL {f2(r['dist_sl_pct'],1)}%")
        if not alerts:
            L.append("✅ 持倉監控正常（今個交易時段首次；之後有事先會再通知）")
        L += ["", footer()]
        msg = "\n".join(L)
        tg_ok, tg_res = telegram.send(msg, dry_run=dry_run, label="hourly")
    if not dry_run:
        ledger.save(pf)
        if need_push and tg_ok:
            guard.mark_sent(ctx.session, JOB, "status" if first and not alerts else f"alert@{ctx.now.strftime('%H%M')}", tg_res)
            if first and alerts:
                guard.mark_sent(ctx.session, JOB, "status", tg_res)
        cur_px = {r["ticker"]: r["px"] for r in rows if not r["action"].endswith("_EXECUTED")}
        guard.update(ctx.session, JOB, last_prices=cur_px, last_regime=regime,
                     alerts=alerted if (not need_push or tg_ok) else st.get("alerts", {}),
                     last_run=clock.now_hkt().isoformat(timespec="seconds"), status="ok", _inc_runs=True)
    out = {"hkt": ctx.now.isoformat(), "session_date": ctx.session, "vix": vix, "regime": regime,
           "positions": [{"ticker": r["ticker"], "shares": r["shares"], "px": round(r["px"], 2), "pnl_pct": r["pnl_pct"],
                          "sl": r["sl"], "tp": r["tp"], "dist_sl_pct": r["dist_sl_pct"], "action": r["action"],
                          "near_stop": (r.get("dist_sl_pct") or 99) < near_pct} for r in rows],
           "executed": executed, "equity_usd": acct["equity_usd"], "cash_usd": acct["cash_usd"], "alerts": alerts,
           "need_push": need_push, "first_today": first, "push_reason": reason, "pushed": bool(tg_ok) and not dry_run,
           "push_err": None if tg_ok or not need_push else str(tg_res), "dry_run": dry_run, "engine": "px v3-core"}
    if not dry_run:
        write_json(path("_last_hourly_check.json"), out)
        _write_quiet(ctx.now.date().isoformat())
        _legacy_state(ctx, out, pf)
    if legacy or dry_run:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    out["status"] = "ok" if (tg_ok or not need_push) else "telegram_failed"
    return out


def _legacy_state(ctx, out, pf):
    """Keep writing the Grok Bot automation state file (only if that directory exists on this machine)."""
    p = load_settings().get("legacy", {}).get("grokbot_state_path")
    if not p or not os.path.isdir(os.path.dirname(p)):
        return
    try:
        state = {
            "last_check_hkt_date": ctx.now.date().isoformat(), "last_check_iso": ctx.now.isoformat(),
            "last_vix": out["vix"], "last_regime": out["regime"], "last_alerts": out["alerts"],
            "last_near_stop": [p["ticker"] for p in out["positions"] if p.get("near_stop")], "sig_changes": [],
            "telegram_sent": out["pushed"], "prices": {p["ticker"]: p["px"] for p in out["positions"]},
            "equity_usd": out["equity_usd"], "cash_usd": out["cash_usd"],
            "eval": [{"ticker": p["ticker"], "shares": p["shares"], "entry": next((x["entry_price"] for x in pf["positions"]
                      if x["ticker"] == p["ticker"]), None), "current": p["px"], "pnl_pct": p["pnl_pct"], "stop": p["sl"],
                      "take_profit": p["tp"], "dist_to_sl_pct": p["dist_sl_pct"],
                      "triggered_sl": p["action"].startswith("STOP_LOSS"), "triggered_tp": p["action"].startswith("TAKE_PROFIT"),
                      "near_stop": p["near_stop"]} for p in out["positions"]],
            "executed": [t["id"] for t in out["executed"]],
            "quote_note": "hourly tracker (px v3-core; SL/TP auto-executed in code)",
            "push_reason": out["push_reason"], "need_wake_parent": bool(out["alerts"]),
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("legacy state write skipped:", type(e).__name__)
