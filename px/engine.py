"""Daily analysis engine shared by `run.py daily` and the legacy analyzer.py.

Indicators use COMPLETED daily bars (1y history); the live price is used only
for display and SL/TP. Writes the legacy-compatible root files the current
website reads (daily_report.json, signals.json, profiles.json)."""
import datetime as dt
import json
import os

from . import clock, indicators, marketdata, signals as sigmod, ledger
from .config import load_settings, path, theme_of, bucket_of, universe_all

REPORT_PATH = path("daily_report.json")
SIGNALS_PATH = path("signals.json")
PROFILES_PATH = path("profiles.json")


def _sanitize(o):
    if isinstance(o, dict):
        return {k: _sanitize(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_sanitize(v) for v in o]
    try:
        import numpy as np
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
    except Exception:
        pass
    return o


def save_json(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_sanitize(data), f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def load_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def market_context():
    s = load_settings()
    vix = marketdata.vix()
    regime = marketdata.regime_for(vix)
    reg = s["regimes"][regime]
    spy, qqq = marketdata.quote("SPY"), marketdata.quote("QQQ")
    fxi = marketdata.fx_info()
    spy = spy if spy.get("ok") else {}
    qqq = qqq if qqq.get("ok") else {}
    return {
        "vix": round(vix, 2) if vix else None, "regime": regime, "regime_zh": reg["title"], "emoji": reg["emoji"],
        "max_positions": min(s["rules"]["max_positions"], reg["max_positions"]),
        "min_confidence": max(s["rules"]["min_confidence"], reg["min_confidence"]),
        "spy": spy.get("price"), "spy_chg_pct": spy.get("change_pct"),
        "qqq": qqq.get("price"), "qqq_chg_pct": qqq.get("change_pct"),
        "fx_usdhkd": fxi["rate"], "fx_live": fxi["live"],
        "session_date": spy.get("session_date") or qqq.get("session_date"),
    }


def build_signal(ticker, regime, owned, now=None):
    s = load_settings()
    hist = marketdata.history(ticker)
    ind = indicators.compute(hist, now, s["indicators"]["min_bars"])
    if "error" in ind:
        return {"ticker": ticker, "error": ind["error"]}
    q = marketdata.quote(ticker)
    price = q["price"] if q.get("ok") else ind["close"]
    sc = sigmod.score(ind, regime, owned)
    min_conf = max(s["rules"]["min_confidence"], s["regimes"][regime]["min_confidence"]) * 100
    signal, action, reasons = sc["signal"], sc["action"], list(sc["reasons"])
    if signal == "BUY" and sc["confidence"] < min_conf:
        signal, action = "HOLD", "信心度不足，觀望"
        reasons.append(f"信心度 {sc['confidence']:.0f}% < 門檻 {min_conf:.0f}%")
    sl, tp = ledger.compute_sl_tp(price, ind.get("atr14"))
    return {
        "ticker": ticker, "name": s["names"].get(ticker, ticker), "bucket": bucket_of(ticker), "theme": theme_of(ticker),
        "signal": signal, "raw_signal": sc["signal"], "action": action, "confidence": sc["confidence"],
        "price": round(price, 2), "change_pct": q.get("change_pct") if q.get("ok") else ind["change_pct"],
        "price_source": q.get("source"),
        "rsi": ind["rsi14"], "macd": ind["macd"], "macd_histogram": ind["macd_hist"],
        "macd_bullish": (ind["macd_hist"] or 0) > 0, "vol_ratio": ind["vol_ratio"], "ma20": ind["ma20"],
        "ma50": ind["ma50"], "atr": ind["atr14"], "regime": regime, "above_ma50": ind["close"] > ind["ma50"],
        "trend_score": ind["trend_score"], "trend_label": ind["trend_label"],
        "reasons": reasons, "signal_reasons": sc["reasons"], "is_owned": owned,
        "suggested_sl": sl, "suggested_tp": tp, "indicators": ind,
        "timestamp": clock.now_hkt().isoformat(timespec="seconds"),
    }


def analyze(now=None, write_files=True, fetch_profiles=None):
    """Run the full-universe analysis. Returns (report, signals_all)."""
    s = load_settings()
    now = now or clock.now_hkt()
    ctx = market_context()
    regime = ctx["regime"]
    pf = ledger.load()
    owned = {p["ticker"] for p in pf.get("positions", [])}
    core = s["universe"]["core"] + s["universe"]["secondary"]
    opp = s["universe"]["opportunity"]
    sigs, errors = [], []
    for t in core + opp:
        sg = build_signal(t, regime, t in owned, now)
        if "error" in sg:
            errors.append(sg)
            print(f"  ⚠️ {t}: {sg['error']}")
            continue
        sigs.append(sg)
    core_sigs = [x for x in sigs if x["ticker"] in core]
    opp_sigs = [x for x in sigs if x["ticker"] in opp]
    acct = ledger.recompute(pf)
    max_px = s["rules"]["max_position_pct"] * acct["equity_usd"]
    opp_picks = [
        {k: x.get(k) for k in ("ticker", "name", "price", "signal", "confidence", "change_pct", "reasons", "rsi",
                               "action", "trend_score", "ma50", "vol_ratio")}
        for x in sorted(opp_sigs, key=lambda y: y["confidence"], reverse=True)
        if x["signal"] == "BUY" and 0 < x["price"] <= max_px
    ]
    profiles = {}
    if fetch_profiles is None:
        fetch_profiles = s.get("legacy", {}).get("fetch_profiles", True)
    if fetch_profiles and write_files:
        try:
            import finnhub_api  # legacy module (root)
            for t in core:
                p = finnhub_api.get_stock_profile(t)
                if p and "error" not in p:
                    profiles[t] = p
        except Exception as e:
            print("profiles skipped:", type(e).__name__)
    for x in core_sigs:  # merge fundamentals for the current website (as the old analyzer did)
        prof = profiles.get(x["ticker"])
        if prof:
            for k in ("analyst_consensus", "analyst_emoji", "analyst_rating_str", "num_analysts", "target_mean",
                      "target_high", "target_low", "upside_pct", "earnings_date", "earnings_days", "pe_ratio",
                      "forward_pe", "profit_margin_pct", "revenue_growth_pct", "earnings_growth_pct", "industry", "sector"):
                if k in prof:
                    x[k] = prof.get(k)
            x["analyst_news"] = prof.get("news", [])
    # catalyst column: fill missing earnings dates from the earnings calendar (Finnhub, yfinance fallback)
    try:
        from . import scan as _scan
        need = [x["ticker"] for x in core_sigs if not x.get("earnings_date")]
        cal = _scan.earnings_calendar(need) if need else {}
        today = clock.session_date(now)
        for x in core_sigs:
            if not x.get("earnings_date") and cal.get(x["ticker"]):
                x["earnings_date"] = cal[x["ticker"]]
                try:
                    x["earnings_days"] = clock.trading_days_between(today, dt.date.fromisoformat(cal[x["ticker"]]))
                except Exception:
                    x["earnings_days"] = None
    except Exception as e:
        print("earnings calendar skipped:", type(e).__name__)
    quotes = {}
    for t in ["SPY", "QQQ", "^VIX"] + core:
        q = marketdata.quote(t)
        quotes[t] = {"symbol": t, "price": q.get("price"), "change_pct": q.get("change_pct"),
                     "prev_close": q.get("prev_close"), "source": q.get("source")}
    buys = [x for x in core_sigs if x["signal"] == "BUY"]
    report = {
        "date": clock.now_hkt().date().isoformat(),
        "session_date": clock.session_date(now).isoformat(),
        "timestamp": clock.now_hkt().isoformat(timespec="seconds"),
        "source": "Yahoo Finance (yfinance); indicators on completed daily bars (1y)",
        "data_note": "指標用已收市日 bar（1年數據，Wilder RSI、真 MA20/MA50）；即時價只作 SL/TP 及顯示",
        "market": {"vix": ctx["vix"], "regime": ctx["regime_zh"], "regime_code": regime, "regime_emoji": ctx["emoji"],
                   "spy_price": ctx["spy"], "spy_change": ctx["spy_chg_pct"], "qqq_price": ctx["qqq"],
                   "qqq_change": ctx["qqq_chg_pct"], "fx_usdhkd": ctx["fx_usdhkd"], "fx_live": ctx["fx_live"],
                   "quote_session": ctx["session_date"]},
        "guardrail": {"regime": regime, "vix_value": ctx["vix"], "emoji": ctx["emoji"], "title": ctx["regime_zh"],
                      "max_positions": ctx["max_positions"], "min_confidence": ctx["min_confidence"]},
        "signals": core_sigs,
        "opportunity_signals": opp_sigs,
        "all_quotes": quotes,
        "profiles": profiles,
        "summary": {"total_stocks": len(core_sigs), "buy_signals": len(buys),
                    "hold_signals": len([x for x in core_sigs if x["signal"] == "HOLD"]),
                    "sell_signals": len([x for x in core_sigs if x["signal"] == "SELL"])},
        "top_picks": [{k: x.get(k) for k in ("ticker", "name", "action", "confidence", "price", "change_pct", "rsi",
                                             "macd_bullish", "vol_ratio", "above_ma50", "reasons", "signal_reasons",
                                             "is_owned")} for x in sorted(buys, key=lambda y: y["confidence"], reverse=True)],
        "opportunity_picks": opp_picks,
        "errors": errors,
        "quotes_ts": clock.now_hkt().isoformat(timespec="seconds"),
    }
    if write_files and marketdata.yahoo_blocked():
        print("[analyze] Yahoo rate-limited this run — not overwriting data files with a partial report")
        write_files = False
    if write_files:
        save_json(REPORT_PATH, report)
        if profiles:
            save_json(PROFILES_PATH, profiles)
        append_signal_history(core_sigs, report["date"], ctx)
    return report, sigs


def append_signal_history(core_sigs, date_str, ctx):
    """Legacy signals.json: replace today's core signals (slim rows, no news blobs), update hit rate."""
    data = load_json(SIGNALS_PATH, {"signals": [], "performance": {}})
    data["signals"] = [x for x in data.get("signals", []) if x.get("date") != date_str]
    keep = ("ticker", "name", "signal", "raw_signal", "action", "confidence", "price", "change_pct", "rsi", "macd",
            "macd_histogram", "macd_bullish", "vol_ratio", "ma20", "ma50", "atr", "regime", "above_ma50",
            "trend_score", "reasons", "signal_reasons", "is_owned", "timestamp")
    for x in core_sigs:
        row = {k: x.get(k) for k in keep}
        row["date"] = date_str
        data["signals"].append(row)
    data["last_updated"] = clock.now_hkt().isoformat(timespec="seconds")
    data["vix_regime"] = ctx["regime_zh"]
    data["vix_value"] = ctx["vix"]
    data["performance"] = hit_rate(data["signals"], data.get("performance", {}))
    save_json(SIGNALS_PATH, data)


def hit_rate(signals, perf):
    """Signal hit-rate sample (BUY signal -> next analysed day's price: >=+2% hit, 0..2 partial, <=-2 miss)."""
    by = {}
    for x in signals:
        if x.get("date"):
            by.setdefault(x["date"], []).append(x)
    dates = sorted(by)
    hits = partials = misses = neutrals = 0
    for i in range(len(dates) - 1):
        nxt = {x["ticker"]: x for x in by[dates[i + 1]]}
        for x in by[dates[i]]:
            if x.get("signal") != "BUY" or x["ticker"] not in nxt or not x.get("price"):
                continue
            chg = (nxt[x["ticker"]].get("price", x["price"]) - x["price"]) / x["price"] * 100
            if chg >= 2:
                hits += 1
            elif chg >= 0:
                partials += 1
            elif chg <= -2:
                misses += 1
            else:
                neutrals += 1
    total = hits + partials + misses
    out = dict(perf or {})
    if total:
        out.update({"total_signals": total, "hits": hits, "partials": partials, "misses": misses, "neutrals": neutrals,
                    "hit_rate_pct": round(hits / total * 100, 1), "partial_rate_pct": round(partials / total * 100, 1),
                    "miss_rate_pct": round(misses / total * 100, 1)})
    out["label"] = "信號命中率樣本（唔係實際交易筆數）"
    return out

