"""weekly job (Monday HKT morning): 7-day review, trades, equity vs start and SPY,
signal hit-rate SAMPLE (not trade count), lessons, next-week watchlist. 1 Telegram message.
Guard key = the HKT Monday date (weekly runs regardless of US holidays)."""
import datetime as dt
import json

from .. import clock, guard, ledger, marketdata, telegram, engine
from ..config import load_settings, path
from ..messages import esc, f2, pct, footer, money
from .common import Ctx, write_json, write_text, report_path, strip_html
from .daily import spy_return_since_rebase

JOB = "weekly"


def run(dry_run=False, force=False, legacy=False, now=None):
    ctx = Ctx(JOB, dry_run, force, legacy, now)
    today = ctx.now.date()
    week_key = (today - dt.timedelta(days=today.weekday())).isoformat()  # HKT Monday
    if guard.was_sent(week_key, JOB, "main") and not force:
        msg = f"[weekly] already sent for week {week_key} — not sending again (use --force)"
        print(msg)
        return {"status": "duplicate", "reason": msg}
    start = today - dt.timedelta(days=7)
    pf = ledger.load()
    quotes = {p["ticker"]: marketdata.quote(p["ticker"]) for p in pf.get("positions", [])}
    ledger.mark(pf, {t: q["price"] for t, q in quotes.items() if q.get("ok")}, ctx.now)
    acct = ledger.recompute(pf)
    vix = marketdata.vix()
    regime = marketdata.regime_for(vix)
    reg = load_settings()["regimes"][regime]
    spy = marketdata.quote("SPY").get("price")
    qqq = marketdata.quote("QQQ").get("price")
    spy_ret = spy_return_since_rebase()
    trades = [t for t in pf.get("trade_log", []) if start.isoformat() <= str(t.get("date", "")) <= today.isoformat()]
    sig = engine.load_json(engine.SIGNALS_PATH, {})
    perf = sig.get("performance", {})
    by_day = {}
    for x in sig.get("signals", []):
        if start.isoformat() <= x.get("date", "") <= today.isoformat():
            by_day.setdefault(x["date"], []).append(x)
    n_buy = sum(1 for d in by_day.values() for x in d if x["signal"] == "BUY")
    n_hold = sum(1 for d in by_day.values() for x in d if x["signal"] == "HOLD")
    n_sell = sum(1 for d in by_day.values() for x in d if x["signal"] == "SELL")
    rep = engine.load_json(engine.REPORT_PATH, {})
    watch = sorted(rep.get("opportunity_signals", []) + rep.get("signals", []), key=lambda y: y.get("confidence", 0), reverse=True)
    watch = [x for x in watch if x.get("raw_signal") == "BUY"][:3]
    L = [f"<b>📊 Project X 每週回顧</b> {start} 至 {today}",
         f"{reg['emoji']} VIX {f2(vix)} {reg['title']} · SPY {f2(spy)} · QQQ {f2(qqq)}", "",
         "<b>💼 組合</b>",
         f"權益 {money(acct['equity_usd'], acct['fx_usdhkd'])} · 現金 {f2(acct['cash_pct'],1)}%",
         f"對起始 USD {acct['start_equity_usd']:.2f}：{acct['total_return_usd']:+.2f}（{pct(acct['total_return_pct'])}）"
         + (f" vs SPY {pct(spy_ret)}" if spy_ret is not None else ""),
         f"已實現 {acct['realized_pnl_usd']:+.2f} · 未實現 {acct['unrealized_pnl_usd']:+.2f}"]
    for p in pf.get("positions", []):
        L.append(f"• {p['ticker']} x{p['shares']} @{f2(p['entry_price'])} → {f2(p.get('current_price'))}（{pct(p.get('pnl_pct'))}）"
                 f" SL {f2(p.get('stop_loss_price'))} / TP {f2(p.get('take_profit_price'))} 距SL {f2(p.get('dist_to_sl_pct'),1)}%")
    L += ["", "<b>📝 本週交易</b>"]
    if trades:
        for t in trades:
            if t["action"] == "SELL":
                L.append(f"• {t['date'][5:]} {t['ticker']} x{t['shares']} {t.get('reason')} @{f2(t.get('exit_price'))} 淨 {float(t.get('net_pnl_usd') or 0):+.2f}")
            elif t["action"] == "BUY":
                L.append(f"• {t['date'][5:]} 買入 {t['ticker']} x{t['shares']} @{f2(t.get('entry_price'))}（{esc(t.get('setup') or t.get('reason',''))[:40]}）")
    else:
        L.append("• 本週冇開倉／平倉")
    L += ["", f"<b>📡 信號</b>（核心＋次要，{len(by_day)} 日）BUY {n_buy} · HOLD {n_hold} · SELL {n_sell}"]
    if perf.get("total_signals"):
        L.append(f"信號命中率（樣本 {perf['total_signals']}，唔係交易筆數）：{f2(perf.get('hit_rate_pct'),0)}%"
                 f"（中 {perf.get('hits')}／部分 {perf.get('partials')}／失誤 {perf.get('misses')}）")
    L += ["", "<b>🎓 本週重點</b>",
          "1. 止損／止盈由 code 自動執行，唔靠臨場感覺。",
          "2. 每筆風險 ≤2% 權益、每日最多 1 個新倉、同主題 1 隻、唔攤平。",
          "3. 止盈後冷靜期內唔追返；等新 setup。"]
    if watch:
        L += ["", "<b>👀 下週觀察</b>"] + [f"• {x['ticker']} {x.get('confidence', 0):.0f}% RSI {f2(x.get('rsi'),0)} 趨勢 {x.get('trend_score', 0):+d}" for x in watch]
    L += ["", footer()]
    msg = "\n".join(L)
    tg_ok, tg_res = telegram.send(msg, dry_run=dry_run, label="weekly")
    out = {"type": "weekly_report", "week_start": str(start), "week_end": str(today), "generated": ctx.now.isoformat(),
           "market": {"vix": vix, "regime": reg["title"], "spy_price": spy, "qqq_price": qqq},
           "account": {k: acct.get(k) for k in ("equity_usd", "cash_usd", "cash_pct", "realized_pnl_usd", "unrealized_pnl_usd",
                                                 "total_pnl_usd", "total_return_pct")}, "spy_return_since_rebase_pct": spy_ret,
           "trades": trades, "week_summary": {"days_analyzed": len(by_day), "buy_signals": n_buy, "hold_signals": n_hold,
                                              "sell_signals": n_sell}, "signal_hit_rate_sample": perf,
           "telegram_ok": tg_ok, "engine": "px v3-core"}
    if not dry_run:
        ledger.save(pf)
        write_json(report_path(f"WeeklyReport_{today}.json"), out)
        write_text(report_path(f"WeeklySummary_{today}.txt"), strip_html(msg))
        try:
            from .. import archive
            archive.save_report("weekly", str(today), [msg], summary=f"每週回顧 {start} 至 {today}")
        except Exception as e:
            print("[weekly] archive failed:", type(e).__name__)
        if tg_ok:
            guard.mark_sent(week_key, JOB, "main", tg_res)
        guard.update(week_key, JOB, status="ok" if tg_ok else "telegram_failed", _inc_runs=True,
                     finished=clock.now_hkt().isoformat(timespec="seconds"))
    out["status"] = "ok" if tg_ok else "telegram_failed"
    return out
