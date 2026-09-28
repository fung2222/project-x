#!/usr/bin/env python3
"""Project X CLI — the ONLY entry point the scheduler (Hermes / optional GitHub Actions) needs.

    python run.py open    [--dry-run] [--force] [--push]   # ET 09:35  (HKT 21:35 EDT / 22:35 EST)
    python run.py daily   [--dry-run] [--force] [--push]   # ET 09:53  (HKT 21:53 EDT / 22:53 EST), push ~10:00 ET
    python run.py hourly  [--dry-run] [--force] [--push]   # ET :06 past 10..16 (alert-only + 1 status/session)
    python run.py close   [--dry-run] [--force] [--push]   # ET 17:00  (HKT 05:00 EDT / 06:00 EST)
    python run.py morning [--dry-run] [--force] [--push]   # HKT 08:30 Tue-Sat after a US session
    python run.py weekly  [--dry-run] [--force] [--push]   # HKT Monday 09:44
    python run.py tick    [--dry-run] [--push]             # RECOMMENDED cron entry, every minute, any host TZ:
                                                            #   runs every due slot once, then the watchdog pass
    python run.py check   [--dry-run] [--push]             # watchdog only: re-run missed/failed slots, else 1 alert
    python run.py scan                                      # print today's opportunity Top 5 (no Telegram)
    python run.py status                                    # config/secrets presence, schedule, run ledger
    python run.py tgcheck                                   # getMe + getChat (bot username, chat type/title; no send)
    python run.py tgtest --yes                              # cutover test: 1 text + 1 chart image to TELEGRAM_CHAT_ID
    python run.py pos add SYMBOL QTY PRICE --sl X --tp Y [--date YYYY-MM-DD] [--fee 2] [--note ..]  # record Roy's REAL buy
    python run.py pos close SYMBOL PRICE [QTY] [--date YYYY-MM-DD] [--fee 2]                         # record a REAL sell
    python run.py pos set SYMBOL [--sl X] [--tp Y]  |  python run.py pos list [--live]                # edit levels / show
                                                            #   (data/futu_positions.json; the system NEVER places orders)

--dry-run : no Telegram, no file/ledger writes, no git (prints messages instead)
--force   : ignore holiday/time-window checks and the duplicate-send guard
--push    : after a successful live run, git commit + push the generated data files
Exit code 0 = ok / skipped quietly (holiday, outside window, already sent); 1 = error; 2 = Telegram failed.
"""
import argparse
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from px import clock, config, guard, schedule, telegram  # noqa: E402

JOBS = ("open", "daily", "hourly", "close", "morning", "weekly", "heatmap")


def _job_fn(job):
    from px.jobs import open_monitor, daily, hourly, weekly, close, morning
    from px import heatmap
    return {"open": open_monitor.run, "daily": daily.run, "hourly": hourly.run, "weekly": weekly.run,
            "close": close.run, "morning": morning.run, "heatmap": heatmap.run}[job]


def _alert(text):
    ok, _ = telegram.send(text, label="watchdog")
    return ok


def _rerun(job, slot):
    os.environ["PX_RERUN"] = "1"
    try:
        res = schedule.run_job(job, _job_fn(job), via="watchdog", dry_run=False, force=False)
        return (res or {}).get("status", "ok")
    except Exception as e:
        print(f"[check] rerun {job} failed: {type(e).__name__}: {telegram._redact(str(e))[:200]}")
        return "failed"
    finally:
        os.environ.pop("PX_RERUN", None)


def _error_alert(job, e):
    """One immediate 🛠 alert per job per US session when a job raises (both manual and tick runs)."""
    err = telegram._redact(f"{type(e).__name__}: {e}")[:300]
    sess = clock.session_date().isoformat()
    try:
        if not guard.was_sent(sess, job, "error"):
            ok, ids = telegram.send(f"<b>🛠 Project X 系統警告</b> {job} 失敗（{sess} ET）：{err}\n"
                                    f"watchdog 會喺窗口內自動重試；請 Hermes 睇 logs/ 同 HERMES_HANDOVER §10。", label="error")
            if ok:
                guard.mark_sent(sess, job, "error", ids)
        guard.update(sess, job, status="failed", error=err, _inc_runs=True)
    except Exception as e2:
        print("[run.py] error alert failed:", type(e2).__name__)


def _tick_run(job, slot):
    try:
        res = schedule.run_job(job, _job_fn(job), via="tick", dry_run=False, force=False)
        return (res or {}).get("status", "ok")
    except Exception as e:
        traceback.print_exc()
        print(f"[tick] {job} failed: {type(e).__name__}: {telegram._redact(str(e))[:200]}")
        _error_alert(job, e)
        try:
            if not schedule.get(job, slot):  # run_job records failures itself; only cover pre-run errors
                schedule.record(job, slot, "failed", f"{type(e).__name__}", via="tick")
        except Exception:
            pass
        return "failed"


REPORT_JOBS = ("open", "daily", "close", "morning", "weekly")  # multi-source reports: wait out a Yahoo rate limit


def _realwatch(dry_run):
    """5-minute real-position watch (px/jobs/realwatch.py). Never affects the schedule tick."""
    try:
        from px.jobs import realwatch
        return realwatch.run(dry_run=dry_run)
    except Exception as e:
        print(f"[realwatch] failed (tick continues): {type(e).__name__}: {telegram._redact(str(e))[:200]}")
        return {"status": "failed"}


def _heatmap(dry_run):
    """Stock heatmap refresh (px/heatmap.py -> data/heatmap.json). Never sends Telegram; a failure never blocks other jobs."""
    try:
        from px import heatmap
        res = heatmap.run(dry_run=dry_run)
        if res and res.get("status") not in ("skipped", "duplicate", "disabled"):
            print(f"[heatmap] {res.get('status')}: { {k: res.get(k) for k in ('slot','data_date','phase','counts','sources') if k in res} }")
        return res
    except Exception as e:
        print(f"[heatmap] failed (tick continues): {type(e).__name__}: {telegram._redact(str(e))[:200]}")
        return {"status": "failed"}


def _tick(dry_run, push=False):
    def runner(job, slot):
        if job in REPORT_JOBS:
            from px import marketdata
            if marketdata.yahoo_blocked():
                print(f"[tick] {job}: Yahoo rate-limit cooldown active — deferred (no attempt used; retried after cooldown)")
                return "deferred"
        # first attempt of a slot = normal run; later attempts come from the watchdog (window bypass)
        e = schedule.get(job, slot)
        return _rerun(job, slot) if e else _tick_run(job, slot)
    _realwatch(dry_run)
    acts = schedule.tick(runner=runner, alert=_alert, dry_run=dry_run)
    hm = _heatmap(dry_run)
    if acts:
        print(json.dumps({"now_hkt": clock.now_hkt().isoformat(timespec="minutes"), "actions": acts}, ensure_ascii=False, indent=1))
    # push when a schedule job ran OR the heatmap wrote a fresh JSON (website update; heatmap itself never Telegrams)
    if push and not dry_run and (any(a.get("action") in ("run", "rerun") for a in acts) or (hm or {}).get("status") == "ok"):
        from px import gitops
        gitops.commit_and_push(f"px tick: {clock.now_hkt():%Y-%m-%d %H:%M} HKT")
    return 0


def _check(dry_run, push=False):
    acts = schedule.check(runner=_rerun, alert=_alert, dry_run=dry_run)
    print(json.dumps({"now_hkt": clock.now_hkt().isoformat(timespec="minutes"), "actions": acts}, ensure_ascii=False, indent=1))
    if push and not dry_run and acts:
        from px import gitops
        gitops.commit_and_push(f"px check: {clock.now_hkt():%Y-%m-%d %H:%M} HKT")
    return 0


def _scan():
    from px import scan, messages, archive
    res = scan.run_scan()
    print(archive.strip_html(messages.scan_message(res)))
    return 0


def _status():
    s = config.load_settings()
    now = clock.now_hkt()
    et = clock.to_et(now)
    d = et.date()
    print(f"now: {now:%Y-%m-%d %H:%M} HKT = {et:%Y-%m-%d %H:%M %Z}")
    print(f"US trading day: {clock.is_trading_day(d)}" + (f" ({clock.holiday_name(d)})" if clock.holiday_name(d) else "")
          + (" [early close 13:00 ET]" if clock.is_early_close(d) else ""))
    print("secrets present (values never shown):", json.dumps(config.secret_status()))
    print("dry-run env:", config.is_dry_run(), "| telegram disabled:", config.telegram_disabled())
    print("schedule today/next (local -> HKT) and run-ledger status:")
    for job, c in schedule.jobs().items():
        tz = schedule._tz(c)
        day = now.astimezone(tz).date()
        slots = schedule.expected_slots(job, day)
        if not slots:
            print(f"  {job:<8} (no slot on {day} {c['tz']}: {c['days']})")
            continue
        txt = ", ".join(f"{sl:%H:%M}->{sl.astimezone(clock.HKT):%H:%M}:{(schedule.get(job, sl) or {}).get('status', '-')}" for sl in slots)
        print(f"  {job:<8} {c['tz']} {txt}")
    print(schedule.health_line(d, now))
    try:
        from px import heatmap as hm
        hs = hm.slots(d)
        print("heatmap slots today (ET):", ", ".join(f"{k}@{s:%H:%M}" for k, s in hs) if hs else "(none)")
    except Exception as e:
        print("heatmap:", type(e).__name__)
    print("guard today:", json.dumps(guard.get_all().get(clock.session_date(now).isoformat(), {}), ensure_ascii=False)[:1500])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "pos":  # Roy's REAL Futu trade record (never places orders)
        from px import realpos
        return realpos.cli(argv[1:])
    ap = argparse.ArgumentParser(description="Project X jobs")
    ap.add_argument("job", choices=list(JOBS) + ["status", "tick", "check", "scan", "tgcheck", "tgtest"])
    ap.add_argument("--yes", action="store_true", help="confirm tgtest (sends 2 real Telegram messages)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args(argv)
    if a.job == "status":
        _status()
        return 0
    if a.dry_run:
        os.environ["PX_DRY_RUN"] = "1"
    if a.job == "check":
        return _check(a.dry_run, a.push)
    if a.job == "tick":
        return _tick(a.dry_run, a.push)
    if a.job == "scan":
        return _scan()
    if a.job == "tgcheck":
        print(json.dumps({"getMe": telegram.get_me(), "getChat": telegram.get_chat()}, ensure_ascii=False))
        return 0
    if a.job == "tgtest":
        if not a.yes and not a.dry_run:
            print("tgtest sends 1 text + 1 image to TELEGRAM_CHAT_ID. Re-run with --yes to confirm.")
            return 1
        from px import charts, archive
        me = telegram.get_me() or {}
        ok1, r1 = telegram.send(f"✅ Project X 測試訊息（cutover）— bot @{me.get('username')}，{clock.now_hkt():%Y-%m-%d %H:%M} HKT",
                                dry_run=a.dry_run, label="tgtest")
        hist = archive.load_pnl()
        img = charts.equity_chart(hist, "/tmp/px_tgtest.png") if len(hist) >= 2 else charts.line_chart("/tmp/px_tgtest.png", [[1, 2, 3, 2, 4]], ["a", "b"])
        ok2, r2 = telegram.send_photo(img, caption="✅ Project X 測試圖表（cutover）", dry_run=a.dry_run, label="tgtest")
        print(json.dumps({"text": ok1, "photo": ok2, "text_err": None if ok1 else r1, "photo_err": None if ok2 else r2}, ensure_ascii=False))
        return 0 if (ok1 and ok2) else 2
    fn = _job_fn(a.job)
    try:
        res = schedule.run_job(a.job, fn, via="manual" if a.force else "cron", dry_run=a.dry_run, force=a.force)
    except Exception as e:
        traceback.print_exc()
        if not a.dry_run:
            _error_alert(a.job, e)
        return 1
    status = res.get("status")
    print(f"[run.py] {a.job}: {status}")
    if a.push and not a.dry_run and status in ("ok", "telegram_failed"):
        from px import gitops
        gitops.commit_and_push(f"px {a.job}: {clock.session_date().isoformat()} ({clock.now_hkt():%H:%M} HKT)")
    return 2 if status == "telegram_failed" else 0


if __name__ == "__main__":
    sys.exit(main())
