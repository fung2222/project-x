"""weekly job (Monday HKT morning): 7-day review, trades, equity vs start and SPY,
signal hit-rate SAMPLE (not trade count), lessons, next-week watchlist. 1 Telegram message.
Guard key = the HKT Monday date (weekly runs regardless of US holidays)."""
import datetime as dt
import json

from .. import archive, clock, guard, ledger, marketdata, telegram, engine
from ..config import load_settings, path
from ..messages import esc, f2, pct, footer, money, real_section, paper_brief, usd_s, hkd_s
from .common import Ctx, write_json, write_text, report_path, strip_html, real_snapshot, paper_max_positions
from .daily import spy_return_since_rebase

JOB = "weekly"


def three_way(book, ev, acct):
    """Since real-trading start: real account vs paper book vs QQQ / SPY (None where not computable)."""
    d0 = book.get("real_start_date")
    if not d0:
        return {"since": None}
    hist = archive.load_pnl()
    base = next((h for h in reversed(hist) if h.get("date", "") < d0 and h.get("equity_usd")), None)
    base_eq = float(base["equity_usd"]) if base else float(acct.get("start_equity_usd") or 0)
    paper = round((float(acct["equity_usd"]) / base_eq - 1) * 100, 2) if base_eq else None
    return {"since": d0, "real_pct": ev.get("return_pct"), "real_usd": ev.get("return_usd"), "paper_pct": paper,
            "paper_base_date": base.get("date") if base else None,
            "qqq_pct": marketdata.return_since("QQQ", d0), "spy_pct": marketdata.return_since("SPY", d0),
            "n_closed": ev.get("n_closed"), "n_wins": ev.get("n_wins"), "win_rate_pct": ev.get("win_rate_pct")}


def three_way_lines(tw, book, ev, start, today):
    if not tw.get("since"):
        return ["<b>⚖️ 三方比較</b>：真倉未開始（第一筆 `pos add` 之後開始計：真倉 vs 紙上倉 vs QQQ／SPY）"]
    L = [f"<b>⚖️ 三方比較（真倉 {tw['since']} 起）</b>",
         f"真倉 {pct(tw['real_pct'])}（{usd_s(tw['real_usd'])} / {hkd_s((tw['real_usd'] or 0) * ev['fx'])}）· 紙上倉 {pct(tw['paper_pct'])}"
         f" · QQQ {pct(tw['qqq_pct'])} · SPY {pct(tw['spy_pct'])}"]
    wr = f"勝率 {f2(tw['win_rate_pct'], 0)}%（贏 {tw['n_wins']}／輸 {tw['n_closed'] - tw['n_wins']}）" if tw.get("n_closed") else "勝率 —"
    wk = [t for t in book.get("closed_trades", []) if str(start) <= str(t.get("exit_date", "")) <= str(today)]
    wk_buys = [p for p in book.get("positions", []) if str(start) <= str(p.get("entry_date", "")) <= str(today)]
    L.append(f"真倉交易：已平倉 {tw.get('n_closed') or 0} 筆 · {wr} · 持倉中 {ev['n_open']} 隻 · 目標樣本 20–30 筆先下結論")
    for t in wk:
        L.append(f"· {t['exit_date'][5:]} 真倉賣 {t['ticker']} {t['shares']}股 @{f2(t['exit_price'])} 淨 {usd_s(t['net_pnl_usd'])}（{pct(t.get('net_pnl_pct'))}，{t.get('exit_reason')}）")
    for p in wk_buys:
        L.append(f"· {p['entry_date'][5:]} 真倉買 {p['ticker']} {p['shares']}股 @{f2(p['entry_price'])}")
    return L


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
    real_book, real_ev = real_snapshot(ctx, acct.get("fx_usdhkd"))
    tw = three_way(real_book, real_ev, acct)
    L = [f"<b>📊 Project X 每週回顧</b> {start} 至 {today}",
         f"{reg['emoji']} VIX {f2(vix)} {reg['title']} · SPY {f2(spy)} · QQQ {f2(qqq)}", ""]
    L += real_section(real_ev)
    L += [""] + three_way_lines(tw, real_book, real_ev, start, today)
    qqq_ret = marketdata.return_since("QQQ", load_settings()["account"]["rebase_date"])
    L += [""] + paper_brief(acct, len(pf.get("positions", [])), paper_max_positions(regime), spy_ret, qqq_ret,
                            [f"本週紙上交易 {len(trades)} 筆（買 {sum(1 for t in trades if t.get('action') == 'BUY')}／"
                             f"賣 {sum(1 for t in trades if t.get('action') == 'SELL')}）",
                             f"已實現 {acct['realized_pnl_usd']:+.2f} · 未實現 {acct['unrealized_pnl_usd']:+.2f} USD"], label="紙上本週")
    for t in trades:
        if t["action"] == "SELL":
            L.append(f"· {t['date'][5:]} 紙上 {t['ticker']} x{t['shares']} {t.get('reason')} @{f2(t.get('exit_price'))} 淨 {float(t.get('net_pnl_usd') or 0):+.2f}")
        elif t["action"] == "BUY":
            L.append(f"· {t['date'][5:]} 紙上買入 {t['ticker']} x{t['shares']} @{f2(t.get('entry_price'))}")
    L += ["", f"<b>📡 信號</b>（核心＋次要，{len(by_day)} 日）BUY {n_buy} · HOLD {n_hold} · SELL {n_sell}"]
    if perf.get("total_signals"):
        L.append(f"信號命中率（樣本 {perf['total_signals']}，唔係交易筆數）：{f2(perf.get('hit_rate_pct'),0)}%"
                 f"（中 {perf.get('hits')}／部分 {perf.get('partials')}／失誤 {perf.get('misses')}）")
    L += ["", "<b>🎓 本週重點</b>",
          "1. 真倉：止蝕／止賺入場前定好，系統只提醒，你喺富途手動執行；紙上倉由 code 自動執行做對照。",
          "2. 每筆風險 ≤2% 權益、每日最多 1 個新倉、同主題 1 隻、唔攤平。",
          "3. 止盈後冷靜期內唔追返；等新 setup。"]
    if watch:
        L += ["", "<b>👀 下週觀察</b>"] + [f"• {x['ticker']} {x.get('confidence', 0):.0f}% RSI {f2(x.get('rsi'),0)} 趨勢 {x.get('trend_score', 0):+d}" for x in watch]
    L += ["", footer()]
    msg = "\n".join(L)
    tg_ok, tg_res = telegram.send(msg, dry_run=dry_run, label="weekly")
    out = {"type": "weekly_report", "week_start": str(start), "week_end": str(today), "generated": ctx.now.isoformat(),
           "market": {"vix": vix, "regime": reg["title"], "spy_price": spy, "qqq_price": qqq},
           "real": {"summary": {k: real_ev.get(k) for k in ("n_open", "equity_usd", "cash_usd", "unrealized_usd", "realized_usd",
                                                         "return_pct", "n_closed", "n_wins", "win_rate_pct", "real_start_date")},
                    "three_way": tw},
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
            archive.save_report("weekly", str(today), [msg], summary=f"每週回顧 {start} 至 {today}")
        except Exception as e:
            print("[weekly] archive failed:", type(e).__name__)
        if tg_ok:
            guard.mark_sent(week_key, JOB, "main", tg_res)
        guard.update(week_key, JOB, status="ok" if tg_ok else "telegram_failed", _inc_runs=True,
                     finished=clock.now_hkt().isoformat(timespec="seconds"))
    out["status"] = "ok" if tg_ok else "telegram_failed"
    return out
