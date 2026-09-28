#!/usr/bin/env python3
"""Project X CLI — the ONLY entry point the scheduler (Hermes / optional GitHub Actions) needs.

    python run.py open    [--dry-run] [--force] [--push]   # ET 09:35  (HKT 21:35 EDT / 22:35 EST)
    python run.py daily   [--dry-run] [--force] [--push]   # ET 09:53  (HKT 21:53 EDT / 22:53 EST), push ~10:00 ET
    python run.py hourly  [--dry-run] [--force] [--push]   # ET :06 past 10..16 (alert-only + 1 status/session)
    python run.py close   [--dry-run] [--force] [--push]   # ET 17:00  (HKT 05:00 EDT / 06:00 EST)
    python run.py morning [--dry-run] [--force] [--push]   # HKT 08:30 Tue-Sat after a US session
    python run.py weekly  [--dry-run] [--force] [--push]   # HKT Monday 09:44
    python run.py check   [--dry-run]                      # watchdog: re-run missed/failed slots, else 1 alert
    python run.py scan                                      # print today's opportunity Top 5 (no Telegram)
    python run.py status                                    # config/secrets presence, schedule, run ledger
    python run.py tgcheck                                   # getMe + getChat (bot username, chat type/title; no send)
    python run.py tgtest --yes                              # cutover test: 1 text + 1 chart image to TELEGRAM_CHAT_ID

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

JOBS = ("open", "daily", "hourly", "close", "morning", "weekly")


def _job_fn(job):
    from px.jobs import open_monitor, daily, hourly, weekly, close, morning
    return {"open": open_monitor.run, "daily": daily.run, "hourly": hourly.run, "weekly": weekly.run,
            "close": close.run, "morning": morning.run}[job]


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


def _check(dry_run):
    acts = schedule.check(runner=_rerun, alert=_alert, dry_run=dry_run)
    print(json.dumps({"now_hkt": clock.now_hkt().isoformat(timespec="minutes"), "actions": acts}, ensure_ascii=False, indent=1))
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
    print("guard today:", json.dumps(guard.get_all().get(clock.session_date(now).isoformat(), {}), ensure_ascii=False)[:1500])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Project X jobs")
    ap.add_argument("job", choices=list(JOBS) + ["status", "check", "scan", "tgcheck", "tgtest"])
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
        return _check(a.dry_run)
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
        err = telegram._redact(f"{type(e).__name__}: {e}")[:300]
        if not a.dry_run:
            sess = clock.session_date().isoformat()
            if not guard.was_sent(sess, a.job, "error"):
                ok, ids = telegram.send(f"<b>🛠 Project X 系統警告</b> {a.job} 失敗（{sess} ET）：{err}\n"
                                        f"請 Hermes 睇 log 同按 HERMES_HANDOVER 重跑。", label="error")
                if ok:
                    guard.mark_sent(sess, a.job, "error", ids)
            guard.update(sess, a.job, status="failed", error=err, _inc_runs=True)
        return 1
    status = res.get("status")
    print(f"[run.py] {a.job}: {status}")
    if a.push and not a.dry_run and status in ("ok", "telegram_failed"):
        from px import gitops
        gitops.commit_and_push(f"px {a.job}: {clock.session_date().isoformat()} ({clock.now_hkt():%H:%M} HKT)")
    return 2 if status == "telegram_failed" else 0


if __name__ == "__main__":
    sys.exit(main())
