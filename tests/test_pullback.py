"""Pullback scanner state, completed-bar and scheduling tests (offline)."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401

from px import clock, guard, schedule  # noqa: E402
from px.jobs import pullback  # noqa: E402


def prices(hit=False, end="2026-11-06", extra=False):
    p = (np.r_[np.linspace(80, 100, 220), np.linspace(100.1, 125, 30), np.linspace(124, 112, 10)]
         if hit else np.full(260, 100.0))
    if extra:
        p = np.r_[p, p[-1] + 5]
    idx = pd.bdate_range(end=end, periods=260)
    if extra:
        idx = idx.append(pd.DatetimeIndex(["2026-11-09"]))
    return pd.DataFrame({"Close": p, "High": p * 1.001, "Open": p, "Low": p * .99, "Volume": 1_000_000}, index=idx)


def small_cfg():
    return {"universe": ["AAA"], "history_period": "1y", "min_bars": 70,
            "min_3m_return": 0.0, "drop_range": [-0.18, -0.08],
            "ma50_ratio_range": [1.0, 1.05], "ma50_slope_lookback": 10}


class TestPullbackScan(unittest.TestCase):
    def test_four_rules_produce_structured_hit(self):
        now = dt.datetime(2026, 11, 9, 9, 0, tzinfo=clock.ET)
        res = pullback.scan(now=now, fetcher=lambda t, p: prices(True), cfg=small_cfg())
        self.assertEqual(res["bar_date"], "2026-11-06")
        self.assertEqual([x["ticker"] for x in res["hits"]], ["AAA"])
        self.assertEqual(res["failures"], [])
        self.assertAlmostEqual(res["hits"][0]["price_ma50_ratio"], 1.01, places=2)

    def test_forming_today_bar_is_discarded(self):
        now = dt.datetime(2026, 11, 9, 10, 0, tzinfo=clock.ET)
        res = pullback.scan(now=now, fetcher=lambda t, p: prices(True, extra=True), cfg=small_cfg())
        self.assertEqual(res["bar_date"], "2026-11-06")
        self.assertEqual(res["hits"][0]["bar_date"], "2026-11-06")


class TestPullbackRunStates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ps = [mock.patch.object(pullback, "OUTPUT", os.path.join(self.tmp, "pullback.json")),
                   mock.patch.object(guard, "PATH", os.path.join(self.tmp, "guard.json")),
                   mock.patch.object(guard, "STATE_DIR", self.tmp)]
        for p in self.ps:
            p.start()
        self.now = dt.datetime(2026, 11, 9, 9, 0, tzinfo=clock.ET)

    def tearDown(self):
        for p in self.ps:
            p.stop()

    def test_complete_zero_hits_is_ok_and_silent(self):
        with mock.patch.object(pullback.telegram, "send", return_value=(True, [1])) as send:
            res = pullback.run(now=self.now, fetcher=lambda t, p: prices(False))
        self.assertEqual(res["status"], "ok")
        send.assert_not_called()
        with open(pullback.OUTPUT, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual((data["status"], data["scanned"], data["hit_count"]), ("ok", 45, 0))
        self.assertEqual(data["failure_count"], 0)

    def test_partial_data_failure_is_not_zero_hit_success(self):
        def fetch(t, p):
            if t == "AAPL":
                raise RuntimeError("offline")
            return prices(False)
        with mock.patch.object(pullback.telegram, "send", return_value=(True, [1])) as send:
            res = pullback.run(now=self.now, fetcher=fetch)
        self.assertEqual(res["status"], "failed")
        send.assert_not_called()
        self.assertEqual(res["result"]["hit_count"], 0)
        self.assertEqual(res["result"]["failure_count"], 1)
        self.assertEqual(res["result"]["failures"][0]["ticker"], "AAPL")

    def test_complete_failure_is_structured(self):
        def fetch(t, p):
            raise RuntimeError("offline")
        res = pullback.run(now=self.now, fetcher=fetch)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["result"]["scanned"], 0)
        self.assertEqual(res["result"]["failure_count"], 45)


class TestPullbackSchedule(unittest.TestCase):
    def test_preopen_slot_follows_dst_and_nyse_calendar(self):
        edt = schedule.expected_slots("pullback", dt.date(2026, 10, 30))[0]
        est = schedule.expected_slots("pullback", dt.date(2026, 11, 2))[0]
        self.assertEqual(edt.astimezone(clock.HKT).strftime("%H:%M"), "21:00")
        self.assertEqual(est.astimezone(clock.HKT).strftime("%H:%M"), "22:00")
        self.assertEqual(schedule.expected_slots("pullback", dt.date(2026, 11, 26)), [])


if __name__ == "__main__":
    unittest.main()
