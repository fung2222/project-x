"""analyzer.py - 趨勢導向分析引擎（硬數據 + 明確指引）"""
from data_fetcher import (get_verified_quote, get_indicators,
                           get_vix, get_fx_usdhkd, get_spy)
import json
from datetime import datetime


def _trend_bias(ind):
    """綜合 MA20/MA50/RSI/量能 得出趨勢偏向"""
    score = 0
    notes = []

    # 中期趨勢：價格 vs MA50
    if ind["price_vs_ma50_pct"] >= 3:
        score += 2
        notes.append("中期偏強(價>MA50)")
    elif ind["price_vs_ma50_pct"] >= 0:
        score += 1
        notes.append("中期略強")
    elif ind["price_vs_ma50_pct"] > -5:
        score -= 1
        notes.append("中期略弱")
    else:
        score -= 2
        notes.append("中期偏弱(價遠低MA50)")

    # 短期趨勢：價格 vs MA20 + MA20 vs MA50
    if ind["price_vs_ma20_pct"] >= 0 and ind.get("ma20_vs_ma50_pct", 0) >= 0:
        score += 2
        notes.append("短期上升結構")
    elif ind["price_vs_ma20_pct"] >= 0:
        score += 1
        notes.append("短線回穩")
    elif ind["price_vs_ma20_pct"] > -3:
        score -= 1
        notes.append("短線回吐")
    else:
        score -= 2
        notes.append("短線弱勢")

    # 動能 RSI
    rsi = ind["rsi14"]
    if 45 <= rsi <= 65:
        score += 1
        notes.append(f"RSI健康({rsi})")
    elif rsi > 70:
        score -= 1
        notes.append(f"RSI過熱({rsi})")
    elif rsi < 30:
        score += 0  # 超賣可反彈，但唔代表趨勢轉強
        notes.append(f"RSI超賣({rsi})")
    elif rsi < 40:
        notes.append(f"RSI偏弱({rsi})")

    # 5日動能
    chg5 = ind.get("chg_5d_pct", 0)
    if chg5 >= 3:
        score += 1
        notes.append(f"5日+{chg5}%")
    elif chg5 <= -5:
        score -= 1
        notes.append(f"5日{chg5}%")

    # 量能確認
    vol = ind["volume_ratio"]
    if vol >= 1.5 and score > 0:
        score += 1
        notes.append(f"放量確認({vol}x)")
    elif vol >= 1.5 and score < 0:
        score -= 1
        notes.append(f"放量下跌({vol}x)")

    return score, notes


def generate_signal(ticker):
    q = get_verified_quote(ticker)
    ind = get_indicators(ticker)
    if not q or not ind:
        return {"ticker": ticker, "error": "數據取唔到"}

    price = q["price"]
    rsi = ind["rsi14"]
    score, notes = _trend_bias(ind)

    # 明確趨勢分級
    if score >= 4:
        trend = "上升趨勢"
        signal = "偏多持有/可分批佈局"
        action = "趨勢偏多：可持有；若未持倉可等回踩 MA20 分批觀察"
        confidence = min(78, 58 + score * 3)
    elif score >= 2:
        trend = "偏多整理"
        signal = "偏多觀望"
        action = "短中線略偏多，但未到強力追入位；以持有/觀望為主"
        confidence = 62
    elif score >= 0:
        trend = "中性震盪"
        signal = "觀望為主"
        action = "方向未明，唔好追高殺低；等站穩 MA20/MA50 先再諗"
        confidence = 55
    elif score >= -2:
        trend = "偏空回調"
        signal = "偏空觀望/減倉準備"
        action = "弱勢回調中：已持倉嚴守止損；未持倉暫唔好抄底"
        confidence = 62
    else:
        trend = "下降趨勢"
        signal = "防禦/避免新倉"
        action = "趨勢偏空：優先風險控制；新資金暫時避開"
        confidence = min(78, 58 + abs(score) * 3)

    # 超買超賣微調（唔推翻主趨勢）
    if rsi > 70 and score > 0:
        signal = "偏多但勿追高"
        action = "上升中但 RSI 過熱，宜等回檔，唔好 FOMO 追入"
        confidence = max(55, confidence - 8)
    if rsi < 32 and score < 0:
        signal = "偏空但留意反彈"
        action = "下跌中接近超賣，可觀察止跌，但未確認前唔好重倉抄底"
        confidence = max(55, confidence - 5)

    reason = f"趨勢={trend}（score {score:+d}）。" + "；".join(notes[:4]) + "。"

    sl = round(price * 0.90, 2)
    tp = round(price * 1.20, 2)

    return {
        "ticker": ticker,
        "price": price,
        "change_pct": q["change_pct"],
        "signal": signal,
        "trend": trend,
        "trend_score": score,
        "action": action,
        "confidence": confidence,
        "reason": reason,
        "stop_loss_suggested": sl,
        "take_profit_suggested": tp,
        "indicators": ind
    }


def analyze_all():
    results = []
    for t in ["NVDA", "TSLA", "RKLB"]:
        results.append(generate_signal(t))

    secondary = []
    for t in ["AMD", "MSFT"]:
        q = get_verified_quote(t)
        if q:
            secondary.append({
                "ticker": t,
                "price": q["price"],
                "change_pct": q["change_pct"]
            })

    vix_now = get_vix()
    spy_now = get_spy()
    fx_now = get_fx_usdhkd()

    # 組合層面一句指引
    bull = sum(1 for s in results if s.get("trend_score", 0) >= 2)
    bear = sum(1 for s in results if s.get("trend_score", 0) <= -2)
    if bull >= 2:
        portfolio_bias = "組合偏多：可持有強勢股，弱勢股單獨管理"
    elif bear >= 2:
        portfolio_bias = "組合偏空：優先防守，新倉暫緩"
    else:
        portfolio_bias = "組合中性：分股處理，唔好一刀切"

    report = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M HKT"),
        "data_cutoff_note": "⚠️ 數據來自 yfinance 真實報價；開盤時段波動大",
        "vix": vix_now,
        "spy": spy_now,
        "fx_usdhkd": fx_now,
        "regime": "正常市場" if vix_now < 20 else ("謹慎" if vix_now < 30 else "防禦"),
        "portfolio_bias": portfolio_bias,
        "signals": results,
        "secondary": secondary,
        "learning_focus": "今日重點：趨勢(score) + MA20/MA50 結構 + 止損距離，先守紀律再談進場"
    }

    with open("daily_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


if __name__ == "__main__":
    r = analyze_all()
    print(json.dumps(r, ensure_ascii=False, indent=2))
