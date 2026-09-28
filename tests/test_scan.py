"""Opportunity-scan rule tests on synthetic data (offline)."""
import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401  (offline + temp state dir)

from px import scan  # noqa: E402
from px.config import load_settings  # noqa: E402


def frame(prices, vol=5_000_000):
    idx = pd.bdate_range("2025-01-01", periods=len(prices))
    p = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame({"Open": p * 0.995, "High": p * 1.02, "Low": p * 0.98, "Close": p, "Volume": vol}, index=idx)


def trend(n=260, start=10.0, drift=0.004, seed=1):
    rng = np.random.default_rng(seed)
    r = drift + rng.normal(0, 0.01, n)
    return start * np.cumprod(1 + r)


class TestScan(unittest.TestCase):
    def setUp(self):
        self.c = dict(load_settings()["scan"])
        self.q = scan.features(frame(trend(seed=9, drift=0.001))).iloc[-1]

    def ev(self, prices, vol=5_000_000, t="TEST"):
        row = scan.features(frame(prices, vol)).iloc[-1]
        return scan.evaluate(t, row, self.q, 1280.0, 7.8, 0.8, self.c, None)

    def test_downtrend_rejected(self):
        x = self.ev(trend(drift=-0.004)[::1])
        self.assertFalse(x["pass"])
        self.assertTrue(any("MA50" in f for f in x["fail"]))

    def test_penny_and_illiquid_rejected(self):
        x = self.ev(trend(start=0.5), vol=100_000)
        self.assertTrue(any("股價" in f for f in x["fail"]))
        self.assertTrue(any("成交額" in f for f in x["fail"]))

    def test_unaffordable_rejected(self):
        x = self.ev(trend(start=250.0))
        self.assertTrue(any("每股太貴" in f for f in x["fail"]))

    def test_levels_and_sizing_respect_rules(self):
        row = scan.features(frame(trend())).iloc[-1]
        lv = scan.levels(row, self.c)
        self.assertGreaterEqual(lv["stop_pct"], self.c["sl_min_pct"] * 100 - 1e-9)
        self.assertLessEqual(lv["stop_pct"], self.c["sl_max_pct"] * 100 + 1e-9)
        self.assertLess(lv["stop"], lv["entry"])
        self.assertGreater(lv["target"], lv["entry"])
        sz = scan.size(lv["entry"], lv["stop"], 1280.0, 7.8, self.c)
        self.assertLessEqual(sz["risk_usd"], 0.02 * 1280 + 1e-6)
        self.assertLessEqual(sz["cost_usd"], 0.25 * 1280 + 1e-6)

    def test_rank_one_per_theme(self):
        a = {"ticker": "MARA", "pass": True, "score": 90, "rr": 3, "theme": "BTC_MINING_HPC"}
        b = {"ticker": "RIOT", "pass": True, "score": 89, "rr": 3, "theme": "BTC_MINING_HPC"}
        c = {"ticker": "IONQ", "pass": True, "score": 70, "rr": 3, "theme": "QUANTUM"}
        top = scan.rank([a, b, c], top_n=5)
        self.assertEqual([x["ticker"] for x in top], ["MARA", "IONQ"])

    def test_earnings_blackout(self):
        row = scan.features(frame(trend())).iloc[-1]
        x = scan.evaluate("TEST", row, self.q, 1280.0, 7.8, 0.8, self.c, earnings_days=2)
        self.assertTrue(any("業績" in f for f in x["fail"]))


if __name__ == "__main__":
    unittest.main()
