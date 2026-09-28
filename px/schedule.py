"""Master schedule, run ledger and watchdog (missed-run detector).

- expected_slots(job, day): the scheduled run times for a job on a local date
  (ET jobs: NYSE trading days only, hourly slots trimmed on early-close days;
   morning: HKT 08:30 after a completed US session; weekly: every HKT Monday).
- run_job(job, fn, ...): run a job and record the result in state/run_ledger.json
  against the matching slot (or "manual").
- check(now): watchdog. For every expected slot whose grace period has passed:
  ok/duplicate/skipped(holiday)  -> fine
  (the first live pass only "arms" the watchdog: ledger _meta.watch_since = now;
   slots before watch_since are ignored, so a runner switch never floods alerts)
  missing/failed/telegram_failed -> re-run once or twice while inside the slot's
                                    rerun window (duplicate-send guard still applies)
                                 -> otherwise ONE short Telegram alert per slot.
- health_line(session): one-line summary of tonight's runs (used in the close report).
"""
import datetime as dt
import json
import os
import tempfile

from . import clock
from .config import STATE_DIR, load_settings

LEDGER = os.path.join(STATE_DIR, "run_ledger.json")
OK_STATES = ("ok", "duplicate")
MAX_ATTEMPTS = 3  # original + 2 watchdog re-runs


def _tz(job_cfg):
    return clock.ET if job_cfg["tz"] == "ET" else clock.HKT


def _hm(s):
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def jobs():
    return {k: v for k, v in load_settings()["schedule"].items() if not k.startswith("_")}


def day_applies(job, day):
    c = jobs()[job]
    rule = c["days"]
    if rule == "trading":
        return clock.is_trading_day(day)
    if rule == "after_trading":  # HKT morning after a US session: ET date = HKT date - 1
        return clock.is_trading_day(day - dt.timedelta(days=1))
    if rule == "monday":
        return day.weekday() == 0
    raise ValueError(rule)


def expected_slots(job, day):
    """Aware datetimes (job tz) of scheduled runs on local date `day`."""
    c = jobs()[job]
    if not day_applies(job, day):
        return []
    tz = _tz(c)
    out = []
    for t in c["times"]:
        slot = dt.datetime.combine(day, _hm(t), tzinfo=tz)
        if job == "hourly" and clock.is_early_close(day):
            if slot.time() > dt.time(13, 45):
                continue
        out.append(slot)
    return out


def slot_for(job, now=None, tolerance_min=10):
    """The expected slot this run belongs to: latest slot <= now + tolerance, within its rerun window."""
    now = now or clock.now_hkt()
    c = jobs()[job]
    local = now.astimezone(_tz(c))
    best = None
    for day in (local.date(), local.date() - dt.timedelta(days=1)):
        for s in expected_slots(job, day):
            if s <= local + dt.timedelta(minutes=tolerance_min) and local <= rerun_deadline(job, s):
                if best is None or s > best:
                    best = s
    return best


def rerun_deadline(job, slot):
    c = jobs()[job]
    if "rerun_minutes" in c:
        return slot + dt.timedelta(minutes=c["rerun_minutes"])
    return dt.datetime.combine(slot.date(), _hm(c["rerun_until"]), tzinfo=slot.tzinfo)


def key(job, slot):
    return f"{job}|{slot.astimezone(clock.HKT).isoformat(timespec='minutes')}" if slot else f"{job}|manual"


# ---------------------------------------------------------------- ledger io
def _load():
    try:
        with open(LEDGER, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    cutoff = (clock.now_hkt() - dt.timedelta(days=45)).isoformat()
    d = {k: v for k, v in d.items() if v.get("last_at", "9") >= cutoff}
    fd, tmp = tempfile.mkstemp(prefix=".run_ledger.", dir=STATE_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(d.items())), f, ensure_ascii=False, indent=1)
    os.replace(tmp, LEDGER)


def record(job, slot, status, detail="", now=None, via="cron"):
    now = now or clock.now_hkt()
    d = _load()
    k = key(job, slot)
    e = d.get(k, {"job": job, "slot_hkt": slot.astimezone(clock.HKT).isoformat(timespec="minutes") if slot else None,
                  "slot_local": slot.strftime("%Y-%m-%d %H:%M ") + ("ET" if slot and slot.tzinfo == clock.ET else "HKT") if slot else None,
                  "attempts": 0, "history": []})
    e["attempts"] = e.get("attempts", 0) + 1
    # Sticky success: once a slot is "ok" (messages sent), a later duplicate/skip/failed
    # run of the same slot (e.g. the DST-superset HKT cron line) must not downgrade it.
    if e.get("status") != "ok" or status == "ok":
        e["status"] = status
    e["last_at"] = now.isoformat(timespec="seconds")
    e["detail"] = str(detail)[:300]
    e["history"] = (e.get("history", []) + [{"at": e["last_at"], "status": status, "via": via}])[-6:]
    d[k] = e
    _save(d)
    return e


def get(job, slot):
    return _load().get(key(job, slot))


def mark_alerted(job, slot):
    d = _load()
    k = key(job, slot)
    d.setdefault(k, {"job": job, "attempts": 0, "status": "missing", "last_at": clock.now_hkt().isoformat(timespec="seconds")})
    d[k]["alerted"] = clock.now_hkt().isoformat(timespec="seconds")
    _save(d)


# ---------------------------------------------------------------- run wrapper
def run_job(job, fn, now=None, via="cron", **kw):
    """Run fn(**kw) and record the outcome against the job's slot. Returns fn's result dict."""
    now_ = now or clock.now_hkt()
    slot = slot_for(job, now_)
    dry = kw.get("dry_run", False)
    try:
        res = fn(now=now, **kw) if now is not None else fn(**kw)
    except Exception as e:
        if not dry:
            record(job, slot, "failed", f"{type(e).__name__}: {e}", via=via)
        raise
    status = (res or {}).get("status", "ok")
    if not dry:
        record(job, slot, status, (res or {}).get("reason", ""), via=via)
    return res


# ---------------------------------------------------------------- watchdog
def due_slots(now=None, lookback_hours=30):
    """All expected slots whose grace has passed within the lookback window."""
    now = now or clock.now_hkt()
    out = []
    for job, c in jobs().items():
        tz = _tz(c)
        local = now.astimezone(tz)
        for back in range(0, 3):
            day = local.date() - dt.timedelta(days=back)
            for s in expected_slots(job, day):
                if s + dt.timedelta(minutes=c["grace_min"]) <= local and local - s <= dt.timedelta(hours=lookback_hours):
                    out.append((job, s))
    return sorted(out, key=lambda x: x[1])


def check(now=None, runner=None, alert=None, dry_run=False):
    """Watchdog pass. runner(job, slot) -> status str; alert(text) -> bool. Returns list of actions."""
    now = now or clock.now_hkt()
    actions = []
    # Arming: the watchdog only looks at slots after `watch_since` (set on the first live pass),
    # so switching runners (cutover) never produces a burst of "missed" alerts for old slots.
    led = _load()
    ws = (led.get("_meta") or {}).get("watch_since")
    if not ws:
        if not dry_run:
            led.setdefault("_meta", {})["watch_since"] = now.isoformat(timespec="minutes")
            _save(led)
        return [{"action": "armed", "watch_since": now.isoformat(timespec="minutes")}]
    ws_dt = dt.datetime.fromisoformat(ws)
    for job, slot in due_slots(now):
        if slot < ws_dt:
            continue
        e = get(job, slot) or {}
        st = e.get("status", "missing")
        if st in OK_STATES or st == "skipped":
            continue
        local = now.astimezone(slot.tzinfo)
        can_rerun = local <= rerun_deadline(job, slot) and e.get("attempts", 0) < MAX_ATTEMPTS
        if can_rerun and runner is not None:
            actions.append({"job": job, "slot": key(job, slot), "action": "rerun", "prev": st})
            if not dry_run:
                new = runner(job, slot)
                actions[-1]["result"] = new
                if new in OK_STATES or new == "skipped":
                    continue
                e = get(job, slot) or {}
                if local <= rerun_deadline(job, slot) and e.get("attempts", 0) < MAX_ATTEMPTS:
                    continue  # next watchdog pass will retry
            else:
                continue
        if e.get("alerted"):
            continue
        slot_txt = slot.strftime("%m-%d %H:%M ") + ("ET" if slot.tzinfo == clock.ET else "HKT")
        hkt_txt = slot.astimezone(clock.HKT).strftime("%H:%M HKT")
        text = (f"🛠 Project X 漏跑/失敗：{job} {slot_txt}（{hkt_txt}）狀態 {e.get('status', 'missing')}，"
                f"已試 {e.get('attempts', 0)} 次。請 Hermes 睇 log：python run.py {job} --force（小心重覆推送）")
        actions.append({"job": job, "slot": key(job, slot), "action": "alert", "prev": st, "text": text})
        if not dry_run and alert is not None and alert(text):
            mark_alerted(job, slot)
    return actions


def health_line(session_et, now=None, exclude=()):
    """One line: status of every expected ET slot of a US session + the next morning/weekly slot."""
    parts, bad = [], 0
    for job in ("open", "daily", "hourly", "close"):
        if job in exclude:
            continue
        slots = expected_slots(job, session_et)
        if not slots:
            continue
        oks = sum(1 for s in slots if (get(job, s) or {}).get("status") in OK_STATES)
        if (now or clock.now_hkt()) < slots[-1].astimezone(clock.HKT):
            slots_due = [s for s in slots if s.astimezone(clock.HKT) <= (now or clock.now_hkt())]
        else:
            slots_due = slots
        due = len(slots_due)
        mark = "✅" if oks >= due else "⚠️"
        if oks < due:
            bad += 1
        parts.append(f"{job} {oks}/{due}{mark}" if len(slots) > 1 else f"{job}{mark}")
    if not parts:
        return "🩺 系統健康：今日冇美股排程"
    head = "🩺 系統健康" + ("：全部準時" if bad == 0 else f"：{bad} 項有問題")
    return head + "｜" + " · ".join(parts)
