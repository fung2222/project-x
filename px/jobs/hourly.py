"""hourly job (ET :06 past 10..16, trimmed on half days; see settings.schedule): MTM, SL/TP auto execution,
alert-only Telegram (+ one short status message on the first run of each session). Quiet unless something happens.
Prominent alerts = Roy's REAL positions (SL / TP / near-SL / day drop / day surge, each with a one-line reason; he
executes on Futu, the system only alerts) + VIX regime change. Paper-book events are one short line.
De-dup: real-alert conditions share one per-session store with the 5-minute realwatch (guard.real_alerted), and each
hourly slot pushes at most once ("slot@HH:MM" ET) so a re-run after a timeout can never re-push the same slot."""
import json
import os

from .. import clock, guard, ledger, marketdata, plain, schedule, telegram
from ..config import load_settings, path
from ..messages import esc, real_alerts, REAL_NOTE
from ..plain import vix_words
from .common import (Ctx, gate_run, refresh_positions, write_json, real_snapshot, paper_bench, paper_max_positions,
                     real_context)

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
    alerted = {**st.get("alerts", {}), **guard.real_alerted(ctx.session)}
    slot = schedule.slot_for(JOB, ctx.now)
    slot_key = f"slot@{slot.strftime('%H:%M')}" if slot else f"manual@{ctx.now.strftime('%H%M')}"
    if slot and guard.was_sent(ctx.session, JOB, slot_key) and not force:
        msg = f"[hourly] slot {slot_key} already pushed for session {ctx.session} — not pushing again"
        print(msg)
        return {"status": "duplicate", "reason": msg}
    pf = ledger.load()
    vix = marketdata.vix()
    regime = marketdata.regime_for(vix)
    rows, executed, acct = refresh_positions(ctx, pf)
    # ---------- REAL positions first (Roy executes on Futu; the system only alerts)
    real_book, real_ev = real_snapshot(ctx, acct.get("fx_usdhkd"))
    real_al, _new = real_alerts(real_ev, alerted)
    rsn, trends = {}, {}
    # ---------- paper book (control group): alerts demoted to one short line
    paper_notes = []
    for tr in executed:
        kind = "止盈" if tr["reason"] == "TAKE_PROFIT" else "止損"
        paper_notes.append(f"紙上{kind} {tr['ticker']}（淨 {tr['net_pnl_usd']:+.2f} 美元）")
    near_pct = s["rules"]["near_sl_alert_pct"]
    for r in rows:
        if r["action"].endswith("_EXECUTED"):
            continue
        t = r["ticker"]
        d = r.get("dist_sl_pct")
        if d is not None and d < near_pct:
            paper_notes.append(f"{t} 距止損 {d:.1f}%")
        if not r["quote_ok"]:
            paper_notes.append(f"{t} 報價異常，今次唔執行止蝕止賺")
    market = []
    prev_regime = st.get("last_regime")
    if prev_regime and prev_regime != regime and "UNKNOWN" not in (prev_regime, regime):
        rg = s["regimes"]
        market.append(f"🌡 大市情緒轉變：{rg.get(prev_regime, {}).get('title', prev_regime)} → {rg[regime]['title']}（{vix_words(vix)}）")
    first = s["telegram"].get("hourly_first_of_session_status", True) and not guard.was_sent(ctx.session, JOB, "status")
    need_push = bool(real_al) or bool(market) or bool(executed) or first
    alerts = real_al + market
    reason = "real_alerts" if real_al else ("alerts" if market else ("paper_exit" if executed else ("first_of_session" if first else "none")))
    msg = None
    tg_ok, tg_res = False, None
    if need_push:
        if real_ev.get("rows"):  # one-line reasons only when we actually push
            _b, _e, rsn, trends = real_context(ctx, acct.get("fx_usdhkd"))
            real_al, _new = real_alerts(real_ev, alerted, reasons=rsn)
            alerts = real_al + market
        head = "<b>🚨 真倉警報</b>" if real_al else ("<b>⚠️ 市況警報</b>" if market else "<b>📊 持倉監控</b>")
        L = [f"{head} {ctx.now.strftime('%m-%d %H:%M')} HKT"]
        L += [f"• {esc(a)}" for a in alerts]
        if real_al:
            L.append(REAL_NOTE)
        L += [""] + plain.real_block(real_ev, rsn, trends, "今日")
        spy_ret, qqq_ret = paper_bench()
        L += ["", plain.paper_line(acct, len(pf.get("positions", [])), paper_max_positions(regime), spy_ret, qqq_ret, paper_notes),
              "🌍 " + vix_words(vix)]
        if not alerts and not executed:
            L.append("✅ 一切正常（今個交易時段第一次報告；之後真倉有事先會再通知）")
        L += ["", plain.footer_line()]
        msg = "\n".join(L)
        tg_ok, tg_res = telegram.send(msg, dry_run=dry_run, label="hourly")
        if tg_ok and not dry_run:  # mark immediately: a crash/timeout after this line must not re-push
            guard.mark_sent(ctx.session, JOB, slot_key, tg_res)
            if first:
                guard.mark_sent(ctx.session, JOB, "status", tg_res)
            guard.save_real_alerted(ctx.session, {k: v for k, v in _new.items() if k.startswith("REAL:")}, by=JOB)
    alerted = _new if (not need_push or tg_ok) else alerted
    if not dry_run:
        ledger.save(pf)
        cur_px = {r["ticker"]: r["px"] for r in rows if not r["action"].endswith("_EXECUTED")}
        cur_real = {r["ticker"]: r["px"] for r in real_ev["rows"] if r.get("live")}
        guard.update(ctx.session, JOB, last_prices=cur_px, last_real_prices=cur_real,
                     last_regime=regime if regime != "UNKNOWN" else st.get("last_regime"),
                     alerts=alerted if (not need_push or tg_ok) else st.get("alerts", {}),
                     last_run=clock.now_hkt().isoformat(timespec="seconds"), status="ok", _inc_runs=True)
    out = {"hkt": ctx.now.isoformat(), "session_date": ctx.session, "vix": vix, "regime": regime,
           "positions": [{"ticker": r["ticker"], "shares": r["shares"], "px": round(r["px"], 2), "pnl_pct": r["pnl_pct"],
                          "sl": r["sl"], "tp": r["tp"], "dist_sl_pct": r["dist_sl_pct"], "action": r["action"],
                          "near_stop": (r.get("dist_sl_pct") or 99) < near_pct} for r in rows],
           "executed": executed, "equity_usd": acct["equity_usd"], "cash_usd": acct["cash_usd"], "alerts": alerts,
           "real_alerts": real_al, "paper_notes": paper_notes,
           "real_positions": [{k: r.get(k) for k in ("ticker", "shares", "entry", "px", "pnl_usd", "pnl_pct", "sl", "tp",
                                                     "dist_sl_pct", "dist_tp_pct", "days_held", "status")} for r in real_ev["rows"]],
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
