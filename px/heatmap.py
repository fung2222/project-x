"""Stock heatmap data for the website (heatmap.html). NEVER sends Telegram; writes data/heatmap.json only.

Ported from the standalone prototype /workspace/px-heatmap/build_heatmap.py (Roy approved 2026-09-28).

What it writes (schema "heatmap_v1", small JSON; the page renders it client-side with plotly from a CDN):
  * stocks[]  every scan.universe name + Roy's real positions (◆, data/futu_positions.json) + paper holdings (★,
              portfolio.json): day % change, theme group (settings.themes, small themes merged -> THEME_ZH), box size =
              cube root of market cap in US$bn (floor US$1B), colour.
  * index     SPY / QQQ / ^VIX header;  sectors[]  the 12 sector ETFs with Chinese names.
  * data_date (ET session), phase ("intraday" = today's in-progress bar | "close" = completed session), generated HKT time.
Colours: RED = up, GREEN = down (HK convention); full colour at ±5 %; |chg| < 0.1 % = flat grey.
Missing / stale / insane data (last bar not on the reference session, or a jump > rules.max_price_sanity_jump_pct)
-> chg None -> grey "數據暫缺". Never guessed.

Data sources / API budget:
  * Prices: histories already downloaded in this process by the scan/close jobs (px.marketdata._hist_cache) are
    reused; the rest come from ONE batched yfinance download (period 5d). Yahoo cooldown respected (no run while
    px.marketdata.yahoo_blocked()); a rate limit hit here sets the shared cooldown like every other Yahoo caller.
  * Market caps (box size only): Finnhub /stock/profile2 through px.finnhub (counted in state/api_state.json,
    429 cooldown shared), cached 7 days in state/heatmap_mcap.json, at most heatmap.finnhub_mcap_per_run calls per
    run. No cap -> median-size box (listed in no_mcap). No Yahoo fallback (keeps Yahoo usage down).

Schedule (px.heatmap.slots; called from `run.py tick` AFTER the push jobs, like realwatch it is NOT a watchdog
slot, so a failure never alerts, never blocks another job and never pushes anything):
  NYSE trading days only (px.clock calendar, DST aware): every 30 min from 10:00 ET while the session is open
  (last slot 30 min before the close; half days end 12:30 ET) + one "close" run at 17:00 ET right after the close
  job in the same tick (reuses the close job's price downloads). Per slot: at most heatmap.max_attempts attempts
  (state/heatmap_state.json); Yahoo cooldown -> deferred, no attempt used."""
import datetime as dt
import json
import math
import os
import tempfile
import time

from . import clock
from .config import STATE_DIR, load_settings, network_off, path

SCHEMA = "heatmap_v1"
OUT_PATH = os.environ.get("PX_HEATMAP_PATH") or path("data", "heatmap.json")
STATE_NAME = "heatmap_state.json"
MCAP_NAME = "heatmap_mcap.json"

INDEX = [("SPY", "SPY 標普500"), ("QQQ", "QQQ 納指100"), ("^VIX", "VIX 恐慌指數")]
SECTOR_ETFS = [  # (ticker, 中文) — same 12 as the prototype
    ("XLK", "科技"), ("SMH", "半導體"), ("XLY", "非必需消費"), ("XLC", "通訊／媒體"),
    ("XLF", "金融"), ("XLV", "醫療"), ("XLI", "工業"), ("XLE", "能源"),
    ("XLB", "原材料"), ("XLU", "公用事業"), ("XLRE", "房地產"), ("XLP", "必需消費"),
]
# settings.themes -> Chinese group (small themes merged so every group has a readable header) — same as the prototype
THEME_ZH = {
    "AI_SOFTWARE": "AI 軟件", "DATA_AI": "AI 軟件", "AI_SPEECH": "AI 軟件",
    "QUANTUM": "量子電腦", "SPACE": "太空", "NUCLEAR": "核能／新能源", "CLEAN_ENERGY": "核能／新能源",
    "FINTECH": "金融科技", "CRYPTO": "加密貨幣", "BTC_MINING_HPC": "比特幣礦場／AI 算力",
    "AI_CLOUD_INFRA": "AI 雲端／伺服器", "EV": "電動車", "EVTOL": "飛行的士", "DRONES_DEFENSE": "無人機／機械人",
    "AI_CHIPS": "AI 晶片", "MEGA_SOFT": "科技巨頭", "MATERIALS_URANIUM": "稀土／鈾礦",
    "HEALTH_CONSUMER": "醫療／消費", "BIOTECH_AI": "醫療／消費", "INTERNET": "互聯網平台",
    "ROBOTICS": "無人機／機械人",
}
OTHER_GROUP = "其他"
MISSING_TEXT = "數據暫缺"

UP_LIGHT, UP_DEEP = "#f6c9c4", "#a3111b"   # red family = UP
DN_LIGHT, DN_DEEP = "#c6e8cc", "#0b6b2f"   # green family = DOWN
FLAT, MISSING = "#dfe2e6", "#b9bec5"

DEFAULTS = {"enabled": True, "first_et": "10:00", "every_min": 30, "last_before_close_min": 30,
            "final_et": "17:00", "final_until_et": "20:30", "slot_grace_min": 25, "max_attempts": 2,
            "mcap_cache_days": 7, "mcap_floor_usd": 1e9, "finnhub_mcap_per_run": 20,
            "full_colour_pct": 5.0, "flat_pct": 0.1}


def cfg():
    c = dict(DEFAULTS)
    c.update({k: v for k, v in (load_settings().get("heatmap") or {}).items() if not k.startswith("_")})
    return c


# ---------------------------------------------------------------- colours / sizes
def _mix(a, b, t):
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def colour(chg, full_pct=5.0, flat_pct=0.1):
    """(background, text colour). RED = up, GREEN = down; deepest at ±full_pct; None -> missing grey."""
    if chg is None:
        return MISSING, "#333333"
    if abs(chg) < flat_pct:
        return FLAT, "#222222"
    t = min(abs(chg) / full_pct, 1.0) ** 0.75
    c = _mix(UP_LIGHT, UP_DEEP, t) if chg > 0 else _mix(DN_LIGHT, DN_DEEP, t)
    return c, ("#ffffff" if t > 0.5 else "#1a1a1a")


def box_size(mcap, floor_usd=1e9):
    """Cube root of market cap in US$bn (floor US$1B): 1000x bigger company -> only 10x bigger box."""
    return (max(float(mcap or 0), float(floor_usd)) / 1e9) ** (1 / 3)


def group_of(t, themes):
    for th, members in (themes or {}).items():
        if t in members:
            return THEME_ZH.get(th, OTHER_GROUP)
    return OTHER_GROUP


def fmt_pct(chg):
    return MISSING_TEXT if chg is None else f"{chg:+.2f}%"


# ---------------------------------------------------------------- schedule (NYSE calendar, DST aware)
def _hm(s):
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def slots(day_et):
    """[(kind, aware ET datetime)] for an ET date: intraday every `every_min` from first_et while the session is open
    (last one `last_before_close_min` before the close; half days shorter) + one 'close' run at final_et."""
    if not clock.is_trading_day(day_et):
        return []
    c = cfg()
    close = dt.datetime.combine(day_et, clock.close_time(day_et), tzinfo=clock.ET)
    last = close - dt.timedelta(minutes=int(c["last_before_close_min"]))
    t = dt.datetime.combine(day_et, _hm(c["first_et"]), tzinfo=clock.ET)
    out = []
    while t <= last:
        out.append(("intraday", t))
        t += dt.timedelta(minutes=int(c["every_min"]))
    out.append(("close", dt.datetime.combine(day_et, _hm(c["final_et"]), tzinfo=clock.ET)))
    return out


def slot_deadline(kind, s):
    c = cfg()
    if kind == "close":
        return dt.datetime.combine(s.date(), _hm(c["final_until_et"]), tzinfo=clock.ET)
    return s + dt.timedelta(minutes=int(c["slot_grace_min"]))


def due_slot(now=None):
    """(kind, slot) whose window contains now (the latest one), else None. Old intraday slots are never caught up."""
    now_et = clock.to_et(now or clock.now_hkt())
    best = None
    for kind, s in slots(now_et.date()):
        if s <= now_et <= slot_deadline(kind, s):
            best = (kind, s)
    return best


def slot_key(s):
    return s.strftime("%Y-%m-%dT%H:%M") + " ET"


# ---------------------------------------------------------------- state
def _read(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_atomic(p, data):
    d = os.path.dirname(p) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".heatmap.", dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o644)  # mkstemp creates 0600; the site file must be world-readable
    os.replace(tmp, p)


def _state_path():
    return os.path.join(STATE_DIR, STATE_NAME)


def _record(key, status, detail=""):
    st = _read(_state_path(), {})
    sl = st.setdefault("slots", {})
    e = sl.setdefault(key, {"attempts": 0})
    if status == "running":
        e["attempts"] = e.get("attempts", 0) + 1
    if e.get("status") != "ok" or status == "ok":
        e["status"] = status
    e["at"] = clock.now_hkt().isoformat(timespec="seconds")
    e["detail"] = str(detail)[:200]
    st["slots"] = dict(sorted(sl.items())[-60:])  # keep ~4 trading days
    _write_atomic(_state_path(), st)


# ---------------------------------------------------------------- holdings / universe
def universe_and_flags():
    s = load_settings()
    universe = list((s.get("scan") or {}).get("universe") or [])
    paper, real = [], []
    try:
        from . import ledger
        paper = sorted({p["ticker"] for p in (ledger.load().get("positions") or []) if p.get("ticker") and (p.get("shares") or 0) > 0})
    except Exception as e:
        print(f"[heatmap] paper book unreadable: {type(e).__name__}")
    try:
        from . import realpos
        real = sorted({p["ticker"] for p in (realpos.load().get("positions") or []) if p.get("ticker")})
    except Exception as e:
        print(f"[heatmap] real book unreadable: {type(e).__name__}")
    for t in real + paper:  # holdings always shown even if they drop out of the scan list
        if t not in universe:
            universe.append(t)
    return universe, s.get("themes") or {}, paper, real


# ---------------------------------------------------------------- prices
def _to_series(closes):
    try:
        s = closes.dropna()
        s.index = [getattr(i, "date", lambda: i)() for i in s.index]
        return s if len(s) else None
    except Exception:
        return None


def _from_process_cache(sym):
    from . import marketdata
    df = marketdata._hist_cache.get(sym)
    if df is None or not len(df):
        return None
    return _to_series(df["Close"])


def _batch_download(symbols):
    """One batched yfinance download (period 5d). Returns ({sym: Series}, error or None)."""
    from . import apistate, marketdata
    if not symbols:
        return {}, None
    if network_off():
        return {}, "network off"
    if marketdata.yahoo_blocked():
        return {}, "yahoo cooldown"
    try:
        yf = marketdata._yf()
        df = yf.download(symbols, period="5d", interval="1d", auto_adjust=False, group_by="ticker",
                         threads=4, progress=False)
    except Exception as e:
        if marketdata._is_rate_limit(e):
            marketdata._mark_yahoo_limited("heatmap batch")
        return {}, f"{type(e).__name__}"
    try:
        apistate.count("yahoo_heatmap", len(symbols))
    except Exception:
        pass
    try:  # yfinance swallows per-ticker errors into shared._ERRORS; a rate limit there must still set the cooldown
        import yfinance.shared as ysh
        errs = " ".join(str(v) for v in (getattr(ysh, "_ERRORS", {}) or {}).values())
        if "RateLimit" in errs or "Too Many Requests" in errs or "Rate limited" in errs:
            marketdata._mark_yahoo_limited("heatmap batch")
    except Exception:
        pass
    out = {}
    if df is None or not len(df):
        return out, "empty download"
    import pandas as pd
    multi = isinstance(df.columns, pd.MultiIndex)
    for sym in symbols:
        try:
            s = _to_series(df[sym]["Close"] if multi else df["Close"])
        except Exception:
            s = None
        if s is not None:
            out[sym] = s
    return out, None


def load_series(symbols):
    """Reuse this process's scan/close downloads, batch-download only the rest."""
    series, need = {}, []
    for sym in symbols:
        s = _from_process_cache(sym)
        if s is not None:
            series[sym] = s
        else:
            need.append(sym)
    got, err = _batch_download(need)
    series.update(got)
    return series, {"reused": len(symbols) - len(need), "downloaded": len(need), "error": err}


def reference_session(series, now=None):
    """The ET session to show: most common latest bar date, never later than today ET."""
    today = clock.to_et(now or clock.now_hkt()).date()
    lasts = [s.index[-1] for s in series.values() if s is not None and len(s) >= 2 and s.index[-1] <= today]
    return max(set(lasts), key=lasts.count) if lasts else None


def day_change(s, ref, sanity_pct=50.0):
    """(last, chg %) for the reference session vs the previous bar; None when stale/missing/insane."""
    if s is None or ref is None or len(s) < 2 or s.index[-1] != ref:
        return None, None
    last, prev = float(s.iloc[-1]), float(s.iloc[-2])
    if not (prev > 0 and math.isfinite(last) and last > 0):
        return None, None
    chg = (last / prev - 1) * 100
    if abs(chg) > sanity_pct:
        return None, None
    return last, chg


# ---------------------------------------------------------------- market caps (Finnhub, cached 7 days)
def market_caps(tickers, now_ts=None):
    """{ticker: mcap_usd} from the 7-day cache, topping up at most finnhub_mcap_per_run names via Finnhub
    /stock/profile2 (counted in state/api_state.json). Returns (caps, missing, n_finnhub_calls)."""
    c = cfg()
    now_ts = now_ts or time.time()
    p = os.path.join(STATE_DIR, MCAP_NAME)
    cache = _read(p, {})
    ttl = float(c["mcap_cache_days"]) * 86400
    caps, need = {}, []
    for t in tickers:
        e = cache.get(t) or {}
        if e.get("mcap") and now_ts - float(e.get("ts", 0)) < ttl:
            caps[t] = float(e["mcap"])
        else:
            need.append(t)
    calls = 0
    if need and not network_off():
        from . import finnhub
        for t in need[: int(c["finnhub_mcap_per_run"])]:
            d, err = finnhub.get("stock/profile2", {"symbol": t})
            calls += 1
            if d is None:
                if err and ("429" in err or "cooldown" in err or "no FINNHUB" in err):
                    break
                continue
            mc = (d or {}).get("marketCapitalization")
            if isinstance(mc, (int, float)) and mc > 0:
                caps[t] = float(mc) * 1e6  # Finnhub reports US$ millions
                cache[t] = {"mcap": caps[t], "ts": now_ts, "src": "finnhub"}
        if calls:
            _write_atomic(p, cache)
    for t in tickers:  # an expired cache value is still better than nothing for box SIZE only (never for colour)
        if t not in caps and (cache.get(t) or {}).get("mcap"):
            caps[t] = float(cache[t]["mcap"])
    return caps, [t for t in tickers if t not in caps], calls


# ---------------------------------------------------------------- build
def build(now=None, series=None, caps=None, holdings=None, as_of=None):
    """Pure-ish builder (series/caps/holdings injectable for tests). Returns the heatmap_v1 dict.
    as_of = when the prices were fetched (defaults to now; only differs when re-rendering a saved download)."""
    c = cfg()
    now = now or clock.now_hkt()
    as_of = as_of or now
    s_all = load_settings()
    sanity = float((s_all.get("rules") or {}).get("max_price_sanity_jump_pct", 50.0))
    universe, themes, paper, real = holdings or universe_and_flags()
    idx_syms = [t for t, _ in INDEX]
    etf_syms = [t for t, _ in SECTOR_ETFS]
    symbols = list(dict.fromkeys(universe + idx_syms + etf_syms))
    meta = {"reused": 0, "downloaded": 0, "error": None}
    if series is None:
        series, meta = load_series(symbols)
    ref = reference_session({k: v for k, v in series.items() if k in universe or k in idx_syms}, as_of)
    n_calls = 0
    if caps is None:
        caps, no_cap, n_calls = market_caps(universe)
    else:
        no_cap = [t for t in universe if not caps.get(t)]
    full, flat = float(c["full_colour_pct"]), float(c["flat_pct"])
    floor = float(c["mcap_floor_usd"])
    med = sorted(caps[t] for t in universe if caps.get(t))
    med = med[len(med) // 2] if med else floor

    stocks = []
    for t in universe:
        last, chg = day_change(series.get(t), ref, sanity)
        bg, fg = colour(chg, full, flat)
        mc = caps.get(t)
        stocks.append({"t": t, "g": group_of(t, themes), "last": None if last is None else round(last, 4),
                       "chg_pct": None if chg is None else round(chg, 3), "mcap_usd": None if not mc else round(mc),
                       "size": round(box_size(mc if mc else med, floor), 4), "size_is_median": not mc,
                       "paper": t in paper, "real": t in real, "color": bg, "text_color": fg,
                       "label": fmt_pct(chg)})
    groups = {}
    for r in stocks:
        groups.setdefault(r["g"], []).append(r)
    group_rows = []
    for g, rs in groups.items():
        chgs = [r["chg_pct"] for r in rs if r["chg_pct"] is not None]
        group_rows.append({"g": g, "n": len(rs), "size": round(sum(r["size"] for r in rs), 4),
                           "avg_chg_pct": round(sum(chgs) / len(chgs), 3) if chgs else None})
    group_rows.sort(key=lambda x: -x["size"])

    index = {}
    for t, zh in INDEX:
        last, chg = day_change(series.get(t), ref, 1000.0 if t == "^VIX" else sanity)
        key = "VIX" if t == "^VIX" else t
        bg, fg = colour(chg, full, flat) if t != "^VIX" else ("#ffffff", "#1d2129")
        index[key] = {"name": zh, "last": None if last is None else round(last, 4),
                      "chg_pct": None if chg is None else round(chg, 3), "color": bg, "text_color": fg,
                      "label": fmt_pct(chg)}
    sectors = []
    for t, zh in SECTOR_ETFS:
        last, chg = day_change(series.get(t), ref, sanity)
        bg, fg = colour(chg, full, flat)
        sectors.append({"t": t, "zh": zh, "last": None if last is None else round(last, 4),
                        "chg_pct": None if chg is None else round(chg, 3), "color": bg, "text_color": fg,
                        "label": fmt_pct(chg)})

    missing = [r["t"] for r in stocks if r["chg_pct"] is None]
    up = sum(1 for r in stocks if r["chg_pct"] is not None and r["chg_pct"] >= flat)
    down = sum(1 for r in stocks if r["chg_pct"] is not None and r["chg_pct"] <= -flat)
    now_et = clock.to_et(as_of)
    live = ref is not None and ref == now_et.date() and clock.market_is_open(as_of)
    phase = "intraday" if live else "close"
    wk = "一二三四五六日"[ref.weekday()] if ref else ""
    if ref is None:
        date_label = MISSING_TEXT
    elif live:
        date_label = f"美股 {ref.isoformat()}（星期{wk}）盤中，截至 {now_et:%H:%M} 美東（{clock.to_hkt(as_of):%H:%M} 香港時間）"
    else:
        date_label = f"美股 {ref.isoformat()}（星期{wk}）收市"
    return {
        "schema": SCHEMA,
        "generated_at": clock.to_hkt(now).isoformat(timespec="seconds"),
        "generated_hkt": clock.to_hkt(now).strftime("%Y-%m-%d %H:%M") + " HKT",
        "prices_as_of": clock.to_hkt(as_of).isoformat(timespec="seconds"),
        "data_date": ref.isoformat() if ref else None,
        "phase": phase,
        "date_label": date_label,
        "colour": {"up": "red", "down": "green", "full_at_pct": full, "flat_pct": flat,
                   "legend": "紅＝升　綠＝跌　格越大＝公司越大",
                   "scale": [{"pct": v, "color": colour(v if v else None, full, flat)[0] if v else FLAT} for v in (-5, -3, -1, 0, 1, 3, 5)]},
        "size_rule": "cube_root_mcap_usd_bn_floor_1bn",
        "index": index,
        "sectors": sectors,
        "groups": group_rows,
        "stocks": stocks,
        "counts": {"total": len(stocks), "up": up, "down": down, "flat": len(stocks) - len(missing) - up - down,
                   "missing": len(missing)},
        "missing": missing,
        "no_mcap": no_cap,
        "paper": paper,
        "real": real,
        "sources": {"prices": "Yahoo Finance 日線（yfinance）", "mcap": "Finnhub /stock/profile2（7 日 cache，只用嚟定格大細）",
                    "prices_reused": meta.get("reused", 0), "prices_downloaded": meta.get("downloaded", 0),
                    "finnhub_mcap_calls": n_calls},
    }


def close_link(session_date, site_url=None, p=None):
    """'🗺 今日板塊熱力圖：<url>heatmap.html' for the close push, only when data/heatmap.json is for that session."""
    try:
        with open(p or OUT_PATH, encoding="utf-8") as f:
            hm = json.load(f)
    except Exception:
        return None
    if hm.get("schema") != SCHEMA or not session_date or hm.get("data_date") != str(session_date):
        return None
    site = (site_url or "https://fung2222.github.io/project-x/").rstrip("/") + "/"
    return f'🗺 今日板塊熱力圖：<a href="{site}heatmap.html">{site}heatmap.html</a>'


# ---------------------------------------------------------------- run (called from run.py tick / run.py heatmap)
def run(now=None, dry_run=False, force=False, out=None):
    """Build + write data/heatmap.json for the due slot. NEVER sends Telegram. Never raises for data problems.
    dry_run: no state/ledger writes; the JSON is written only to an explicit `out` path."""
    from . import marketdata
    c = cfg()
    now = now or clock.now_hkt()
    if not c.get("enabled", True) or os.environ.get("PX_HEATMAP_DISABLED") == "1":
        return {"status": "disabled"}
    due = due_slot(now)
    if not force:
        if due is None:
            return {"status": "skipped", "reason": "no heatmap slot now"}
        e = (_read(_state_path(), {}).get("slots") or {}).get(slot_key(due[1])) or {}
        if e.get("status") == "ok":
            return {"status": "duplicate", "slot": slot_key(due[1])}
        if e.get("attempts", 0) >= int(c["max_attempts"]):
            return {"status": "gave_up", "slot": slot_key(due[1])}
        if marketdata.yahoo_blocked():
            return {"status": "deferred", "reason": "Yahoo cooldown", "slot": slot_key(due[1])}
    key = slot_key(due[1]) if due else "manual"
    if not dry_run:
        _record(key, "running", "started")
    try:
        data = build(now)
    except Exception as e:
        if not dry_run:
            _record(key, "failed", f"{type(e).__name__}: {e}")
        return {"status": "failed", "reason": f"{type(e).__name__}", "slot": key}
    if data["counts"]["total"] and data["counts"]["missing"] == data["counts"]["total"]:
        # nothing usable: keep the last good file (it carries its own date) instead of an all-grey page
        if not dry_run:
            _record(key, "no_data", "all prices missing")
        return {"status": "no_data", "slot": key}
    target = out or (None if dry_run else OUT_PATH)
    if target:
        _write_atomic(target, data)
    if not dry_run:
        _record(key, "ok", f"{data['counts']['up']} up / {data['counts']['down']} down")
    return {"status": "ok", "slot": key, "path": target, "data_date": data["data_date"], "phase": data["phase"],
            "counts": data["counts"], "sources": data["sources"]}
