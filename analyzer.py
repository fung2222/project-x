"""
Project X — 每日分析引擎（legacy entry point; engine = px/engine.py, v3-core）
完整流程：VIX Guardrail → 真實報價 → 技術分析（已收市日 bar，1年數據）→ 生成信號 → 記錄命中率
`python analyzer.py` still writes daily_report.json / signals.json / profiles.json for the website.
It does NOT open paper trades (use `python run.py daily` for the full job with code-enforced gates).
"""
import json, os, datetime, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import finnhub_api   # 整合了 yfinance 的股價模組
import vix_guardrail

PORTFOLIO_PATH = os.path.join(BASE_DIR, "portfolio.json")
SIGNALS_PATH  = os.path.join(BASE_DIR, "signals.json")
REPORT_PATH   = os.path.join(BASE_DIR, "daily_report.json")

STOCK_NAMES = {
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "RKLB": "Rocket Lab",
    "AMD":  "Adv. Micro Devices",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "META": "Meta Platforms",
    "AMZN": "Amazon",
    "PLTR": "Palantir",
    "ARM":  "Arm Holdings",
    # Opportunity scan (small capital)
    "SOUN": "SoundHound AI",
    "BBAI": "BigBear.ai",
    "IONQ": "IonQ",
    "ASTS": "AST SpaceMobile",
    "LUNR": "Intuitive Machines",
    "SOFI": "SoFi Technologies",
    "HOOD": "Robinhood",
    "RIVN": "Rivian",
    "JOBY": "Joby Aviation",
    "SMCI": "Super Micro Computer",
}

from px import config as _pxconfig, engine as _engine, clock as _clock
# Max price for 1 share ≈ 25% of ~USD 1280 capital; min confidence = config rules.min_confidence (0.75)
OPP_MAX_PRICE = _pxconfig.load_settings()["rules"]["max_position_pct"] * _pxconfig.load_settings()["account"]["start_equity_usd"]
OPP_MIN_CONFIDENCE = _pxconfig.load_settings()["rules"]["min_confidence"] * 100


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sanitize(obj):
    """將 numpy/Python3 類型轉為 JSON 可序列化類型"""
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    import numpy as np
    if isinstance(obj, (np.bool_, np.int64, np.float64)):
        return obj.item()
    return obj


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sanitize(data), f, ensure_ascii=False, indent=2)


def get_owned_tickers():
    """取得已持倉的股票列表"""
    try:
        pf = load_json(PORTFOLIO_PATH)
        return [p.get("ticker") for p in pf.get("positions", [])]
    except Exception:
        return []


def generate_signal(ticker, quote, tech, gr):
    """根據真實數據生成信號（整合持倉）"""
    if not tech or "error" in tech:
        return None

    rsi = tech["rsi"]
    price = tech["price"]
    chg = tech["change_pct"]
    regime = gr["regime"]
    min_conf = gr["min_confidence"]
    owned = get_owned_tickers()

    # 使用 finnhub_api 計算的信心度
    confidence = tech.get("confidence", 50)

    # VIX Guardrail 調整（config regimes.*.confidence_adj）
    confidence += _pxconfig.load_settings()["regimes"].get(regime, {}).get("confidence_adj", 0)

    confidence = max(20, min(95, confidence))

    # 最終信號
    signal = tech["signal"]
    action = tech["action"]
    reasons = list(tech.get("signal_reasons", []))

    # 已持倉調整
    if ticker in owned:
        if signal == "BUY":
            signal = "HOLD"
            action = "已持有，觀望"
            confidence = 50
            reasons = [f"{ticker} 已在持倉中，不重複買入"]
        elif signal == "SELL":
            reasons.append("已持倉，考慮止盈")

    # 信心度門檻
    if signal == "BUY" and confidence < min_conf * 100:
        signal = "HOLD"
        action = "信心度不足，觀望"
        confidence = max(30, confidence)
        reasons.append(f"信心度 {confidence:.0f}% < 門檻 {min_conf*100:.0f}%")

    return {
        "ticker": ticker,
        "name": STOCK_NAMES.get(ticker, ticker),
        "signal": signal,
        "action": action,
        "confidence": round(confidence, 1),
        "price": price,
        "change_pct": chg,
        "rsi": rsi,
        "macd": tech.get("macd"),
        "macd_histogram": tech.get("macd_histogram"),
        "macd_bullish": tech.get("macd_bullish"),
        "vol_ratio": tech.get("vol_ratio"),
        "ma50": tech.get("ma50"),
        "atr": tech.get("atr"),
        "regime": regime,
        "above_ma50": tech.get("above_ma50", False),
        "reasons": reasons,
        "signal_reasons": tech.get("signal_reasons", []),
        "is_owned": ticker in owned,
        "timestamp": datetime.datetime.now().isoformat()
    }



def enrich_signal_with_profile(sig, prof):
    """合併基本面欄位到信號（缺失資料時安全跳過）"""
    if not sig or not prof or "error" in prof:
        return sig
    for key in (
        "analyst_consensus", "analyst_emoji", "analyst_rating_str", "num_analysts",
        "target_mean", "target_high", "target_low", "upside_pct",
        "earnings_date", "earnings_days", "pe_ratio", "forward_pe",
        "profit_margin_pct", "revenue_growth_pct", "earnings_growth_pct",
        "industry", "sector",
    ):
        if key in prof:
            sig[key] = prof.get(key)
    if "news" in prof:
        sig["analyst_news"] = prof.get("news", [])
    return sig


def build_opportunity_picks(quotes, tech_batch, profiles, gr):
    """
    機會掃描：產生信號但不寫入核心 signals.json / 不觸發自動入倉邏輯。
    僅將 BUY 且信心≥70、股價適合小資金者寫入 daily_report.opportunity_picks。
    """
    picks = []
    for ticker in getattr(finnhub_api, "WATCH_OPPORTUNITY", []):
        tech = tech_batch.get(ticker, {})
        if not tech or "error" in tech:
            continue
        quote = quotes.get(ticker, {})
        try:
            sig = generate_signal(ticker, quote, tech, gr)
        except Exception:
            continue
        if not sig:
            continue
        enrich_signal_with_profile(sig, profiles.get(ticker, {}))
        price = sig.get("price") or 0
        conf = sig.get("confidence") or 0
        if sig.get("signal") != "BUY":
            continue
        if conf < OPP_MIN_CONFIDENCE:
            continue
        if price <= 0 or price > OPP_MAX_PRICE:
            continue
        picks.append({
            "ticker": ticker,
            "name": sig.get("name", ticker),
            "price": price,
            "signal": sig.get("signal"),
            "confidence": conf,
            "change_pct": sig.get("change_pct"),
            "reasons": sig.get("reasons") or sig.get("signal_reasons") or [],
            "upside_pct": sig.get("upside_pct"),
            "rsi": sig.get("rsi"),
            "action": sig.get("action"),
        })
    picks.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return picks


def get_cached_report(max_age_minutes=30):
    """如果今日報告存在且不超過 max_age_minutes，返回緩存的報告"""
    try:
        if not os.path.exists(REPORT_PATH):
            return None
        report = load_json(REPORT_PATH)
        if report.get("date") != _clock.now_hkt().date().isoformat():
            return None
        ts = report.get("timestamp", "")
        if ts:
            try:
                report_time = datetime.datetime.fromisoformat(ts)
                if report_time.tzinfo is None:
                    report_time = report_time.replace(tzinfo=_clock.HKT)
                age = _clock.now_hkt() - report_time
                if age.total_seconds() > max_age_minutes * 60:
                    return None
                return report
            except Exception:
                return None
        return None
    except Exception:
        return None


def analyze_day(quiet=False):
    """Execute full daily analysis"""
    if quiet:
        import io, sys as _sys
        _old = _sys.stdout
        _sys.stdout = io.StringIO()
        try:
            return _analyze_impl()
        finally:
            _sys.stdout = _old
    return _analyze_impl()


def _analyze_impl():
    """Actual analysis logic -> px.engine.analyze (writes daily_report.json, signals.json, profiles.json)."""
    print("=" * 60)
    print("Project X — 每日分析引擎 (px v3-core)")
    print(f"時間：{_clock.now_hkt().strftime('%Y-%m-%d %H:%M')} HKT")
    print("數據來源：Yahoo Finance (yfinance)；指標用已收市日 bar（1年）")
    print("=" * 60)
    report, sigs = _engine.analyze(write_files=True)
    gr = report["guardrail"]
    print(f"VIX: {report['market']['vix']} → {gr['title']}（門檻 {gr['min_confidence']*100:.0f}%，最多 {gr['max_positions']} 隻）")
    for sig in report["signals"] + report.get("opportunity_signals", []):
        sig_icon = "🟢" if sig["signal"] == "BUY" else "🔴" if sig["signal"] == "SELL" else "🟡"
        print(f"  {sig_icon} {sig['ticker']:5} | ${sig['price']:8.2f} | RSI:{sig['rsi']:5.1f} | MA50:{sig['ma50']:8.2f} | "
              f"vol:{(sig['vol_ratio'] or 0):.2f} | trend:{sig['trend_score']:+d} | {sig['confidence']:3.0f}% | {sig['action']}")
    print(f"\n💡 機會掃描候選：{len(report.get('opportunity_picks', []))} 隻")
    perf = load_json(SIGNALS_PATH).get("performance", {})
    if perf.get("total_signals"):
        print(f"📊 信號命中率樣本：{perf.get('hit_rate_pct', 0):.0f}%（樣本 {perf['total_signals']}）")
    print("\n✅ 分析完成！")
    return report


def generate_report(signals, quotes, gr, vix, regime, profiles=None, opportunity_picks=None):
    """生成完整的中文每日報告"""
    buys = [s for s in signals if s["signal"] == "BUY"]
    holds = [s for s in signals if s["signal"] == "HOLD"]
    sells = [s for s in signals if s["signal"] == "SELL"]

    spy = quotes.get("SPY", {})
    qqq = quotes.get("QQQ", {})

    report = {
        "date": datetime.date.today().isoformat(),
        "timestamp": datetime.datetime.now().isoformat(),
        "source": "Yahoo Finance (yfinance)",
        "market": {
            "vix": round(vix, 2),
            "regime": gr["title"],
            "regime_emoji": gr["emoji"],
            "spy_price": spy.get("price"),
            "spy_change": spy.get("change_pct"),
            "qqq_price": qqq.get("price"),
            "qqq_change": qqq.get("change_pct"),
        },
        "guardrail": gr,
        "signals": signals,
        "all_quotes": quotes,
        "profiles": profiles or {},
        "summary": {
            "total_stocks": len(signals),
            "buy_signals": len(buys),
            "hold_signals": len(holds),
            "sell_signals": len(sells),
        },
        "top_picks": [
            {
                "ticker": s["ticker"],
                "name": s["name"],
                "action": s["action"],
                "confidence": s["confidence"],
                "price": s["price"],
                "change_pct": s["change_pct"],
                "rsi": s["rsi"],
                "macd_bullish": s.get("macd_bullish"),
                "vol_ratio": s.get("vol_ratio"),
                "above_ma50": s.get("above_ma50"),
                "reasons": s.get("reasons", []),
                "signal_reasons": s.get("signal_reasons", []),
                "is_owned": s.get("is_owned", False),
                "analyst_emoji": (profiles or {}).get(s["ticker"], {}).get("analyst_emoji", ""),
                "analyst_consensus": (profiles or {}).get(s["ticker"], {}).get("analyst_consensus", ""),
                "upside_pct": (profiles or {}).get(s["ticker"], {}).get("upside_pct"),
                "earnings_days": (profiles or {}).get(s["ticker"], {}).get("earnings_days"),
                "earnings_date": (profiles or {}).get(s["ticker"], {}).get("earnings_date"),
            }
            for s in sorted(buys, key=lambda x: x["confidence"], reverse=True)
        ],
        "opportunity_picks": opportunity_picks or [],
        "quotes_ts": datetime.datetime.now().isoformat()
    }
    return report


def update_hit_rate():
    """更新命中率統計（signal hit-rate sample; see px.engine.hit_rate）"""
    sig_data = load_json(SIGNALS_PATH)
    sig_data["performance"] = _engine.hit_rate(sig_data.get("signals", []), sig_data.get("performance", {}))
    save_json(SIGNALS_PATH, sig_data)


if __name__ == "__main__":
    report = analyze_day()
