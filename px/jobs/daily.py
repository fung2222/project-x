"""daily job (ET 10:00): full-universe indicators/signals on completed bars, SL/TP,
deterministic gates -> at most 1 paper entry, decisions/teaching/scenarios (kept on the website),
ONE plain-language Telegram report (Roy 2026-09-28): 真倉 -> 資金 -> 買賣信號 -> 潛力股 -> 大市 -> 今日學一樣 ->
紙上倉 one line -> site link. No new entries / buy suggestions when VIX is missing (regime UNKNOWN) or the
earnings date is unknown.
Paper entry: gated legacy BUY signal first; otherwise the top opportunity-scan candidate with
score >= scan.paper_entry_min_score (forward test of the scan), both through ledger rules. Idempotent per session:
each message part is sent at most once; the 1-entry-per-day rule is enforced by the ledger."""
import json

from .. import archive, clock, decide, guard, ledger, marketdata, telegram, engine, scan
from ..config import load_settings, path
from ..messages import (catalyst_text, esc, f2, pct, footer, daily_teaching, scenarios, scan_message,
                        real_alerts, REAL_NOTE)
from .common import (Ctx, gate_run, refresh_positions, write_text, report_path, strip_html, paper_bench, real_context,
                     data_wait, pick_news, annotate_scan, save_reasons)

JOB = "daily"
PARTS = ("report",)
LEGACY_PARTS = ("decision", "signals", "scan", "teaching")  # pre-2026-09-28 parts: any sent => session already reported


def owned_news(tickers, max_items=3):
    out = []
    try:
        import yfinance as yf
        for t in tickers:
            for item in (yf.Ticker(t).news or [])[:2]:
                c = item.get("content", item)
                title = c.get("title")
                if title:
                    out.append(f"{t}: {title[:110]}")
                if len(out) >= max_items:
                    return out
    except Exception:
        pass
    return out


def signals_message(report, evals=None, news=None):
    """Message 2: one line per core/secondary name + opportunity BUY candidates with failed gates."""
    L = [f"<b>📊 信號</b> {report.get('session_date', report.get('date'))}（指標：已收市日 bar，1年數據）"]
    rows = []
    for x in report.get("signals", []):
        tag = x["signal"]
        if x["signal"] == "SELL" and not x.get("is_owned"):
            tag = "SELL(冇倉)"
        rows.append(f"{x['ticker']:<5} {x['price']:>8.2f} RSI{x['rsi']:>5.1f} 趨勢{x.get('trend_score', 0):+d} {tag} {x['confidence']:.0f}%")
    if rows:
        L.append("<pre>" + esc("\n".join(rows)) + "</pre>")
    # catalyst / earnings column (Roy requirement): next earnings date per name, soonest first
    cal = [x for x in report.get("signals", []) + report.get("opportunity_signals", []) if x.get("earnings_date")]
    cal.sort(key=lambda x: (x.get("earnings_days") if x.get("earnings_days") is not None else 999, x["ticker"]))
    if cal:
        L.append("📅 <b>業績日（催化劑）</b>：" + " · ".join(
            f"{x['ticker']} {catalyst_text(x['earnings_date'], x.get('earnings_days'))}" for x in cal[:8]))
    else:
        L.append("📅 業績日：暫時攞唔到（Finnhub／yfinance 冇數據）")
    opp = sorted(report.get("opportunity_signals", []), key=lambda y: y["confidence"], reverse=True)
    ev = {e["ticker"]: e for e in (evals or report.get("gates", []) or [])}
    cands = [x for x in opp if x.get("raw_signal") == "BUY"]
    top = cands[:4] if cands else opp[:3]
    if top:
        L.append("<b>💡 機會掃描</b>")
        for x in top:
            e = ev.get(x["ticker"])
            gates = ("✓ 全部 gates 通過" if e and e["passed"] else ("✗" + " ✗".join(e["failed"]) if e else ""))
            L.append(f"• {x['ticker']} ${f2(x['price'])} {x.get('raw_signal', x['signal'])} {x['confidence']:.0f}% "
                     f"RSI {f2(x['rsi'],0)} 趨勢 {x.get('trend_score', 0):+d} {gates}")
    if news:
        L.append("<b>📰 持倉新聞</b>")
        L += [f"• {esc(n)}" for n in news[:3]]
    L.append("<i>G1信心 G2 setup G3成交量 G4趨勢 G5組合 G6注碼 G8冷靜期 G9暫停</i>")
    return "\n".join(L)


def run(dry_run=False, force=False, legacy=False, now=None):
    ctx = Ctx(JOB, dry_run, force, legacy, now)
    ok, why = gate_run(ctx, "daily")
    if not ok:
        print(f"[daily] {why}")
        return {"status": "skipped", "reason": why}
    sent_all = (all(guard.was_sent(ctx.session, JOB, p) for p in PARTS)
                or any(guard.was_sent(ctx.session, JOB, p) for p in LEGACY_PARTS))
    if sent_all and not force:
        msg = f"[daily] all {len(PARTS)} messages already sent for session {ctx.session} — nothing to do (use --force)"
        print(msg)
        return {"status": "duplicate", "reason": msg}
    s = load_settings()
    print(f"[daily] session {ctx.session} ET, now {ctx.now.strftime('%Y-%m-%d %H:%M')} HKT, dry_run={dry_run}")
    report, sigs = engine.analyze(ctx.now, write_files=not dry_run)
    pf = ledger.load()
    rows, executed, acct = refresh_positions(ctx, pf)
    regime = report["guardrail"]["regime"]
    owned = {p["ticker"] for p in pf.get("positions", [])}
    for x in sigs:
        x["is_owned"] = x["ticker"] in owned
    chosen, evals = decide.run_gates(pf, sigs, regime, ctx.now)
    no_new = bool(s["regimes"].get(regime, {}).get("no_new_entries"))
    if no_new and chosen:
        print(f"[daily] regime {regime}: no new paper entries (VIX data missing)")
        chosen = None
    entry = None
    entry_err = None
    if chosen:
        sig = next(x for x in sigs if x["ticker"] == chosen["ticker"])
        reason = (f"ENTRY_{chosen['setup']}: {sig['name']} 信心 {sig['confidence']:.0f}%，RSI {sig['rsi']:.0f}，"
                  f"趨勢 {sig['trend_score']:+d}，vol×{f2(sig['vol_ratio'])}")
        if dry_run:
            entry = {"ticker": chosen["ticker"], "shares": chosen["shares"], "entry_price": sig["price"],
                     "setup": chosen["setup"], "stop_loss_price": chosen["sl"], "take_profit_price": chosen["tp"],
                     "confidence": sig["confidence"], "dry_run": True}
        else:
            try:
                entry = ledger.execute_entry(pf, chosen["ticker"], sig["price"], chosen["shares"], chosen["sl"],
                                             chosen["tp"], regime, reason, chosen["setup"], sig["confidence"], ctx.now)
            except ledger.RuleViolation as e:
                entry_err = str(e)
    # ---------- opportunity scan (core product) + optional paper entry from it
    try:
        scan_res = scan.run_scan(ctx.now, ledger.recompute(pf)["equity_usd"], report["market"]["fx_usdhkd"])
    except Exception as e:
        print("[daily] scan failed:", type(e).__name__, e)
        scan_res = {"top": [], "near_misses": [], "error": f"{type(e).__name__}"}
    min_sc = s["scan"].get("paper_entry_min_score", 75)
    min_conf = report["guardrail"]["min_confidence"] * 100 if report["guardrail"]["min_confidence"] <= 1 else report["guardrail"]["min_confidence"]
    cutoff = s["schedule_et"]["daily"].get("no_new_entries_after", "15:00")
    ov = decide.load_overrides()
    scan_entry_ok = (clock.market_is_open(ctx.now) and ctx.now_et.strftime("%H:%M") < cutoff
                     and not ov.get("pause_new_entries") and not no_new)
    unknown_blocks = s.get("earnings", {}).get("unknown_blocks_entry", True)
    if not chosen and not entry and scan_entry_ok:
        for x in scan_res.get("top", []):
            if x["score"] < max(min_sc, min_conf) or x["ticker"] in owned or x["ticker"] in (ov.get("blocklist") or []):
                continue
            if x.get("earnings_days") is not None and x["earnings_days"] <= s["scan"]["earnings_blackout_days"]:
                continue
            if unknown_blocks and not x.get("earnings_date") and x.get("earnings_known") is False:
                x.setdefault("paper_note", "業績日未知，保守起見唔入")
                continue
            q = marketdata.quote(x["ticker"])
            px_ = q["price"] if q.get("ok") else x["entry"]
            if not (x["entry_zone"][0] * 0.99 <= px_ <= x["entry_zone"][1] * 1.02):
                x.setdefault("paper_note", f"現價 {px_:.2f} 唔喺入場區，唔追")
                continue
            sl_, tp_ = x["stop"], x["target"]
            shares, _caps = ledger.size_position(ledger.recompute(pf)["equity_usd"], ledger.recompute(pf)["cash_usd"], px_, sl_)
            reason = (f"SCAN_ENTRY: {x['ticker']} 分數 {x['score']:.0f}，{x['setup']}，R:R {x['rr']:.1f}，"
                      f"SL {sl_:.2f} / TP {tp_:.2f}")
            if dry_run:
                entry = {"ticker": x["ticker"], "shares": shares, "entry_price": px_, "setup": "SCAN",
                         "stop_loss_price": sl_, "take_profit_price": tp_, "confidence": x["score"], "dry_run": True}
                break
            try:
                entry = ledger.execute_entry(pf, x["ticker"], px_, shares, sl_, tp_, regime, reason, "SCAN", x["score"], ctx.now)
                break
            except ledger.RuleViolation as e:
                x["paper_note"] = f"規則阻止：{e}"
                entry_err = str(e)
    acct = ledger.recompute(pf)
    skipped = []
    for e in sorted(evals, key=lambda y: y["confidence"], reverse=True):
        if chosen and e["ticker"] == chosen["ticker"] and entry:
            continue
        skipped.append({"ticker": e["ticker"], "confidence": e["confidence"], "failed": e["failed"],
                        "why": decide.why_text(e) or (entry_err or "")})
    # ---------- plain report (Roy 2026-09-28): real first, money, signals, picks, market, one lesson, paper 1 line
    from .. import plain, lessons, reasons as rs
    mk = report["market"]
    real_book, real_ev, rsn, trends = real_context(ctx, mk.get("fx_usdhkd") or acct.get("fx_usdhkd"))
    real_al, _ = real_alerts(real_ev, reasons=rsn)
    actions = []
    for tr in executed:
        actions.append(f"紙上{'止損' if tr['reason']=='STOP_LOSS' else '止盈'} {tr['ticker']} x{tr['shares']} @ ${f2(tr['exit_price'])}（淨 {tr['net_pnl_usd']:+.2f}）")
    if entry:
        pos_pct = entry["entry_price"] * entry["shares"] / acct["equity_usd"] * 100
        actions.append(f"{'（dry-run）' if dry_run else ''}紙上買入 {entry['ticker']} x{entry['shares']} @ ${f2(entry['entry_price'])}"
                       f"（setup {entry['setup']}，信心 {f2(entry.get('confidence'),0)}%，SL ${f2(entry['stop_loss_price'])} / "
                       f"TP ${f2(entry['take_profit_price'])}，佔 {pos_pct:.1f}%）")
    for p in pf.get("positions", []):
        if entry and p["ticker"] == entry["ticker"]:
            continue
        actions.append(f"HOLD {p['ticker']} @ {f2(p.get('current_price'))}（{pct(p.get('pnl_pct'))}，距SL {f2(p.get('dist_to_sl_pct'),1)}%，唔攤平）")
    if not entry:
        if no_new:
            actions.append("冇新倉：VIX 數據暫缺，唔開新倉")
        elif skipped:
            top = skipped[0]
            actions.append(f"冇新倉：最高 {top['ticker']} {top['confidence']:.0f}% → {top['why']}")
        else:
            actions.append("冇新倉：今日冇 BUY 候選")
    short_acts = [f"紙上{'止損' if tr['reason']=='STOP_LOSS' else '止盈'} {tr['ticker']}" for tr in executed]
    if entry:
        short_acts.append(f"{'（dry-run）' if dry_run else ''}紙上買入 {entry['ticker']} {entry['shares']} 股")
    spy_ret, qqq_ret = paper_bench()
    news = pick_news(scan_res)
    annotate_scan(scan_res, news)
    dw = plain.day_word(mk.get("quote_session"), ctx.now)
    mood = plain.market_lines(mk.get("spy_change"), mk.get("qqq_change"), mk.get("vix"), rs.market_headline(), when=dw)
    lesson = lessons.pick(clock.session_date(ctx.now), save=not dry_run)
    L = [f"<b>📘 每日報告 {ctx.session}</b>（{plain.session_label(ctx.now)}）"]
    L += plain.real_block(real_ev, rsn, trends, dw)
    if real_al:
        L += ["<b>⚠️ 要留意</b>"] + [f"• {esc(a)}" for a in real_al] + [REAL_NOTE]
    L.append(plain.capital_line(real_ev, mk.get("fx_live", report["market"].get("fx_live", True))))
    L += ["", "<b>🧭 買賣信號</b>"] + plain.hold_signal_lines(real_ev, trends)
    L += plain.buy_suggestion(real_ev, scan_res, regime, clock.market_is_open(ctx.now), now=ctx.now)[0]
    L += [""] + plain.picks_block(scan_res, news)
    L += ["", "<b>🌍 大市</b>"] + mood
    L += ["", f"<b>🎓 今日學一樣</b>：{esc(lesson)}"]
    L += ["", plain.paper_line(acct, len(pf.get("positions", [])), report["guardrail"]["max_positions"], spy_ret, qqq_ret,
                               short_acts), "", plain.footer_line()]
    m_report = "\n".join(L)
    # website keeps the detailed teaching / scenarios
    overbought = len([x for x in report.get("signals", []) if (x.get("rsi") or 0) > 68])
    teach = daily_teaching({"regime": regime, "vix": mk["vix"], "regime_zh": mk["regime"]}, pf, entry, executed,
                           skipped[0] if skipped else None, overbought)
    sc, invalid = scenarios({"regime": regime, "vix": mk["vix"], "regime_zh": mk["regime"]}, pf, entry, real_ev["rows"])
    msgs = {"report": m_report}
    wait = data_wait(JOB)
    if wait:
        return wait
    # ---------- persist
    report["v3"] = {
        "session_date": ctx.session, "job": JOB, "generated_at": clock.now_hkt().isoformat(timespec="seconds"),
        "decisions": {"actions": actions, "entries": [entry] if entry else [], "exits": executed, "skipped": skipped},
        "gates": evals, "portfolio_summary": {k: acct.get(k) for k in (
            "equity_usd", "cash_usd", "cash_pct", "realized_pnl_usd", "unrealized_pnl_usd", "total_pnl_usd",
            "total_return_pct")} | {"positions": len(pf.get("positions", [])), "spy_return_pct": spy_ret, "qqq_return_pct": qqq_ret},
        "real_summary": {k: real_ev.get(k) for k in ("n_open", "equity_usd", "cash_usd", "unrealized_usd", "realized_usd",
                                                    "return_pct", "n_closed", "win_rate_pct", "real_start_date")},
        "teaching": teach, "scenarios": sc, "invalidation": invalid, "lesson": lesson,
    }
    report["opportunity_scan"] = {k: scan_res.get(k) for k in ("generated_at", "bar_date", "top", "near_misses", "passed",
                                                               "scanned", "max_position_usd", "risk_per_trade_usd", "method")}
    if not dry_run:
        pf["account"]["last_decision"] = {"date": ctx.session, "style": "px_gates_v3", "actions": actions,
                                          "skipped": [f"{x['ticker']} {x['confidence']:.0f}%：{x['why']}" for x in skipped[:5]],
                                          "cash_pct": acct["cash_pct"], "deployed_pct": acct["deployed_pct"]}
        pf["account"]["updated"] = ctx.session
        pf["updated"] = ctx.session
        ledger.save(pf)
        engine.save_json(engine.REPORT_PATH, report)
        if scan_res.get("top") is not None and not scan_res.get("error"):
            archive.save_scan(scan_res)
        save_reasons(rsn, scan_res, news)
    results = {}
    for part in PARTS:
        if guard.was_sent(ctx.session, JOB, part) and not force:
            results[part] = "already-sent"
            continue
        ok_, res = telegram.send(msgs[part], dry_run=dry_run, label=f"daily/{part}")
        results[part] = "ok" if ok_ else f"failed: {res}"
        if ok_ and not dry_run:
            guard.mark_sent(ctx.session, JOB, part, res)
    if not dry_run:
        brief = "\n\n".join(strip_html(msgs[p]) for p in PARTS)
        write_text(report_path(f"DailyBrief_{ctx.session}.txt"), brief)
        archive.save_report(JOB, ctx.session, [msgs[p] for p in PARTS],
                            summary=f"每日分析 · 真倉 {real_ev['n_open']} 隻（{pct(real_ev['return_pct'])}）· 紙上 {pct(acct['total_return_pct'])} · Top: "
                                    + ", ".join(x["ticker"] for x in scan_res.get("top", [])),
                            pnl=acct["total_return_pct"])
        guard.update(ctx.session, JOB, status="ok" if all(v in ("ok", "already-sent") for v in results.values()) else "partial",
                     finished=clock.now_hkt().isoformat(timespec="seconds"), telegram=results,
                     entry=entry.get("id") if entry and not dry_run else None, _inc_runs=True)
    print(json.dumps({"session": ctx.session, "telegram": results, "entry": entry, "exits": [t["id"] for t in executed],
                      "skipped": skipped[:5], "equity_usd": acct["equity_usd"]}, ensure_ascii=False, indent=2, default=str))
    return {"status": "ok" if all(v in ("ok", "already-sent") for v in results.values()) else "telegram_failed",
            "telegram": results, "messages": msgs, "entry": entry, "exits": executed}


def spy_return_since_rebase():
    try:
        rb = load_settings()["account"]["rebase_date"]
        df = marketdata.history("SPY")
        import datetime as dt
        d0 = dt.date.fromisoformat(rb)
        before = df[[i.date() < d0 for i in df.index]]
        base = float(before["Close"].iloc[-1])
        last = marketdata.quote("SPY").get("price") or float(df["Close"].iloc[-1])
        return round((last / base - 1) * 100, 2)
    except Exception:
        return None


def legacy_signals_push(dry_run=None):
    """Used by telegram_push.send_daily_push(): send ONLY the signals message (the Grok Bot routine
    adds its own decision/teaching messages). Guarded: at most once per session."""
    now = clock.now_hkt()
    session = clock.session_date(now).isoformat()
    if guard.was_sent(session, JOB, "signals"):
        print(f"[daily/signals] already sent for session {session}; skipping")
        return True, "0/0 parts sent (already sent)"
    report = engine.load_json(engine.REPORT_PATH, {})
    pf = ledger.load()
    try:
        _, sigs = None, report.get("signals", []) + report.get("opportunity_signals", [])
        regime = report.get("guardrail", {}).get("regime", "NORMAL")
        owned = {p["ticker"] for p in pf.get("positions", [])}
        for x in sigs:
            x["is_owned"] = x["ticker"] in owned
            x.setdefault("indicators", {})
        evals = [decide.evaluate(pf, x, regime, now) for x in sigs if x.get("raw_signal") == "BUY" and not x["is_owned"]
                 and x.get("indicators", {}).get("close")]
    except Exception as e:
        print("gate preview skipped:", type(e).__name__, e)
        evals = []
    news = owned_news(sorted({p["ticker"] for p in pf.get("positions", [])}))
    msg = signals_message(report, evals, news) + "\n\n" + footer()
    from ..config import is_dry_run
    live = not (dry_run if dry_run is not None else is_dry_run())
    ok, res = telegram.send(msg, dry_run=dry_run, label="daily/signals (legacy)")
    if ok and live:
        guard.mark_sent(session, JOB, "signals", res)
    sent = 1 if ok else 0
    total = 1
    # opportunity scan Top 5 (core product) — its own message, guarded separately
    if not guard.was_sent(session, JOB, "scan"):
        total += 1
        try:
            acct = ledger.recompute(pf)
            sc = scan.run_scan(now, acct["equity_usd"], report.get("market", {}).get("fx_usdhkd") or acct.get("fx_usdhkd"))
            if live:
                archive.save_scan(sc)
                report["opportunity_scan"] = {k: sc.get(k) for k in ("generated_at", "bar_date", "top", "near_misses",
                                                                     "passed", "scanned", "max_position_usd",
                                                                     "risk_per_trade_usd", "method")}
                engine.save_json(engine.REPORT_PATH, report)
            ok2, res2 = telegram.send(scan_message(sc) + "\n\n" + footer(), dry_run=dry_run, label="daily/scan (legacy)")
            if ok2 and live:
                guard.mark_sent(session, JOB, "scan", res2)
            sent += 1 if ok2 else 0
            ok = ok and ok2
        except Exception as e:
            print("[daily/scan] failed:", type(e).__name__, e)
            ok = False
    if live:
        try:
            from .. import schedule
            schedule.record("daily", schedule.slot_for("daily", now), "ok" if ok else "telegram_failed",
                            f"legacy telegram_push {sent}/{total}", via="legacy")
        except Exception as e:
            print("[daily] run-ledger record failed:", type(e).__name__)
    return ok, (f"{sent}/{total} parts sent" if ok else f"{sent}/{total} parts sent (see log)")
