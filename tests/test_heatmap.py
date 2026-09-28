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
        # HOURLY at the hourly job's minute: 10:06..15:06 + 17:00 final (= 7 runs/day)
        reg = heatmap.slots(dt.date(2026, 9, 28))
        self.assertEqual(reg[0], ("intraday", dt.datetime(2026, 9, 28, 10, 6, tzinfo=ET)))
        self.assertEqual(reg[-2], ("intraday", dt.datetime(2026, 9, 28, 15, 6, tzinfo=ET)))
        self.assertEqual(reg[-1], ("close", dt.datetime(2026, 9, 28, 17, 0, tzinfo=ET)))
        self.assertEqual([s.strftime("%H:%M") for k, s in reg if k == "intraday"],
                         ["10:06", "11:06", "12:06", "13:06", "14:06", "15:06"])
        # half day (day after Thanksgiving 2026-11-27): last intraday 12:06, final still 17:00
        half = heatmap.slots(dt.date(2026, 11, 27))
        self.assertEqual([s.strftime("%H:%M") for k, s in half if k == "intraday"],
                         ["10:06", "11:06", "12:06"])
        self.assertEqual(half[-1][0], "close")
        # Thanksgiving: no slots
        self.assertEqual(heatmap.slots(dt.date(2026, 11, 26)), [])
        # DST: 10:06 ET = 23:06 HKT after the fall-back
        nov = heatmap.slots(dt.date(2026, 11, 2))[0][1].astimezone(HKT)
        self.assertEqual(nov.strftime("%H:%M"), "23:06")  # EST: ET+13
        # aligned with existing hourly slots
        from px import schedule
        hourly = [s.strftime("%H:%M") for s in schedule.expected_slots("hourly", dt.date(2026, 9, 28))]
        self.assertEqual([s.strftime("%H:%M") for k, s in reg if k == "intraday"],
                         [t for t in hourly if t <= "15:06"])

    def test_due_slot_window(self):
        self.assertEqual(heatmap.due_slot(dt.datetime(2026, 9, 28, 22, 7, tzinfo=HKT))[0], "intraday")  # 10:07 ET
        self.assertIsNone(heatmap.due_slot(dt.datetime(2026, 9, 28, 21, 0, tzinfo=HKT)))  # pre-first
        self.assertIsNone(heatmap.due_slot(dt.datetime(2026, 9, 28, 22, 0, tzinfo=HKT)))  # between open and first
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

    def test_finnhub_cooldown_defers_intraday_without_attempt(self):
        with mock.patch("px.apistate.in_cooldown", return_value=True):
            res = heatmap.run(now=dt.datetime(2026, 9, 28, 22, 7, tzinfo=HKT), force=False)
        self.assertEqual(res["status"], "deferred")
        self.assertIn("Finnhub", res["reason"])
        sp = os.path.join(self.tmp, "heatmap_state.json")
        self.assertTrue(not os.path.exists(sp) or not (json.load(open(sp)).get("slots") or {}))

    def test_core_slot_guard_defers_near_push(self):
        # 10:04 ET = 2 min before the 10:06 heatmap AND inside the hourly open's window — wait for the push
        with mock.patch.object(heatmap, "core_slot_soon", return_value="hourly 10:06"):
            # Force a due slot by mocking due_slot so the guard is what we exercise
            due = ("intraday", dt.datetime(2026, 9, 28, 10, 6, tzinfo=ET))
            with mock.patch.object(heatmap, "due_slot", return_value=due):
                res = heatmap.run(now=dt.datetime(2026, 9, 28, 22, 4, tzinfo=HKT), force=False)
        self.assertEqual(res["status"], "deferred")
        self.assertIn("push slot", res["reason"])


class TestIntradayFinnhub(unittest.TestCase):
    def test_collect_intraday_rejects_stale_and_jump_and_paces(self):
        now = dt.datetime(2026, 9, 28, 23, 0, tzinfo=HKT)  # 11:00 ET
        now_ts = now.timestamp()
        sleeps = []
        def quote(sym, max_age_s=None):
            if sym == "AAA":  # fresh +5 %
                return {"price": 10.5, "prev_close": 10.0, "change_pct": 5.0, "t": now_ts - 60}, None
            if sym == "BBB":  # stale (>15 min)
                return None, "stale quote (20 min old)"
            if sym == "CCC":  # >50 % jump
                return {"price": 20.0, "prev_close": 10.0, "change_pct": 100.0, "t": now_ts - 30}, None
            if sym == "DDD":  # Finnhub 429 -> abort
                return None, "HTTP 429 rate limited"
            return None, "empty"
        with mock.patch("px.finnhub.quote", side_effect=quote), \
             mock.patch("px.apistate.in_cooldown", return_value=False), \
             mock.patch("px.apistate.count"):
            pacer = heatmap._Pacer(sleep=lambda s: sleeps.append(s), now_fn=lambda: now_ts + len(sleeps) * 0.01)
            pacer.gap = 1.5  # pretend 40/min
            out, meta = heatmap.collect_intraday(["AAA", "BBB", "CCC", "DDD"], now, pacer)
        self.assertEqual(list(out), ["AAA"])
        self.assertAlmostEqual(out["AAA"][1], 5.0)
        self.assertIn("BBB", meta["stale_or_failed"])
        self.assertIn("CCC", meta["rejected_jump"])
        self.assertIn("429", meta["aborted"] or "")
        self.assertGreaterEqual(meta["calls"], 3)  # stopped at DDD
        self.assertTrue(any(x >= 1.4 for x in sleeps))  # paced

    def test_vix_from_cache_fresh_and_stale(self):
        now = dt.datetime(2026, 9, 28, 23, 0, tzinfo=HKT)
        ref = dt.date(2026, 9, 28)
        good = {"price": 16.0, "change_pct": 3.0, "session_date": "2026-09-28",
                "at": (now - dt.timedelta(minutes=10)).isoformat()}
        with mock.patch("px.marketdata.last_vix", return_value=good):
            self.assertEqual(heatmap.vix_from_cache(ref, "intraday", now), (16.0, 3.0))
        stale = dict(good, at=(now - dt.timedelta(minutes=90)).isoformat())
        with mock.patch("px.marketdata.last_vix", return_value=stale):
            self.assertEqual(heatmap.vix_from_cache(ref, "intraday", now), (None, None))
        # close phase: an intraday VIX (before the close) must not be used
        early = dict(good, at=dt.datetime(2026, 9, 28, 14, 0, tzinfo=ET).isoformat())
        with mock.patch("px.marketdata.last_vix", return_value=early):
            self.assertEqual(heatmap.vix_from_cache(ref, "close", now), (None, None))
        after = dict(good, at=dt.datetime(2026, 9, 28, 17, 5, tzinfo=ET).isoformat())
        with mock.patch("px.marketdata.last_vix", return_value=after):
            self.assertEqual(heatmap.vix_from_cache(ref, "close",
                                                    dt.datetime(2026, 9, 29, 5, 10, tzinfo=HKT)), (16.0, 3.0))


class TestCloseReuse(unittest.TestCase):
    def test_collect_close_reuses_cache_and_batches_only_missing(self):
        d0, d1 = dt.date(2026, 9, 25), dt.date(2026, 9, 26)
        series = {t: _series([(d0, 10.0), (d1, 11.0)]) for t in ("AAA", "BBB", "SPY", "QQQ")}
        # seed process cache for AAA/BBB/SPY/QQQ; XLK missing -> one small batch
        class FakeDF(dict):
            pass
        # Use pandas DataFrames in the marketdata cache
        import pandas as pd
        from px import marketdata
        for t, s in series.items():
            df = pd.DataFrame({"Close": pd.Series(s.values, index=pd.to_datetime(s.index))})
            marketdata._hist_cache[t] = df
        downloaded = []
        def fake_batch(syms):
            downloaded.extend(syms)
            out = {}
            for t in syms:
                out[t] = _series([(d0, 50.0), (d1, 51.0)])
            return out, None
        with mock.patch.object(heatmap, "_batch_download", side_effect=fake_batch), \
             mock.patch("px.finnhub.quote", return_value=(None, "unused")):
            changes, ref, meta = heatmap.collect_close(["AAA", "BBB", "SPY", "QQQ", "XLK"],
                                                       now=dt.datetime(2026, 9, 27, 5, 0, tzinfo=HKT))
        self.assertEqual(ref, d1)
        self.assertAlmostEqual(changes["AAA"][1], 10.0)
        self.assertEqual(downloaded, ["XLK"])  # only the missing ETF
        self.assertEqual(meta["reused"], 4)
        self.assertEqual(meta["yahoo_batch"], 1)
        marketdata._hist_cache.clear()


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
