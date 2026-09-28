"""Offline acceptance tests (MERGE_PLAN §16, runnable parts). Run: python -m unittest -v  (or pytest -q)"""
import copy
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401  (offline + temp state dir)

from px import archive, clock, decide, guard, indicators, ledger, signals  # noqa: E402

ET = clock.ET


def make_df(n=260, end=dt.date(2026, 9, 25), seed=1, drift=0.0, start=100.0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=pd.Timestamp(end), periods=n, tz=ET)
    rets = rng.normal(drift, 0.02, n)
    close = start * np.exp(np.cumsum(rets))
    high = close * (1 + rng.uniform(0, 0.02, n))
    low = close * (1 - rng.uniform(0, 0.02, n))
    vol = rng.integers(1_000_000, 2_000_000, n).astype(float)
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol}, index=days)


def ref_wilder_rsi(closes, period=14):
    d = np.diff(closes)
    g = np.where(d > 0, d, 0.0)
    l_ = np.where(d < 0, -d, 0.0)
    ag, al = g[0], l_[0]  # pandas ewm(adjust=False) seeds with the first value
    a = 1 / period
    for i in range(1, len(d)):
        ag = a * g[i] + (1 - a) * ag
        al = a * l_[i] + (1 - a) * al
    return 100 - 100 / (1 + ag / al)


def base_pf():
    return {
        "account": {"cash_usd": 1140.56},
        "positions": [{"ticker": "SOUN", "shares": 25, "entry_price": 6.26, "entry_date": "2026-09-13",
                       "trade_id": "T004", "current_price": 6.05, "stop_loss_price": 5.76, "take_profit_price": 6.89}],
        "trade_log": [
            {"id": "T001", "date": "2026-07-07", "ticker": "NVDA", "action": "BUY", "shares": 1, "entry_price": 195.55, "cost_usd": 195.55},
            {"id": "T002", "date": "2026-08-05", "ticker": "NVDA", "action": "SELL", "shares": 1, "exit_price": 218.27,
             "gross_proceeds_usd": 218.27, "fee_usd": 1.09, "net_pnl_usd": 21.63},
            {"id": "T003", "date": "2026-09-13", "ticker": "RKLB", "action": "BUY", "shares": 3, "entry_price": 62.95, "cost_usd": 188.85, "fee_usd": 1.0},
            {"id": "T004", "date": "2026-09-13", "ticker": "SOUN", "action": "BUY", "shares": 25, "entry_price": 6.26, "cost_usd": 156.5, "fee_usd": 1.0},
            {"id": "T005", "date": "2026-09-21", "ticker": "RKLB", "action": "SELL", "shares": 3, "entry_price": 62.95, "exit_price": 69.65,
             "gross_proceeds_usd": 208.95, "fee_usd": 1.04, "net_pnl_usd": 18.06, "reason": "TAKE_PROFIT"},
        ],
    }


class T1_T3_Indicators(unittest.TestCase):
    def test_T1_wilder_rsi(self):
        df = make_df()
        ind = indicators.compute(df, now=dt.datetime(2026, 9, 26, 12, tzinfo=ET))
        self.assertAlmostEqual(ind["rsi14"], round(ref_wilder_rsi(df["Close"].values), 1), delta=0.1)

    def test_T2_ma50_real_50_bars_and_min_bars(self):
        df = make_df()
        ind = indicators.compute(df, now=dt.datetime(2026, 9, 26, 12, tzinfo=ET))
        self.assertAlmostEqual(ind["ma50"], round(df["Close"].iloc[-50:].mean(), 2), places=2)
        self.assertAlmostEqual(ind["ma20"], round(df["Close"].iloc[-20:].mean(), 2), places=2)
        short = indicators.compute(make_df(n=100), now=dt.datetime(2026, 9, 26, 12, tzinfo=ET))
        self.assertIn("error", short)

    def test_T3_completed_bars_only(self):
        df = make_df(end=dt.date(2026, 9, 28))
        df.iloc[-1, df.columns.get_loc("Volume")] = 50_000.0  # tiny in-progress volume at 11:00 ET
        now = dt.datetime(2026, 9, 28, 11, 0, tzinfo=ET)
        ind = indicators.compute(df, now=now)
        self.assertEqual(ind["bar_date"], "2026-09-25")
        exp = df["Volume"].iloc[-2] / df["Volume"].iloc[-22:-2].mean()
        self.assertAlmostEqual(ind["vol_ratio"], round(exp, 2), places=2)
        after = indicators.compute(df, now=dt.datetime(2026, 9, 28, 16, 5, tzinfo=ET))
        self.assertEqual(after["bar_date"], "2026-09-28")


class T4_Signals(unittest.TestCase):
    def test_T4_no_unconditional_plus5(self):
        ind = {"rsi14": 50.0, "macd_hist": 0.1, "vol_ratio": 1.0, "close": 10, "ma50": 9, "trend_score": 0}
        sc = signals.score(ind, "NORMAL")
        self.assertEqual((sc["signal"], sc["confidence"]), ("HOLD", 50.0))

    def test_regime_adjust(self):
        ind = {"rsi14": 38.0, "macd_hist": 0.1, "vol_ratio": 1.0, "close": 10, "ma50": 9, "trend_score": 0}
        n = signals.score(ind, "NORMAL")["confidence"]
        c = signals.score(ind, "CAUTION")["confidence"]
        self.assertEqual(n - c, 10)


class T5_T8_Ledger(unittest.TestCase):
    def test_T5_fees(self):
        flat = {"model": "flat", "min_usd": 1.0, "rate": 0.005}  # pre-2026-09-28 paper model (history)
        self.assertEqual(ledger.fee(188.85, fcfg=flat), 1.00)
        self.assertEqual(ledger.fee(208.95, fcfg=flat), 1.04)
        self.assertEqual(ledger.fee(218.27, fcfg=flat), 1.09)
        # Futu HK fixed plan: 0.99 + 1.00 minimums + 0.003/sh settlement (+ TAF on sells)
        self.assertEqual(ledger.fee(136.0, 3, "buy"), 2.00)
        self.assertEqual(ledger.fee(136.0, 3, "sell"), 2.01)
        self.assertEqual(ledger.round_trip_fee(45.33, 3), 4.01)
        self.assertEqual(ledger.fee(30000.0, 1000, "buy"), 12.9)  # per-share parts above minimums

    def test_T6_reconciliation_fixture(self):
        pf = base_pf()
        a = ledger.recompute(pf, fx=7.8)
        self.assertEqual(a["cash_usd"], 1140.56)
        self.assertEqual(a["equity_usd"], 1291.81)
        self.assertEqual(a["realized_pnl_usd"], 18.06)
        self.assertEqual(a["unrealized_pnl_usd"], -5.25)
        self.assertEqual(a["total_pnl_usd"], 11.81)
        self.assertEqual(a["total_return_pct"], 0.92)
        self.assertEqual(a["total_fees_usd"], 3.04)
        self.assertNotIn("pnl_reconcile_warning", a)

    def test_T6_repo_portfolio_json(self):
        pf = ledger.load()
        a = ledger.recompute(copy.deepcopy(pf))
        self.assertNotIn("cash_reconcile_warning", a)
        self.assertNotIn("pnl_reconcile_warning", a)
        t5 = next(t for t in pf["trade_log"] if t["id"] == "T005")
        self.assertEqual(t5["net_pnl_usd"], 18.06)

    def test_T8_stop_loss_execution(self):
        pf = base_pf()
        cash0 = ledger.recompute(pf)["cash_usd"]
        pf["positions"][0]["current_price"] = 5.70
        self.assertEqual(ledger.check_exit(pf["positions"][0], 5.70), "STOP_LOSS")
        tr = ledger.execute_exit(pf, "SOUN", 5.70, "STOP_LOSS", now=dt.datetime(2026, 9, 29, 22, 0, tzinfo=clock.HKT))
        self.assertEqual((tr["action"], tr["shares"], tr["exit_price"], tr["fee_usd"]), ("SELL", 25, 5.70, 2.08))  # Futu: 1.99 + 25*0.003 + TAF 0.01
        self.assertEqual(round(pf["account"]["cash_usd"] - cash0, 2), 140.42)
        self.assertEqual(pf["positions"], [])
        self.assertEqual(tr["net_pnl_usd"], round(142.5 - 2.08 - 156.5 - 1.0, 2))  # SOUN buy fee was booked at 1.00 (old model)


class T7_Gates(unittest.TestCase):
    def sofi(self, **kw):
        ind = {"close": 16.73, "ma50": 18.2, "rsi14": 30.0, "hist_rising": False, "up_day": False, "vol_ratio": 0.6,
               "trend_score": -3, "atr14": 0.8}
        ind.update(kw)
        return {"ticker": "SOFI", "signal": "BUY", "raw_signal": "BUY", "confidence": 70.0, "price": ind["close"], "indicators": ind}

    NOW = dt.datetime(2026, 9, 28, 22, 0, tzinfo=clock.HKT)  # 10:00 ET

    def test_T7_sofi_rejected(self):
        ev = decide.evaluate(base_pf(), self.sofi(), "NORMAL", self.NOW)
        self.assertFalse(ev["passed"])
        self.assertIn("G1", ev["failed"])
        self.assertIn("G2", ev["failed"])
        self.assertIn("G3", ev["failed"])

    def test_gate_pass_setup_A_and_sizing(self):
        sig = self.sofi(close=20.0, ma50=19.0, rsi14=40.0, vol_ratio=1.1, trend_score=2, atr14=0.6)
        sig["confidence"] = 80.0
        sig["price"] = 20.0
        ev = decide.evaluate(base_pf(), sig, "NORMAL", self.NOW)
        self.assertTrue(ev["passed"], ev)
        self.assertEqual(ev["setup"], "A")
        eq = 1291.81
        self.assertLessEqual((20.0 - ev["sl"]) * ev["shares"], 0.02 * eq + 0.01)
        self.assertLessEqual(20.0 * ev["shares"], 0.25 * eq)

    def test_theme_and_one_entry_per_day(self):
        pf = base_pf()
        ev = decide.evaluate(pf, dict(self.sofi(), ticker="BBAI"), "NORMAL", self.NOW)
        self.assertIn("G5", ev["failed"])  # AI_SPEECH theme already held (SOUN)
        ledger.execute_entry(pf, "IONQ", 40.0, 3, 37.0, 44.0, "NORMAL", "test", "A", 80, now=self.NOW)
        with self.assertRaises(ledger.RuleViolation):
            ledger.execute_entry(pf, "HOOD", 30.0, 2, 28.0, 33.0, "NORMAL", "test", "A", 80, now=self.NOW)

    def test_no_averaging_down_risk_cap_cooldown(self):
        pf = base_pf()
        with self.assertRaises(ledger.RuleViolation):
            ledger.execute_entry(pf, "SOUN", 5.9, 10, 5.5, 6.5, "NORMAL", "avg down", now=self.NOW)
        with self.assertRaises(ledger.RuleViolation):  # risk (40-30)*3=30 > 2% of 1291.81
            ledger.execute_entry(pf, "IONQ", 40.0, 3, 30.0, 44.0, "NORMAL", "too risky", now=self.NOW)
        pf2 = base_pf()
        pf2["trade_log"][-1]["date"] = "2026-09-25"  # RKLB TP exit 1 trading day before 09-28
        with self.assertRaises(ledger.RuleViolation):
            ledger.execute_entry(pf2, "RKLB", 70.0, 1, 66.0, 77.0, "NORMAL", "fomo", now=self.NOW)


class T9_T10_Clock(unittest.TestCase):
    def test_T9_dst(self):
        self.assertEqual(clock.et_to_hkt_str("09:35", dt.date(2026, 10, 30)), "21:35")
        self.assertEqual(clock.et_to_hkt_str("09:35", dt.date(2026, 11, 2)), "22:35")
        self.assertEqual(clock.et_to_hkt_str("10:00", dt.date(2026, 11, 2)), "23:00")

    def test_T10_holidays(self):
        self.assertFalse(clock.is_trading_day(dt.date(2026, 11, 26)))
        self.assertTrue(clock.is_early_close(dt.date(2026, 11, 27)))
        self.assertTrue(clock.is_early_close(dt.date(2026, 12, 24)))
        self.assertFalse(clock.is_trading_day(dt.date(2026, 12, 25)))
        self.assertFalse(clock.is_trading_day(dt.date(2027, 3, 26)))  # Good Friday
        self.assertTrue(clock.is_trading_day(dt.date(2026, 9, 28)))

    def test_holiday_job_skips_quietly(self):
        from px.jobs import open_monitor
        r = open_monitor.run(dry_run=True, now=dt.datetime(2026, 11, 26, 22, 35, tzinfo=clock.HKT))
        self.assertEqual(r["status"], "skipped")
        r = open_monitor.run(dry_run=True, now=dt.datetime(2026, 9, 28, 20, 0, tzinfo=clock.HKT))  # 08:00 ET pre-open
        self.assertEqual(r["status"], "skipped")


class T11_Idempotency(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pf_path = os.path.join(self.tmp, "portfolio.json")
        with open(self.pf_path, "w") as f:
            json.dump(base_pf(), f)
        self.patches = [
            mock.patch.object(ledger, "PORTFOLIO_PATH", self.pf_path),
            mock.patch.object(guard, "PATH", os.path.join(self.tmp, "job_runs.json")),
            mock.patch.object(guard, "STATE_DIR", self.tmp),
            mock.patch.object(archive, "REPORTS", os.path.join(self.tmp, "reports")),
            mock.patch.object(archive, "INDEX", os.path.join(self.tmp, "reports_index.json")),
            mock.patch.object(archive, "PNL", os.path.join(self.tmp, "pnl_history.json")),
            mock.patch.object(archive, "SCAN", os.path.join(self.tmp, "scan.json")),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _fake_quote(self, prices):
        def q(t):
            return {"ticker": t, "price": prices.get(t, 100.0), "prev_close": prices.get(t, 100.0), "change_pct": 0.0,
                    "source": "fake", "ok": True}
        return q

    def test_T11_open_sends_once_and_executes_tp_once(self):
        from px.jobs import open_monitor, common
        sent = []
        now = dt.datetime(2026, 9, 29, 21, 36, tzinfo=clock.HKT)  # Tue 09:36 ET
        fake = self._fake_quote({"SOUN": 6.95, "^VIX": 15.0, "SPY": 770, "QQQ": 740, "HKD=X": 7.83})
        with mock.patch("px.marketdata.quote", side_effect=fake), \
             mock.patch("px.telegram.send", side_effect=lambda text, **k: (sent.append(text) or (True, [1]))), \
             mock.patch.object(open_monitor, "write_json"), mock.patch.object(open_monitor, "write_text"):
            r1 = open_monitor.run(now=now)
            r2 = open_monitor.run(now=now)
        self.assertEqual(r1["status"], "ok")
        self.assertEqual(r2["status"], "duplicate")
        self.assertEqual(len(sent), 1)
        pf = ledger.load(self.pf_path)
        sells = [t for t in pf["trade_log"] if t["action"] == "SELL" and t["ticker"] == "SOUN"]
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0]["reason"], "TAKE_PROFIT")
        self.assertIn("紙上已止盈", sent[0])

    def test_hourly_alert_dedup(self):
        from px.jobs import hourly
        sent = []
        fake = self._fake_quote({"SOUN": 5.85, "^VIX": 15.0})
        base = dt.datetime(2026, 9, 29, 22, 30, tzinfo=clock.HKT)
        with mock.patch("px.marketdata.quote", side_effect=fake), \
             mock.patch("px.telegram.send", side_effect=lambda text, **k: (sent.append(text) or (True, [1]))), \
             mock.patch.object(hourly, "write_json"), mock.patch.object(hourly, "_legacy_state"), \
             mock.patch.object(hourly, "_write_quiet"):
            hourly.run(now=base)
            hourly.run(now=base + dt.timedelta(hours=1))
        self.assertEqual(len(sent), 1)  # NEAR_SL alerted once; second run has no new alert
        self.assertIn("距止損", sent[0])


class T16_Secrets(unittest.TestCase):
    def test_T16_no_secret_files_tracked(self):
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        self.assertFalse([f for f in out if f.endswith("_config.json") or f == ".env"])
        grep = subprocess.run(["git", "grep", "-nIE", r"[0-9]{8,10}:[A-Za-z0-9_-]{30,}"], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(grep.stdout.strip(), "")


class TestSecretsPrecedence(unittest.TestCase):
    def test_px_prefix_and_env_file(self):
        import os, tempfile
        from px import config
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("export PX_TEST_SECRET_X=fromfile\n# comment\n")
            fn = f.name
        old = dict(os.environ)
        try:
            os.environ["PX_ENV_FILE"] = fn
            os.environ["TEST_SECRET_X"] = "plain"
            config._dotenv_loaded = False
            self.assertEqual(config.get_secret("TEST_SECRET_X"), "fromfile")
            os.environ["PX_TEST_SECRET_X"] = "explicit"
            self.assertEqual(config.get_secret("TEST_SECRET_X"), "explicit")
        finally:
            os.environ.clear(); os.environ.update(old); os.unlink(fn); config._dotenv_loaded = False


class TestNoLLMAndConfigDriven(unittest.TestCase):
    """Roy requirement: scheduled jobs never depend on an LLM; Telegram target purely from config/env."""
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _py(self):
        for d in ("px",):
            for dp, _, fs in os.walk(os.path.join(self.ROOT, d)):
                for f in fs:
                    if f.endswith(".py"):
                        yield os.path.join(dp, f)
        yield os.path.join(self.ROOT, "run.py")

    def test_no_llm_imports_or_hosts(self):
        pat = re.compile(r"\b(import openai|from openai|import anthropic|from anthropic|api\.x\.ai|xai-oauth|grok-4|api\.openai\.com)")
        bad = [f for f in self._py() if pat.search(open(f, encoding="utf-8").read())]
        self.assertEqual(bad, [])

    def test_no_hardcoded_chat_id_or_token(self):
        tok = re.compile(r"\d{8,10}:[A-Za-z0-9_-]{30,}")
        chat = re.compile(r"chat_id\s*[=:]\s*['\"]?-?\d{6,}")
        bad = [f for f in self._py() if tok.search(open(f, encoding="utf-8").read()) or chat.search(open(f, encoding="utf-8").read())]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
