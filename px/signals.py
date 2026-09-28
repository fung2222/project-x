"""Signal + confidence rules (MERGE_PLAN §5.3). No unconditional +5 bump;
regime adjustment comes from config (NORMAL 0, CAUTION -10, DEFENSIVE -20)."""
from .config import load_settings


def base_signal(rsi):
    if rsi < 30:
        return "BUY", min(90.0, 70 + (30 - rsi) * 2), "超賣區域，強烈買入信號", f"RSI {rsi:.0f} 超賣"
    if rsi < 40:
        return "BUY", min(80.0, 60 + (40 - rsi)), "偏低，買入機會", f"RSI {rsi:.0f} 偏低"
    if rsi < 45:
        return "HOLD", 55.0, "中性偏低，觀望", f"RSI {rsi:.0f} 中性偏低"
    if rsi > 75:
        return "SELL", min(90.0, 60 + (rsi - 75) * 2), "嚴重超買，止盈", f"RSI {rsi:.0f} 嚴重超買"
    if rsi > 68:
        return "SELL", min(80.0, 55 + (rsi - 68)), "超買，考慮止盈", f"RSI {rsi:.0f} 超買"
    if rsi > 62:
        return "HOLD", 55.0, "偏高，觀望", f"RSI {rsi:.0f} 偏高"
    return "HOLD", 50.0, "觀望", f"RSI {rsi:.0f} 中性"


def score(ind, regime="NORMAL", owned=False):
    """Return dict(signal, action, confidence, reasons) from indicator dict."""
    s = load_settings()
    rsi = ind["rsi14"]
    signal, conf, action, r0 = base_signal(rsi)
    reasons = [r0]
    hist = ind.get("macd_hist") or 0.0
    vol = ind.get("vol_ratio")
    close = ind.get("close")
    ma50 = ind.get("ma50")
    ts = ind.get("trend_score", 0)
    if signal == "BUY":
        if hist > 0:
            conf += 8
            reasons.append("MACD 柱為正（看漲確認）")
        else:
            conf -= 10
            reasons.append("⚠️ MACD 柱仍為負")
        if vol is not None and vol >= 1.2:
            conf += 5
            reasons.append(f"放量確認 (vol×{vol:.1f})")
        elif vol is not None and vol < 0.5:
            conf -= 8
            reasons.append(f"⚠️ 成交量不足 (vol×{vol:.1f})")
        if close and ma50:
            if close > ma50:
                conf += 5
                reasons.append("價格高於 MA50")
            else:
                conf -= 5
                reasons.append("⚠️ 價格低於 MA50")
        if ts >= 3:
            conf += 5
            reasons.append(f"趨勢分 {ts:+d}（上升趨勢）")
        elif ts <= -3:
            conf -= 10
            reasons.append(f"⚠️ 趨勢分 {ts:+d}（下降趨勢）")
    elif signal == "SELL":
        if hist < 0:
            conf += 5
            reasons.append("MACD 柱為負（看跌確認）")
    adj = s["regimes"].get(regime, {}).get("confidence_adj", 0)
    if adj:
        conf += adj
        reasons.append(f"VIX {regime} 調整 {adj:+d}")
    if owned and signal == "BUY":
        signal, action = "HOLD", "已持有，觀望（唔攤平／唔加倉）"
        reasons.append("已在持倉中，不重複買入")
    elif owned and signal == "SELL":
        reasons.append("已持倉，留意止盈／止損位")
    elif signal == "SELL":
        action += "（冇持倉，唔做空）"
    conf = max(20.0, min(95.0, conf))
    return {"signal": signal, "action": action, "confidence": round(conf, 1), "reasons": reasons}
