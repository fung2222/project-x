"""2026-09-28 changes: API hardening (Finnhub 429 cooldown, earnings weekly windows + cache, Yahoo rate-limit stop,
running-marker attempts, deferred reruns), UNKNOWN regime, hourly slot de-dup, realwatch 5-minute watch, move
reasons, lessons rotation, plain message length. All offline (HTTP mocked)."""
import datetime as dt
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401

from px import apistate, clock, earnings, finnhub, guard, ledger, lessons, marketdata, plain, reasons, realpos, schedule  # noqa: E402
from px import messages, telegram  # noqa: E402
from px.jobs import realwatch  # noqa: E402

HKT = clock.HKT
OPEN_NOW = dt.datetime(2026, 9, 29, 22, 36, tzinfo=HKT)  # Tue 10:36 ET, market open (hourly slot 10:06)


class _TmpState(unittest.TestCase):
    """Every stateful module points at a fresh temp dir."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._p = [mock.patch.object(guard, "PATH", os.path.join(self.tmp, "job_runs.json")),
                   mock.patch.object(guard, "STATE_DIR", self.tmp),
                   mock.patch.object(apistate, "STATE_DIR", self.tmp),
                   mock.patch.object(earnings, "STATE_DIR", self.tmp),
                   mock.patch.object(realwatch, "STATE_DIR", self.tmp),
                   mock.patch.object(lessons, "STATE_DIR", self.tmp),
                   mock.patch.object(schedule, "LEDGER", os.path.join(self.tmp, "run_ledger.json")),
                   mock.patch.object(schedule, "STATE_DIR", self.tmp)]
        for p in self._p:
            p.start()
        marketdata._hist_cache.clear()
        marketdata._live_cache.clear()
        marketdata._state["yahoo_limited"] = False

    def tearDown(self):
        for p in self._p:
            p.stop()
        marketdata._state["yahoo_limited"] = False


class _Resp:
    def __init__(self, code=200, data=None, headers=None):
        self.status_code, self._d, self.headers = code, data, headers or {}

    def json(self):
        return self._d


# ---------------------------------------------------------------- 1B Finnhub 429 cooldown
class TestFinnhub(_TmpState):
    def _env(self):
        return [mock.patch.object(finnhub, "network_off", return_value=False),
                mock.patch.object(finnhub, "get_secret", return_value="k")]

    def test_429_sets_cooldown_from_reset_header_and_skips_next_calls(self):
        reset = time.time() + 40
        with self._env()[0], self._env()[1], redirect_stdout(io.StringIO()), \
                mock.patch.object(finnhub.requests, "get", return_value=_Resp(429, {}, {"X-Ratelimit-Reset": str(reset)})) as g:
            d, err = finnhub.get("quote", {"symbol": "IONQ"})
            self.assertIsNone(d)
            self.assertIn("429", err)
            self.assertTrue(apistate.in_cooldown("finnhub"))
            self.assertAlmostEqual(apistate.cooldown_until("finnhub"), reset, delta=1)
            d2, err2 = finnhub.get("quote", {"symbol": "IONQ"})
            self.assertIsNone(d2)
            self.assertIn("cooldown", err2)
            self.assertEqual(g.call_count, 1)  # no HTTP during cooldown

    def test_errors_are_explicit_and_counted(self):
        with self._env()[0], self._env()[1], redirect_stdout(io.StringIO()) as out, \
                mock.patch.object(finnhub.requests, "get", return_value=_Resp(500, {})):
            d, err = finnhub.get("quote", {"symbol": "IONQ"})
        self.assertIsNone(d)
        self.assertEqual(err, "HTTP 500")
        self.assertIn("HTTP 500", out.getvalue())
        self.assertEqual(apistate.used_today("finnhub"), 1)

    def test_stale_quote_rejected(self):
        old = time.time() - 3600
        with self._env()[0], self._env()[1], \
                mock.patch.object(finnhub.requests, "get", return_value=_Resp(200, {"c": 40, "pc": 41, "dp": -2.4, "t": old})):
            q, err = finnhub.quote("IONQ", max_age_s=15 * 60)
        self.assertIsNone(q)
        self.assertIn("stale", err)


# ---------------------------------------------------------------- 1A earnings
class TestEarnings(_TmpState):
    TODAY = dt.date(2026, 9, 28)

    def _run(self, query, yf=None, tickers=("AAA", "BBB", "CCC")):
        with mock.patch.object(earnings, "network_off", return_value=False), \
                mock.patch.object(earnings, "_query", side_effect=query) as q, \
                mock.patch.object(earnings, "_yf_date", side_effect=yf or (lambda t, d, h: (None, False))) as y, \
                mock.patch.object(marketdata, "yahoo_blocked", return_value=False), redirect_stdout(io.StringIO()):
            return earnings.lookup(list(tickers), self.TODAY), q, y

    def test_weekly_windows_and_daily_cache(self):
        def query(a, b):
            self.assertLessEqual((b - a).days, 6)
            return [{"symbol": "AAA", "date": "2026-10-20"}] if a <= dt.date(2026, 10, 20) <= b else []
        out, q, _ = self._run(query)
        self.assertEqual(q.call_count, 10)  # 63-day horizon / 7-day windows (+ the last partial window)
        self.assertEqual(out["AAA"], {"date": "2026-10-20", "source": "finnhub", "known": True})
        out2, q2, y2 = self._run(query)
        self.assertEqual(q2.call_count, 0)  # cached for the HKT day
        self.assertEqual(y2.call_count, 0)  # yfinance attempts are cached too

    def test_capped_window_requeried_day_by_day(self):
        calls = []

        def query(a, b):
            calls.append((a, b))
            if a == self.TODAY and b > a:
                return [{"symbol": f"X{i}", "date": "2026-09-30"} for i in range(1500)]
            if a == b == dt.date(2026, 10, 1):
                return [{"symbol": "BBB", "date": "2026-10-01"}]
            return []
        out, _, _ = self._run(query)
        self.assertEqual(out["BBB"]["date"], "2026-10-01")
        self.assertEqual(len([c for c in calls if c[0] == c[1] and c[0] <= self.TODAY + dt.timedelta(days=6)]), 7)

    def test_yfinance_fallback_and_unknown(self):
        def yf(t, d, h):
            return {"BBB": ("2026-11-04", True), "CCC": (None, True)}.get(t, (None, False))
        out, _, _ = self._run(lambda a, b: [], yf, tickers=("BBB", "CCC", "DDD"))
        self.assertEqual(out["BBB"], {"date": "2026-11-04", "source": "yfinance", "known": True})
        self.assertEqual(out["CCC"]["known"], True)   # Yahoo answered: no earnings inside the horizon
        self.assertEqual(out["DDD"]["known"], False)  # neither source knows -> 業績日未知

    def test_unknown_earnings_blocks_real_buy_suggestion(self):
        ev = realpos.evaluate(realpos.empty_book(), {}, 7.8)
        scan = {"top": [{"ticker": "DDD", "earnings_date": None, "earnings_known": False, "earnings_days": None,
                         "entry_zone": [10, 11], "stop": 9, "target": 14, "live_price": 10.5}]}
        lines, t = plain.buy_suggestion(ev, scan, "NORMAL", market_open=True)
        self.assertIsNone(t)
        self.assertIn("業績日未知", lines[0])


# ---------------------------------------------------------------- 1C Yahoo rate limit / attempts / deferral
class YFRateLimitError(Exception):
    pass


class TestYahooAndAttempts(_TmpState):
    def test_rate_limit_stops_all_yahoo_requests(self):
        calls = []

        class T:
            def __init__(self, t):
                calls.append(t)

            def history(self, **k):
                raise YFRateLimitError("Too Many Requests. Rate limited. Try after a while.")
        fake = mock.Mock(Ticker=T)
        with mock.patch.object(marketdata, "network_off", return_value=False), \
                mock.patch.object(marketdata, "_yf", return_value=fake), \
                mock.patch.object(marketdata.time, "sleep") as sl, redirect_stdout(io.StringIO()):
            self.assertIsNone(marketdata.history("AAA"))
            self.assertIsNone(marketdata.history("BBB"))
        self.assertEqual(calls, ["AAA"])  # stopped after the first 429, no retry
        sl.assert_not_called()
        self.assertTrue(marketdata.yahoo_blocked())
        self.assertTrue(apistate.in_cooldown("yahoo"))

    def test_no_sleep_after_final_retry(self):
        class T:
            def __init__(self, t):
                pass

            def history(self, **k):
                raise ConnectionError("boom")
        with mock.patch.object(marketdata, "network_off", return_value=False), \
                mock.patch.object(marketdata, "_yf", return_value=mock.Mock(Ticker=T)), \
                mock.patch.object(marketdata.time, "sleep") as sl, redirect_stdout(io.StringIO()):
            marketdata.history("AAA", retries=2)
        self.assertEqual(sl.call_count, 1)  # between attempt 1 and 2 only

    def test_vix_missing_means_unknown_never_normal(self):
        self.assertEqual(marketdata.regime_for(None), "UNKNOWN")
        self.assertIn("數據暫缺", plain.vix_words(None))
        ev = realpos.evaluate(realpos.empty_book(), {}, 7.8)
        lines, t = plain.buy_suggestion(ev, {"top": [{"ticker": "AAA"}]}, "UNKNOWN")
        self.assertIsNone(t)
        self.assertIn("數據暫缺", lines[0])
        pf = {"account": {"start_equity_usd": 1280, "cash_usd": 1280, "fx_usdhkd": 7.8}, "positions": [], "trade_log": []}
        with self.assertRaises(ledger.RuleViolation):
            ledger.enforce_entry_rules(pf, "AAA", 10, 1, 9, "UNKNOWN", OPEN_NOW)

    def test_running_marker_counts_attempt_before_job(self):
        now = dt.datetime(2026, 10, 2, 21, 36, tzinfo=HKT)
        seen = {}

        def job(dry_run=False, force=False, now=None):
            e = schedule.get("open", schedule.slot_for("open", now))
            seen.update(status=e["status"], attempts=e["attempts"])
            raise TimeoutError("killed")  # e.g. the 900 s timeout
        with mock.patch.object(clock, "now_hkt", return_value=now):
            with self.assertRaises(TimeoutError):
                schedule.run_job("open", job, now=now)
            e = schedule.get("open", schedule.slot_for("open", now))
        self.assertEqual(seen, {"status": "running", "attempts": 1})
        self.assertEqual(e["attempts"], 1)  # final record does not double count

    def test_deferred_rerun_uses_no_attempt(self):
        with open(os.path.join(self.tmp, "run_ledger.json"), "w") as f:
            json.dump({"_meta": {"watch_since": "2026-01-01T00:00+08:00"}}, f)
        now = dt.datetime(2026, 10, 2, 21, 58, tzinfo=HKT)
        with mock.patch.object(clock, "now_hkt", return_value=now):
            for _ in range(5):
                acts = schedule.check(now=now, runner=lambda j, s: "deferred", alert=lambda t: True)
            e = schedule.get("open", schedule.slot_for("open", dt.datetime(2026, 10, 2, 21, 40, tzinfo=HKT)))
        self.assertIsNone(e)  # never recorded -> full attempts left for after the cooldown
        self.assertFalse([a for a in acts if a.get("action") == "alert" and a["job"] == "open"])


# ---------------------------------------------------------------- realwatch
def ionq_book(sl=37.0, tp=50.0):
    b = realpos.empty_book()
    realpos.add_position(b, "IONQ", 3, 44.5, sl, tp, date="2026-09-23", fee=2, now=OPEN_NOW)
    return b


class TestRealwatch(_TmpState):
    def _run(self, book, price=None, chg=None, now=OPEN_NOW, send_ok=True, fq=None, yq=None, force=False):
        sent = []
        fq = fq if fq is not None else ({"price": price, "prev_close": price / (1 + chg / 100), "change_pct": chg,
                                         "source": "finnhub"}, None)
        with mock.patch.object(realpos, "load", return_value=book), \
                mock.patch.object(finnhub, "quote", return_value=fq) as fh, \
                mock.patch.object(marketdata, "quote", return_value=yq or {"ok": False}) as ym, \
                mock.patch.object(marketdata, "fx_info", return_value={"rate": 7.8, "live": True}), \
                mock.patch.object(reasons, "reason", return_value={"text": "冇特別新聞，似係跟大市跌（納指 -2.0%）"}), \
                mock.patch.object(telegram, "send", side_effect=lambda m, **k: (sent.append(m), (send_ok, [1] if send_ok else "HTTP 502"))[1]), \
                redirect_stdout(io.StringIO()):
            out = realwatch.run(now=now, dry_run=False, force=force)
        return out, sent, fh, ym

    def _step(self, book, price, chg, minutes):
        return self._run(book, price, chg, now=OPEN_NOW + dt.timedelta(minutes=minutes))

    def test_zero_api_calls_without_positions(self):
        out, sent, fh, ym = self._run(realpos.empty_book(), 40, 1)
        self.assertEqual(out["status"], "no_positions")
        fh.assert_not_called()
        ym.assert_not_called()
        self.assertEqual(sent, [])

    def test_market_closed_and_interval_gate(self):
        sat = dt.datetime(2026, 10, 3, 22, 36, tzinfo=HKT)
        out, _, fh, _ = self._run(ionq_book(), 40, 1, now=sat)
        self.assertEqual(out["status"], "skipped")
        fh.assert_not_called()
        self._run(ionq_book(), 40, 1)
        out2, _, fh2, _ = self._step(ionq_book(), 40, 1, 2)
        self.assertEqual(out2["reason"], "interval")
        fh2.assert_not_called()
        out3, _, fh3, _ = self._step(ionq_book(), 40, 1, 5)
        self.assertEqual(out3["status"], "ok")
        fh3.assert_called_once()

    def test_each_condition(self):
        cases = [(36.5, -3.0, "跌穿止蝕"), (50.5, 2.0, "到止賺"), (37.6, -1.0, "就快到止蝕"),
                 (41.0, -6.0, "今日急跌"), (46.0, 9.0, "今日急升")]
        for i, (px, chg, word) in enumerate(cases):
            with self.subTest(word=word):
                self.setUp()
                out, sent, _, _ = self._run(ionq_book(), px, chg)
                self.assertEqual(len(sent), 1, word)  # max one message per run
                self.assertIn(word, sent[0])
                self.assertIn("原因：", sent[0])
                self.assertIn("系統只提醒", sent[0])
                self.assertIn("fung2222.github.io/project-x", sent[0])
                self.tearDown()

    def test_once_per_session_and_further_steps(self):
        b = ionq_book()
        _, s1, _, _ = self._step(b, 41.8, -6.0, 0)
        _, s2, _, _ = self._step(b, 41.4, -7.0, 5)      # same step (5%) -> quiet
        _, s3, _, _ = self._step(b, 39.8, -10.5, 10)    # further step (10%) -> alert
        _, s4, _, _ = self._step(b, 46.0, 9.0, 15)      # surge +8
        _, s5, _, _ = self._step(b, 46.5, 10.0, 20)     # same surge step -> quiet
        _, s6, _, _ = self._step(b, 49.0, 16.0, 25)     # +15 step
        self.assertEqual([len(x) for x in (s1, s2, s3, s4, s5, s6)], [1, 0, 1, 1, 0, 1])
        self.assertIn("-10.5%", s3[0])

    def test_rearm_when_sl_changes(self):
        _, s1, _, _ = self._step(ionq_book(sl=37.0), 36.5, -3.0, 0)
        _, s2, _, _ = self._step(ionq_book(sl=37.0), 36.4, -3.2, 5)
        _, s3, _, _ = self._step(ionq_book(sl=38.0), 37.5, -3.1, 10)
        self.assertEqual([len(s1), len(s2), len(s3)], [1, 0, 1])
        self.assertIn("$38.00", s3[0])

    def test_marked_only_after_successful_send(self):
        b = ionq_book()
        out, s1, _, _ = self._run(b, 36.5, -3.0, send_ok=False)
        self.assertEqual(out["status"], "telegram_failed")
        _, s2, _, _ = self._step(b, 36.5, -3.0, 5)
        self.assertEqual((len(s1), len(s2)), (1, 1))  # retried because the first send failed
        _, s3, _, _ = self._step(b, 36.5, -3.0, 10)
        self.assertEqual(len(s3), 0)

    def test_stale_finnhub_falls_back_to_yfinance_else_no_fake_price(self):
        today = clock.to_et(OPEN_NOW).date().isoformat()
        yq = {"ok": True, "price": 36.0, "prev_close": 37.5, "change_pct": -4.0, "session_date": today}
        out, sent, _, ym = self._run(ionq_book(), fq=(None, "stale quote (40 min old)"), yq=yq)
        ym.assert_called_once()
        self.assertEqual(out["quotes"]["IONQ"]["source"], "yfinance")
        self.assertIn("跌穿止蝕", sent[0])
        self.setUp()
        out2, sent2, _, _ = self._run(ionq_book(), fq=(None, "HTTP 429 rate limited"), yq={"ok": False})
        self.assertFalse(out2["quotes"]["IONQ"]["ok"])
        self.assertIn("報價攞唔到", sent2[0])
        self.assertNotIn("跌穿", sent2[0])

    def test_insane_move_rejected(self):
        out, sent, _, ym = self._run(ionq_book(), 4.0, -90.0)
        ym.assert_called_once()  # sanity check failed -> fallback tried
        self.assertNotIn("跌穿止蝕", "".join(sent))

    def test_disabled_flag(self):
        with mock.patch.dict(os.environ, {"PX_REALWATCH_DISABLED": "1"}):
            out, sent, fh, _ = self._run(ionq_book(), 36.5, -3.0)
        self.assertEqual(out["status"], "disabled")
        fh.assert_not_called()


# ---------------------------------------------------------------- hourly slot de-dup + shared store
class TestHourlyDedup(_TmpState):
    def _hourly(self, book, quotes, now=OPEN_NOW):
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
                    mock.patch.object(hourly.ledger, "load", return_value={"positions": []}), \
                    mock.patch.object(hourly.ledger, "save"), mock.patch.object(hourly, "write_json"), \
                    mock.patch.object(hourly, "_legacy_state"), mock.patch.object(hourly, "_write_quiet"), \
                    mock.patch.object(hourly, "real_context", side_effect=lambda ctx, fx=None: (None, None, {}, {})), \
                    mock.patch.object(realpos, "quotes_for", return_value=quotes), \
                    mock.patch.object(hourly.telegram, "send", side_effect=lambda m, **k: (sent.append(m), (True, [7]))[1]), \
                    redirect_stdout(io.StringIO()):
                out = hourly.run(now=now)
        return out, sent

    def test_same_slot_never_pushes_twice(self):
        q = {"IONQ": {"ok": True, "price": 36.5, "change_pct": -3.0, "source": "t"}}
        o1, s1 = self._hourly(ionq_book(), q)
        q2 = {"IONQ": {"ok": True, "price": 39.0, "change_pct": -12.0, "source": "t"}}  # new condition, same slot
        o2, s2 = self._hourly(ionq_book(), q2, now=OPEN_NOW + dt.timedelta(minutes=8))
        self.assertEqual(len(s1), 1)
        self.assertEqual(o2["status"], "duplicate")
        self.assertEqual(s2, [])

    def test_hourly_and_realwatch_share_alert_store(self):
        q = {"IONQ": {"ok": True, "price": 36.5, "change_pct": -3.0, "source": "t"}}
        self._hourly(ionq_book(), q)
        sent = []
        with mock.patch.object(realpos, "load", return_value=ionq_book()), \
                mock.patch.object(finnhub, "quote", return_value=({"price": 36.4, "prev_close": 37.6, "change_pct": -3.2}, None)), \
                mock.patch.object(marketdata, "fx_info", return_value={"rate": 7.8, "live": True}), \
                mock.patch.object(telegram, "send", side_effect=lambda m, **k: (sent.append(m), (True, [1]))[1]), \
                redirect_stdout(io.StringIO()):
            realwatch.run(now=OPEN_NOW + dt.timedelta(minutes=3), dry_run=False)
        self.assertEqual(sent, [])  # SL@37 already pushed by hourly this session


# ---------------------------------------------------------------- reasons / lessons / plain messages
class TestReasonsLessonsPlain(_TmpState):
    def test_move_class(self):
        self.assertEqual(reasons.move_class(-2.1, -1.8)[0], "market")
        self.assertIn("跟大市", reasons.move_class(-2.1, -1.8)[1])
        self.assertEqual(reasons.move_class(-6.0, 0.2)[0], "stock")
        self.assertEqual(reasons.move_class(-4.0, 0.3, -3.8, "QTUM")[0], "sector")
        self.assertEqual(reasons.move_class(None, 1.0)[0], "unknown")
        self.assertEqual(reasons.move_class(0.4, 0.2)[0], "flat")

    def test_reason_never_invents_a_cause(self):
        with mock.patch.object(reasons, "news", return_value=[]), \
                mock.patch.object(marketdata, "quote", return_value={"ok": True, "change_pct": -1.9}):
            r = reasons.reason("IONQ", -2.2)
        self.assertIn("冇特別新聞", r["text"])
        self.assertIsNone(r["headline"])

    def test_generic_headlines_filtered(self):
        now = time.time()
        items = [{"headline": "Stocktwits M&A Watch: PSKY, WBD, IONQ Stocks In Focus", "ts": now},
                 {"headline": "3 Quantum Stocks to Buy Now", "ts": now}]
        self.assertIsNone(reasons.best_headline("IONQ", items))
        good = [{"headline": "IonQ wins $50M Air Force contract", "ts": now, "provider": "finnhub"}]
        self.assertEqual(reasons.best_headline("IONQ", good)["headline"], good[0]["headline"])

    def test_marketaux_hard_daily_budget(self):
        with mock.patch.object(reasons, "get_secret", return_value="k"), \
                mock.patch("requests.get", return_value=_Resp(200, {"data": []})) as g, redirect_stdout(io.StringIO()):
            limit = int(reasons._cfg()["marketaux_per_day"])
            self.assertLessEqual(limit, 60)
            for _ in range(limit + 5):
                reasons._marketaux_news("IONQ")
        self.assertEqual(g.call_count, limit)
        self.assertEqual(reasons.marketaux_left(), 0)

    def test_lessons_no_repeat_30_days(self):
        d0 = dt.date(2026, 9, 1)
        got = [lessons.pick(d0 + dt.timedelta(days=i)) for i in range(30)]
        self.assertEqual(len(set(got)), 30)
        self.assertEqual(lessons.pick(d0), got[0])  # same day -> same lesson (re-runs)

    def test_plain_blocks_have_no_jargon_and_fit_telegram(self):
        b = realpos.empty_book()
        for t, px in (("IONQ", 44.5), ("RKLB", 70.0), ("SOUN", 15.0)):
            realpos.add_position(b, t, 1, px, px * 0.9, px * 1.3, date="2026-09-23", fee=2, now=OPEN_NOW)
        q = {t: {"ok": True, "price": px * 0.97, "change_pct": -3.0} for t, px in (("IONQ", 44.5), ("RKLB", 70.0), ("SOUN", 15.0))}
        ev = realpos.evaluate(b, q, 7.8)
        rsn = {t: {"text": "似係個股消息（比大市弱 2.0%）：" + "Very long headline " * 10} for t in q}
        scan = {"top": [{"ticker": f"T{i}", "setup": "趨勢延續", "ex_qqq_20d_pp": 3, "ex_qqq_60d_pp": 9,
                         "earnings_date": "2026-11-05", "live_price": 20} for i in range(3)]}
        L = plain.real_block(ev, rsn, {t: "下跌" for t in q}) + [plain.capital_line(ev)] + plain.hold_signal_lines(ev)
        L += plain.picks_block(scan, {f"T{i}": "x" * 70 for i in range(3)}) + plain.market_lines(0.5, 0.6, 18)
        txt = "\n".join(L)
        self.assertLessEqual(len(txt), 4096)
        for word in ("RSI", "ATR", "MACD", "Sharpe", "分數", "score"):
            self.assertNotIn(word, txt)
        self.assertIn("恐慌指數 18，正常", txt)
        self.assertIn("HK$", txt)

    def test_day_word_never_mislabels_old_session(self):
        now = dt.datetime(2026, 9, 28, 20, 0, tzinfo=HKT)  # Monday pre-market
        self.assertEqual(plain.day_word("2026-09-25", now), "上個交易日（09-25）")
        self.assertEqual(plain.day_word("2026-09-28", now), "今日")


if __name__ == "__main__":
    unittest.main()
