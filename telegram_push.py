"""
Project X — 每日 Telegram 推送 (legacy entry point)

v3-core (2026-09-28): the old 12-part daily push is replaced.
- `python telegram_push.py` / send_daily_push(): refreshes the analysis if stale and sends ONE
  compact signals message (guarded: once per US session). The Grok Bot routine's own
  decision/teaching messages stay as before, so the nightly total drops from ~15 to ~4.
- The full new daily job (<= 3 messages incl. decisions, teaching, scenarios) is `python run.py daily`.
- Credentials: env TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID first, else local git-ignored telegram_config.json.
"""
import json, os, datetime, sys, requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import finnhub_api
import analyzer
import vix_guardrail

CONFIG_PATH = os.path.join(BASE_DIR, "telegram_config.json")


def load_config():
    """Telegram config (env-first). Returns dict with bot_token / chat_id (values never printed)."""
    from px import config as _pxconfig
    cfg = {}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg["bot_token"] = _pxconfig.get_secret("TELEGRAM_BOT_TOKEN")
    cfg["chat_id"] = _pxconfig.get_secret("TELEGRAM_CHAT_ID")
    return cfg


def html_escape(text):
    if not text:
        return ""
    return (str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;"))


def get_today_news():
    """從 Yahoo Finance 獲取市場新聞"""
    try:
        import yfinance as yf, datetime as dt
        tickers_news = ["SPY", "QQQ", "NVDA", "AMD"]
        all_news = []
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=36)
        for ticker in tickers_news:
            try:
                tk = yf.Ticker(ticker)
                news = tk.news
                if news:
                    for item in news[:3]:
                        content = item.get("content", {})
                        title = content.get("title", "")
                        pub_str = content.get("pubDate", "")
                        if title and pub_str:
                            try:
                                pub_date = datetime.datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                                if pub_date.replace(tzinfo=None) >= cutoff:
                                    all_news.append({
                                        "title": title,
                                        "ticker": ticker,
                                        "pubDate": pub_str[:10],
                                        "summary": content.get("summary", "")[:150]
                                    })
                            except Exception:
                                if title:
                                    all_news.append({
                                        "title": title,
                                        "ticker": ticker,
                                        "pubDate": "",
                                        "summary": content.get("summary", "")[:150]
                                    })
            except Exception:
                pass
        seen = set()
        unique = []
        for n in all_news:
            key = n["title"][:50]
            if key not in seen:
                seen.add(key)
                unique.append(n)
        return unique[:5]
    except Exception as e:
        print(f"News fetch error: {e}")
        return []


def format_news_section(news):
    """新聞區塊 — 中文分析版本（用關鍵詞 + 中文模板，唔顯示英文標題）"""
    ticker_zh = {
        "NVDA": "NVDA 英偉達", "TSLA": "TSLA 特斯拉", "RKLB": "RKLB Rocket Lab",
        "AMD": "AMD", "MSFT": "MSFT 微軟", "GOOGL": "GOOGL 谷歌",
        "META": "META", "AMZN": "AMZN 亞馬遜", "PLTR": "PLTR Palantir", "ARM": "ARM"
    }
    lines = ["<b>📰 核心股新聞分析 (72h內)</b>"]
    lines.append("<i>已分析真實新聞並轉換為中文要點（數據來源：Yahoo + Finnhub + Marketaux）</i>")
    lines.append("")
    has_news = False
    # 來源 1: Yahoo Finance 中文分析
    try:
        prof_path = os.path.join(BASE_DIR, "profiles.json")
        if os.path.exists(prof_path):
            profiles = json.load(open(prof_path, encoding="utf-8"))
            for ticker in ["NVDA", "TSLA", "RKLB"]:
                prof = profiles.get(ticker, {})
                news_items = prof.get("news", [])[:2]
                if news_items:
                    has_news = True
                    lines.append(f"<b>🔹 {ticker_zh.get(ticker, ticker)}</b>")
                    for n in news_items:
                        desc_zh = n.get("desc_zh", "市場相關動態")
                        sentiment = n.get("sentiment", "中性")
                        sentiment_emoji = n.get("sentiment_emoji", "⚪")
                        date = n.get("date", "")
                        lines.append(f"  • {sentiment_emoji} {desc_zh}{f' ({date})' if date else ''}")
                    lines.append("")
    except Exception:
        pass
    # 來源 2: Finnhub 中文分析
    try:
        import finnhub_api
        lines.append("<b>🔄 Finnhub 新聞中文分析</b>")
        fh_count = 0
        for ticker in ["NVDA", "TSLA", "RKLB"]:
            fh_news = finnhub_api.fetch_finnhub_company_news(ticker, days_back=3)
            if fh_news:
                fh_count += 1
                lines.append(f"<i>• {ticker} ({len(fh_news)} 條新聞):</i>")
                for n in fh_news[:1]:
                    desc_zh = n.get("desc_zh") if n.get("desc_zh") else "市場相關動態"
                    sentiment = n.get("sentiment", "中性")
                    sentiment_emoji = n.get("sentiment_emoji", "⚪")
                    date = n.get("date", "")
                    source = n.get("source", "")
                    lines.append(f"  {sentiment_emoji} {sentiment} | {desc_zh} ({date}, {source})")
                lines.append("")
        if fh_count == 0:
            lines.append("<i>暫無 Finnhub 新聞</i>")
    except Exception as e:
        lines.append(f"<i>Finnhub 載入失敗: {html_escape(str(e)[:50])}")
    lines.append("")
    # 來源 3: Marketaux 中文分析（含真實 sentiment 分數）
    try:
        import finnhub_api as fh
        lines.append("<b>🔄 Marketaux 中文分析（含真實 sentiment 分數）</b>")
        for ticker in ["NVDA", "TSLA", "RKLB"]:
            mx_news = fh.fetch_marketaux_news(ticker, limit=2, days_back=3)
            if mx_news:
                lines.append(f"<i>• {ticker}:</i>")
                for n in mx_news[:1]:
                    sentiment_score = n.get("sentiment_score", 0)
                    sentiment_label = n.get("sentiment", "中性")
                    sentiment_emoji = n.get("sentiment_emoji", "⚪")
                    source = n.get("source", "")
                    date = n.get("date", "")
                    # 中文 sentiment 描述
                    if sentiment_score > 0.3:
                        sentiment_zh = "市場明顯看好"
                    elif sentiment_score > 0.1:
                        sentiment_zh = "市場稍為看好"
                    elif sentiment_score < -0.3:
                        sentiment_zh = "市場明顯看淡"
                    elif sentiment_score < -0.1:
                        sentiment_zh = "市場稍為看淡"
                    else:
                        sentiment_zh = "市場中性"
                    lines.append(f"  {sentiment_emoji} {sentiment_zh}（{sentiment_score:+.2f}）")
                    lines.append(f"    <i>來源: {source} ({date})</i>")
                lines.append("")
            else:
                lines.append(f"<i>• {ticker}: 暫無 Marketaux 新聞</i>")
    except Exception as e:
        lines.append(f"<i>Marketaux 載入失敗: {html_escape(str(e)[:50])}")
    return "\n".join(lines)


def format_analyst_detail_section():
    """分析師詳細分佈（Finnhub 數據）"""
    try:
        import finnhub_api
        lines = ["<b>👥 分析師詳細分佈 (Finnhub)</b>"]
        lines.append("")
        for ticker in ["NVDA", "TSLA", "RKLB"]:
            rec = finnhub_api.fetch_finnhub_recommendation(ticker)
            if rec:
                total = rec["total"]
                bullish_pct = (rec["strong_buy"] + rec["buy"]) / total * 100 if total else 0
                lines.append(f"<b>{ticker}</b> ({rec['period']})：")
                lines.append(f"  🟢 強烈買入: {rec['strong_buy']} | 🟢 買入: {rec['buy']}")
                lines.append(f"  🟡 觀望: {rec['hold']} | 🔴 賣出: {rec['sell']} | 🔴 強烈賣出: {rec['strong_sell']}")
                lines.append(f"  看好比例: <b>{bullish_pct:.0f}%</b> ({rec['strong_buy'] + rec['buy']}/{total})")
                lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"<b>👥 分析師詳細分佈</b>\n載入失敗: {html_escape(str(e))}"


def format_market_section(report):
    regime = report.get("market", {})
    regime_emoji = regime.get("regime_emoji", "🟡")
    regime_title = regime.get("regime", "未知")
    vix = regime.get("vix", 0)
    spy = regime.get("spy_price", 0)
    spy_chg = regime.get("spy_change", 0)
    qqq = regime.get("qqq_price", 0)
    qqq_chg = regime.get("qqq_change", 0)
    guardrail = report.get("guardrail", {})
    max_positions = guardrail.get("max_positions", 3)
    min_conf = guardrail.get("min_confidence", 0.7)
    spy_sign = '+' if spy_chg >= 0 else ''
    qqq_sign = '+' if qqq_chg >= 0 else ''
    lines = [
        "<b>📊 市場狀況</b>",
        f"{regime_emoji} VIX: {vix:.2f} - {html_escape(regime_title)}",
        f"SPY: ${spy:.2f} ({spy_sign}{spy_chg:.2f}%)",
        f"QQQ: ${qqq:.2f} ({qqq_sign}{qqq_chg:.2f}%)",
        "",
        "<b>🛡️ VIX Guardrail</b>",
        f"   持倉上限: {max_positions} 隻",
        f"   信心度門檻: {min_conf*100:.0f}%",
    ]
    return "\n".join(lines)


def format_signals_section(report):
    summary = report.get("summary", {})
    buys = summary.get("buy_signals", 0)
    holds = summary.get("hold_signals", 0)
    sells = summary.get("sell_signals", 0)
    lines = ["<b>📡 今日信號摘要</b>"]
    lines.append(f"🟢 買入候選: {buys} 隻")
    lines.append(f"🟡 觀望: {holds} 隻")
    lines.append(f"🔴 考慮止盈: {sells} 隻")
    lines.append("")
    top_picks = report.get("top_picks", [])
    if top_picks:
        lines.append("<b>🎯 TOP 揀選（含買入理由）</b>")
        for pick in top_picks[:3]:
            ticker = pick.get("ticker", "")
            price = pick.get("price", 0)
            conf = pick.get("confidence", 0)
            action = html_escape(pick.get("action", ""))
            rsi = pick.get("rsi", 0)
            macd = pick.get("macd_bullish")
            vol = pick.get("vol_ratio", 1)
            ma50 = pick.get("above_ma50")
            upside = pick.get("upside_pct")
            analyst = pick.get("analyst_consensus", "")
            lines.append(f"\n<b>{html_escape(ticker)}</b> @ ${price:.2f}（置信 {conf:.0f}%）")
            lines.append(f"<b>點解買入：</b>")
            why_buy = []
            if rsi < 40:
                why_buy.append(f"  • RSI {rsi:.0f} 偏低，超賣訊號")
            elif rsi < 50:
                why_buy.append(f"  • RSI {rsi:.0f} 偏低")
            if macd:
                why_buy.append(f"  • MACD 看漲交叉確認")
            if vol >= 1.2:
                why_buy.append(f"  • 成交量放大 {vol:.1f}x")
            if ma50:
                why_buy.append(f"  • 價格高於 50 日均線")
            if upside and upside > 5:
                why_buy.append(f"  • 分析師目標價升幅 +{upside:.1f}%")
            if analyst:
                why_buy.append(f"  • 分析師共識：{analyst}")
            lines.extend(why_buy or ["  • 信心度達標"])
            lines.append(f"<b>建議動作：</b> {action}")
    else:
        lines.append("<b>🔍 點解今日無買入信號？</b>")
        signals = report.get("signals", [])
        if signals:
            for s in signals[:5]:
                ticker = s.get("ticker", "")
                rsi = s.get("rsi", 0)
                conf = s.get("confidence", 0)
                sig_reasons = s.get("signal_reasons", [])
                lines.append(f"\n<b>{html_escape(ticker)}</b>（置信 {conf:.0f}%）")
                why_hold = []
                if rsi >= 50:
                    why_hold.append(f"  • RSI {rsi:.0f} 偏高，未到超賣區")
                if conf < 70:
                    why_hold.append(f"  • 信心度 {conf:.0f}% < 門檻 70%")
                if not s.get("macd_bullish"):
                    why_hold.append(f"  • MACD 尚未看漲")
                if not s.get("above_ma50"):
                    why_hold.append(f"  • 價格仍低於 50 日均線")
                lines.extend(why_hold or ["  • 市場訊號不夠明確"])
                if sig_reasons:
                    lines.append(f"  • 觀望原因：{sig_reasons[0]}")

    opp_picks = report.get("opportunity_picks") or []
    if opp_picks:
        lines.append("")
        lines.append("<b>💡 小資金機會掃描</b>")
        for pick in opp_picks[:3]:
            t = html_escape(pick.get("ticker", ""))
            price = pick.get("price", 0) or 0
            conf = pick.get("confidence", 0) or 0
            upside = pick.get("upside_pct")
            up_s = f" · 目標 +{upside:.1f}%" if upside is not None else ""
            lines.append(f"• <b>{t}</b> @ ${price:.2f}（置信 {conf:.0f}%）{up_s}")

    return "\n".join(lines)


def format_enhanced_indicators_section():
    """增強版分析（MACD 修正、RSI 背馳、多時框、板塊、宏觀、行業）"""
    try:
        import enhanced_indicators as ei
        lines = ["<b>📊 增強分析（資深投資者建議）</b>"]
        # 1. 板塊輪動
        lines.append("\n<b>📌 板塊輪動 (20日回報)</b>")
        sectors = ei.sector_rotation()
        for i, (name, ret) in enumerate(list(sectors.items())[:5]):
            emoji = "🟢" if ret > 0 else "🔴"
            lines.append(f"  {emoji} {name}: {ret:+.2f}%")
        lines.append(f"  <i>最弱: {list(sectors.keys())[-1]} ({sectors[list(sectors.keys())[-1]]:+.2f}%)</i>")
        # 2. 宏觀指標
        lines.append("\n<b>🌍 宏觀經濟指標</b>")
        macro = ei.macro_indicators()
        for name, data in macro.items():
            chg = data['change_pct']
            emoji = "🟢" if chg > 0 else "🔴"
            lines.append(f"  {emoji} {name}: {data['value']} ({chg:+.2f}%)")
        lines.append(f"  <i>下次 FOMC: {ei.get_fomc_next_date()}</i>")
        # 3. 核心股多時框
        lines.append("\n<b>⏰ 多時框分析（日線 + 週線）</b>")
        for ticker in ["NVDA", "TSLA", "RKLB"]:
            ind = ei.get_enhanced_indicators(ticker)
            if ind and 'error' not in ind:
                tf = ind.get('multi_timeframe', {})
                alignment = tf.get('alignment', 'unknown')
                emoji_map = {
                    'strong_bullish': '🟢🟢',
                    'daily_only_bullish': '🟡',
                    'weekly_only_bullish': '🟡',
                    'bearish': '🔴🔴',
                    'unknown': '⚪'
                }
                emoji = emoji_map.get(alignment, '⚪')
                lines.append(f"  {emoji} {ticker}: {alignment}")
                # RSI 背馳
                div = ind.get('rsi_divergence', {})
                if div.get('divergence') == 'bullish':
                    lines.append(f"    <i>⚡ 看漲背馳: {div.get('description', '')}</i>")
                elif div.get('divergence') == 'bearish':
                    lines.append(f"    <i>⚠️ 看跌背馳: {div.get('description', '')}</i>")
        return "\n".join(lines)
    except Exception as e:
        return f"<b>📊 增強分析</b>\n生成失敗: {html_escape(str(e)[:50])}"


def format_review_section(report):
    """每日自我檢討 — 答中／答錯／改善建議"""
    try:
        sig_data = json.load(open(os.path.join(BASE_DIR, "signals.json"), encoding="utf-8"))
        perf = sig_data.get("performance", {})
        total = perf.get("total_signals", 0)
        hits = perf.get("hits", 0)
        misses = perf.get("misses", 0)
        hit_rate = perf.get("hit_rate_pct", 0)
        lines = ["<b>🔍 每日自我檢討</b>"]
        lines.append("")
        if total == 0:
            lines.append("📊 <b>今日檢討重點：</b>")
            lines.append("  • 暫無交易紀錄，繼續觀察")
            lines.append("  • 系統會自動追蹤信號，等到有實際買入先評估表現")
        else:
            lines.append(f"📊 <b>目前表現：</b>")
            lines.append(f"  • 總交易：{total} 筆")
            lines.append(f"  • 命中：{hits} 筆 ({hit_rate:.0f}%)")
            lines.append(f"  • 失誤：{misses} 筆")
            lines.append("")
            lines.append("💡 <b>改善建議：</b>")
            if hit_rate >= 60:
                lines.append("  • 命中率理想，繼續保持紀律")
                lines.append("  • 可以考慮增加倉位至最大上限")
            elif hit_rate >= 40:
                lines.append("  • 命中率中等，檢討 RSI 門檻是否過嚴")
                lines.append("  • 觀察失誤個案嘅共通點")
            else:
                lines.append("  • 命中率偏低，暫停加倉")
                lines.append("  • 重新審視入場條件")
        lines.append("")
        lines.append("⚠️ <b>風險提醒：</b>")
        vix = report.get("market", {}).get("vix", 0)
        if vix >= 25:
            lines.append(f"  • VIX 偏高 ({vix:.1f})，嚴控倉位")
        elif vix >= 20:
            lines.append(f"  • VIX 中等 ({vix:.1f})，謹慎為上")
        else:
            lines.append(f"  • VIX 平靜 ({vix:.1f})，正常操作")
        return "\n".join(lines)
    except Exception as e:
        return f"<b>🔍 自我檢討</b>\n生成失敗: {html_escape(str(e))}"


def format_portfolio_section():
    """持倉狀態"""
    try:
        pf = json.load(open(os.path.join(BASE_DIR, "portfolio.json"), encoding="utf-8"))
        positions = pf.get("positions", [])
        account = pf.get("account", {})
        mode = account.get("mode", "observer")
        phase = account.get("phase", "PHASE_1_OBSERVER")
        cash_usd = account.get("cash_usd", 0)
        equity_usd = account.get("equity_usd", 0)
        lines = ["<b>💼 持倉狀態</b>"]
        lines.append(f"模式: {html_escape(account.get('description', '未知'))}")
        lines.append(f"階段: {html_escape(phase.replace('PHASE_', 'Phase '))}")
        lines.append(f"現金: USD {cash_usd:.2f} | 總值: USD {equity_usd:.2f}")
        if positions:
            lines.append(f"持倉: {len(positions)} 隻")
            for p in positions:
                ticker = p.get("ticker", "")
                qty = p.get("shares", 0)
                entry = p.get("entry_price", 0)
                cur = p.get("current_price", entry)
                pnl_pct = p.get("pnl_pct", 0)
                lines.append(f"  • {html_escape(ticker)} x{qty} @ ${entry:.2f} → ${cur:.2f} ({pnl_pct:+.2f}%)")
        else:
            lines.append("目前無持倉")
        return "\n".join(lines)
    except Exception:
        return "<b>💼 持倉狀態</b>\n暫時無法載入"


def format_yesterday_review():
    """回顧昨日信號 vs 今日結果 — 答中／答錯一目了然"""
    try:
        sig_data = json.load(open(os.path.join(BASE_DIR, "signals.json"), encoding="utf-8"))
        signals = sig_data.get("signals", [])
        # 取昨日 BUY 信號
        from datetime import datetime as dt, timedelta
        today = dt.now().date()
        yesterday = (today - timedelta(days=1)).isoformat()
        yesterday_buys = [s for s in signals if s.get("signal") == "BUY" and s.get("date") == yesterday]
        if not yesterday_buys:
            return "<b>📋 昨日信號回顧</b>\n昨日無 BUY 信號，繼續觀望"
        # 取今日對應股票的價格
        today_str = today.isoformat()
        today_signals = {s.get("ticker"): s for s in signals if s.get("date") == today_str}
        lines = ["<b>📋 昨日信號 vs 今日結果</b>"]
        lines.append(f"（昨日：{yesterday}）")
        lines.append("")
        correct, wrong, pending = 0, 0, 0
        for yb in yesterday_buys[:5]:
            ticker = yb.get("ticker")
            entry_price = yb.get("price", 0)
            today_data = today_signals.get(ticker)
            if today_data:
                exit_price = today_data.get("price", 0)
                pct = ((exit_price - entry_price) / entry_price * 100) if entry_price else 0
                if pct >= 2:
                    status, emoji = "✅ 命中", "var(--green)"
                    correct += 1
                elif pct >= 0:
                    status, emoji = "🟡 部分", "var(--amber)"
                    correct += 1  # 部分算半對
                elif pct >= -2:
                    status, emoji = "➖ 中立", "var(--muted)"
                    pending += 1
                else:
                    status, emoji = "❌ 失誤", "var(--red)"
                    wrong += 1
                lines.append(f"{emoji} <b>{ticker}</b> ${entry_price:.2f} → ${exit_price:.2f} ({pct:+.1f}%) {status}")
            else:
                lines.append(f"⏳ <b>{ticker}</b> ${entry_price:.2f} → 數據未更新")
                pending += 1
        lines.append("")
        lines.append(f"昨日表現：✅{correct} 中／❌{wrong} 失誤／⏳{pending} 等待")
        return "\n".join(lines)
    except Exception as e:
        return f"<b>📋 昨日信號回顧</b>\n無法生成: {html_escape(str(e))}"


def format_performance_section():
    try:
        sig_data = json.load(open(os.path.join(BASE_DIR, "signals.json"), encoding="utf-8"))
        perf = sig_data.get("performance", {})
        total = perf.get("total_signals", 0)
        hits = perf.get("hits", 0)
        partials = perf.get("partials", 0)
        misses = perf.get("misses", 0)
        hit_rate = perf.get("hit_rate_pct", 0)
        partial_rate = perf.get("partial_rate_pct", 0)
        lines = ["<b>📈 系統績效</b>"]
        if total == 0:
            lines.append("累積交易: 0\n尚無足夠數據評估")
        else:
            lines.append(f"累積交易: {total} 筆")
            lines.append(f"✅ 獲利: {hits} 筆 ({hit_rate:.0f}%)")
            lines.append(f"📊 持平: {partials} 筆 ({partial_rate:.0f}%)")
            lines.append(f"❌ 虧損: {misses} 筆")
            lines.append("")
            lines.append(f"總命中率: <b>{hit_rate:.0f}%</b>")
        return "\n".join(lines)
    except Exception:
        return "<b>📈 系統績效</b>\n暫時無法載入"


def generate_self_review():
    try:
        sig_data = json.load(open(os.path.join(BASE_DIR, "signals.json"), encoding="utf-8"))
        signals = sig_data.get("signals", [])
        perf = sig_data.get("performance", {})
        issues, suggestions, strengths = [], [], []
        total = perf.get("total_signals", 0)
        hit_rate = perf.get("hit_rate_pct", 0)
        vix_regime = sig_data.get("vix_regime", "NORMAL")
        buy_signals = [s for s in signals if s.get("signal") == "BUY"]
        hold_signals = [s for s in signals if s.get("signal") == "HOLD"]
        if total > 0:
            if hit_rate < 50:
                issues.append("命中率偏低，需檢討信號標準")
            if len(buy_signals) > len(hold_signals) * 0.5:
                issues.append("買入信號偏多，可能信心度門檻過低")
        else:
            issues.append("數據不足，難以評估系統表現")
        rsi_values = [s.get("rsi", 50) for s in signals]
        if rsi_values and sum(rsi_values)/len(rsi_values) > 55:
            suggestions.append("平均RSI偏高，市場偏熱，需更嚴格篩選")
        if vix_regime == "NORMAL":
            strengths.append("VIX 環境良好，系統正常運行")
        elif vix_regime == "CAUTION":
            suggestions.append("市場警覺期，考慮降低倉位")
        elif vix_regime == "DEFENSIVE":
            issues.append("高波動市場，建議觀望或減倉")
        if total >= 5:
            suggestions.append("數據充足，可考慮調整 RSI 門檻")
        lines = ["<b>🔍 系統自我檢討</b>"]
        if strengths:
            lines.append("<b>✨ 系統優點</b>")
            for s in strengths[:2]:
                lines.append(f"  • {html_escape(s)}")
            lines.append("")
        if issues:
            lines.append("<b>⚠️ 需關注</b>")
            for issue in issues[:2]:
                lines.append(f"  • {html_escape(issue)}")
            lines.append("")
        if suggestions:
            lines.append("<b>💡 優化建議</b>")
            for sug in suggestions[:2]:
                lines.append(f"  • {html_escape(sug)}")
        elif not issues and not suggestions:
            lines.append("系統運行正常，暫無特別建議")
            lines.append("繼續監察市場，及時調整策略")
        return "\n".join(lines)
    except Exception as e:
        return f"<b>🔍 系統自我檢討</b>\n無法生成: {html_escape(str(e))}"


def send_telegram_message(token, chat_id, text):
    """發送 Telegram 訊息（HTML格式）"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        result = resp.json()
        if result.get("ok"):
            return True, result.get("result", {}).get("message_id")
        else:
            return False, result.get("description", "Unknown error")
    except Exception as e:
        from px.telegram import _redact
        return False, _redact(f"{type(e).__name__}: {e}")


def _ensure_fresh_report():
    report = analyzer.get_cached_report(max_age_minutes=30)
    if report is None:
        report = analyzer.analyze_day(quiet=True)
    return report


def build_daily_message():
    """v3: returns [signals_message] (was 12 parts)."""
    from px.jobs import daily as _daily
    from px import messages as _m
    report = _ensure_fresh_report()
    return [_daily.signals_message(report) + "\n\n" + _m.footer()]


def send_daily_push():
    """發送每日推送 — v3: signals message + opportunity-scan Top 5 message, each at most once per US session."""
    from px import config as _pxconfig
    from px.jobs import daily as _daily
    if not _pxconfig.get_secret("TELEGRAM_BOT_TOKEN") or not _pxconfig.get_secret("TELEGRAM_CHAT_ID"):
        if not _pxconfig.is_dry_run():
            print("❌ 未配置 Telegram（TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID）")
            return False, "Token未配置"
    _ensure_fresh_report()
    return _daily.legacy_signals_push()


if __name__ == "__main__":
    print("=" * 60)
    print("Project X — 每日 Telegram 推送")
    print(f"時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    ok, msg = send_daily_push()
    print(f"\n{'✅ 推送成功！' if ok else '❌ 推送失敗: ' + msg}")
