"""Opportunity scan v2 — ranked Top-N watchlist of higher-upside, affordable US names.

Rule-based (no LLM). All inputs are COMPLETED daily bars; the live price is only
used for display / position sizing at run time. The same `evaluate()` is used by
scripts/backtest_scan.py so the backtest tests exactly the live logic.

Pipeline per ticker:
  hard filters  : price >= min_price, 20d avg dollar volume >= min_dollar_vol,
                  >= min_bars history, close > MA50 (no falling knives),
                  affordable (>= min_shares under the 25% position cap),
                  reward/risk >= min_rr
  score 0..100  : relative strength vs QQQ (30) + trend structure (25)
                  + momentum quality / RSI (15) + setup (15) + liquidity (10) + R:R (5)
  levels        : entry zone, ATR stop (clamped), structural target, R:R
  sizing        : min(2% equity risk / (entry-stop), 25% equity / entry) shares
  catalysts     : next earnings date (Finnhub calendar, yfinance fallback);
                  earnings inside the blackout window => flagged, no new entry
Language in outputs is scenario-based (情境), never a guarantee.
"""
import datetime as dt
import math

import numpy as np
import pandas as pd

from . import clock
from .config import load_settings


def cfg():
    return load_settings()["scan"]


# ---------------------------------------------------------------- features
def features(df):
    """Vectorised per-day features from a daily OHLCV frame (completed bars only)."""
    d = df.dropna(subset=["Close"]).copy()
    c, h, l, v = d["Close"].astype(float), d["High"].astype(float), d["Low"].astype(float), d["Volume"].astype(float)
    out = pd.DataFrame(index=d.index)
    out["open"] = d["Open"].astype(float)
    out["high"], out["low"], out["close"] = h, l, c
    out["ma20"] = c.rolling(20).mean()
    out["ma50"] = c.rolling(50).mean()
    out["ma200"] = c.rolling(200).mean()
    out["ma50_slope10"] = out["ma50"] / out["ma50"].shift(10) - 1
    delta = c.diff()
    ag = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rsi = 100 - 100 / (1 + ag / al)
    out["rsi"] = rsi.where(al != 0, 100.0)
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    out["atr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    out["hi20_prev"] = h.shift(1).rolling(20).max()
    out["hi120"] = h.rolling(120).max()
    out["dollar_vol20"] = (c * v).rolling(20).mean()
    out["vol_ratio"] = v / v.shift(1).rolling(20).mean()
    out["ret20"] = c / c.shift(20) - 1
    out["ret60"] = c / c.shift(60) - 1
    out["bars"] = np.arange(1, len(d) + 1)
    return out


# ---------------------------------------------------------------- levels & scoring
def levels(row, c=None):
    """Entry zone / stop / target / R:R from one feature row."""
    c = c or cfg()
    close, atr, ma20 = float(row["close"]), float(row["atr"]), float(row["ma20"])
    entry = close  # reference entry = last completed close (next-session limit around it)
    zone_lo = max(ma20, close - 0.5 * atr)
    zone_lo = min(zone_lo, close)
    stop_dist = c["sl_atr_mult"] * atr
    stop_dist = min(max(stop_dist, c["sl_min_pct"] * entry), c["sl_max_pct"] * entry)
    stop = entry - stop_dist
    hi120 = float(row["hi120"])
    near_high = close >= hi120 * (1 - c["near_high_pct"])
    if near_high:  # no overhead supply -> projection target
        target = entry + c["breakout_rr"] * stop_dist
        tmode = "突破投射"
    else:          # prior 120-day high = first resistance
        target = hi120
        tmode = "前高阻力"
    rr = (target - entry) / stop_dist if stop_dist > 0 else 0.0
    return {"entry": entry, "zone_lo": zone_lo, "zone_hi": close, "stop": stop, "stop_pct": stop_dist / entry * 100,
            "target": target, "target_pct": (target / entry - 1) * 100, "rr": rr, "target_mode": tmode,
            "atr_pct": atr / close * 100}


def size(entry, stop, equity_usd, fx, c=None, rules=None):
    rules = rules or load_settings()["rules"]
    risk_budget = rules["risk_per_trade_pct"] * equity_usd
    cap = rules["max_position_pct"] * equity_usd
    per_share_risk = max(entry - stop, 1e-9)
    shares = int(min(risk_budget / per_share_risk, cap / entry))
    return {"shares": shares, "cost_usd": shares * entry, "cost_hkd": shares * entry * fx,
            "risk_usd": shares * per_share_risk, "cap_usd": cap, "risk_budget_usd": risk_budget}


def evaluate(ticker, row, qqq_row, equity_usd, fx, rs_pct=None, c=None, earnings_days=None):
    """Return a candidate dict with pass/fail reasons and score (always returns a dict)."""
    c = c or cfg()
    why_fail, why = [], []
    close = float(row["close"])
    if any(pd.isna(row.get(k)) for k in ("ma50", "atr", "hi120", "dollar_vol20", "ret60", "rsi")) or row["bars"] < c["min_bars"]:
        return {"ticker": ticker, "pass": False, "score": 0, "fail": ["數據不足"]}
    lv = levels(row, c)
    sz = size(lv["entry"], lv["stop"], equity_usd, fx, c)
    # ---- hard filters
    if close < c["min_price"]:
        why_fail.append(f"股價 < ${c['min_price']}")
    if row["dollar_vol20"] < c["min_dollar_vol_usd"]:
        why_fail.append(f"成交額 ${row['dollar_vol20']/1e6:.0f}M < ${c['min_dollar_vol_usd']/1e6:.0f}M")
    if close <= row["ma50"]:
        why_fail.append("價低於 MA50（唔接跌緊嘅刀）")
    if sz["shares"] < c["min_shares"]:
        why_fail.append(f"每股太貴：25% 上限只買到 {sz['shares']} 股")
    rules = load_settings()["rules"]
    from .ledger import round_trip_fee
    fee_rt = round_trip_fee(lv["entry"], sz["shares"]) if sz["shares"] > 0 else 99.0
    fee_drag = fee_rt / sz["cost_usd"] * 100 if sz["cost_usd"] > 0 else 99.0
    if sz["shares"] >= c["min_shares"] and fee_drag > c.get("max_fee_drag_pct", 2.0):
        why_fail.append(f"注碼太細：來回手續費佔 {fee_drag:.1f}%（> {c.get('max_fee_drag_pct', 2.0)}%）")
    if lv["rr"] < c["min_rr"]:
        why_fail.append(f"R:R {lv['rr']:.1f} < {c['min_rr']}")
    if row["rsi"] > c["max_rsi"]:
        why_fail.append(f"RSI {row['rsi']:.0f} 過熱")
    # ---- score
    ex20 = (row["ret20"] - qqq_row["ret20"]) * 100 if qqq_row is not None else row["ret20"] * 100
    ex60 = (row["ret60"] - qqq_row["ret60"]) * 100 if qqq_row is not None else row["ret60"] * 100
    if rs_pct is None:  # absolute mapping when no cross-section available
        rs_pct = max(0.0, min(1.0, 0.5 + (0.5 * ex20 + 0.5 * ex60) / 60))
    s_rs = 30 * rs_pct
    s_tr = 0
    if close > row["ma20"]:
        s_tr += 8
    if row["ma20"] > row["ma50"]:
        s_tr += 8
    if row["ma50_slope10"] > 0:
        s_tr += 5
    if not pd.isna(row["ma200"]) and close > row["ma200"]:
        s_tr += 4
    r = row["rsi"]
    s_mo = 15 if 50 <= r <= 68 else (8 if (68 < r <= 75 or 45 <= r < 50) else 0)
    ext_atr = (close - row["ma20"]) / row["atr"] if row["atr"] else 9
    breakout = close > row["hi20_prev"] and (row["vol_ratio"] or 0) >= 1.3
    pullback = 0 <= ext_atr <= 1.0 and row["ma20"] > row["ma50"]
    if breakout:
        s_set, setup = 15, "放量突破20日高"
    elif pullback:
        s_set, setup = 15, "上升趨勢回踩MA20"
    elif ext_atr > 3:
        s_set, setup = 0, "離MA20太遠（追高風險）"
        why_fail.append(f"離 MA20 {ext_atr:.1f} 個 ATR（唔追高／唔 FOMO）")
    else:
        s_set, setup = 7, "趨勢延續"
    if c.get("allowed_setups") and setup not in c["allowed_setups"]:
        why_fail.append(f"setup「{setup}」唔喺允許名單")
    dv = row["dollar_vol20"]
    s_liq = 10 if dv >= 50e6 else (6 if dv >= c["min_dollar_vol_usd"] else 0)
    s_rr = 5 if lv["rr"] >= 3 else (3 if lv["rr"] >= c["min_rr"] else 0)
    score = s_rs + s_tr + s_mo + s_set + s_liq + s_rr
    catalyst = None
    if earnings_days is not None:
        catalyst = earnings_days
        if 0 <= earnings_days <= c["earnings_blackout_days"]:
            why_fail.append(f"{earnings_days} 日內有業績（跳空風險，唔喺業績前開新倉）")
    why.append(f"相對 QQQ：20日 {ex20:+.1f}pp / 60日 {ex60:+.1f}pp")
    why.append(f"結構：價 {'>' if close > row['ma20'] else '<'} MA20，MA20 {'>' if row['ma20'] > row['ma50'] else '<'} MA50，MA50 {'向上' if row['ma50_slope10'] > 0 else '向下'}")
    why.append(f"RSI {r:.0f}，setup：{setup}，ATR {lv['atr_pct']:.1f}%")
    return {
        "ticker": ticker, "pass": not why_fail, "fail": why_fail, "score": round(float(score), 1),
        "confidence": round(float(score), 1),
        "components": {"rs": round(s_rs, 1), "trend": s_tr, "momentum": s_mo, "setup": s_set, "liquidity": s_liq, "rr": s_rr},
        "setup": setup, "close": round(close, 4), "rsi": round(float(r), 1),
        "ex_qqq_20d_pp": round(float(ex20), 2), "ex_qqq_60d_pp": round(float(ex60), 2),
        "dollar_vol20_musd": round(float(dv) / 1e6, 1),
        "entry_zone": [round(lv["zone_lo"], 2), round(lv["zone_hi"], 2)], "entry": round(lv["entry"], 2),
        "stop": round(lv["stop"], 2), "stop_pct": round(lv["stop_pct"], 2), "target": round(lv["target"], 2),
        "target_pct": round(lv["target_pct"], 2), "rr": round(lv["rr"], 2), "target_mode": lv["target_mode"],
        "atr_pct": round(lv["atr_pct"], 2), "shares": sz["shares"], "cost_usd": round(sz["cost_usd"], 2),
        "cost_hkd": round(sz["cost_hkd"], 0), "risk_usd": round(sz["risk_usd"], 2), "fee_drag_pct": round(fee_drag, 2),
        "earnings_days": catalyst, "why": why,
    }


def rs_percentiles(rows, qqq_row):
    """Cross-sectional relative-strength percentile (0..1) among the scanned names."""
    vals = {}
    for t, r in rows.items():
        if pd.isna(r.get("ret20")) or pd.isna(r.get("ret60")):
            continue
        q20 = qqq_row["ret20"] if qqq_row is not None else 0
        q60 = qqq_row["ret60"] if qqq_row is not None else 0
        vals[t] = 0.5 * (r["ret20"] - q20) + 0.5 * (r["ret60"] - q60)
    if not vals:
        return {}
    order = sorted(vals, key=vals.get)
    n = len(order)
    return {t: (i / (n - 1) if n > 1 else 0.5) for i, t in enumerate(order)}


def rank(cands, top_n=None, max_per_theme=None):
    """Top-N passing candidates by score, at most `max_per_theme` per theme (diversification,
    mirrors the one-position-per-theme rule of the paper book)."""
    c = cfg()
    top_n = top_n or c["top_n"]
    max_per_theme = max_per_theme or c.get("max_per_theme", 1)
    ok = sorted([x for x in cands if x["pass"]], key=lambda x: (x["score"], x["rr"]), reverse=True)
    out, per = [], {}
    for x in ok:
        th = x.get("theme") or theme_of_scan(x["ticker"])
        if per.get(th, 0) >= max_per_theme:
            x.setdefault("fail", []).append(f"同主題 {th} 已有更高分")
            continue
        per[th] = per.get(th, 0) + 1
        out.append(x)
        if len(out) >= top_n:
            break
    return out


# ---------------------------------------------------------------- catalysts
def earnings_calendar(tickers, today=None, horizon_days=60):
    """{ticker: 'YYYY-MM-DD'} next earnings date. Finnhub calendar (1 call), yfinance fallback per name."""
    from .config import get_secret
    today = today or clock.now_et().date()
    out = {}
    key = get_secret("FINNHUB_API_KEY")
    if key:
        try:
            import requests
            r = requests.get("https://finnhub.io/api/v1/calendar/earnings",
                             params={"from": today.isoformat(), "to": (today + dt.timedelta(days=horizon_days)).isoformat(),
                                     "token": key}, timeout=20)
            if r.status_code == 200:
                want = set(tickers)
                for e in r.json().get("earningsCalendar", []) or []:
                    sym = e.get("symbol")
                    if sym in want and e.get("date"):
                        if sym not in out or e["date"] < out[sym]:
                            out[sym] = e["date"]
        except Exception as e:
            print("[scan] finnhub earnings calendar failed:", type(e).__name__)
    missing = [t for t in tickers if t not in out]
    if missing and cfg().get("yf_earnings_fallback", True):
        try:
            import yfinance as yf
            for t in missing:
                try:
                    cal = yf.Ticker(t).calendar
                    ds = cal.get("Earnings Date") if isinstance(cal, dict) else None
                    if ds:
                        fut = sorted(d for d in ds if d >= today)
                        if fut and (fut[0] - today).days <= horizon_days:
                            out[t] = fut[0].isoformat()
                except Exception:
                    continue
        except Exception:
            pass
    return out


def trading_days_until(date_str, today):
    try:
        d = dt.date.fromisoformat(date_str)
    except Exception:
        return None
    if d < today:
        return None
    n, cur = 0, today
    while cur < d:
        cur += dt.timedelta(days=1)
        if clock.is_trading_day(cur):
            n += 1
    return n


# ---------------------------------------------------------------- live run
def run_scan(now=None, equity_usd=None, fx=None, with_catalysts=True):
    from . import marketdata, indicators, ledger
    c = cfg()
    now = now or clock.now_hkt()
    if equity_usd is None or fx is None:
        acct = ledger.recompute(ledger.load())
        equity_usd = equity_usd or acct["equity_usd"]
        fx = fx or acct.get("fx_usdhkd") or 7.8
    feats, errors = {}, []
    qdf = marketdata.history("QQQ", period=c["history_period"])
    qqq_row = None
    if qdf is not None and len(qdf):
        qf = features(indicators.drop_incomplete_bar(qdf, now))
        qqq_row = qf.iloc[-1]
    for t in c["universe"]:
        df = marketdata.history(t, period=c["history_period"])
        if df is None or len(df) == 0:
            errors.append({"ticker": t, "error": "no data"})
            continue
        f = features(indicators.drop_incomplete_bar(df, now))
        if len(f) == 0:
            errors.append({"ticker": t, "error": "no completed bars"})
            continue
        feats[t] = f.iloc[-1]
    rsp = rs_percentiles(feats, qqq_row)
    today = clock.to_et(now).date()
    cal = earnings_calendar(list(feats), today) if with_catalysts else {}
    cands = []
    for t, row in feats.items():
        ed = cal.get(t)
        edays = trading_days_until(ed, today) if ed else None
        x = evaluate(t, row, qqq_row, equity_usd, fx, rsp.get(t), c, edays)
        x["earnings_date"] = ed
        x["bar_date"] = str(row.name.date()) if hasattr(row.name, "date") else str(row.name)
        x["theme"] = theme_of_scan(t)
        cands.append(x)
    top = rank(cands)
    for x in top:  # live display price (not used in scoring)
        try:
            q = marketdata.quote(x["ticker"])
            if q.get("ok"):
                x["live_price"] = round(q["price"], 2)
                x["live_change_pct"] = q.get("change_pct")
        except Exception:
            pass
    return {
        "generated_at": clock.now_hkt().isoformat(timespec="seconds"),
        "bar_date": max((x.get("bar_date") for x in cands), default=None),
        "equity_usd": round(equity_usd, 2), "fx_usdhkd": fx,
        "max_position_usd": round(load_settings()["rules"]["max_position_pct"] * equity_usd, 2),
        "risk_per_trade_usd": round(load_settings()["rules"]["risk_per_trade_pct"] * equity_usd, 2),
        "universe_size": len(c["universe"]), "scanned": len(cands), "passed": len([x for x in cands if x["pass"]]),
        "top": top,
        "near_misses": sorted([x for x in cands if not x["pass"] and len(x.get("fail", [])) == 1],
                              key=lambda x: x["score"], reverse=True)[:5],
        "all": sorted(cands, key=lambda x: x["score"], reverse=True),
        "errors": errors,
        "method": "px.scan v2 — 相對強度(QQQ)+趨勢結構+RSI+setup+流動性+R:R；已收市日bar；ATR止損；情境參考，非保證",
    }


def theme_of_scan(t):
    for th, names in load_settings()["themes"].items():
        if t in names:
            return th
    return "OTHER"
