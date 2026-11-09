"""Large-cap pullback research scan with explicit data and delivery states.

Successful zero-hit runs are ``ok`` and stay silent on Telegram. Any missing,
stale or insufficient ticker history makes the run ``failed`` so the master
watchdog retries it; an incomplete hit list is never presented as complete.
"""
import datetime as dt
import json
import os
import tempfile

from .. import clock, guard, telegram
from ..config import BASE_DIR, load_settings

JOB = "pullback"
OUTPUT = os.path.join(BASE_DIR, "data", "pullback.json")


def _history(ticker, period):
    import yfinance as yf
    return yf.Ticker(ticker).history(period=period)


def _bar_date(index_value):
    # pandas.Timestamp and datetime both support date(); keep this helper small
    # so synthetic offline tests use exactly the same path as production data.
    return index_value.date().isoformat()


def expected_bar_date(now=None):
    """Latest completed regular-session daily bar for the current ET time."""
    et = clock.to_et(now or clock.now_hkt())
    day = et.date()
    if clock.is_trading_day(day) and clock.session_closed(et):
        return day.isoformat()
    return clock.previous_trading_day(day).isoformat()


def scan(now=None, fetcher=None, cfg=None):
    """Return a structured result; never hide per-ticker data failures."""
    cfg = cfg or load_settings()[JOB]
    fetcher = fetcher or _history
    now = now or clock.now_hkt()
    expected_bar = expected_bar_date(now)
    hits, failures, bar_dates = [], [], set()
    for ticker in cfg["universe"]:
        try:
            hist = fetcher(ticker, cfg["history_period"])
            if hist is None or hist.empty or "Close" not in hist or "High" not in hist:
                raise ValueError("no price history")
            hist = hist.dropna(subset=["Close", "High"])
            if len(hist) < cfg["min_bars"]:
                raise ValueError(f"only {len(hist)} complete bars; need {cfg['min_bars']}")
            bar_date = _bar_date(hist.index[-1])
            # A forced intraday run must not treat today's forming bar as close data.
            et_today = clock.to_et(now).date().isoformat()
            if bar_date == et_today and not clock.session_closed(now):
                hist = hist.iloc[:-1]
                if len(hist) < cfg["min_bars"]:
                    raise ValueError("insufficient completed bars")
                bar_date = _bar_date(hist.index[-1])
            if bar_date != expected_bar:
                raise ValueError(f"stale bar {bar_date}; expected {expected_bar}")
            close = hist["Close"]
            last = float(close.iloc[-1])
            high52 = float(hist["High"].max())
            ma50_series = close.rolling(50).mean()
            ma50 = float(ma50_series.iloc[-1])
            lookback = int(cfg["ma50_slope_lookback"])
            ma50_prev = float(ma50_series.iloc[-1 - lookback])
            ret_3m = last / float(close.iloc[-63]) - 1
            drop = last / high52 - 1
            ratio = last / ma50
            ma50_up = ma50 > ma50_prev
            lo_drop, hi_drop = cfg["drop_range"]
            lo_ma, hi_ma = cfg["ma50_ratio_range"]
            if (ret_3m > cfg["min_3m_return"] and lo_drop <= drop <= hi_drop
                    and ma50_up and lo_ma <= ratio <= hi_ma):
                hits.append({
                    "ticker": ticker, "close": last, "return_3m_pct": ret_3m * 100,
                    "from_52w_high_pct": drop * 100, "price_ma50_ratio": ratio,
                    "ma50": ma50, "bar_date": bar_date,
                })
            bar_dates.add(bar_date)
        except Exception as exc:
            failures.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"[:180]})
    return {
        "hits": hits, "failures": failures, "scanned": len(cfg["universe"]) - len(failures),
        "universe_size": len(cfg["universe"]), "bar_date": expected_bar,
        "bar_dates": sorted(bar_dates),
    }


def _previous():
    try:
        with open(OUTPUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write(payload):
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pullback.", dir=os.path.dirname(OUTPUT))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, OUTPUT)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def message(result):
    lines = [f"<b>🎯 Project X 回調研究名單</b>（{result['bar_date']} 收市數據）",
             "四個條件同時符合：3 個月上升、離 52 週高位 8–18%、MA50 向上、收市價／MA50 為 1.00–1.05。", ""]
    for x in result["hits"]:
        lines.append(f"• <b>{x['ticker']}</b> ${x['close']:.2f}｜3 月 {x['return_3m_pct']:+.1f}%｜"
                     f"離高 {x['from_52w_high_pct']:.1f}%｜價/MA50 {x['price_ma50_ratio']:.2f}")
    lines += ["", f"完整掃描 {result['scanned']}/{result['universe_size']} 隻。只係研究名單，唔係買入訊號；請另設止蝕、注碼同費用預算。"]
    return "\n".join(lines)


def run(dry_run=False, force=False, now=None, fetcher=None):
    now = now or clock.now_hkt()
    et = clock.to_et(now)
    if not force:
        if not clock.is_trading_day(et.date()):
            return {"status": "skipped", "reason": f"no US session on {et.date()} ET"}
        window = load_settings()["schedule_et"][JOB]["window"]
        if not clock.in_window(window, now) and os.environ.get("PX_RERUN") != "1":
            return {"status": "skipped", "reason": f"outside pullback window {window} ET"}
        if guard.was_sent(et.date().isoformat(), JOB, "main"):
            return {"status": "duplicate", "reason": "pullback hits already sent for this session"}
    started = now.isoformat(timespec="seconds")
    result = scan(now=now, fetcher=fetcher)
    finished = now.isoformat(timespec="seconds")
    complete = not result["failures"]
    previous = _previous()
    payload = {
        "schema": "pullback_scan_v2", "status": "ok" if complete else "failed",
        "started_at": started, "generated_at": finished,
        "last_success_at": finished if complete else previous.get("last_success_at"),
        "strategy": "large_cap_pullback_research", "research_only": True,
        "criteria": {k: load_settings()[JOB][k] for k in
                     ("min_3m_return", "drop_range", "ma50_ratio_range", "ma50_slope_lookback")},
        **result,
        "hit_count": len(result["hits"]),
        "failure_count": len(result["failures"]),
        "message": "完整掃描完成" if complete else "數據不完整；今次結果不視為完整名單，watchdog 會重試",
    }
    if not dry_run:
        _write(payload)
    if not complete:
        return {"status": "failed", "reason": f"{len(result['failures'])} ticker data failures", "result": payload}
    if not result["hits"]:
        return {"status": "ok", "reason": "complete scan; zero hits (Telegram silent)", "result": payload}
    ok, response = telegram.send(message(payload), dry_run=dry_run, label=JOB)
    if ok and not dry_run:
        guard.mark_sent(et.date().isoformat(), JOB, "main", response)
    return {"status": "ok" if ok else "telegram_failed", "result": payload,
            "reason": "hits delivered" if ok else "Telegram delivery failed"}
