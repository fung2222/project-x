"""Backtest of the opportunity scan (px/scan.py) on ~1 year of daily bars.

Uses the SAME features()/evaluate()/rank() as the live scan. Honest caveats are
written into the output: survivorship bias (universe chosen in 2026-09), no
historical earnings blackout, daily-bar ambiguity (stop assumed hit before target
when both are inside one bar), fills at next-day open, fees max(US$1, 0.5%) per side
in the portfolio simulation, no slippage beyond that.

Usage:  python scripts/backtest_scan.py [--period 2y] [--out data/backtest/scan_backtest.json]
"""
import argparse
import datetime as dt
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from px import scan
from px.config import load_settings


# Variants are fixed a-priori definitions; ALL results are reported (no cherry-picking).
VARIANTS = {
    "live": {},                                                     # current settings.json (3xATR, max 20%, 30d)
    "v1_2atr": {"sl_atr_mult": 2.0, "sl_max_pct": 0.15, "time_stop_days": 20},   # original 2026-09-28 draft
    "wide_stop": {"sl_atr_mult": 3.0, "sl_max_pct": 0.20, "time_stop_days": 30},
    "pullback_only": {"allowed_setups": ["上升趨勢回踩MA20"]},
    "trend_trail": {"exit_mode": "ma20_trail", "time_stop_days": 60},  # initial ATR stop, exit on close < MA20
    "trend_trail_wide": {"exit_mode": "ma20_trail", "time_stop_days": 60, "sl_atr_mult": 3.0, "sl_max_pct": 0.20},
}


def download(tickers, period):
    import yfinance as yf
    df = yf.download(tickers, period=period, interval="1d", auto_adjust=False, group_by="ticker",
                     progress=False, threads=True)
    out = {}
    for t in tickers:
        try:
            d = df[t].dropna(subset=["Close"])
            if len(d):
                out[t] = d
        except Exception:
            pass
    return out


def simulate_trade(f, i, stop, target, max_days, exit_mode="fixed"):
    """Enter at bar i+1 open. Returns dict or None (gap through stop / no data)."""
    n = len(f)
    if i + 1 >= n:
        return None
    entry = float(f["open"].iloc[i + 1])
    if not entry or entry <= stop:
        return {"skipped": "gap_below_stop"}
    risk = entry - stop
    for k in range(i + 1, min(n, i + 1 + max_days)):
        o, h, l, c = (float(f[x].iloc[k]) for x in ("open", "high", "low", "close"))
        if k > i + 1 and o <= stop:  # gap down through stop
            return {"entry": entry, "exit": o, "r": (o - entry) / risk, "days": k - i, "outcome": "stop_gap", "exit_idx": k}
        if l <= stop:
            return {"entry": entry, "exit": stop, "r": (stop - entry) / risk, "days": k - i, "outcome": "stop", "exit_idx": k}
        if exit_mode == "fixed" and h >= target:
            px = max(o, target) if k > i + 1 else target
            return {"entry": entry, "exit": px, "r": (px - entry) / risk, "days": k - i, "outcome": "target", "exit_idx": k}
        if exit_mode == "ma20_trail" and c < float(f["ma20"].iloc[k]) and k > i + 1:
            return {"entry": entry, "exit": c, "r": (c - entry) / risk, "days": k - i,
                    "outcome": "target" if c >= target else "trail", "exit_idx": k}
    k = min(n - 1, i + max_days)
    if k <= i:
        return None
    c = float(f["close"].iloc[k])
    open_end = (i + max_days) > (n - 1)
    return {"entry": entry, "exit": c, "r": (c - entry) / risk, "days": k - i,
            "outcome": "open_at_end" if open_end else "time", "exit_idx": k}


def stats(trades):
    rs = [t["r"] for t in trades if "r" in t]
    if not rs:
        return {"n": 0}
    wins = [r for r in rs if r > 0]
    cum = np.cumsum(rs)
    peak = np.maximum.accumulate(np.concatenate([[0], cum]))[1:]
    dd_r = float((cum - peak).min()) if len(cum) else 0.0
    return {"n": len(rs), "target_hit_rate": round(sum(1 for t in trades if t.get("outcome") == "target") / len(rs), 3),
            "win_rate": round(len(wins) / len(rs), 3), "avg_r": round(float(np.mean(rs)), 3),
            "median_r": round(float(np.median(rs)), 3), "total_r": round(float(np.sum(rs)), 2),
            "max_drawdown_r": round(dd_r, 2), "avg_days": round(float(np.mean([t["days"] for t in trades if "days" in t])), 1),
            "outcomes": {o: sum(1 for t in trades if t.get("outcome") == o) for o in
                         ("target", "trail", "stop", "stop_gap", "time", "open_at_end")}}


def fee(notional, rules):
    return max(rules["fee"]["min_usd"], rules["fee"]["rate"] * notional)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="2y")
    ap.add_argument("--out", default="data/backtest/scan_backtest.json")
    ap.add_argument("--variant", default="live", choices=sorted(VARIANTS))
    a = ap.parse_args()
    S = load_settings()
    rules = S["rules"]
    c = dict(S["scan"])
    c.update(VARIANTS[a.variant])
    exit_mode = c.get("exit_mode", "fixed")
    fx = S["account"]["fx_fallback_usdhkd"]
    uni = c["universe"]
    raw = download(uni + ["QQQ", "SPY"], a.period)
    feats = {t: scan.features(d) for t, d in raw.items()}
    qf = feats["QQQ"]
    dates = qf.index
    warm = c["min_bars"]
    test_dates = dates[warm:]
    idx = {t: {d: k for k, d in enumerate(f.index)} for t, f in feats.items()}
    max_days = c["time_stop_days"]

    top1, top5, baseline = [], [], []
    busy1, busy5, busyb = {}, {}, {}
    daily_top = {}
    for d in test_dates[:-1]:
        qrow = qf.loc[d]
        rows = {t: feats[t].iloc[idx[t][d]] for t in uni if t in feats and d in idx[t]}
        rsp = scan.rs_percentiles(rows, qrow)
        cands = []
        for t, row in rows.items():
            x = scan.evaluate(t, row, qrow, 1280.0, fx, rsp.get(t), c, None)
            x["theme"] = scan.theme_of_scan(t)
            cands.append(x)
        ranked = scan.rank(cands)
        daily_top[str(d.date())] = [x["ticker"] for x in ranked]
        for pos, x in enumerate(ranked):
            t = x["ticker"]
            k = idx[t][d]
            if busy5.get(t, -1) < k:
                tr = simulate_trade(feats[t], k, x["stop"], x["target"], max_days, exit_mode)
                if tr and "r" in tr:
                    tr.update({"ticker": t, "date": str(d.date()), "score": x["score"], "rank": pos + 1})
                    top5.append(tr)
                    busy5[t] = tr["exit_idx"]
            if pos == 0 and busy1.get(t, -1) < k:
                tr = simulate_trade(feats[t], k, x["stop"], x["target"], max_days, exit_mode)
                if tr and "r" in tr:
                    tr.update({"ticker": t, "date": str(d.date()), "score": x["score"]})
                    top1.append(tr)
                    busy1[t] = tr["exit_idx"]
        # baseline: every liquid, affordable name with a computable level set, same stop/target method, no scoring
        for x in cands:
            if x.get("score", 0) == 0 and x.get("fail") == ["數據不足"]:
                continue
            t = x["ticker"]
            basic_fail = [f for f in x.get("fail", []) if f.startswith("股價") or f.startswith("成交額") or f.startswith("每股太貴")]
            if basic_fail or "stop" not in x:
                continue
            k = idx[t][d]
            if busyb.get(t, -1) < k:
                tr = simulate_trade(feats[t], k, x["stop"], x["target"], max_days, exit_mode)
                if tr and "r" in tr:
                    tr.update({"ticker": t, "date": str(d.date())})
                    baseline.append(tr)
                    busyb[t] = tr["exit_idx"]

    # ---------------- portfolio simulation (rules of the paper book)
    equity0 = S["account"]["start_equity_usd"]
    cash, positions, curve, ptrades = equity0, {}, [], []
    for d in test_dates[:-1]:
        # exits on today's bar for positions opened earlier
        for t in list(positions):
            p = positions[t]
            k = idx[t].get(d)
            if k is None:
                continue
            o, h, l, cl = (float(feats[t][x].iloc[k]) for x in ("open", "high", "low", "close"))
            exit_px = None
            if k > p["entry_idx"]:
                if o <= p["stop"]:
                    exit_px, why = o, "stop_gap"
                elif l <= p["stop"]:
                    exit_px, why = p["stop"], "stop"
                elif exit_mode == "fixed" and h >= p["target"]:
                    exit_px, why = max(o, p["target"]), "target"
                elif exit_mode == "ma20_trail" and cl < float(feats[t]["ma20"].iloc[k]):
                    exit_px, why = cl, "trail"
                elif k - p["entry_idx"] >= max_days:
                    exit_px, why = cl, "time"
            if exit_px is not None:
                notional = exit_px * p["shares"]
                f_ = fee(notional, rules)
                cash += notional - f_
                pnl = (exit_px - p["entry"]) * p["shares"] - f_ - p["fee_in"]
                ptrades.append({"ticker": t, "entry_date": p["date"], "exit_date": str(d.date()), "shares": p["shares"],
                                "entry": round(p["entry"], 4), "exit": round(exit_px, 4), "net_pnl_usd": round(pnl, 2), "why": why})
                del positions[t]
        # mark to market
        mv = sum(float(feats[t]["close"].iloc[idx[t][d]]) * p["shares"] for t, p in positions.items() if d in idx[t])
        equity = cash + mv
        curve.append({"date": str(d.date()), "equity": round(equity, 2)})
        # one new entry per day from today's ranked list (filled next open)
        if len(positions) >= rules["max_positions"]:
            continue
        held_themes = {scan.theme_of_scan(t) for t in positions}
        for tk in daily_top.get(str(d.date()), []):
            if tk in positions or scan.theme_of_scan(tk) in held_themes:
                continue
            k = idx[tk][d]
            if k + 1 >= len(feats[tk]):
                break
            row = feats[tk].iloc[k]
            lv = scan.levels(row, c)
            entry = float(feats[tk]["open"].iloc[k + 1])
            if entry <= lv["stop"]:
                continue
            sz = scan.size(entry, lv["stop"], equity, fx, c, rules)
            sh = sz["shares"]
            cost = sh * entry
            f_in = fee(cost, rules)
            if sh < 1 or cash - cost - f_in < rules["min_cash_pct"] * equity:
                continue
            cash -= cost + f_in
            positions[tk] = {"entry": entry, "shares": sh, "stop": lv["stop"], "target": lv["target"],
                             "entry_idx": k + 1, "date": str(feats[tk].index[k + 1].date()), "fee_in": f_in}
            break
    eq = pd.Series([x["equity"] for x in curve])
    mdd = float((eq / eq.cummax() - 1).min() * 100) if len(eq) else 0.0
    def bh(t):
        f = feats[t]
        a0 = float(f.loc[test_dates[0], "close"]); a1 = float(f.loc[test_dates[-2], "close"])
        s = f.loc[test_dates[0]:test_dates[-2], "close"]
        return round((a1 / a0 - 1) * 100, 2), round(float((s / s.cummax() - 1).min() * 100), 2)
    ew = []
    for t in uni:
        if t in feats and test_dates[0] in idx[t] and test_dates[-2] in idx[t]:
            ew.append(float(feats[t].loc[test_dates[-2], "close"]) / float(feats[t].loc[test_dates[0], "close"]) - 1)
    wins = [t for t in ptrades if t["net_pnl_usd"] > 0]
    result = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "variant": a.variant, "variant_params": VARIANTS[a.variant], "exit_mode": exit_mode,
        "period": {"from": str(test_dates[0].date()), "to": str(test_dates[-2].date()), "trading_days": len(test_dates) - 1},
        "universe_size": len(uni), "downloaded": len(raw) - 2,
        "method": "same px.scan features/evaluate/rank as live; entry next open; stop/target from signal-day levels; "
                  f"time stop {max_days} trading days; stop assumed first if stop and target in the same bar",
        "caveats": ["survivorship bias: universe chosen in 2026-09 with hindsight of which names are still listed/liquid",
                    "no historical earnings blackout (catalyst filter not simulated)",
                    "daily bars only: intrabar order unknown -> conservative stop-first assumption",
                    "fees in portfolio sim: max(US$1, 0.5%) per side; no extra slippage",
                    "small sample: one market regime; not predictive of future returns"],
        "signal_level": {"top1_each_day": stats(top1), "top5_each_day": stats(top5),
                         "baseline_all_liquid_names_same_exits": stats(baseline)},
        "portfolio_sim": {"start_equity_usd": equity0, "end_equity_usd": round(float(eq.iloc[-1]), 2) if len(eq) else None,
                          "return_pct": round((float(eq.iloc[-1]) / equity0 - 1) * 100, 2) if len(eq) else None,
                          "max_drawdown_pct": round(mdd, 2), "trades": len(ptrades),
                          "win_rate": round(len(wins) / len(ptrades), 3) if ptrades else None,
                          "fees_note": "fees included", "open_positions_at_end": len(positions)},
        "benchmarks": {"QQQ_buy_hold_pct_and_mdd": bh("QQQ"), "SPY_buy_hold_pct_and_mdd": bh("SPY"),
                       "universe_equal_weight_buy_hold_pct": round(float(np.mean(ew)) * 100, 2) if ew else None},
        "portfolio_trades": ptrades, "equity_curve": curve,
        "top5_trades_sample": top5[-30:],
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1, default=str)
    slim = {k: result[k] for k in ("variant", "period", "signal_level", "portfolio_sim", "benchmarks")}
    print(json.dumps(slim, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
