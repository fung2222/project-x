"""telegram_push.py - 硬數據短報告（開市/收市/晨早）
所有股價/P&L 只讀 JSON，禁止 LLM 手算。
"""
import json
import argparse
from datetime import datetime


def _load():
    with open("daily_report.json", "r", encoding="utf-8") as f:
        r = json.load(f)
    with open("portfolio.json", "r", encoding="utf-8") as f:
        p = json.load(f)
    return r, p


def _pos_map(p):
    return {pos["ticker"]: pos for pos in p.get("positions", [])}


def _flag_emoji(flag):
    return {
        "STOP": "🚨",
        "DANGER": "🔴",
        "WARN": "🟠",
        "TP": "💰",
        "OK": "🟢",
    }.get(flag or "OK", "🟢")


def _trend_line(sig, pos=None):
    ind = sig.get("indicators", {})
    line = (
        f"【{sig['ticker']}】US${sig['price']} ({sig['change_pct']:+.2f}%)\n"
        f"趨勢：{sig.get('trend', '—')} | 指引：{sig.get('signal', '—')} ({sig.get('confidence', 0)}%)\n"
        f"結構：MA20 {ind.get('price_vs_ma20_pct', 0):+.1f}% · MA50 {ind.get('price_vs_ma50_pct', 0):+.1f}% · "
        f"5日 {ind.get('chg_5d_pct', 0):+.1f}% · RSI {ind.get('rsi14', 0)} · 量 {ind.get('volume_ratio', 0)}x\n"
        f"行動：{sig.get('action', '—')}"
    )
    if pos:
        flag = _flag_emoji(pos.get("risk_flag"))
        line += (
            f"\n持倉：入 ${pos['entry_price']} → 現 ${pos.get('current_price', sig['price'])} "
            f"({pos.get('pnl_pct', 0):+.2f}%) {flag}\n"
            f"止損 ${pos.get('stop_loss', sig.get('stop_loss_suggested'))} "
            f"(距 {pos.get('dist_to_sl_pp', '?')}pp) · "
            f"止盈 ${pos.get('take_profit', sig.get('take_profit_suggested'))}"
        )
    else:
        line += (
            f"\n建議止損 ${sig.get('stop_loss_suggested')} · "
            f"建議止盈 ${sig.get('take_profit_suggested')}"
        )
    return line


def build_daily_messages():
    """21:30 開盤/日報：趨勢為主，短而硬"""
    r, p = _load()
    posm = _pos_map(p)
    fx = r.get("fx_usdhkd", 7.8)
    msgs = []

    # Part 1: 總覽 + 今日總指引
    alerts = []
    try:
        from risk_manager import update_portfolio
        # 唔再重跑報價（避免 double fetch）；讀 portfolio 已有 alerts 需 risk 先跑
        # pipeline 已跑 risk_manager，直接用 portfolio flags
        for pos in p.get("positions", []):
            if pos.get("risk_flag") in ("WARN", "DANGER", "STOP", "TP"):
                alerts.append(
                    f"{_flag_emoji(pos['risk_flag'])} {pos['ticker']} "
                    f"{pos.get('pnl_pct', 0):+.1f}% flag={pos.get('risk_flag')}"
                )
    except Exception:
        pass

    alert_block = ("\n".join(alerts) if alerts else "✅ 無緊急止損/止盈警示")

    msgs.append(
        f"""📊 Project X 趨勢日報 | {r['date']}

🌍 市場：VIX {r['vix']}（{r['regime']}）· SPY ${r['spy']} · 匯率 {fx}
💼 模擬倉：US${p['total_value_usd']}（{p['total_pnl_pct']:+.2f}%）· 現金 US${p['cash_usd']}

🎯 組合指引：{r.get('portfolio_bias', '—')}

{alert_block}

{r.get('data_cutoff_note', '')}"""
    )

    # Part 2-4: 每隻股趨勢
    for sig in r.get("signals", []):
        if sig.get("error"):
            msgs.append(f"【{sig['ticker']}】數據錯誤：{sig['error']}")
            continue
        msgs.append(_trend_line(sig, posm.get(sig["ticker"])))

    # Part 5: 觀察 + 今日紀律
    sec = r.get("secondary") or []
    sec_txt = " · ".join([f"{s['ticker']} ${s['price']}({s['change_pct']:+.1f}%)" for s in sec]) or "—"
    msgs.append(
        f"""📋 觀察：{sec_txt}

📚 {r.get('learning_focus', '')}

✅ 硬規則
1. 所有價格來自 yfinance 真實數據
2. 止損 -10% / 止盈 +20%（入場價計算）
3. PHASE 1：趨勢未轉強前，優先觀察唔追高
4. 最終買賣決定永遠係你自己"""
    )
    return msgs


def build_close_messages():
    """05:00 收市報告"""
    r, p = _load()
    posm = _pos_map(p)
    msgs = []

    # 找出最佳/最差
    ranked = sorted(p.get("positions", []), key=lambda x: x.get("pnl_pct", 0), reverse=True)
    best = ranked[0] if ranked else None
    worst = ranked[-1] if ranked else None

    msgs.append(
        f"""🌙 Project X 收市報告 | {r['date']}

💼 總值 US${p['total_value_usd']}（{p['total_pnl_pct']:+.2f}% / US${p.get('total_pnl_usd', 0):+.2f}）
💵 現金 US${p['cash_usd']}
🌍 VIX {r['vix']} · SPY ${r['spy']} · {r['regime']}

🎯 {r.get('portfolio_bias', '—')}"""
    )

    pos_lines = []
    for pos in p.get("positions", []):
        pos_lines.append(
            f"{_flag_emoji(pos.get('risk_flag'))} {pos['ticker']}: "
            f"${pos['entry_price']}→${pos.get('current_price')} "
            f"({pos.get('pnl_pct', 0):+.2f}%) · 距止損 {pos.get('dist_to_sl_pp', '?')}pp"
        )
    msgs.append("📈 持倉結算\n" + "\n".join(pos_lines))

    # 趨勢一句
    trend_lines = []
    for sig in r.get("signals", []):
        if not sig.get("error"):
            trend_lines.append(
                f"{sig['ticker']}: {sig.get('trend')} · {sig.get('signal')} "
                f"(score {sig.get('trend_score', 0):+d})"
            )
    msgs.append("🧭 趨勢狀態\n" + "\n".join(trend_lines))

    note = []
    if best:
        note.append(f"最強：{best['ticker']} {best.get('pnl_pct', 0):+.2f}%")
    if worst:
        note.append(f"最弱：{worst['ticker']} {worst.get('pnl_pct', 0):+.2f}%")
    if worst and worst.get("risk_flag") in ("WARN", "DANGER", "STOP"):
        note.append(f"⚠️ 重點盯：{worst['ticker']}（{worst.get('risk_flag')}）")

    msgs.append(
        "📝 收市重點\n" + "\n".join(note) +
        "\n\n聽日動作：只跟趨勢+止損紀律；無明確轉強唔加倉。"
    )
    return msgs


def build_morning_messages():
    """08:30 隔夜複盤（唔係美股盤前）"""
    r, p = _load()
    msgs = []

    msgs.append(
        f"""🌅 Project X 隔夜複盤 | {r['date']}

（香港早晨 · 美股已收市，呢份係隔夜結果複盤）

💼 總值 US${p['total_value_usd']}（{p['total_pnl_pct']:+.2f}%）
🌍 VIX {r['vix']} · SPY ${r['spy']}
🎯 {r.get('portfolio_bias', '—')}"""
    )

    lines = []
    for pos in p.get("positions", []):
        lines.append(
            f"{_flag_emoji(pos.get('risk_flag'))} {pos['ticker']} "
            f"${pos.get('current_price')} ({pos.get('pnl_pct', 0):+.2f}%) · "
            f"止損 ${pos.get('stop_loss')} · 距 {pos.get('dist_to_sl_pp', '?')}pp"
        )
    msgs.append("💼 持倉快睇\n" + "\n".join(lines))

    focus = []
    for sig in r.get("signals", []):
        if sig.get("error"):
            continue
        focus.append(
            f"{sig['ticker']}: {sig.get('trend')} → {sig.get('action')}"
        )
    msgs.append("🧭 趨勢指引\n" + "\n".join(focus))

    danger = [pos for pos in p.get("positions", []) if pos.get("risk_flag") in ("WARN", "DANGER", "STOP")]
    if danger:
        dtxt = "\n".join([
            f"{_flag_emoji(d['risk_flag'])} {d['ticker']} {d.get('pnl_pct'):+.1f}% 要預先寫好止損執行計劃"
            for d in danger
        ])
        msgs.append(f"⚠️ 風險清單\n{dtxt}\n\n今日任務：觀察 + 記筆記，唔好 FOMO。")
    else:
        msgs.append("✅ 暫無高危持倉\n今日任務：觀察趨勢有無延續，唔好追高。")

    return msgs


def build_messages(kind="daily"):
    if kind == "close":
        return build_close_messages()
    if kind == "morning":
        return build_morning_messages()
    return build_daily_messages()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["daily", "close", "morning"], default="daily")
    args = parser.parse_args()
    msgs = build_messages(args.kind)
    for i, m in enumerate(msgs, 1):
        print(f"\n=== Part {i} ({len(m)} chars) ===")
        print(m)
