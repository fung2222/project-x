"""Telegram message templates (HTML, Traditional Chinese / Cantonese). Concise by design:
open = 1 msg, daily <= 3 msgs, hourly = alert-only (+ first-of-session status), weekly = 1 msg."""
from html import escape as _esc

from .config import load_settings


def esc(x):
    return _esc(str(x if x is not None else ""), quote=False)


def f2(x, nd=2):
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return "n/a"


def pct(x, nd=2):
    try:
        return f"{float(x):+.{nd}f}%"
    except Exception:
        return "n/a"


def footer():
    t = load_settings()["telegram"]
    return f"<i>{esc(t['footer'])}</i>\n{t['site_url']}"


def money(usd, fx):
    try:
        return f"USD {float(usd):,.2f}（HK${float(usd) * float(fx):,.0f}）"
    except Exception:
        return f"USD {usd}"


# ---------------------------------------------------------------- teaching bank
OPEN_TEACH = {
    "NORMAL": "開市唔使急：先睇 VIX 同大盤方向，持倉只跟預設止損／止盈，唔好喺頭半小時用感覺加倉攤平。",
    "CAUTION": "VIX 已入謹慎區：開市波動會放大，優先守住止損線，新倉等確認訊號先動手。",
    "DEFENSIVE": "高波動防禦日：現金係倉位，開市只容許止損／止盈執行，唔追缺口、唔攤平。",
    "NEAR_SL": "開市近止損最危險：唔好加倉攤平；價一穿預設止損就執行，情緒留畀下一個訊號。",
    "GAP_DOWN": "開市急跌先分清缺口定趨勢：未穿止損就忍住唔抄底，等頭半小時波動收斂再決定。",
    "EXIT_TP": "觸及止盈：鎖利優先於貪多，執行預設規則最穩陣；賣咗之後再升都唔好 FOMO 追返。",
    "EXIT_SL": "止損執行咗：細蝕係保護本金嘅成本，冷靜期內唔好即刻買返同一隻報仇。",
}


def daily_teaching(ctx, pf, entry, exits, top_skip, overbought):
    """Pick one concise lesson (<= ~220 chars) that matches today's situation."""
    pos = pf.get("positions", [])
    near = [p for p in pos if (p.get("dist_to_sl_pct") or 99) < 3]
    if exits:
        e = exits[0]
        if e["reason"] == "STOP_LOSS":
            return (f"{e['ticker']} 今日按紀律止損（淨 {e['net_pnl_usd']:+.2f}）。止損唔係失敗，係將虧損限死喺 2% 風險之內；"
                    f"冷靜期 {load_settings()['rules']['cooldown_after_sl_days']} 個交易日內唔好買返同一隻。")
        return (f"{e['ticker']} 今日止盈（淨 {e['net_pnl_usd']:+.2f}）。鎖利之後再升都唔好追，"
                "重開要有新論述＋新確認位；固定 +10% 止盈就係為咗避免貪心。")
    if entry:
        return (f"今日紙上買入 {entry['ticker']}（setup {entry.get('setup')}）。入場前已經計好：止損位、每筆風險 ≤2% 權益、"
                "倉位 ≤25%、現金 ≥20%。之後只跟計劃，唔因為一兩日波動改止損。")
    if near:
        p = near[0]
        return (f"{p['ticker']} 距止損只有 {f2(p.get('dist_to_sl_pct'),1)}%。近止損最忌加倉攤平「拉低成本」——"
                "規則寫明唔攤平；穿咗就走，保留子彈畀下一個高質量 setup。")
    if ctx["regime"] != "NORMAL":
        return "VIX 升溫時，系統自動收緊：持倉上限減少、信心門檻提高。高波動日少做少錯，現金本身就係一個倉位。"
    if top_skip:
        return (f"今日最接近嘅候選係 {top_skip['ticker']}（{f2(top_skip['confidence'],0)}%），但 {top_skip['why']}。"
                "機械 BUY 唔等於要買：要同時過晒信心、setup、成交量、趨勢同組合限制先值得落注。")
    if overbought >= 3:
        return f"今日有 {overbought} 隻超買（RSI>68）。超買唔等於即刻跌，但追高嘅風險回報差；冇持倉就唔做空，等回調到 MA50 附近先再評估。"
    return "冇合適 setup 嘅日子，最好嘅動作就係唔動。細資金最大優勢係可以等：等升勢回調（企穩 MA50＋RSI 30–45）先出手。"


def scenarios(ctx, pf, entry):
    pos = pf.get("positions", [])
    parts_base, parts_bull, parts_bear, invalid = [], [], [], []
    for p in pos:
        t, px, sl, tp = p["ticker"], p.get("current_price"), p.get("stop_loss_price"), p.get("take_profit_price")
        parts_base.append(f"{t} 喺 {f2(sl)}–{f2(tp)} 之間繼續 HOLD（而家 {f2(px)}）")
        parts_bull.append(f"{t} 升穿 {f2(tp)} → 紙上止盈")
        parts_bear.append(f"{t} 跌穿 {f2(sl)} → 紙上止損、唔攤平")
        invalid.append(f"{t} 跌穿 {f2(sl)} → 止損離場")
    vix = ctx.get("vix")
    base = "；".join(parts_base) or "空倉／低倉位，等高質量 setup"
    bull = "；".join(parts_bull) or "出現過晒 gates 嘅候選 → 最多開 1 個新倉"
    bear = "；".join(parts_bear) or "大市轉弱 → 維持高現金"
    base = f"VIX {f2(vix)} {ctx['regime_zh']}；" + base
    bear += "；VIX >30 → 防禦模式、暫停新倉"
    invalid.append("VIX > 30 → 防禦模式：只准 setup A 且信心 ≥85%")
    return {"base": base, "bull": bull, "bear": bear}, invalid


# ---------------------------------------------------------------- opportunity scan (Top 5)
def scan_message(scan, title="🚀 高潛力機會掃描 Top 5", show_misses=True):
    """Ranked watchlist with entry zone / stop / target / R:R / size (shares + HKD) / why / catalyst."""
    if not scan or not scan.get("top") and not scan.get("near_misses"):
        return f"<b>{title}</b>\n今日冇數據（掃描失敗），請睇網站。"
    fx = scan.get("fx_usdhkd") or 7.8
    L = [f"<b>{title}</b>（{esc(scan.get('bar_date') or '')} 收市數據；掃 {scan.get('scanned', 0)} 隻，"
         f"{scan.get('passed', 0)} 隻過濾）",
         f"每注上限 US${f2(scan.get('max_position_usd'), 0)}（25%）· 每注最大風險 US${f2(scan.get('risk_per_trade_usd'), 0)}（2%）"]
    if not scan.get("top"):
        L.append("今日冇一隻同時過晒趨勢／流動性／R:R≥2 條件 → 唔入場都係一種決定。")
    for i, x in enumerate(scan.get("top", []), 1):
        live = f"（現 ${f2(x.get('live_price'))} {pct(x.get('live_change_pct'))}）" if x.get("live_price") else ""
        cat = ""
        if x.get("earnings_date"):
            cat = f"｜📅 業績 {x['earnings_date']}" + (f"（{x['earnings_days']} 個交易日後）" if x.get("earnings_days") is not None else "")
        L.append(
            f"\n<b>{i}. {esc(x['ticker'])}</b> {esc(load_settings()['names'].get(x['ticker'], ''))} · 分數 {f2(x['score'], 0)} · {esc(x['setup'])}{live}\n"
            f"入場區 ${f2(x['entry_zone'][0])}–{f2(x['entry_zone'][1])} · 止損 ${f2(x['stop'])}（−{f2(x['stop_pct'], 1)}%）· "
            f"目標 ${f2(x['target'])}（+{f2(x['target_pct'], 1)}%，{esc(x['target_mode'])}）· R:R {f2(x['rr'], 1)}\n"
            f"注碼：{x['shares']} 股 ≈ US${f2(x['cost_usd'], 0)} / HK${x['cost_hkd']:,.0f}（風險 US${f2(x['risk_usd'], 0)}，來回費用 {f2(x.get('fee_drag_pct'), 1)}%）{cat}\n"
            f"點解：{esc('；'.join(x.get('why', [])))}")
    if show_misses and scan.get("near_misses"):
        L.append("\n<i>差少少：" + "；".join(f"{esc(m['ticker'])}（{esc(m['fail'][0])}）" for m in scan["near_misses"][:4]) + "</i>")
    L.append("\n<i>情境參考，唔係保證：入場區內先考慮、跌穿止損即走、業績前唔開新倉。回測結果見網站（edge 未證實）。</i>")
    return "\n".join(L)


def catalyst_text(earnings_date, days):
    if not earnings_date:
        return "—"
    return f"{earnings_date}" + (f"（{days}日）" if days is not None else "")
