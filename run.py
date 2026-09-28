#!/usr/bin/env python3
"""Project X CLI — the ONLY entry point the scheduler (Hermes / optional GitHub Actions) needs.

    python run.py open    [--dry-run] [--force] [--push]   # ET 09:35  (HKT 21:35 EDT / 22:35 EST)
    python run.py daily   [--dry-run] [--force] [--push]   # ET 10:00  (HKT 22:00 EDT / 23:00 EST)
    python run.py hourly  [--dry-run] [--force] [--push]   # ET 10:30..15:30 + 16:10
    python run.py weekly  [--dry-run] [--force] [--push]   # Monday HKT 09:45
    python run.py status                                    # config/secrets presence/today's guard state

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

from px import clock, config, guard, telegram  # noqa: E402


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
    print("schedule (ET -> HKT today):")
    for job in ("open", "daily"):
        t = s["schedule_et"][job]["time"]
        print(f"  {job:<7} {t} ET -> {clock.et_to_hkt_str(t, d)} HKT")
    print("  hourly  " + ", ".join(f"{t}->{clock.et_to_hkt_str(t, d)}" for t in s["schedule_et"]["hourly"]["times"]))
    print("guard today:", json.dumps(guard.get_all().get(clock.session_date(now).isoformat(), {}), ensure_ascii=False)[:1500])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Project X jobs")
    ap.add_argument("job", choices=["open", "daily", "hourly", "weekly", "status"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args(argv)
    if a.job == "status":
        _status()
        return 0
    if a.dry_run:
        os.environ["PX_DRY_RUN"] = "1"
    from px.jobs import open_monitor, daily, hourly, weekly
    fn = {"open": open_monitor.run, "daily": daily.run, "hourly": hourly.run, "weekly": weekly.run}[a.job]
    try:
        res = fn(dry_run=a.dry_run, force=a.force)
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
