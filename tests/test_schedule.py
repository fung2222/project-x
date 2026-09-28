"""Schedule / holiday / watchdog / duplicate-guard tests (offline)."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from px import clock, schedule, guard  # noqa: E402

ET, HKT = clock.ET, clock.HKT


def hkt(y, m, d, hh, mm):
    return dt.datetime(y, m, d, hh, mm, tzinfo=HKT)


class TestHolidays(unittest.TestCase):
    def test_nyse_2026_2027(self):
        exp = {
            2026: ["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19",
                   "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"],
            2027: ["2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18",
                   "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"],
        }
        for y, days in exp.items():
            self.assertEqual(sorted(d.isoformat() for d in clock.nyse_holidays(y)), days)

    def test_early_closes(self):
        self.assertTrue(clock.is_early_close(dt.date(2026, 11, 27)))
        self.assertTrue(clock.is_early_close(dt.date(2026, 12, 24)))
        self.assertTrue(clock.is_early_close(dt.date(2027, 11, 26)))
        self.assertFalse(clock.is_early_close(dt.date(2026, 7, 2)))
        self.assertFalse(clock.is_early_close(dt.date(2027, 12, 23)))


class TestSlots(unittest.TestCase):
    def test_dst_boundary_open_slot(self):
        fri = schedule.expected_slots("open", dt.date(2026, 10, 30))[0].astimezone(HKT)
        mon = schedule.expected_slots("open", dt.date(2026, 11, 2))[0].astimezone(HKT)
        self.assertEqual(fri.strftime("%H:%M"), "21:35")   # EDT
        self.assertEqual(mon.strftime("%H:%M"), "22:35")   # EST after 2026-11-01
        mar = schedule.expected_slots("open", dt.date(2027, 3, 15))[0].astimezone(HKT)
        self.assertEqual(mar.strftime("%H:%M"), "21:35")   # EDT again after 2027-03-14

    def test_close_slot_hkt_both_seasons(self):
        self.assertEqual(schedule.expected_slots("close", dt.date(2026, 10, 30))[0].astimezone(HKT).strftime("%m-%d %H:%M"), "10-31 05:00")
        self.assertEqual(schedule.expected_slots("close", dt.date(2026, 11, 2))[0].astimezone(HKT).strftime("%m-%d %H:%M"), "11-03 06:00")

    def test_friday_overnight_hourly(self):
        slots = [s.astimezone(HKT) for s in schedule.expected_slots("hourly", dt.date(2026, 10, 2))]
        self.assertEqual(slots[-1].strftime("%a %H:%M"), "Sat 04:06")  # second half of Friday's session = Saturday HKT
        self.assertTrue(any(s.weekday() == 5 for s in slots))
        # Sunday ET has no slots -> nothing on Monday 00-04 HKT
        self.assertEqual(schedule.expected_slots("hourly", dt.date(2026, 10, 4)), [])

    def test_holiday_and_half_day(self):
        self.assertEqual(schedule.expected_slots("daily", dt.date(2026, 11, 26)), [])        # Thanksgiving
        self.assertEqual(schedule.expected_slots("morning", dt.date(2026, 11, 27)), [])      # HKT morning after holiday
        half = schedule.expected_slots("hourly", dt.date(2026, 11, 27))
        self.assertEqual([s.strftime("%H:%M") for s in half], ["10:06", "11:06", "12:06", "13:06"])
        self.assertEqual(len(schedule.expected_slots("close", dt.date(2026, 11, 27))), 1)

    def test_morning_and_weekly_days(self):
        self.assertEqual(len(schedule.expected_slots("morning", dt.date(2026, 10, 3))), 1)   # Sat HKT after Fri
        self.assertEqual(schedule.expected_slots("morning", dt.date(2026, 10, 5)), [])       # Mon HKT after Sun
        self.assertEqual(len(schedule.expected_slots("weekly", dt.date(2026, 10, 5))), 1)
        self.assertEqual(schedule.expected_slots("weekly", dt.date(2026, 10, 6)), [])

    def test_slot_for_tolerance(self):
        s = schedule.slot_for("hourly", hkt(2026, 10, 2, 22, 7))
        self.assertEqual(s.strftime("%H:%M"), "10:06")
        self.assertIsNone(schedule.slot_for("hourly", hkt(2026, 10, 2, 21, 15)))  # 09:15 ET pre-open: unscheduled


class TestWatchdog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p1 = mock.patch.object(schedule, "LEDGER", os.path.join(self.tmp, "run_ledger.json"))
        self.p2 = mock.patch.object(schedule, "STATE_DIR", self.tmp)
        self.p3 = mock.patch.object(guard, "PATH", os.path.join(self.tmp, "job_runs.json"))
        self.p4 = mock.patch.object(guard, "STATE_DIR", self.tmp)
        for p in (self.p1, self.p2, self.p3, self.p4):
            p.start()
        with open(os.path.join(self.tmp, "run_ledger.json"), "w") as f:
            json.dump({"_meta": {"watch_since": "2026-01-01T00:00+08:00"}}, f)

    def tearDown(self):
        for p in (self.p1, self.p2, self.p3, self.p4):
            p.stop()

    def test_missing_slot_rerun_then_ok(self):
        now = hkt(2026, 10, 2, 21, 58)  # 09:58 ET: open slot 09:35 grace 20 passed
        calls = []

        def runner(job, slot):
            calls.append(job)
            schedule.record(job, slot, "ok", now=now)
            return "ok"
        with mock.patch.object(clock, "now_hkt", return_value=now):
            acts = schedule.check(now=now, runner=runner, alert=lambda t: True)
        self.assertIn("open", calls)
        today = [a for a in acts if "2026-10-02T21" in a["slot"]]
        self.assertTrue(today and all(a["action"] == "rerun" for a in today))
        with mock.patch.object(clock, "now_hkt", return_value=now):
            acts2 = schedule.check(now=now, runner=runner, alert=lambda t: True)
        self.assertEqual([a for a in acts2 if a["job"] == "open"], [])  # already ok -> nothing

    def test_alert_once_after_deadline(self):
        now = hkt(2026, 10, 2, 23, 30)  # 11:30 ET: open rerun deadline 10:45 passed
        with mock.patch.object(clock, "now_hkt", return_value=now):
            acts = schedule.check(now=now, runner=lambda j, s: "failed", alert=lambda t: True)
            acts2 = schedule.check(now=now, runner=lambda j, s: "failed", alert=lambda t: True)
        is_open = lambda a: a["job"] == "open" and a["slot"].startswith("open|2026-10-02T21:35") and a["action"] == "alert"
        self.assertEqual(len([a for a in acts if is_open(a)]), 1)
        self.assertEqual(len([a for a in acts2 if is_open(a)]), 0)  # no second alert

    def test_duplicate_rerun_is_guarded(self):
        now = hkt(2026, 10, 2, 21, 36)
        sends = []

        def job(dry_run=False, force=False, now=None):
            sess = "2026-10-02"
            if guard.was_sent(sess, "open", "main") and not force:
                return {"status": "duplicate"}
            sends.append(1)
            guard.mark_sent(sess, "open", "main", [1])
            return {"status": "ok"}
        with mock.patch.object(clock, "now_hkt", return_value=now):
            r1 = schedule.run_job("open", job, now=now)
            r2 = schedule.run_job("open", job, now=now)
        self.assertEqual((r1["status"], r2["status"]), ("ok", "duplicate"))
        self.assertEqual(len(sends), 1)
        e = schedule.get("open", schedule.expected_slots("open", dt.date(2026, 10, 2))[0])
        self.assertEqual(e["attempts"], 2)
        self.assertEqual(e["status"], "ok")  # sticky success: duplicate re-run does not downgrade

    def test_first_check_arms_only(self):
        os.remove(os.path.join(self.tmp, "run_ledger.json"))
        now = hkt(2026, 10, 2, 23, 30)
        with mock.patch.object(clock, "now_hkt", return_value=now):
            acts = schedule.check(now=now, runner=lambda j, s: "failed", alert=lambda t: True)
            self.assertEqual([a["action"] for a in acts], ["armed"])
            acts2 = schedule.check(now=now, runner=lambda j, s: "failed", alert=lambda t: True)
        self.assertEqual(acts2, [])  # all earlier slots are before watch_since

    def test_superset_cron_skip_keeps_ok(self):
        slot = schedule.expected_slots("close", dt.date(2026, 10, 2))[0]
        schedule.record("close", slot, "ok")
        schedule.record("close", slot, "skipped")
        self.assertEqual(schedule.get("close", slot)["status"], "ok")

    def test_holiday_no_watchdog_action(self):
        now = hkt(2026, 11, 27, 1, 0)  # Thanksgiving ET evening
        with mock.patch.object(clock, "now_hkt", return_value=now):
            acts = schedule.check(now=now, runner=lambda j, s: "ok", alert=lambda t: True, dry_run=True)
        self.assertFalse([a for a in acts if a["slot"].startswith(("open|2026-11-26", "daily|2026-11-26"))])

    def test_health_line(self):
        now = hkt(2026, 10, 3, 5, 10)
        with mock.patch.object(clock, "now_hkt", return_value=now):
            for job in ("open", "daily"):
                schedule.record(job, schedule.expected_slots(job, dt.date(2026, 10, 2))[0], "ok", now=now)
            line = schedule.health_line(dt.date(2026, 10, 2), now, exclude=("close",))
        self.assertIn("open✅", line)
        self.assertIn("hourly 0/7⚠️", line)


class TestTick(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ps = [mock.patch.object(schedule, "LEDGER", os.path.join(self.tmp, "run_ledger.json")),
                   mock.patch.object(schedule, "STATE_DIR", self.tmp)]
        for p in self.ps:
            p.start()
        with open(os.path.join(self.tmp, "run_ledger.json"), "w") as f:
            json.dump({"_meta": {"watch_since": "2026-01-01T00:00+08:00"}}, f)
        self.calls = []

    def tearDown(self):
        for p in self.ps:
            p.stop()

    def runner_at(self, now):
        def r(job, slot):
            self.calls.append((job, slot.strftime("%Y-%m-%d %H:%M")))
            schedule.record(job, slot, "ok", now=now)
            return "ok"
        return r

    def _tick(self, now):
        with mock.patch.object(clock, "now_hkt", return_value=now):
            return schedule.tick(now=now, runner=self.runner_at(now), alert=lambda t: True)

    def test_open_runs_once_edt(self):
        self._tick(hkt(2026, 10, 2, 21, 34))
        self.assertEqual(self.calls, [])
        self._tick(hkt(2026, 10, 2, 21, 35))
        self._tick(hkt(2026, 10, 2, 21, 36))
        self.assertEqual(self.calls, [("open", "2026-10-02 09:35")])

    def test_open_after_dst_is_2235_hkt(self):
        self._tick(hkt(2026, 11, 2, 21, 35))
        self.assertEqual(self.calls, [])
        self._tick(hkt(2026, 11, 2, 22, 35))
        self.assertEqual(self.calls, [("open", "2026-11-02 09:35")])

    def test_friday_second_half_runs_on_saturday_hkt(self):
        self._tick(hkt(2026, 10, 3, 0, 6))  # Sat 00:06 HKT = Fri 12:06 ET
        self.assertIn(("hourly", "2026-10-02 12:06"), self.calls)

    def test_holiday_nothing(self):
        for h, m in ((22, 35), (22, 53), (23, 6)):
            self._tick(hkt(2026, 11, 26, h, m))  # Thanksgiving (EST)
        self.assertEqual([c for c in self.calls if c[0] in ("open", "daily", "hourly")], [])

    def test_morning_saturday_not_monday(self):
        self._tick(hkt(2026, 10, 3, 8, 30))  # Sat after Fri session
        self._tick(hkt(2026, 10, 5, 8, 30))  # Mon after weekend -> no morning; weekly at 09:44
        self._tick(hkt(2026, 10, 5, 9, 44))
        self.assertIn(("morning", "2026-10-03 08:30"), self.calls)
        self.assertNotIn(("morning", "2026-10-05 08:30"), self.calls)
        self.assertIn(("weekly", "2026-10-05 09:44"), self.calls)


if __name__ == "__main__":
    unittest.main()
