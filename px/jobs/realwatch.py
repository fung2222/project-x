"""realwatch — 5-minute watch on Roy's REAL (Futu) positions (agreed with Roy 2026-09-28).

Runs from `run.py tick` BEFORE schedule.tick (not a schedule slot, not watched by the watchdog, never commits):
  * only while the US regular session is open and >= interval_min since the last run (state/realwatch.json);
  * zero API calls when there are no real positions;
  * Finnhub /quote first (rejects quotes older than max_quote_age_min and moves beyond the sanity limit);
    yfinance only if Finnhub fails for that ticker;
  * conditions (config real_account.intraday_watch): price <= SL · price >= TP · within near_sl_pct above SL ·
    day drop >= 5% vs previous close (re-alert at 10/15/20%) · day surge >= 8% (re-alert at 15/25%);
  * each condition once per ticker per US session (shared store with hourly: guard.real_alerted); SL/TP keys carry
    the level so changing SL/TP re-arms them; alerts are marked only AFTER Telegram accepted the message;
  * at most ONE Telegram message per run (all new alerts of the run combined), each alert with a one-line reason.
Disable: config/settings.json real_account.intraday_watch.enabled = false (or env PX_REALWATCH_DISABLED=1)."""
import datetime as dt
import json
import os
import tempfile

from .. import clock, guard, realpos, telegram
from ..config import STATE_DIR, load_settings, is_dry_run

JOB = "realwatch"


def _path():
    return os.path.join(STATE_DIR, "realwatch.json")


def load_state():
    try:
        with open(_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".realwatch.", dir=STATE_DIR)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _path())
    except Exception as e:
        print("[realwatch] state write failed:", type(e).__name__)


def cfg():
    w = {"enabled": True, "interval_min": 5, "max_quote_age_min": 15}
    w.update(load_settings().get("real_account", {}).get("intraday_watch", {}) or {})
    return w


def fetch_quote(ticker, max_age_s, jump_pct, now=None):
    """{ok, price, prev_close, change_pct, source} — Finnhub first; yfinance only if Finnhub fails. Never a fake price."""
    from .. import finnhub
    q, err = finnhub.quote(ticker, max_age_s=max_age_s)
    if q:
        chg = q.get("change_pct")
        if q["price"] > 0 and (chg is None or abs(chg) <= jump_pct):
            return {"ok": True, "price": q["price"], "prev_close": q.get("prev_close"), "change_pct": chg,
                    "source": "finnhub"}
        err = f"sanity check failed ({chg:+.0f}% vs prev close)" if chg is not None else "bad price"
    print(f"[realwatch] {ticker}: Finnhub unusable ({err}) -> yfinance fallback")
    try:
        from .. import marketdata
        y = marketdata.quote(ticker, now=now)
        today = (clock.to_et(now) if now else clock.now_et()).date().isoformat()
        if y.get("ok") and y.get("session_date") == today:  # today's bar only (never yesterday's close as "live")
            return {"ok": True, "price": y["price"], "prev_close": y.get("prev_close"), "change_pct": y.get("change_pct"),
                    "source": "yfinance"}
        print(f"[realwatch] {ticker}: yfinance fallback unusable ({y.get('source')})")
    except Exception as e:
        print(f"[realwatch] {ticker}: yfinance fallback failed: {type(e).__name__}")
    return {"ok": False, "price": None, "source": f"none ({err})"}


def build_message(now, alerts):
    from ..messages import esc, REAL_NOTE
    from ..plain import link_line
    L = [f"<b>🚨 真倉即時警報</b> {now.strftime('%m-%d %H:%M')} HKT（每 5 分鐘監察）"]
    L += [f"• {esc(a)}" for a in alerts]
    L += [REAL_NOTE, link_line()]
    return "\n".join(L)


def run(now=None, dry_run=None, force=False):
    """Returns a small status dict. Never raises into the caller's tick (run.py wraps it anyway)."""
    now = now or clock.now_hkt()
    dry_run = is_dry_run() if dry_run is None else dry_run
    w = cfg()
    if not w.get("enabled", True) or os.environ.get("PX_REALWATCH_DISABLED") == "1":
        return {"status": "disabled"}
    if not force and not clock.market_is_open(now):
        return {"status": "skipped", "reason": "market closed"}
    st = load_state()
    last = st.get("last_run")
    if last and not force:
        try:
            if now - dt.datetime.fromisoformat(last) < dt.timedelta(minutes=float(w["interval_min"])) - dt.timedelta(seconds=20):
                return {"status": "skipped", "reason": "interval"}
        except Exception:
            pass
    book = realpos.load()
    positions = book.get("positions", [])
    st["last_run"] = now.isoformat(timespec="seconds")
    if not positions:  # zero API calls
        st["last_result"] = "no_positions"
        save_state(st)
        return {"status": "no_positions"}
    save_state(st)  # record the attempt before any network call (a crash never causes a request storm)
    jump = float(load_settings()["rules"]["max_price_sanity_jump_pct"])
    quotes = {p["ticker"]: fetch_quote(p["ticker"], float(w["max_quote_age_min"]) * 60, jump, now) for p in positions}
    from .. import marketdata
    fx = marketdata.fx_info()["rate"] if any(q.get("ok") for q in quotes.values()) else None
    ev = realpos.evaluate(book, quotes, fx)
    session = clock.session_date(now).isoformat()
    alerted = guard.real_alerted(session)
    from ..messages import real_alerts
    al, new = real_alerts(ev, alerted)
    out = {"status": "ok", "session": session, "quotes": {t: {k: q.get(k) for k in ("ok", "price", "change_pct", "source")}
                                                          for t, q in quotes.items()}, "alerts": al, "sent": False}
    if al:
        rsn = {}
        from .. import reasons as rs
        hit = {r["ticker"] for r in ev["rows"] if any(f" {r['ticker']} " in a for a in al)}
        for r in ev["rows"]:
            if r["ticker"] in hit:
                try:
                    rsn[r["ticker"]] = rs.reason(r["ticker"], r.get("chg_vs_prev"))
                except Exception as e:
                    print(f"[realwatch] reason {r['ticker']} skipped:", type(e).__name__)
        al, new = real_alerts(ev, alerted, reasons=rsn)
        msg = build_message(now, al)
        ok, res = telegram.send(msg, dry_run=dry_run, label="realwatch")
        out.update({"alerts": al, "message": msg, "sent": bool(ok), "send_result": str(res)[:200]})
        if ok and not dry_run:
            guard.save_real_alerted(session, {k: v for k, v in new.items() if k.startswith("REAL:")}, by=JOB)
        elif not ok:
            out["status"] = "telegram_failed"  # not marked -> retried on the next 5-minute run
    st["last_result"] = out["status"] + (f" · {len(al)} alert(s)" if al else " · quiet")
    save_state(st)
    print("[realwatch]", json.dumps({k: out[k] for k in ("status", "quotes", "sent")}, ensure_ascii=False))
    return out
