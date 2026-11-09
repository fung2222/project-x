"""Static contracts for the multi-page site; browser checks cover rendering."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ("index.html", "opportunities.html", "signals.html", "portfolio.html", "reports.html", "learn.html", "pullback.html")


class TestFrontendContracts(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            return f.read()

    def test_every_page_has_one_h1_and_versioned_css(self):
        for page in PAGES:
            with self.subTest(page=page):
                html = self.read(page)
                self.assertEqual(len(re.findall(r"<h1\b", html)), 1)
                self.assertIn('id="content" tabindex="-1"', html)
                self.assertIn('css/style.css?v=', html)

    def test_shared_navigation_and_chart_accessibility(self):
        js = self.read("js/px.js")
        self.assertIn('aria-current="page"', js)
        self.assertIn('aria-label="主要導覽"', js)
        self.assertIn('scrollIntoView', js)
        self.assertIn('role="img"', js)
        self.assertIn('<title id=', js)
        self.assertIn('<desc id=', js)
        self.assertIn('enhanceTables', js)

    def test_research_language_and_fee_consistency(self):
        js = self.read("js/px.js")
        self.assertIn("模擬注碼（預算參考）", js)
        self.assertNotIn("建議注碼", js)
        self.assertIn("核心定投", js)
        self.assertIn("衛星學習倉", js)
        learn = self.read("learn.html")
        self.assertIn("一買一賣來回約 US$4", learn)
        self.assertNotIn("每單來回手續費最少 US$2", learn)
        self.assertNotIn("高潛力機會掃描（核心產品）", self.read("opportunities.html"))

    def test_reports_use_buttons_pagination_and_live_status(self):
        html = self.read("reports.html")
        self.assertIn('aria-pressed=', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn("const pageSize = 20", html)
        self.assertNotIn('href="#"', html)

    def test_pullback_reads_real_state_and_does_not_fake_pending(self):
        html = self.read("pullback.html")
        self.assertIn("PX.json('data/pullback.json')", html)
        self.assertIn("等待第一次掃描", html)
        self.assertIn("09:00 ET", html)
        self.assertNotIn("週一至五 HKT 22:00", html)
        with open(os.path.join(ROOT, "data", "pullback.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["status"], "pending")
        self.assertIsNone(data["generated_at"])


if __name__ == "__main__":
    unittest.main()
