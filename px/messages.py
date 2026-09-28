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


def scenarios(ctx, pf, entry, real_rows=None):
    pos = pf.get("positions", [])
    parts_base, parts_bull, parts_bear, invalid = [], [], [], []
    for r in real_rows or []:  # Roy's REAL positions first (he executes on Futu; the system only alerts)
        t, px, sl, tp = r["ticker"], r.get("px"), r.get("sl"), r.get("tp")
        parts_base.append(f"真倉 {t} 喺 {f2(sl)}–{f2(tp)} 之間繼續持有（而家 {f2(px)}）")
        parts_bull.append(f"真倉 {t} 升穿 {f2(tp)} → 你喺富途考慮止賺")
        parts_bear.append(f"真倉 {t} 跌穿 {f2(sl)} → 你喺富途手動止蝕、唔攤平")
        invalid.append(f"真倉 {t} 跌穿 {f2(sl)} → 止蝕離場（富途手動）")
    for p in pos:
        t, px, sl, tp = p["ticker"], p.get("current_price"), p.get("stop_loss_price"), p.get("take_profit_price")
        parts_base.append(f"紙上 {t} 喺 {f2(sl)}–{f2(tp)} 之間繼續 HOLD（而家 {f2(px)}）")
        parts_bull.append(f"紙上 {t} 升穿 {f2(tp)} → 紙上止盈")
        parts_bear.append(f"紙上 {t} 跌穿 {f2(sl)} → 紙上止損、唔攤平")
        invalid.append(f"紙上 {t} 跌穿 {f2(sl)} → 止損離場")
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
         f"真倉建議注碼（本金 ≈US$1,280）：每注上限 US${f2(scan.get('max_position_usd'), 0)}（25%）· 最大風險 US${f2(scan.get('risk_per_trade_usd'), 0)}（2%）"
         "· 最多 3 隻 · 現金 ≥20% · 入場前定好止蝕／止賺"]
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
            f"建議注碼：{x['shares']} 股 ≈ US${f2(x['cost_usd'], 0)} / HK${x['cost_hkd']:,.0f}（風險 US${f2(x['risk_usd'], 0)}，來回費用 {f2(x.get('fee_drag_pct'), 1)}%）{cat}\n"
            f"點解：{esc('；'.join(x.get('why', [])))}")
    if show_misses and scan.get("near_misses"):
        L.append("\n<i>差少少：" + "；".join(f"{esc(m['ticker'])}（{esc(m['fail'][0])}）" for m in scan["near_misses"][:4]) + "</i>")
    L.append("\n<i>情境參考，唔係保證：入場區內先考慮、跌穿止損即走、業績前唔開新倉。回測結果見網站（edge 未證實）。</i>")
    return "\n".join(L)


def catalyst_text(earnings_date, days):
    if not earnings_date:
        return "—"
    return f"{earnings_date}" + (f"（{days}個交易日）" if days is not None else "")


# ---------------------------------------------------------------- REAL positions (Roy's Futu account) — shown FIRST
def usd_s(x, nd=2):
    try:
        v = float(x)
    except Exception:
        return "n/a"
    return f"{'+' if v >= 0 else '−'}US${abs(v):,.{nd}f}"


def hkd_s(x):
    try:
        v = float(x)
    except Exception:
        return "n/a"
    return f"{'+' if v >= 0 else '−'}HK${abs(v):,.0f}"


def _qty(q):
    return str(int(q)) if float(q).is_integer() else f"{float(q):g}"


REAL_EMPTY = "🏦 真倉：暫時冇持倉（買入後叫 Hermes 記錄）"


def real_row_lines(r, stale_note=True):
    if r["status"] == "SL_HIT":
        tag = "⛔"
    elif r["status"] == "TP_HIT":
        tag = "🎯"
    elif r["status"] == "NEAR_SL":
        tag = "🔴"
    elif (r.get("pnl_pct") or 0) <= -5:
        tag = "🟠"
    else:
        tag = "🟢"
    stale = "" if r.get("live", True) else ("（報價暫缺，用上次價）" if stale_note else "（上次記錄價）")
    day = f"｜今日 {pct(r['chg_vs_prev'], 1)}" if r.get("chg_vs_prev") is not None else ""
    sl_txt = (f"止蝕 ${f2(r['sl'])}（" + ("已穿！" if r["status"] == "SL_HIT" else f"距 {f2(r['dist_sl_pct'], 1)}%") + "）") if r.get("sl") else "止蝕 未設"
    tp_txt = (f"止賺 ${f2(r['tp'])}（" + ("已到！" if r["status"] == "TP_HIT" else f"差 {f2(r['dist_tp_pct'], 1)}%") + "）") if r.get("tp") else "止賺 未設"
    days = f"持 {r['days_held']} 日" if r.get("days_held") is not None else ""
    return [f"{tag} <b>{esc(r['ticker'])}</b> {_qty(r['shares'])}股 · 現價 ${f2(r['px'])}（成本 ${f2(r['entry'])}）{day}{stale}",
            f"　P&L {usd_s(r['pnl_usd'])} / {hkd_s(r['pnl_hkd'])}（{pct(r['pnl_pct'])}）· {sl_txt} · {tp_txt} · {days}"]


def real_section(ev, title="🏦 真倉（富途）", stale_note=True):
    """Roy's REAL positions block (always first in every report). ev = realpos.evaluate(...)."""
    closed = ""
    if ev.get("n_closed"):
        closed = (f"已平倉 {ev['n_closed']} 筆 · 已實現 {usd_s(ev['realized_usd'])}"
                  + (f" · 勝率 {f2(ev['win_rate_pct'], 0)}%" if ev.get("win_rate_pct") is not None else ""))
    if not ev.get("rows"):
        return [REAL_EMPTY + (f"｜{closed}" if closed else "")]
    L = [f"<b>{title}</b> {ev['n_open']}/{ev['max_positions']} 隻 · 未實現 {usd_s(ev['unrealized_usd'])} / {hkd_s(ev['unrealized_usd'] * ev['fx'])}"
         f" · 真倉回報 {pct(ev['return_pct'])}（起始 US${ev['start_capital_usd']:,.0f}）"]
    for r in ev["rows"]:
        L += real_row_lines(r, stale_note)
    L.append(f"估算現金 US${ev['cash_usd']:,.0f}（{f2(ev['cash_pct'], 0)}%）" + (f" · {closed}" if closed else "")
             + " · P&L 已扣買入費")
    return L


REAL_NOTE = "👉 真倉提醒：落單由你喺富途手動做，系統只提醒、唔會落單；做咗之後話 Hermes 記錄。"


def real_alerts(ev, alerted=None, prev_px=None, day_move_pct=None, downside_only=True):
    """Alerts for REAL positions. alerted = per-session de-dup dict (keys REAL:<T>:<kind>).
    Returns (alert_texts, updated_alerted)."""
    from . import realpos
    c = realpos.cfg()
    rules = load_settings()["rules"]
    alerted = dict(alerted or {})
    day_move = float(day_move_pct if day_move_pct is not None else c["big_drop_alert_pct"])
    out = []
    for r in ev.get("rows", []):
        t, px_ = r["ticker"], r["px"]
        if not r.get("live"):
            k = f"REAL:{t}:QUOTE"
            if k not in alerted:
                out.append(f"🛠 真倉 {t} 報價攞唔到（用上次價 ${f2(px_)}），請自己喺富途睇住")
                alerted[k] = 1
            continue
        if r["status"] == "SL_HIT":
            k = f"REAL:{t}:SL"
            if k not in alerted:
                out.append(f"🚨 真倉 {t} 跌穿止蝕：${f2(px_)} ≤ ${f2(r['sl'])} → 請你喺富途手動賣出 {_qty(r['shares'])} 股（唔好攤平）")
                alerted[k] = px_
        elif r["status"] == "TP_HIT":
            k = f"REAL:{t}:TP"
            if k not in alerted:
                out.append(f"🎯 真倉 {t} 到止賺：${f2(px_)} ≥ ${f2(r['tp'])} → 考慮喺富途手動止賺 {_qty(r['shares'])} 股")
                alerted[k] = px_
        elif r["status"] == "NEAR_SL":
            k = f"REAL:{t}:NEAR_SL"
            d = r["dist_sl_pct"]
            last = alerted.get(k)
            if last is None or d <= float(last) - 1.0:
                out.append(f"⚠️ 真倉 {t} 距止蝕只剩 {f2(d, 1)}%（${f2(px_)} vs ${f2(r['sl'])}）→ 準備好喺富途執行，唔好攤平")
                alerted[k] = d
        chg = r.get("chg_vs_prev")
        if chg is not None and (chg <= -day_move or (not downside_only and chg >= day_move)):
            k = f"REAL:{t}:DAY{'DN' if chg < 0 else 'UP'}"
            if k not in alerted:
                out.append(f"{'📉' if chg < 0 else '📈'} 真倉 {t} 今日{'急跌' if chg < 0 else '急升'} {chg:+.1f}%（vs 昨收）"
                           + (f"，止蝕 ${f2(r['sl'])} 仲有 {f2(r['dist_sl_pct'], 1)}%" if chg < 0 and r.get("sl") else ""))
                alerted[k] = chg
        if prev_px and prev_px.get(t):
            m = (px_ - float(prev_px[t])) / float(prev_px[t]) * 100
            if abs(m) >= rules["big_move_alert_pct"]:
                out.append(f"{'📈' if m > 0 else '📉'} 真倉 {t} 上次檢查後 {f2(prev_px[t])}→{f2(px_)}（{m:+.1f}%）")
    return out, alerted


def real_suggestion_lines(ev, scan, n=2):
    """Entry ideas phrased for Roy's REAL account (≈US$1,280, max 3 positions, ≤25% each, ≥20% cash, SL/TP first)."""
    from . import realpos
    c = realpos.cfg()
    eq = ev["equity_usd"]
    slots = max(0, int(c["max_positions"]) - ev["n_open"])
    L = [f"<b>💡 真倉建議</b>（本金 ≈US${eq:,.0f}：最多 {c['max_positions']} 隻 · 每隻 ≤{c['max_position_pct'] * 100:.0f}%"
         f" ≈US${f2(c['max_position_pct'] * eq, 0)} · 現金 ≥{c['min_cash_pct'] * 100:.0f}% · 入場前定好止蝕／止賺）",
         f"而家真倉 {ev['n_open']}/{c['max_positions']} 隻 · 估算現金 US${ev['cash_usd']:,.0f}（{f2(ev['cash_pct'], 0)}%）"
         + (f" → 最多可再開 {slots} 隻" if slots else " → 已滿，唔開新倉")]
    held = {r["ticker"] for r in ev.get("rows", [])}
    top = [x for x in ((scan or {}).get("top") or []) if x.get("ticker") not in held]  # no adding to real holdings
    if not slots:
        return L
    if not top:
        L.append("• 今日冇（未持有嘅）候選過晒濾網 → 唔入場都係一種決定")
        return L
    for x in top[:n]:
        entry = float(x.get("live_price") or x["entry_zone"][1])
        sh, budget, why = realpos.suggest_shares(ev, entry, x.get("stop"))
        size = (f"建議 {sh} 股 ≈ US${f2(sh * entry, 0)}（HK${sh * entry * ev['fx']:,.0f}）" if sh else f"唔建議（{why}）")
        L.append(f"• {esc(x['ticker'])} 入場區 ${f2(x['entry_zone'][0])}–{f2(x['entry_zone'][1])} · 止蝕 ${f2(x['stop'])} · "
                 f"止賺 ${f2(x['target'])} · R:R {f2(x.get('rr'), 1)} → {size}")
    t0 = top[0]
    L.append(f"<i>落咗單就話 Hermes：「買咗 {esc(t0['ticker'])} N 股 @價，止蝕 {f2(t0['stop'])}，止賺 {f2(t0['target'])}」</i>")
    return L


def paper_brief(acct, n_pos, max_pos, spy_ret=None, qqq_ret=None, actions=None, label="紙上今日"):
    """Condensed paper book (control group): total P&L %, vs SPY/QQQ same period, open count, today's actions."""
    bench = []
    if spy_ret is not None:
        bench.append(f"SPY {pct(spy_ret)}")
    if qqq_ret is not None:
        bench.append(f"QQQ {pct(qqq_ret)}")
    L = [f"<b>🧪 紙上倉（對照組）</b> 總 P&L {pct(acct.get('total_return_pct'))}"
         + (f"（同期 {' · '.join(bench)}）" if bench else "")
         + f" · 持倉 {n_pos}/{max_pos} · 現金 {f2(acct.get('cash_pct'), 0)}%"]
    acts = [a for a in (actions or []) if a]
    if acts:
        txt = "；".join(acts)
        if len(txt) > 230:
            txt = txt[:228] + "…"
        L.append(f"{label}：{esc(txt)}")
    return L
