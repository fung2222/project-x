"""Stock heatmap (JSON shape, colours, schedule, no Telegram). Offline."""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401

import pandas as pd  # noqa: E402
from px import clock, heatmap, telegram  # noqa: E402

ET, HKT = clock.ET, clock.HKT


def _series(pairs):
    """pairs: [(date, close), ...] -> Series indexed by date."""
    idx, vals = zip(*pairs)
    return pd.Series(vals, index=list(idx))


class TestColour(unittest.TestCase):
    def test_red_up_green_down_hk_convention(self):
        up_bg, _ = heatmap.colour(3.0)
        dn_bg, _ = heatmap.colour(-3.0)
        # red family (R > G) for up; green family (G > R) for down
        self.assertGreater(int(up_bg[1:3], 16), int(up_bg[3:5], 16))
        self.assertGreater(int(dn_bg[3:5], 16), int(dn_bg[1:3], 16))
        self.assertEqual(heatmap.colour(None)[0], heatmap.MISSING)
        self.assertEqual(heatmap.colour(0.05)[0], heatmap.FLAT)  # |chg| < 0.1 %
        deep_up, _ = heatmap.colour(5.0)
        light_up, _ = heatmap.colour(1.0)
        self.assertNotEqual(deep_up, light_up)

    def test_box_size_cube_root_floor(self):
        # 1000x market cap -> 10x box
        a = heatmap.box_size(1e9)
        b = heatmap.box_size(1e12)
        self.assertAlmostEqual(b / a, 10.0, places=5)
        self.assertAlmostEqual(heatmap.box_size(1e8), heatmap.box_size(1e9))  # floor US$1B


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "heatmap.json")
        self.ps = [
            mock.patch.object(heatmap, "STATE_DIR", self.tmp),
            mock.patch.object(heatmap, "OUT_PATH", self.out),
            mock.patch.object(heatmap, "network_off", return_value=True),
        ]
        for p in self.ps:
            p.start()

    def tearDown(self):
        for p in self.ps:
            p.stop()

    def _holdings(self):
        return (["AAA", "BBB", "CCC"], {"QUANTUM": ["AAA"], "SPACE": ["BBB"]}, ["AAA"], [])

    def test_json_shape_and_missing(self):
        d0, d1 = dt.date(2026, 9, 25), dt.date(2026, 9, 26)
        series = {
            "AAA": _series([(d0, 10.0), (d1, 11.0)]),           # +10 %
            "BBB": _series([(d0, 20.0), (d1, 19.0)]),           # -5 %
            # CCC missing entirely
            "SPY": _series([(d0, 100.0), (d1, 101.0)]),
            "QQQ": _series([(d0, 200.0), (d1, 198.0)]),
            "^VIX": _series([(d0, 15.0), (d1, 16.0)]),
            "XLK": _series([(d0, 50.0), (d1, 51.0)]),
        }
        for t, _ in heatmap.SECTOR_ETFS:
            series.setdefault(t, _series([(d0, 10.0), (d1, 10.0)]))
        caps = {"AAA": 5e9, "BBB": 2e9}  # CCC no_mcap
        now = dt.datetime(2026, 9, 27, 5, 0, tzinfo=HKT)  # Saturday HKT, after Fri close
        data = heatmap.build(now=now, series=series, caps=caps, holdings=self._holdings())
        self.assertEqual(data["schema"], "heatmap_v1")
        self.assertEqual(data["data_date"], "2026-09-26")
        self.assertEqual(data["phase"], "close")
        self.assertIn("generated_hkt", data)
        self.assertEqual(data["colour"]["up"], "red")
        self.assertEqual(data["colour"]["down"], "green")
        self.assertEqual(data["colour"]["legend"], "紅＝升　綠＝跌　格越大＝公司越大")
        self.assertEqual(len(data["sectors"]), 12)
        self.assertEqual({s["t"] for s in data["sectors"]}, {t for t, _ in heatmap.SECTOR_ETFS})
        self.assertTrue(all("zh" in s for s in data["sectors"]))
        by = {r["t"]: r for r in data["stocks"]}
        self.assertEqual(by["AAA"]["g"], "量子電腦")
        self.assertTrue(by["AAA"]["paper"])
        self.assertFalse(by["AAA"]["real"])
        self.assertAlmostEqual(by["AAA"]["chg_pct"], 10.0, places=2)
        self.assertEqual(by["CCC"]["chg_pct"], None)
        self.assertEqual(by["CCC"]["label"], "數據暫缺")
        self.assertEqual(by["CCC"]["color"], heatmap.MISSING)
        self.assertIn("CCC", data["missing"])
        self.assertIn("CCC", data["no_mcap"])
        self.assertEqual(data["counts"]["up"], 1)
        self.assertEqual(data["counts"]["down"], 1)
        self.assertEqual(data["counts"]["missing"], 1)
        self.assertEqual(data["index"]["SPY"]["chg_pct"], 1.0)
        # stale ticker (last bar before ref) -> missing
        series["BBB"] = _series([(d0, 20.0)])  # only one bar, or older
        series["BBB"] = _series([(dt.date(2026, 9, 24), 20.0), (d0, 19.0)])  # ends on 9-25, not ref 9-26
        data2 = heatmap.build(now=now, series=series, caps=caps, holdings=self._holdings())
        self.assertIn("BBB", data2["missing"])

    def test_group_merge_matches_prototype(self):
        self.assertEqual(heatmap.group_of("SOUN", {"AI_SOFTWARE": ["SOUN"], "DATA_AI": ["PLTR"]}), "AI 軟件")
        self.assertEqual(heatmap.group_of("PLTR", {"AI_SOFTWARE": ["SOUN"], "DATA_AI": ["PLTR"]}), "AI 軟件")
        self.assertEqual(heatmap.group_of("ZZZ", {}), "其他")


class TestSchedule(unittest.TestCase):
    def test_slots_regular_and_half_day_and_holiday(self):
        # regular: 10:00..15:30 every 30 + 17:00 final
        reg = heatmap.slots(dt.date(2026, 9, 28))
        self.assertEqual(reg[0], ("intraday", dt.datetime(2026, 9, 28, 10, 0, tzinfo=ET)))
        self.assertEqual(reg[-2], ("intraday", dt.datetime(2026, 9, 28, 15, 30, tzinfo=ET)))
        self.assertEqual(reg[-1], ("close", dt.datetime(2026, 9, 28, 17, 0, tzinfo=ET)))
        self.assertEqual(len([k for k, _ in reg if k == "intraday"]), 12)  # 10:00..15:30
        # half day (day after Thanksgiving 2026-11-27): last intraday 12:30, final still 17:00
        half = heatmap.slots(dt.date(2026, 11, 27))
        self.assertEqual(half[-2], ("intraday", dt.datetime(2026, 11, 27, 12, 30, tzinfo=ET)))
        self.assertEqual(half[-1][0], "close")
        self.assertTrue(all(s.time() <= dt.time(12, 30) or k == "close" for k, s in half))
        # Thanksgiving: no slots
        self.assertEqual(heatmap.slots(dt.date(2026, 11, 26)), [])
        # DST: 10:00 ET = 22:00 HKT in November
        nov = heatmap.slots(dt.date(2026, 11, 2))[0][1].astimezone(HKT)
        self.assertEqual(nov.strftime("%H:%M"), "23:00")  # EST: ET+13

    def test_due_slot_window(self):
        self.assertEqual(heatmap.due_slot(dt.datetime(2026, 9, 28, 22, 5, tzinfo=HKT))[0], "intraday")  # 10:05 ET
        self.assertIsNone(heatmap.due_slot(dt.datetime(2026, 9, 28, 21, 0, tzinfo=HKT)))  # pre-first
        self.assertEqual(heatmap.due_slot(dt.datetime(2026, 9, 29, 5, 10, tzinfo=HKT))[0], "close")  # 17:10 ET


class TestRunNoPush(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "heatmap.json")
        self.ps = [
            mock.patch.object(heatmap, "STATE_DIR", self.tmp),
            mock.patch.object(heatmap, "OUT_PATH", self.out),
            mock.patch.object(heatmap, "network_off", return_value=True),
            mock.patch.object(heatmap, "build", return_value={
                "schema": "heatmap_v1", "data_date": "2026-09-26", "phase": "close",
                "counts": {"total": 2, "up": 1, "down": 1, "flat": 0, "missing": 0},
                "sources": {}, "generated_at": "x", "generated_hkt": "x",
            }),
        ]
        for p in self.ps:
            p.start()

    def tearDown(self):
        for p in self.ps:
            p.stop()

    def test_run_never_calls_telegram(self):
        sends = []
        with mock.patch.object(telegram, "send", side_effect=lambda *a, **k: sends.append(1) or (True, [])), \
             mock.patch.object(telegram, "send_photo", side_effect=lambda *a, **k: sends.append(1) or (True, [])):
            # force a build outside any window
            res = heatmap.run(now=dt.datetime(2026, 9, 28, 12, 0, tzinfo=HKT), force=True, dry_run=False)
        self.assertEqual(res["status"], "ok")
        self.assertTrue(os.path.exists(self.out))
        self.assertEqual(sends, [])

    def test_yahoo_cooldown_defers_without_attempt(self):
        with mock.patch("px.marketdata.yahoo_blocked", return_value=True):
            res = heatmap.run(now=dt.datetime(2026, 9, 28, 22, 5, tzinfo=HKT), force=False)
        self.assertEqual(res["status"], "deferred")
        # deferred must not write a "running" attempt
        sp = os.path.join(self.tmp, "heatmap_state.json")
        self.assertTrue(not os.path.exists(sp) or not (json.load(open(sp)).get("slots") or {}))


class TestCloseLine(unittest.TestCase):
    def test_close_line_only_when_heatmap_matches_session(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "heatmap.json")
            self.assertIsNone(heatmap.close_link("2026-09-28", p=p))  # no file -> no line
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"schema": "heatmap_v1", "data_date": "2026-09-28"}, f)
            line = heatmap.close_link("2026-09-28", "https://fung2222.github.io/project-x/", p=p)
            self.assertEqual(line, '🗺 今日板塊熱力圖：<a href="https://fung2222.github.io/project-x/heatmap.html">'
                                   'https://fung2222.github.io/project-x/heatmap.html</a>')
            self.assertIsNone(heatmap.close_link("2026-09-25", p=p))  # stale heatmap -> no line

    def test_heatmap_module_never_imports_telegram(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "px", "heatmap.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("import telegram", src)
        self.assertNotIn("telegram.", src)


if __name__ == "__main__":
    unittest.main()
