"""Real (Futu) positions: pos CLI / file logic + report rendering with 0 and >=1 real positions (offline)."""
import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401  (offline + temp state dir)

from px import clock, messages, realpos, telegram  # noqa: E402

NOW = dt.datetime(2026, 9, 28, 14, 0, tzinfo=clock.HKT)


def book_with_ionq():
    b = realpos.empty_book()
    realpos.add_position(b, "IONQ", 3, 44.5, 37, 50, date="2026-09-23", fee=2, now=NOW)
    return b


class TestRealPosFile(unittest.TestCase):
    def test_committed_file_has_no_positions(self):
        with open(os.path.join(ROOT, "data", "futu_positions.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("schema"), realpos.SCHEMA)
        self.assertEqual(data.get("positions"), [])
        self.assertTrue(os.path.exists(os.path.join(ROOT, data["archived"]["file"])), "archived July record must exist")

    def test_add_valid_and_default_fee(self):
        b = realpos.empty_book()
        pos, warns = realpos.add_position(b, "ionq", "3", "44.5", "37", "50", date="2026-09-23", now=NOW)
        self.assertEqual(pos["ticker"], "IONQ")
        self.assertEqual(pos["shares"], 3)
        self.assertEqual(pos["id"], "R001")
        self.assertAlmostEqual(pos["entry_fee_usd"], 2.0, delta=0.05)  # Futu fixed plan ~US$2 per order
        self.assertEqual(b["real_start_date"], "2026-09-23")
        self.assertEqual(warns, [])

    def test_add_validation(self):
        b = book_with_ionq()
        bad = [
            dict(symbol="XX$", qty=1, price=10, sl=9, tp=12),
            dict(symbol="AAA", qty=0, price=10, sl=9, tp=12),
            dict(symbol="AAA", qty=-1, price=10, sl=9, tp=12),
            dict(symbol="AAA", qty="abc", price=10, sl=9, tp=12),
            dict(symbol="AAA", qty=1, price=10, sl=10, tp=12),
            dict(symbol="AAA", qty=1, price=10, sl=9, tp=10),
            dict(symbol="AAA", qty=1, price=10, sl=9, tp=12, date="2030-01-01"),
            dict(symbol="AAA", qty=1, price=10, sl=9, tp=12, date="28/09/2026"),
            dict(symbol="AAA", qty=1, price=10, sl=9, tp=12, fee=-1),
            dict(symbol="AAA", qty=1.123456, price=10, sl=9, tp=12),
            dict(symbol="IONQ", qty=1, price=45, sl=37, tp=50),  # duplicate without --allow-add
        ]
        for kw in bad:
            with self.subTest(kw=kw), self.assertRaises(realpos.RealPosError):
                realpos.add_position(b, now=NOW, **kw)
        self.assertEqual(len(b["positions"]), 1)

    def test_rule_warnings(self):
        b = realpos.empty_book()
        _, warns = realpos.add_position(b, "NVDA", 2, 180, 165, 200, fee=2, now=NOW)
        self.assertTrue(any("25%" in w for w in warns))

    def test_allow_add_merges(self):
        b = book_with_ionq()
        pos, _ = realpos.add_position(b, "IONQ", 1, 48.5, 40, 55, fee=2, allow_add=True, now=NOW)
        self.assertEqual(pos["shares"], 4)
        self.assertAlmostEqual(pos["entry_price"], 45.5)
        self.assertAlmostEqual(pos["entry_fee_usd"], 4.0)
        self.assertEqual(len(b["positions"]), 1)

    def test_close_full_keeps_realized_history(self):
        b = book_with_ionq()
        tr, _ = realpos.close_position(b, "ionq", 48, fee=2, date="2026-09-28", now=NOW)
        self.assertEqual(b["positions"], [])
        self.assertEqual(len(b["closed_trades"]), 1)
        self.assertAlmostEqual(tr["net_pnl_usd"], (48 - 44.5) * 3 - 4)
        self.assertAlmostEqual(tr["fees_usd"], 4.0)
        self.assertEqual(tr["days_held"], 5)
        self.assertEqual(tr["exit_reason"], "MANUAL")
        self.assertEqual(tr["position_id"], "R001")
        ev = realpos.evaluate(b, {}, 7.8, NOW.date())
        self.assertEqual(ev["n_closed"], 1)
        self.assertEqual(ev["win_rate_pct"], 100.0)
        self.assertAlmostEqual(ev["equity_usd"], 1280 + 6.5)

    def test_close_partial_and_reasons(self):
        b = book_with_ionq()
        tr, _ = realpos.close_position(b, "IONQ", 36, 1, fee=2, now=NOW)
        self.assertEqual(tr["exit_reason"], "STOP_LOSS")
        self.assertAlmostEqual(tr["entry_fee_usd"], 0.67, places=2)
        self.assertEqual(b["positions"][0]["shares"], 2)
        self.assertAlmostEqual(b["positions"][0]["entry_fee_usd"], 1.33, places=2)
        tr2, _ = realpos.close_position(b, "IONQ", 51, fee=2, now=NOW)
        self.assertEqual(tr2["exit_reason"], "TAKE_PROFIT")
        self.assertEqual(tr2["shares"], 2)
        self.assertEqual(b["positions"], [])
        self.assertEqual([t["id"] for t in b["closed_trades"]], ["RC001", "RC002"])

    def test_close_validation(self):
        b = book_with_ionq()
        for args in [("TSLA", 10), ("IONQ", 0), ("IONQ", 48, 5), ("IONQ", 48, None, "2026-09-01")]:
            with self.subTest(args=args), self.assertRaises(realpos.RealPosError):
                realpos.close_position(b, *args, now=NOW)
        self.assertEqual(len(b["positions"]), 1)

    def test_set_levels(self):
        b = book_with_ionq()
        realpos.set_levels(b, "IONQ", sl=45, now=NOW)
        self.assertEqual(b["positions"][0]["stop_loss_price"], 45.0)
        with self.assertRaises(realpos.RealPosError):
            realpos.set_levels(b, "IONQ", sl=60, now=NOW)

    def test_save_load_roundtrip_and_legacy(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "fp.json")
            b = book_with_ionq()
            realpos.save(b, p)
            self.assertEqual(realpos.load(p)["positions"][0]["ticker"], "IONQ")
            self.assertEqual([f for f in os.listdir(d) if f.endswith(".tmp")], [])
            with open(p, "w", encoding="utf-8") as f:  # old July schema -> treated as NO real positions
                json.dump({"platform": "Futu", "positions": [{"ticker": "NVDA", "shares": 1, "entry_price": 194}]}, f)
            old = realpos.load(p)
            self.assertEqual(old["positions"], [])
            self.assertTrue(old.get("legacy_unmigrated"))
            self.assertEqual(realpos.load(os.path.join(d, "missing.json"))["positions"], [])

    def test_mark_prices(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "fp.json")
            realpos.save(book_with_ionq(), p)
            self.assertTrue(realpos.mark_prices({"IONQ": 46.2}, NOW, p))
            self.assertEqual(realpos.load(p)["positions"][0]["last_price"], 46.2)
            realpos.save(realpos.empty_book(), p)
            self.assertFalse(realpos.mark_prices({"IONQ": 46.2}, NOW, p))


class TestPosCLI(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            import run
            rc = run.main(["pos", *args])
        return rc, out.getvalue(), err.getvalue()

    def test_cli_flow(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "futu_positions.json")
            realpos.save(realpos.empty_book(), p)
            with mock.patch.dict(os.environ, {"PX_REAL_POS_PATH": p}):
                rc, out, _ = self.run_cli("add", "IONQ", "3", "44.5", "--sl", "37", "--tp", "50", "--date", "2026-09-23", "--dry-run")
                self.assertEqual(rc, 0)
                self.assertEqual(realpos.load(p)["positions"], [])  # dry-run writes nothing
                rc, out, _ = self.run_cli("add", "IONQ", "3", "44.5", "--sl", "37", "--tp", "50", "--date", "2026-09-23", "--fee", "2")
                self.assertEqual(rc, 0)
                self.assertIn("IONQ", out)
                self.assertEqual(realpos.load(p)["positions"][0]["shares"], 3)
                rc, out, err = self.run_cli("add", "IONQ", "1", "44.5", "--sl", "50", "--tp", "60")
                self.assertEqual(rc, 1)
                self.assertIn("❌", err)
                rc, out, _ = self.run_cli("list")
                self.assertEqual(rc, 0)
                self.assertIn("IONQ", out)
                rc, out, _ = self.run_cli("close", "IONQ", "48", "--fee", "2")
                self.assertEqual(rc, 0)
                bk = realpos.load(p)
                self.assertEqual(bk["positions"], [])
                self.assertAlmostEqual(bk["closed_trades"][0]["net_pnl_usd"], 6.5)
                rc, _, _ = self.run_cli("close", "IONQ", "48")
                self.assertEqual(rc, 1)
                # --push is refused for a non-repo file (and must never touch git in tests)
                with mock.patch("px.gitops.pull") as gp, mock.patch("px.gitops.commit_paths_and_push") as gc:
                    rc, _, err = self.run_cli("add", "TSLA", "1", "300", "--sl", "270", "--tp", "360", "--push")
                self.assertEqual(rc, 1)
                gp.assert_not_called()
                gc.assert_not_called()
                self.assertEqual(realpos.load(p)["positions"], [])


class TestRealRendering(unittest.TestCase):
    def ev(self, px, chg=None, book=None):
        b = book or book_with_ionq()
        q = {"IONQ": {"ok": True, "price": px, "change_pct": chg, "source": "test"}}
        return realpos.evaluate(b, q, 7.8, NOW.date())

    def test_zero_positions(self):
        ev = realpos.evaluate(realpos.empty_book(), {}, 7.8, NOW.date())
        L = messages.real_section(ev)
        self.assertEqual(L, [messages.REAL_EMPTY])
        self.assertIn("真倉：暫時冇持倉（買入後叫 Hermes 記錄）", L[0])
        self.assertEqual(messages.real_alerts(ev)[0], [])

    def test_one_position_detail(self):
        ev = self.ev(46.2)
        r = ev["rows"][0]
        self.assertAlmostEqual(r["pnl_usd"], (46.2 - 44.5) * 3 - 2)
        self.assertAlmostEqual(r["pnl_hkd"], round(((46.2 - 44.5) * 3 - 2) * 7.8, 2))
        self.assertEqual(r["days_held"], 5)
        txt = "\n".join(messages.real_section(ev))
        for s in ("IONQ", "3股", "$46.20", "成本 $44.50", "+US$3.10", "HK$24", "止蝕 $37.00", "止賺 $50.00", "持 5 日", "1/3"):
            self.assertIn(s, txt)

    def test_alerts_sl_tp_near_drop_and_dedupe(self):
        ev = self.ev(36.5, chg=-6.0)
        self.assertEqual(ev["rows"][0]["status"], "SL_HIT")
        al, seen = messages.real_alerts(ev)
        self.assertTrue(any("真倉 IONQ 跌穿止蝕" in a and "富途" in a for a in al))
        self.assertTrue(any("急跌" in a for a in al))
        al2, _ = messages.real_alerts(ev, seen)
        self.assertEqual(al2, [])
        self.assertEqual(self.ev(50.5)["rows"][0]["status"], "TP_HIT")
        self.assertTrue(any("到止賺" in a for a in messages.real_alerts(self.ev(50.5))[0]))
        near = self.ev(37.5)
        self.assertEqual(near["rows"][0]["status"], "NEAR_SL")
        self.assertTrue(any("距止蝕" in a for a in messages.real_alerts(near)[0]))

    def test_paper_brief_and_suggestions(self):
        L = messages.paper_brief({"total_return_pct": 0.92, "cash_pct": 88.3}, 1, 3, 1.4, 5.0, ["HOLD SOUN"])
        txt = "\n".join(L)
        for s in ("紙上倉（對照組）", "+0.92%", "SPY +1.40%", "QQQ +5.00%", "1/3", "HOLD SOUN"):
            self.assertIn(s, txt)
        scan = {"top": [{"ticker": "IONQ", "entry_zone": [43.0, 45.0], "stop": 38.0, "target": 58.0, "rr": 2.5, "live_price": 44.0}]}
        ev0 = realpos.evaluate(realpos.empty_book(), {}, 7.8, NOW.date())
        sug = "\n".join(messages.real_suggestion_lines(ev0, scan))
        self.assertIn("真倉建議", sug)
        sh, _, _ = realpos.suggest_shares(ev0, 44.0, 38.0)
        self.assertGreater(sh, 0)
        self.assertLessEqual(sh * 44.0, 0.25 * 1280 + 1e-6)
        self.assertLessEqual((44.0 - 38.0) * sh, 0.02 * 1280 + 1e-6)
        held = "\n".join(messages.real_suggestion_lines(self.ev(45.0), scan))
        self.assertNotIn("• IONQ", held)  # never suggest adding to an existing real holding
        full = realpos.empty_book()
        for t, px in (("AAA", 10), ("BBB", 10), ("CCC", 10)):
            realpos.add_position(full, t, 1, px, px * 0.9, px * 1.2, fee=2, now=NOW)
        self.assertEqual(realpos.suggest_shares(realpos.evaluate(full, {}, 7.8, NOW.date()), 44.0, 38.0)[0], 0)


class TestHourlyRendering(unittest.TestCase):
    """Run the real hourly job (dry-run, all network mocked) with 0 and 1 real positions."""

    def _run(self, book, quotes):
        from px.jobs import hourly
        acct = {"equity_usd": 1291.81, "cash_usd": 1140.56, "cash_pct": 88.3, "total_return_pct": 0.92, "fx_usdhkd": 7.8}
        sent = []
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "fp.json")
            realpos.save(book, p)
            with mock.patch.dict(os.environ, {"PX_REAL_POS_PATH": p}), \
                    mock.patch.object(hourly, "refresh_positions", return_value=([], [], acct)), \
                    mock.patch.object(hourly.marketdata, "vix", return_value=15.0), \
                    mock.patch.object(hourly, "paper_bench", return_value=(1.4, 5.0)), \
                    mock.patch.object(hourly.guard, "job_state", return_value={"last_prices": {"X": 1}}), \
                    mock.patch.object(hourly.guard, "was_sent", return_value=False), \
                    mock.patch.object(hourly.ledger, "load", return_value={"positions": []}), \
                    mock.patch.object(realpos, "quotes_for", return_value=quotes), \
                    mock.patch.object(hourly.telegram, "send", side_effect=lambda m, **k: (sent.append(m), (True, ["DRY"]))[1]), \
                    redirect_stdout(io.StringIO()):
                out = hourly.run(dry_run=True, force=True, now=NOW.replace(hour=22, minute=6))
        return out, sent

    def test_hourly_zero_real(self):
        out, sent = self._run(realpos.empty_book(), {})
        self.assertEqual(out["status"], "ok")
        self.assertIn("真倉：暫時冇持倉", sent[0])
        self.assertIn("紙上倉（對照組）", sent[0])
        self.assertLess(sent[0].index("真倉"), sent[0].index("紙上倉"))

    def test_hourly_real_sl_alert(self):
        out, sent = self._run(book_with_ionq(), {"IONQ": {"ok": True, "price": 36.5, "change_pct": -6.2, "source": "t"}})
        msg = sent[0]
        self.assertTrue(msg.startswith("<b>🚨 真倉警報</b>"))
        self.assertIn("真倉 IONQ 跌穿止蝕", msg)
        self.assertIn("系統只提醒", msg)
        self.assertLess(msg.index("IONQ"), msg.index("紙上倉"))
        self.assertTrue(out["real_alerts"])
        self.assertLessEqual(max(len(x) for x in telegram.split_message(msg)), 4096)


if __name__ == "__main__":
    unittest.main()
