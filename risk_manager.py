"""
Project X — 止損 / 止盈 / 加倉 邏輯模組
ATR-based 止損，固定 % 止盈
"""
import json, os

PORTFOLIO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.json")
SIGNALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signals.json")


def load_portfolio():
    with open(PORTFOLIO_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_portfolio(pf):
    with open(PORTFOLIO_PATH, "w", encoding="utf-8") as f:
        json.dump(pf, f, ensure_ascii=False, indent=2)


def get_position_with_indicators(ticker):
    """取得持倉 + 對應股票嘅技術指標（RSI、MACD、ATR）"""
    with open(SIGNALS_PATH, encoding="utf-8") as f:
        sig_data = json.load(f)
    today = list({s["date"] for s in sig_data.get("signals", [])})[-1] if sig_data.get("signals") else None
    if not today:
        return None, None
    sig_today = next((s for s in sig_data["signals"] if s.get("date") == today and s.get("ticker") == ticker), None)
    return sig_today, today


def check_stop_loss(position, current_price, atr):
    """ATR-based 止損：跌穿 entry_price - 2*ATR 即觸發"""
    rules = load_portfolio()["rules"]
    atr_mult = rules.get("stop_loss_atr_mult", 2.0)
    entry = position["entry_price"]
    stop_price = entry - (atr * atr_mult)
    stop_pct = (stop_price - entry) / entry * 100
    distance_to_stop = (current_price - stop_price) / current_price * 100
    triggered = current_price <= stop_price
    return {
        "stop_price": round(stop_price, 2),
        "stop_pct": round(stop_pct, 1),
        "current_price": current_price,
        "distance_to_stop_pct": round(distance_to_stop, 1),
        "triggered": triggered,
        "atr": atr,
        "atr_mult": atr_mult
    }


def check_take_profit(position, current_price):
    """固定 % 止盈：升 +10% 即觸發"""
    rules = load_portfolio()["rules"]
    tp_pct = rules.get("take_profit_pct", 0.10)
    entry = position["entry_price"]
    target_price = entry * (1 + tp_pct)
    triggered = current_price >= target_price
    return {
        "target_price": round(target_price, 2),
        "target_pct": round(tp_pct * 100, 0),
        "current_price": current_price,
        "triggered": triggered,
        "pnl_pct": round((current_price - entry) / entry * 100, 2)
    }


def check_add_position(position, current_price, indicators):
    """加倉規則：RSI 仍然 < 45 + MACD 仍然睇漲 + 倉位 < 30% 持倉上限"""
    pf = load_portfolio()
    rules = pf["rules"]
    max_pos_pct = rules.get("max_position_pct", 0.30)
    cash_usd = pf["account"].get("cash_usd", 0)
    equity = pf["account"].get("equity_usd", 641)
    current_pos_pct = (position["current_price"] * position["shares"]) / equity
    can_add = current_pos_pct < max_pos_pct * 0.7  # 已用少於 70% 上限先可以加
    rsi = indicators.get("rsi") if indicators else None
    macd_bull = indicators.get("macd_bullish") if indicators else None
    condition_met = rsi is not None and rsi < 45 and macd_bull
    # 加倉金額 = min(cash * 0.3, equity * (max_pos - current))
    target_add_usd = min(cash_usd * 0.5, equity * max_pos_pct - current_pos_pct * equity)
    shares_to_add = int(target_add_usd / current_price) if current_price else 0
    return {
        "current_pos_pct": round(current_pos_pct * 100, 1),
        "max_pos_pct": round(max_pos_pct * 100, 1),
        "can_add": can_add,
        "rsi": rsi,
        "macd_bullish": macd_bull,
        "condition_met": condition_met,
        "cash_usd": round(cash_usd, 2),
        "shares_to_add": shares_to_add,
        "add_amount_usd": round(shares_to_add * current_price, 2)
    }


def evaluate_all_positions(current_prices):
    """評估所有持倉：止損 / 止盈 / 加倉"""
    pf = load_portfolio()
    results = []
    for pos in pf.get("positions", []):
        ticker = pos["ticker"]
        cur = current_prices.get(ticker, pos["current_price"])
        sig, _ = get_position_with_indicators(ticker)
        atr = sig.get("atr", pos["entry_price"] * 0.03) if sig else pos["entry_price"] * 0.03
        sl = check_stop_loss(pos, cur, atr)
        tp = check_take_profit(pos, cur)
        if pos.get("stop_loss_price"):  # fixed stop recorded at entry wins over recomputed ATR stop
            sl["stop_price"] = pos["stop_loss_price"]
            sl["triggered"] = cur <= pos["stop_loss_price"]
            sl["distance_to_stop_pct"] = round((cur - pos["stop_loss_price"]) / cur * 100, 1)
        if pos.get("take_profit_price"):
            tp["target_price"] = pos["take_profit_price"]
            tp["triggered"] = cur >= pos["take_profit_price"]
        add = check_add_position(pos, cur, sig or {})
        pnl_pct = (cur - pos["entry_price"]) / pos["entry_price"] * 100
        pnl_usd = (cur - pos["entry_price"]) * pos["shares"]
        action = None
        if sl["triggered"]:
            action = "STOP_LOSS"
        elif tp["triggered"]:
            action = "TAKE_PROFIT"
        # ADD_POSITION disabled by rule (no averaging down / no add)
        results.append({
            "ticker": ticker,
            "shares": pos["shares"],
            "entry_price": pos["entry_price"],
            "current_price": cur,
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 2),
            "stop_loss": sl,
            "take_profit": tp,
            "add_position": add,
            "recommended_action": action
        })
    return results


def execute_action(ticker, action, current_price):
    """執行交易動作 → px ledger (v3-core).

    STOP_LOSS / TAKE_PROFIT: paper exit with fee = max(1.00, 0.5%) and net P&L that deducts BOTH
    the buy and the sell fee (fixes the old bug that booked RKLB at +19.06 instead of +18.06).
    ADD_POSITION: refused — averaging down / adding is disabled by rule (config rules.allow_add=false).
    """
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from px import ledger
    if action in ("STOP_LOSS", "TAKE_PROFIT"):
        pf = ledger.load()
        if not ledger.position(pf, ticker):
            return False, "持倉不存在"
        trade = ledger.execute_exit(pf, ticker, float(current_price), action, note="risk_manager.execute_action")
        ledger.save(pf)
        return True, trade
    if action == "ADD_POSITION":
        return False, "規則禁止加倉／攤平（rules.allow_add=false）"
    return False, "不支援嘅動作"


def update_performance_stats(pf, trade):
    """更新命中率統計"""
    signals_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signals.json")
    with open(signals_path, encoding="utf-8") as f:
        sig_data = json.load(f)
    perf = sig_data.get("performance", {})
    total = perf.get("total_signals", 0) + 1
    pnl_pct = trade.get("pnl_pct", 0)
    if pnl_pct >= 2:
        perf["hits"] = perf.get("hits", 0) + 1
    elif pnl_pct >= 0:
        perf["partials"] = perf.get("partials", 0) + 1
    elif pnl_pct <= -2:
        perf["misses"] = perf.get("misses", 0) + 1
    else:
        perf["neutrals"] = perf.get("neutrals", 0) + 1
    perf["total_signals"] = total
    perf["hit_rate_pct"] = round(perf.get("hits", 0) / total * 100, 1) if total else 0
    sig_data["performance"] = perf
    with open(signals_path, "w", encoding="utf-8") as f:
        json.dump(sig_data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 測試：假設 NVDA 今日收 $200
    res = evaluate_all_positions({"NVDA": 200.0})
    print(json.dumps(res, ensure_ascii=False, indent=2))