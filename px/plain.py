"""Plain-language Telegram building blocks (Cantonese, Traditional Chinese) — Roy 2026-09-28:
short, no jargon (no RSI/ATR/MACD/score), real positions first, money in US$ + HK$, one-line reasons,
site link for details. Every number comes from fetched data; anything missing says 數據暫缺."""
from .config import load_settings
from .messages import esc, f2

SITE = "https://fung2222.github.io/project-x/"
MISSING = "數據暫缺"


# ---------------------------------------------------------------- formatting
def pct1(x):
    try:
        return f"{float(x):+.1f}%"
    except Exception:
        return MISSING


def usd(x, signed=False, nd=0):
    try:
        v = float(x)
    except Exception:
        return MISSING
    if signed:
        return f"{'+' if v >= 0 else '-'}US${abs(v):,.{nd}f}"
    return f"US${v:,.{nd}f}"


def hkd(x, fx, signed=False):
    try:
        v = float(x) * float(fx)
    except Exception:
        return MISSING
    if signed:
        return f"{'+' if v >= 0 else '-'}HK${abs(v):,.0f}"
    return f"HK${v:,.0f}"


def price(x):
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return MISSING


def name_of(t):
    n = load_settings().get("names", {}).get(t)
    return f"{t}（{n}）" if n and n != t else t


def link_line():
    return f"👉 詳情睇網站：{SITE}"


def footer_line():
    return "<i>真倉由你喺富途自己落單，系統只提醒；情境參考，唔係保證。</i>\n" + link_line()


# ---------------------------------------------------------------- market mood
def _move_word(x):
    if x is None:
        return None
    a = abs(x)
    if a < 0.3:
        return "窄幅上落"
    if a < 1.2:
        return "升" if x > 0 else "跌"
    return "大升" if x > 0 else "大跌"


def vix_words(vix):
    if vix is None:
        return "恐慌指數（VIX）數據暫缺"
    v = float(vix)
    mood = "正常" if v < 20 else ("偏緊張" if v < 30 else "好緊張，波幅大")
    return f"恐慌指數 {v:.0f}，{mood}"


def day_word(session_date, now=None):
    """'今日' if the quote's session is today's ET session, else '上個交易日（MM-DD）' — never mislabel old data."""
    from . import clock
    if not session_date:
        return "今日"
    today = clock.to_et(now).date().isoformat() if now else clock.now_et().date().isoformat()
    return "今日" if session_date == today else f"上個交易日（{session_date[5:]}）"


def market_lines(spy_chg, qqq_chg, vix, headline=None, when="今日"):
    """1–3 plain sentences on market mood."""
    L = []
    if spy_chg is None and qqq_chg is None:
        L.append(f"美股{when}走勢數據暫缺。")
    else:
        main = qqq_chg if qqq_chg is not None else spy_chg
        L.append(f"美股{when}{_move_word(main)}：標普 {pct1(spy_chg)}、納指 {pct1(qqq_chg)}。")
    L.append(vix_words(vix) + "。")
    if headline:
        from .reasons import headline_text
        L.append("頭條：" + esc(headline_text(headline, 90)))
    return L


# ---------------------------------------------------------------- real positions
def real_rows(ev, reasons=None, trends=None, day_label="今日"):
    """Per stock: day move, since buy (% + US$ + HK$), trend word, one-line reason."""
    reasons, trends = reasons or {}, trends or {}
    L = []
    fx = ev.get("fx")
    for r in ev.get("rows", []):
        t = r["ticker"]
        tag = {"SL_HIT": "⛔", "TP_HIT": "🎯", "NEAR_SL": "🔴"}.get(r["status"], "🟢" if (r.get("pnl_pct") or 0) >= 0 else "🟠")
        day = pct1(r.get("chg_vs_prev")) if r.get("live") and r.get("chg_vs_prev") is not None else MISSING
        stale = "" if r.get("live") else "（報價暫缺，用上次記錄價）"
        tw = trends.get(t)
        L.append(f"{tag} <b>{esc(t)}</b> {_qty(r['shares'])}股｜{day_label} {day}｜買入至今 {pct1(r.get('pnl_pct'))}"
                 f"（{usd(r.get('pnl_usd'), True, 2)}／{hkd(r.get('pnl_usd'), fx, True)}）" + (f"｜趨勢{tw}" if tw else "") + stale)
        L.append(f"　現價 {price(r['px'])}（成本 {price(r['entry'])}）· 止蝕 {price(r.get('sl'))} · 止賺 {price(r.get('tp'))}"
                 + (f" · 持 {r['days_held']} 日" if r.get("days_held") is not None else ""))
        rs = reasons.get(t)
        if rs:
            L.append(f"　原因：{esc(rs.get('text') if isinstance(rs, dict) else rs)}")
    return L


def _qty(q):
    return str(int(q)) if float(q).is_integer() else f"{float(q):g}"


def real_block(ev, reasons=None, trends=None, day_label="今日"):
    from .messages import REAL_EMPTY
    if not ev.get("rows"):
        return [REAL_EMPTY]
    return [f"<b>🏦 真倉 {ev['n_open']}/{ev['max_positions']} 隻</b>"] + real_rows(ev, reasons, trends, day_label)


def capital_line(ev, fx_live=True):
    """資金: 本金、用咗、剩低現金、總賺蝕 (US$ + HK$ + %). Real account (estimate from the recorded trades)."""
    fx = ev.get("fx")
    start = ev.get("start_capital_usd")
    used = (start + (ev.get("realized_usd") or 0) - (ev.get("cash_usd") or 0)) if start is not None else None
    est = "" if fx_live else "（匯率用 7.8 估算）"
    return (f"💰 資金：本金 {usd(start)}（{hkd(start, fx)}）· 用咗 {usd(used)} · 剩低現金 {usd(ev.get('cash_usd'))}"
            f"（{f2(ev.get('cash_pct'), 0)}%）· 總賺蝕 {usd(ev.get('return_usd'), True, 2)}／{hkd(ev.get('return_usd'), fx, True)}"
            f"（{pct1(ev.get('return_pct'))}）{est}")


# ---------------------------------------------------------------- signals (plain)
def hold_signal_lines(ev, trends=None):
    trends = trends or {}
    L = []
    for r in ev.get("rows", []):
        t = r["ticker"]
        if r["status"] == "SL_HIT":
            L.append(f"🔴 考慮賣出 {esc(t)}：已跌穿止蝕 {price(r.get('sl'))}，規則係跌穿就走（喺富途賣 {_qty(r['shares'])} 股）")
        elif r["status"] == "TP_HIT":
            L.append(f"🎯 考慮賣出 {esc(t)}：已到止賺 {price(r.get('tp'))}，可以袋袋平安（喺富途賣 {_qty(r['shares'])} 股）")
        elif r["status"] == "NEAR_SL":
            L.append(f"🟠 揸住 {esc(t)}，但就快到止蝕（差 {f2(r.get('dist_sl_pct'), 1)}%）：跌穿 {price(r.get('sl'))} 就要走，唔好攤平")
        elif not r.get("live"):
            L.append(f"⚪ {esc(t)}：報價暫缺，請自己喺富途睇住止蝕 {price(r.get('sl'))}")
        elif trends.get(t) == "下跌":
            L.append(f"🟡 揸住 {esc(t)}：未到止蝕，但趨勢轉弱，留意止蝕 {price(r.get('sl'))}")
        else:
            L.append(f"🟢 揸住 {esc(t)}：仲喺止蝕 {price(r.get('sl'))} 同止賺 {price(r.get('tp'))} 之間")
    return L


def buy_suggestion(ev, scan, regime=None, market_open=True):
    """(lines, chosen_ticker|None). Plain "考慮買入" for the best scan pick that is safe to suggest,
    sized with realpos.suggest_shares for Roy's real account; otherwise an honest "今日唔建議買".
    Conservative: no suggestion when VIX is missing (UNKNOWN), earnings unknown/within blackout, or outside entry zone."""
    from . import realpos
    c = realpos.cfg()
    s = load_settings()
    slots = max(0, int(c["max_positions"]) - int(ev.get("n_open", 0)))
    fx = ev.get("fx")
    if slots == 0:
        return [f"真倉已經有 {ev['n_open']} 隻（上限 {c['max_positions']}），唔開新倉。"], None
    if regime == "UNKNOWN":
        return ["今日唔建議買新股：恐慌指數（VIX）數據暫缺，睇唔清大市就唔出手。"], None
    held = {r["ticker"] for r in ev.get("rows", [])}
    top = [x for x in ((scan or {}).get("top") or []) if x.get("ticker") not in held]
    if not top:
        return ["今日唔建議買新股：冇一隻過晒系統條件（趨勢向上、成交夠、回報比風險大兩倍以上）。唔買都係一種決定。"], None
    blackout = s["scan"]["earnings_blackout_days"]
    why_not = []
    for x in top[:3]:
        t = x["ticker"]
        if x.get("earnings_days") is not None and x["earnings_days"] <= blackout:
            why_not.append(f"{t} {x['earnings_days']} 個交易日內出業績")
            continue
        if not x.get("earnings_date") and x.get("earnings_known") is False:
            why_not.append(f"{t} 業績日未知")
            continue
        live = x.get("live_price")
        lo, hi = x["entry_zone"]
        if market_open and live and not (lo * 0.99 <= live <= hi * 1.02):
            why_not.append(f"{t} 現價 {price(live)} 唔喺入場區 {price(lo)}–{price(hi)}")
            continue
        entry = float(live or hi)
        sh, _budget, why = realpos.suggest_shares(ev, entry, x.get("stop"))
        if not sh:
            why_not.append(f"{t}：{why}")
            continue
        when = "" if market_open else "今晚開市後"
        zone = f"（價錢喺 {price(lo)}–{price(hi)} 之間先買，唔好追高）" if not market_open or not live else ""
        sl_pct = (float(x["stop"]) / entry - 1) * 100
        tp_pct = (float(x["target"]) / entry - 1) * 100
        far = "，係之前高位、好遠，唔一定去到" if tp_pct > 30 else ""
        return [f"🛒 {when}考慮買入 {esc(name_of(t))}：建議買 {sh} 股約 {usd(sh * entry)}（{hkd(sh * entry, fx)}），"
                f"止蝕 {price(x['stop'])}（{sl_pct:+.0f}%），止賺 {price(x['target'])}（{tp_pct:+.0f}%{far}）{zone}",
                "　（落咗單就話 Hermes：「買咗 " + esc(t) + " N 股 @價，止蝕…，止賺…」）"], t
    return ["今日唔建議買新股：" + "；".join(why_not[:3]) + "。"], None


# ---------------------------------------------------------------- picks (潛力股)
SETUP_WORDS = {"放量突破20日高": "啱啱帶量升穿 20 日高位", "上升趨勢回踩MA20": "升勢中回落到 20 日平均價附近（較穩陣嘅買位）",
               "趨勢延續": "升勢持續"}


def pick_reason(x, news_text=None):
    parts = []
    e20, e60 = x.get("ex_qqq_20d_pp"), x.get("ex_qqq_60d_pp")
    rel = [f"近{lbl}{'比納指強' if v >= 0 else '比納指弱'} {abs(v):.0f}%" for lbl, v in (("1個月", e20), ("3個月", e60)) if v is not None]
    if rel:
        parts.append("、".join(rel))
    sw = SETUP_WORDS.get(x.get("setup"))
    if sw:
        parts.append(sw)
    if x.get("earnings_date"):
        parts.append(f"業績 {x['earnings_date'][5:]}")
    elif x.get("earnings_known") is False:
        parts.append("業績日未知")
    txt = "，".join(parts) or "過晒系統條件"
    if news_text:
        txt += f"｜新聞：{news_text}"
    return txt


def picks_block(scan, news=None, n=3, title="⭐ 潛力股"):
    news = news or {}
    top = ((scan or {}).get("top") or [])[:n]
    if scan is None or scan.get("error"):
        return [f"<b>{title}</b>：掃描數據暫缺，請睇網站。"]
    if not top:
        return [f"<b>{title}</b>：今日冇一隻值得買（冇一隻過晒趨勢、成交同回報風險條件）。"]
    L = [f"<b>{title}</b>（系統揀，唔係保證）"]
    for i, x in enumerate(top, 1):
        live = f" 現價 {price(x.get('live_price'))}" if x.get("live_price") else ""
        L.append(f"{i}. <b>{esc(x['ticker'])}</b> {esc(load_settings()['names'].get(x['ticker'], ''))}{live}："
                 f"{esc(pick_reason(x, news.get(x['ticker'])))}")
    return L


# ---------------------------------------------------------------- paper book (one line)
def paper_line(acct, n_pos, max_pos, spy_ret=None, qqq_ret=None, actions=None, label="今日"):
    from .messages import paper_brief
    return paper_brief(acct, n_pos, max_pos, spy_ret, qqq_ret, actions, label=label)[0]
