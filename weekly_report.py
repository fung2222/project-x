"""
Project X — 每週績效報告 (legacy helper; full weekly job = `python run.py weekly`)
"""
import json, os, datetime, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import finnhub_api
import vix_guardrail

SIGNALS_PATH = os.path.join(BASE_DIR, "signals.json")
REPORT_PATH = os.path.join(BASE_DIR, "daily_report.json")
PORTFOLIO_PATH = os.path.join(BASE_DIR, "portfolio.json")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate_weekly_report():
    """生成每週績效報告"""
    sig_data = load_json(SIGNALS_PATH)
    signals = sig_data.get("signals", [])
    perf = sig_data.get("performance", {})
    pf = load_json(PORTFOLIO_PATH)
    mode = pf.get("account", {}).get("mode", "observer")

    # 上週數據
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)

    # 按日期分組
    by_date = {}
    for s in signals:
        d = s.get("date")
        if d:
            if d not in by_date:
                by_date[d] = []
            by_date[d].append(s)

    # 過去7天的信號
    recent_dates = sorted(by_date.keys())[-7:]
    week_signals = []
    for d in recent_dates:
        week_signals.extend(by_date[d])

    # VIX 狀態
    regime, vix = finnhub_api.get_vix_regime()
    gr = vix_guardrail.check_guardrail(vix_value=vix, regime=regime)

    # 統計
    buy_signals = [s for s in week_signals if s.get("signal") == "BUY"]
    hold_signals = [s for s in week_signals if s.get("signal") == "HOLD"]
    sell_signals = [s for s in week_signals if s.get("signal") == "SELL"]

    total = perf.get("total_signals", 0)
    hit_rate = perf.get("hit_rate_pct", 0)
    hits = perf.get("hits", 0)
    misses = perf.get("misses", 0)

    # 本週市場概覽
    spy = finnhub_api.get_quote("SPY")
    qqq = finnhub_api.get_quote("QQQ")

    report = {
        "type": "weekly_report",
        "week_start": str(week_ago),
        "week_end": str(today),
        "generated": datetime.datetime.now().isoformat(),
        "market": {
            "vix": round(vix, 2),
            "regime": gr.get("title", regime),
            "spy_price": spy.get("price") if spy else None,
            "qqq_price": qqq.get("price") if qqq else None,
        },
        "week_summary": {
            "days_analyzed": len(recent_dates),
            "buy_signals": len(buy_signals),
            "hold_signals": len(hold_signals),
            "sell_signals": len(sell_signals),
        },
        "performance": {
            "total_signals": total,
            "hits": hits,
            "misses": misses,
            "hit_rate_pct": hit_rate,
        },
        "mode": mode,
        "signals_by_day": [
            {
                "date": d,
                "signals": [
                    {"ticker": s["ticker"], "signal": s["signal"], "confidence": s.get("confidence", 0)}
                    for s in by_date[d]
                ]
            }
            for d in recent_dates
        ],
    }

    return report


def format_weekly_message(report):
    """格式化每週報告為 Telegram 訊息"""
    lines = []

    # Header
    lines.append(f"<b>📊 Project X - 每週績效報告</b>")
    lines.append(f"📅 {report['week_start']} 至 {report['week_end']}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    # 市場概覽
    market = report.get("market", {})
    regime_emoji = "🟢" if market.get("regime") == "正常市場" else "🟡" if "警覺" in market.get("regime", "") else "🔴"
    lines.append(f"<b>🌍 市場概覽</b>")
    lines.append(f"{regime_emoji} VIX: {market.get('vix', 0):.2f} - {html_escape(market.get('regime', '未知'))}")
    spy = market.get("spy_price")
    qqq = market.get("qqq_price")
    if spy:
        lines.append(f"SPY: ${spy:.2f}")
    if qqq:
        lines.append(f"QQQ: ${qqq:.2f}")
    lines.append("")

    # 每週信號摘要
    week = report.get("week_summary", {})
    lines.append(f"<b>📡 本週信號 ({week.get('days_analyzed', 0)}天)</b>")
    lines.append(f"🟢 買入候選: {week.get('buy_signals', 0)} 次")
    lines.append(f"🟡 觀望: {week.get('hold_signals', 0)} 次")
    lines.append(f"🔴 考慮止盈: {week.get('sell_signals', 0)} 次")
    lines.append("")

    # 系統績效
    perf = report.get("performance", {})
    total = perf.get("total_signals", 0)
    hit_rate = perf.get("hit_rate_pct", 0)
    hits = perf.get("hits", 0)
    misses = perf.get("misses", 0)
    lines.append(f"<b>📈 系統績效（累積）</b>")
    if total == 0:
        lines.append("尚無足夠交易數據")
    else:
        lines.append(f"信號命中率樣本: {total} 個（唔係交易筆數）")
        lines.append(f"✅ 命中: {hits} · ❌ 失誤: {misses}")
        lines.append(f"信號命中率: <b>{hit_rate:.0f}%</b>")
    lines.append("")

    # 每日信號回顧
    by_day = report.get("signals_by_day", [])
    if by_day:
        lines.append("<b>📅 每日信號回顧</b>")
        for day_info in by_day[-5:]:  # 顯示最近5天
            date_str = day_info.get("date", "")[-5:]
            day_signals = day_info.get("signals", [])
            buys = [s["ticker"] for s in day_signals if s["signal"] == "BUY"]
            sells = [s["ticker"] for s in day_signals if s["signal"] == "SELL"]
            status = ""
            if buys:
                status += f"🟢 {', '.join(buys)}"
            if sells:
                status += f" 🔴 {', '.join(sells)}" if status else f"🔴 {', '.join(sells)}"
            if not status:
                status = "🟡 觀望"
            lines.append(f"{date_str}: {status}")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ 以上僅供參考，不構成投資建議")
    lines.append("🔄 Project X 每週自動生成")

    return "\n".join(lines)


def html_escape(text):
    if not text:
        return ""
    return (str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;"))


if __name__ == "__main__":
    print("=" * 60)
    print("Project X — 每週績效報告")
    print("=" * 60)

    report = generate_weekly_report()
    message = format_weekly_message(report)
    print(message)

    # 保存報告
    report_file = os.path.join(BASE_DIR, "Reports", f"WeeklyReport_{report['week_end']}.json")
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 報告已保存: {report_file}")
