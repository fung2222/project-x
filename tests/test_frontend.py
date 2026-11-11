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

    def test_consistent_visual_hierarchy_and_cache_versions(self):
        for page in PAGES:
            with self.subTest(page=page):
                html = self.read(page)
                self.assertIn('class="page-subtitle"', html)
                self.assertIn('content="#005d71"', html)
                self.assertIn('css/style.css?v=20261109-2', html)
                self.assertIn('js/px.js?v=20261109-2', html)

    def test_home_is_a_summary_not_a_duplicate_of_every_page(self):
        html = self.read("index.html")
        self.assertIn('class="model-links"', html)
        self.assertIn('.slice(0, 3)', html)
        self.assertIn('{compact: true}', html)
        self.assertNotIn('今日重點', html)

    def test_detailed_evidence_is_preserved_but_collapsed(self):
        for page in ("opportunities.html", "portfolio.html", "pullback.html"):
            with self.subTest(page=page):
                html = self.read(page)
                self.assertIn('details class="card detail-card"', html)
                self.assertIn('class="detail-body"', html)
        self.assertIn('回測結果、手續費影響與限制', self.read("opportunities.html"))
        self.assertIn('紙上交易紀錄', self.read("portfolio.html"))

    def test_retired_root_files_are_removed(self):
        retired = (
            "GROK_BOT_SYSTEM_PROMPT.md", "PROJECT_X_BUILD_SPEC.md",
            "PROJECT_X_HANDOFF.md", "PROJECT_X_INVESTMENT_PLAN.md",
            "PROJECT_X_INVESTMENT_PLAN.txt", "PROJECT_X_MANUAL.md",
            "ProjectX_Portfolio.xlsx", "create_portfolio.py", "run_dashboard.py",
            "start_server.bat", "market_open_alert.py", "enhanced_indicators.py",
        )
        for name in retired:
            with self.subTest(name=name):
                self.assertFalse(os.path.exists(os.path.join(ROOT, name)))

    def test_pullback_reads_real_state_and_does_not_fake_pending(self):
        html = self.read("pullback.html")
        self.assertIn("PX.json('data/pullback.json')", html)
        self.assertIn("等待第一次掃描", html)
        self.assertIn("09:00 ET", html)
        self.assertNotIn("週一至五 HKT 22:00", html)
        with open(os.path.join(ROOT, "data", "pullback.json"), encoding="utf-8") as f:
            data = json.load(f)
        # 真實 state：未跑過係 pending，跑咗係 ok（頁面唔可以 fake pending）
        self.assertIn(data["status"], ("pending", "ok"))


if __name__ == "__main__":
    unittest.main()
