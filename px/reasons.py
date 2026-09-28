"""Plain-language move reasons + news headlines (rule-based, NO LLM, never invents a cause).

reason(ticker, chg) compares the stock's move with the market (QQQ / SPY) and its sector ETF
(settings.sector_etfs) and attaches the most relevant recent headline:
  Finnhub /company-news (free; cached per ticker for settings.api_budget.news_cache_hours)
  -> Marketaux /news/all only if Finnhub has nothing (hard cap settings.api_budget.marketaux_per_day, default 60).
Headlines stay in English (trimmed) with a Chinese topic tag from a fixed keyword table; if there is no
relevant headline the text says so ("冇特別新聞…") instead of guessing.
Cache: state/news_cache.json. Website copy: data/reasons.json (written by save_site())."""
import datetime as dt
import json
import os
import re
import tempfile
import time

from . import apistate, clock
from .config import STATE_DIR, get_secret, load_settings, network_off, path

CACHE_NAME = "news_cache.json"
SITE_PATH = os.environ.get("PX_REASONS_PATH") or path("data", "reasons.json")

TAGS = [  # (regex on lower-case headline, Chinese tag) — first match wins
    (r"\b(earnings|quarterly results|q[1-4] results|revenue|eps|beats?|miss(es|ed)?)\b", "業績"),
    (r"\bguidance|outlook|forecast\b", "業績指引"),
    (r"\bupgrade[sd]?\b", "評級上調"),
    (r"\bdowngrade[sd]?\b", "評級下調"),
    (r"\bprice target\b", "目標價"),
    (r"\b(offering|dilution|convertible|raises? \$?\d)", "集資／增發"),
    (r"\b(contract|deal|partnership|partners|agreement|order|award(ed)?)\b", "合作／合約"),
    (r"\b(acquire[sd]?|acquisition|merger|buyout|takeover)\b", "收購合併"),
    (r"\b(lawsuit|probe|investigation|sec |short seller|short report|fraud)\b", "官司／調查"),
    (r"\b(fda|approval|approved|trial)\b", "審批"),
    (r"\b(launch(es|ed)?|unveil(s|ed)?|rollout|release[sd]?)\b", "新產品"),
    (r"\b(tariff|fed|rates?|inflation|cpi|jobs report)\b", "宏觀"),
    (r"\b(bitcoin|crypto|btc)\b", "加密貨幣"),
    (r"\b(insider|ceo|cfo) (buys?|sells?|sold|bought)\b", "管理層買賣"),
]
GENERIC = re.compile(r"(\b\d+\s+(top\s+)?(stocks?|picks|etfs)\b|stocks? to (buy|watch|sell)|\bbest\b.*\bstocks?\b|"
                     r"\bmarket (wrap|update)\b|\bmoving (in|after)\b|\bmovers\b|\bpremarket\b|\bwhy .* stock\b.*\?$)")


def _cfg():
    c = {"marketaux_per_day": 60, "finnhub_news_per_day": 120, "news_cache_hours": 6}
    c.update({k: v for k, v in load_settings().get("api_budget", {}).items() if not k.startswith("_")})
    return c


def _cpath():
    return os.path.join(STATE_DIR, CACHE_NAME)


def _load():
    try:
        with open(_cpath(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    cutoff = time.time() - 3 * 86400
    d = {k: v for k, v in d.items() if float(v.get("ts", 0)) >= cutoff}
    fd, tmp = tempfile.mkstemp(prefix=".news.", dir=STATE_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, _cpath())


def tag_zh(headline):
    h = (headline or "").lower()
    for pat, tag in TAGS:
        if re.search(pat, h):
            return tag
    return None


def trim(s, n=80):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _finnhub_news(ticker, days=3):
    from . import finnhub
    if apistate.used_today("finnhub_news") >= int(_cfg()["finnhub_news_per_day"]):
        print(f"[reasons] finnhub news daily cap reached; skip {ticker}")
        return None
    today = clock.now_et().date()
    apistate.count("finnhub_news")
    d, err = finnhub.get("company-news", {"symbol": ticker, "from": (today - dt.timedelta(days=days)).isoformat(),
                                          "to": today.isoformat()})
    if d is None or not isinstance(d, list):
        return None
    return [{"headline": x.get("headline"), "source": x.get("source"), "url": x.get("url"),
             "ts": x.get("datetime"), "related": x.get("related"), "provider": "finnhub"} for x in d if x.get("headline")]


def marketaux_left():
    return max(0, int(_cfg()["marketaux_per_day"]) - apistate.used_today("marketaux"))


def _marketaux_news(ticker):
    key = get_secret("MARKETAUX_API_KEY")
    if not key:
        return None
    if marketaux_left() <= 0:
        print(f"[reasons] marketaux daily budget used ({_cfg()['marketaux_per_day']}); skip {ticker}")
        return None
    import requests
    apistate.count("marketaux")
    after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    try:
        r = requests.get("https://api.marketaux.com/v1/news/all",
                         params={"symbols": ticker, "filter_entities": "true", "language": "en",
                                 "published_after": after, "limit": 3, "api_token": key}, timeout=10)
    except Exception as e:
        print(f"[reasons] marketaux {ticker} network error: {type(e).__name__}")
        return None
    if r.status_code == 429:
        apistate.set_cooldown("marketaux", time.time() + 3600, "HTTP 429")
        return None
    if r.status_code != 200:
        print(f"[reasons] marketaux {ticker} HTTP {r.status_code}")
        return None
    out = []
    for x in (r.json() or {}).get("data", []) or []:
        try:
            ts = dt.datetime.fromisoformat(str(x.get("published_at")).replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = None
        out.append({"headline": x.get("title"), "source": x.get("source"), "url": x.get("url"), "ts": ts,
                    "related": ticker, "provider": "marketaux"})
    return out


def news(ticker):
    """Recent headlines for ticker (cached). [] when none; None never escapes."""
    c = _load()
    hrs = float(_cfg()["news_cache_hours"])
    e = c.get(ticker)
    if e and time.time() - float(e.get("ts", 0)) < hrs * 3600:
        return e.get("items") or []
    if network_off():
        return (e or {}).get("items") or []
    items = _finnhub_news(ticker)
    if not items and not apistate.in_cooldown("marketaux"):
        items = _marketaux_news(ticker) or items
    if items is None:  # both failed: keep the old cache entry if any, do not overwrite with "no news"
        return (e or {}).get("items") or []
    c[ticker] = {"ts": time.time(), "items": items[:20]}
    _save(c)
    return c[ticker]["items"]


def best_headline(ticker, items, max_age_h=36):
    """Most relevant recent headline: mentions the ticker or company name, not a generic listicle."""
    name = load_settings().get("names", {}).get(ticker, "")
    first = re.split(r"[ .,(]", name)[0].lower() if name else ""
    now = time.time()
    cands = []
    for x in items or []:
        h = x.get("headline") or ""
        ts = float(x.get("ts") or 0)
        if not h or (ts and now - ts > max_age_h * 3600):
            continue
        low = h.lower()
        if GENERIC.search(low):
            continue
        mention = bool(re.search(rf"\b{re.escape(ticker.lower())}\b", low)) or (len(first) >= 3 and first in low)
        if not mention:
            continue
        cands.append((ts, x))
    if not cands:
        return None
    cands.sort(key=lambda y: y[0], reverse=True)
    return cands[0][1]


def headline_text(x, n=80):
    if not x:
        return None
    tag = tag_zh(x.get("headline"))
    return (f"［{tag}］" if tag else "") + trim(x.get("headline"), n)


def sector_etf(ticker):
    s = load_settings()
    for th, names in s.get("themes", {}).items():
        if ticker in names:
            etf = (s.get("sector_etfs") or {}).get(th)
            return etf if etf and etf != "QQQ" else None
    return None


def trend_word(ticker):
    """上升 / 橫行 / 下跌 from completed daily bars (price vs 20- and 50-day averages); None if no data."""
    from . import marketdata
    df = marketdata.history(ticker)
    if df is None or len(df) < 55:
        return None
    c = df["Close"].dropna()
    px, ma20, ma50 = float(c.iloc[-1]), float(c.iloc[-20:].mean()), float(c.iloc[-50:].mean())
    if px > ma20 > ma50:
        return "上升"
    if px < ma20 < ma50:
        return "下跌"
    return "橫行"


def move_class(chg, mkt, sec=None, etf=None):
    """Compare a daily move with the market (QQQ) and sector. Returns (kind, text) — kind in
    market / sector / stock / flat / unknown."""
    if chg is None:
        return "unknown", "今日走勢數據暫缺"
    if abs(chg) < 1.0 and (mkt is None or abs(mkt) < 1.0):
        return "flat", "窄幅上落"
    if mkt is not None:
        diff = chg - mkt
        if abs(diff) <= max(1.5, 0.5 * abs(mkt)) and (chg * mkt > 0 or abs(chg) < 1.0):
            return "market", f"跟大市{'升' if chg > 0 else '跌'}（納指 {mkt:+.1f}%）"
    if sec is not None and etf and abs(chg - sec) <= max(2.0, 0.5 * abs(sec)) and chg * sec > 0:
        return "sector", f"跟板塊{'升' if chg > 0 else '跌'}（{etf} {sec:+.1f}%）"
    if mkt is not None:
        diff = chg - mkt
        return "stock", f"比大市{'強' if diff > 0 else '弱'} {abs(diff):.1f}%"
    return "stock", f"今日 {chg:+.1f}%"


def reason(ticker, chg, mkt_chg=None, fetch_news=True):
    """One plain line explaining today's move. Never invents a cause."""
    from . import marketdata
    etf = sector_etf(ticker)
    sec = None
    if etf and chg is not None:
        q = marketdata.quote(etf)
        sec = q.get("change_pct") if q.get("ok") else None
    if mkt_chg is None:
        q = marketdata.quote("QQQ")
        mkt_chg = q.get("change_pct") if q.get("ok") else None
    kind, move_txt = move_class(chg, mkt_chg, sec, etf)
    hl = best_headline(ticker, news(ticker)) if fetch_news else None
    h_txt = headline_text(hl)
    if kind == "unknown":
        text = move_txt + (f"｜新聞：{h_txt}" if h_txt else "")
    elif h_txt:
        text = (f"{move_txt}｜新聞：{h_txt}" if kind in ("market", "sector", "flat") else f"似係個股消息（{move_txt}）：{h_txt}")
    elif kind == "stock":
        text = f"冇搵到相關新聞，個股自己波動（{move_txt}）"
    elif kind == "flat":
        text = "窄幅上落，冇特別新聞"
    else:
        text = f"冇特別新聞，似係{move_txt}"
    return {"ticker": ticker, "text": text, "kind": kind, "chg_pct": chg, "mkt_chg_pct": mkt_chg, "sector_etf": etf,
            "sector_chg_pct": sec, "headline": hl.get("headline") if hl else None, "url": hl.get("url") if hl else None,
            "news_source": (hl.get("provider") + ":" + str(hl.get("source") or "")) if hl else None,
            "at": clock.now_hkt().isoformat(timespec="seconds")}


def market_headline():
    """One general market headline (Finnhub /news general, cached 6 h) or None."""
    c = _load()
    e = c.get("__general__")
    if e and time.time() - float(e.get("ts", 0)) < float(_cfg()["news_cache_hours"]) * 3600:
        items = e.get("items") or []
    elif network_off():
        items = (e or {}).get("items") or []
    else:
        from . import finnhub
        d, err = finnhub.get("news", {"category": "general"})
        if d is None or not isinstance(d, list):
            items = (e or {}).get("items") or []
        else:
            items = [{"headline": x.get("headline"), "source": x.get("source"), "url": x.get("url"), "ts": x.get("datetime")}
                     for x in d if x.get("headline")][:20]
            c["__general__"] = {"ts": time.time(), "items": items}
            _save(c)
    now = time.time()
    for x in items:
        if x.get("ts") and now - float(x["ts"]) > 24 * 3600:
            continue
        if GENERIC.search((x.get("headline") or "").lower()):
            continue
        return x
    return None


def save_site(reasons_by_ticker, extra=None):
    """data/reasons.json for the website cards (positions + picks)."""
    try:
        old = {}
        try:
            with open(SITE_PATH, encoding="utf-8") as f:
                old = json.load(f).get("reasons", {})
        except Exception:
            pass
        old.update({t: r for t, r in reasons_by_ticker.items() if r})
        data = {"generated_at": clock.now_hkt().isoformat(timespec="seconds"), "reasons": old}
        if extra:
            data.update(extra)
        os.makedirs(os.path.dirname(SITE_PATH), exist_ok=True)
        tmp = SITE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, SITE_PATH)
    except Exception as e:
        print("[reasons] site write failed:", type(e).__name__)
