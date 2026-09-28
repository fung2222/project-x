"""Simulates the Hermes crontab from docs/HERMES_HANDOVER.md §3 against the scheduler.

For the recommended DST-proof HKT "superset" crontab (fires daily, both EDT and EST times):
every expected ET slot (open/daily/hourly/close) and HKT slot (morning/weekly) must be hit
by a cron firing at exactly the slot time, and any extra firing must be harmless: outside the
job's run window, a non-trading day, or mapped to a slot that already ran (duplicate guard).
Covers both DST switches (2026-11-01, 2027-03-14), Thanksgiving + half day, Christmas, New Year.
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from px import clock, schedule  # noqa: E402
from px.config import load_settings  # noqa: E402

# (job, minute, hours, weekdays[0=Mon]) in HKT — must match HERMES_HANDOVER.md §3.2
SUPERSET = [
    ("open", 35, [21, 22], range(7)),
    ("daily", 53, [21, 22], range(7)),
    ("hourly", 6, [22, 23, 0, 1, 2, 3, 4, 5], range(7)),
    ("close", 0, [5, 6], range(7)),
    ("morning", 30, [8], range(7)),
    ("weekly", 44, [9], [0]),
]
WINDOW_KEY = {"open": "open", "daily": "daily", "hourly": "hourly", "close": "close"}


def firings(job, start, end):
    for m_job, minute, hours, wds in SUPERSET:
        if m_job != job:
            continue
        d = start
        while d <= end:
            if d.weekday() in wds:
                for h in hours:
                    yield dt.datetime.combine(d, dt.time(h, minute), tzinfo=clock.HKT)
            d += dt.timedelta(days=1)


def gate_accepts(job, t):
    """Mirror of the job-level gates (px/jobs/common.gate_run, close/morning checks)."""
    s = load_settings()
    if job in WINDOW_KEY:
        et = t.astimezone(clock.ET)
        if not clock.is_trading_day(et.date()):
            return False
        if job == "close":
            return clock.session_closed(t) and clock.in_window(s["schedule_et"]["close"]["window"], et)
        return clock.in_window(s["schedule_et"][job]["window"], et)
    if job == "morning":
        return schedule.day_applies("morning", t.date()) and clock.in_window_hkt(s["schedule_hkt"]["morning"]["window"], t)
    return t.weekday() == 0


class TestSupersetCrontab(unittest.TestCase):
    RANGES = [(dt.date(2026, 10, 26), dt.date(2026, 11, 10)),
              (dt.date(2026, 11, 23), dt.date(2027, 1, 6)),
              (dt.date(2027, 3, 8), dt.date(2027, 3, 19))]

    def test_every_slot_hit_once_and_extras_harmless(self):
        for start, end in self.RANGES:
            for job in ("open", "daily", "hourly", "close", "morning", "weekly"):
                tz = schedule._tz(schedule.jobs()[job])
                expected = set()
                d = start
                while d <= end:
                    expected.update(schedule.expected_slots(job, d))
                    d += dt.timedelta(days=1)
                hits = {}
                for f in firings(job, start - dt.timedelta(days=1), end + dt.timedelta(days=1)):
                    if not gate_accepts(job, f):
                        continue
                    slot = schedule.slot_for(job, f)
                    if slot is None:
                        # accepted by the gate but not tied to a slot: only allowed for hourly
                        # outside its slots (it would be recorded as 'manual' and send at most
                        # alerts), never for report jobs
                        self.assertEqual(job, "hourly", f"{job} fired at {f} without a slot")
                        continue
                    hits.setdefault(slot, []).append(f)
                for s in expected:
                    fs = hits.get(s, [])
                    self.assertTrue(fs, f"{job} slot {s} ({s.astimezone(clock.HKT)}) never fired")
                    self.assertEqual(min(fs).astimezone(tz).replace(tzinfo=None), s.replace(tzinfo=None),
                                     f"{job} slot {s} first fired late at {min(fs)}")

    def test_hourly_superset_never_fires_twice_per_slot(self):
        start, end = dt.date(2026, 10, 26), dt.date(2026, 11, 10)
        per_slot = {}
        for f in firings("hourly", start, end):
            if gate_accepts("hourly", f):
                s = schedule.slot_for("hourly", f)
                if s:
                    per_slot.setdefault(s, []).append(f)
        self.assertTrue(per_slot)
        self.assertTrue(all(len(v) == 1 for v in per_slot.values()))


if __name__ == "__main__":
    unittest.main()
