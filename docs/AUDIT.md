# Project X 全面審計（AUDIT）— A（Grok Bot）＋ B（Hermes）

> 日期：2026-09-28 HKT。審計人：Grok Bot（executor）。解釋用繁體中文；code、路徑、指令用英文。
> 範圍：**A** = `fung2222/project-x`（本 repo；2026-09-28 由 `project-x-minimax` 改名，Grok Bot 平台 routine 跑）；**B** = `fung2222/project-x-2026`（Hermes，每日 05:00／08:30／21:30 commit，2026-08-06 之後有 141 個 commit，最新 2026-09-28）同 B 嘅 pipeline 原始碼 `export/2026-09-28/project_x_learning/`（本 repo 有副本：`data/legacy/hermes_project_x_2026/export_2026-09-28/`）。
> Mag7 觀察池：**retired by Roy 2026-09-28**，唔喺審計範圍。
> 嚴重程度：🔴 高（會令數字錯、漏推、蝕錢或者洩密）　🟠 中（誤導、唔穩定）　🟡 低（整潔、易用）。
> 狀態：✅ 已修（寫明 commit／檔案）　🟡 部分／要切換時做　⏳ 未修（寫明原因）。**所有 🔴 同 🟠 都已經修咗，或者列明要 Roy／Hermes 做嘅一步。**

## 0. 最重要嘅 10 個發現（一頁睇晒）

| # | 發現 | 系統 | 嚴重 | 狀態 |
|---|---|---|---|---|
| S-01 | 舊 hourly cron `6 21-23,0-4 * * 1-5`（HKT）**星期六 00:06–04:06 從來冇跑**（＝星期五美股下半場冇人睇 SL/TP），反而星期一凌晨跑咗冇用嘅 5 次 | A | 🔴 | ✅ 改用 ET 排程＋交易日規則 |
| S-03 | B 嘅收市（`0 5 * * 1-5`）同隔夜複盤（`30 8 * * 1-5`）用 HKT 星期一至五 → **星期五個市從來冇收市報告**，星期一 05:00 就出一份「2026-09-28 收市報告」其實係星期五數據 | B | 🔴 | ✅ |
| S-04 | DST：2026-11-01 之後 B 21:30 HKT 日報變成開市前（08:30 ET）；05:00 收市報告啱啱撞正收市一刻（16:00 ET），價未定 | B（A 嘅 routine 亦係） | 🔴 | ✅ code；🟡 Grok Bot routine 要切換 |
| P-01 | B **止損從來冇執行**：RKLB 由 2026-07-16 起一直低過 −10% 止損線都照揸（09-28 −11.34%）；TSLA 07-30 最低 −24.7% 都冇走 | B | 🔴 | ✅ 合併版自動紙上執行 |
| F-01 | 手續費模型**低估富途真實收費一半**：用咗 `max(US$1, 0.5%)`，富途香港美股實際每張單約 US$2（佣金最低 0.99＋平台費最低 1.00＋交收費，賣出加 TAF） | A（B 完全冇計手續費） | 🔴 | ✅ 新模型；舊交易唔追溯（列明影響） |
| B-T | 回測（誠實版）：用真實富途收費，掃描策略 300 個交易日組合模擬 **−25.5%**（同期 QQQ **+31.9%**）；手續費佔本金約 12% | 合併版 | 🔴（產品風險） | 已喺網站同 Telegram 講明「唔係買入訊號」；要 Roy 決定點用 |
| X-01 | 真 Finnhub／Marketaux key 同 Telegram bot token＋chat id commit 咗入 **public** repo（`*_config.json` 自 `9d9f8de`；`PROJECT_X_BUILD_SPEC.md` 自 `584a752`，2026-07-08） | A | 🔴 | ✅ 已移除；🟡 key 要 rotate、token 要 revoke（history 冇改寫） |
| L-01 | 排程 job 靠 LLM：Hermes cron 用 `xai-oauth/grok-4.5`，**09-18 起 xAI credit 用完，daily 同 mag7 job fail**；A 嘅「專業過濾」同教學亦係 Grok Bot LLM 生成 | A＋B | 🔴 | ✅ 全部 `python run.py <job>`，純規則 |
| I-01 | A 嘅「MA50」其實係約 22 日均線（`history(period="1mo")`）：RKLB 65.98 vs 真 MA50 69.49 | A | 🔴 | ✅ |
| I-04 | 用咗**未收市嘅今日 bar** 計指標：B 喺 21:30（＝09:30 ET 開市嗰一分鐘）計 MA／RSI／量比（量比得 ~0.05x）；A 喺 22:00 一樣 | A＋B | 🟠 | ✅ 只用已收市日 bar |

---

## 1. 方法
1. 逐個檔案讀 code：A 嘅 `analyzer.py`、`finnhub_api.py`、`risk_manager.py`、`telegram_push.py`、`_run_*.py`、Grok Bot routine 設定；B 嘅 `analyzer.py`、`data_fetcher.py`、`risk_manager.py`、`telegram_push.py`、`run_*_pipeline.sh`、`push_*.sh`、`schedule.md`（2026-09-28 export）。
2. 用即時 yfinance 數據重算指標對數（MA50、RSI、ATR）。
3. 用 `git log` 睇兩個 repo 實際幾時 commit（證明排程有冇漏）。
4. 用兩邊嘅 `portfolio.json`／交易紀錄對帳。
5. 寫離線測試（`tests/`，45 個）鎖死修正；排程用模擬 cron 驗證（`tests/test_crontab.py`）。
6. 回測掃描策略（`scripts/backtest_scan.py`），所有數字由 script 生成、存檔 `data/backtest/`，冇人手作數。

---

## 2. 排程／時區／DST／假期（Schedule）

### S-01 🔴 A：hourly cron 用 HKT 星期幾 → 星期五下半場冇監察
- **位置**：Grok Bot 平台 routine「hourly position check」，cron `6 21-23,0-4 * * 1-5`（HKT）。
- **問題**：美股星期一至五嘅交易時段，喺 HKT 係「星期一 21:30 → 星期六 04:00」。`0-4` 小時配 `1-5`（星期一至五）即係：星期一 00:06–04:06 HKT（＝星期日美東，冇市）白跑 5 次；**星期六 00:06–04:06 HKT（＝星期五 12:06–16:06 ET）一次都冇跑**。
- **證據**：cron 表達式本身；`tests/test_schedule.py::test_friday_overnight_hourly` 證明新排程有 星期六 00:06–04:06 HKT 嘅 slot。
- **修正**：`settings.schedule.hourly` = ET 10:06–16:06、NYSE 交易日；Hermes cron 用 ET 或者「HKT 超集」寫法（HERMES_HANDOVER §3）。✅（`834b489`、`9bcf420`）

### S-02 🔴 A：開市監控／每日分析寫死 HKT
- **位置**：Grok Bot routine 21:35 同約 21:53 HKT。
- **問題**：2026-11-01 之後開市係 22:30 HKT，21:35 HKT = 08:35 ET（未開市）。
- **修正**：新 code 用 ET 判斷；未開市就靜靜跳過（唔會亂 send）。🟡 Grok Bot routine 本身仲係 HKT → 切換去 Hermes 之前如果仲用緊，要推遲 1 小時（見 HERMES_HANDOVER §4）。

### S-03 🔴 B：收市／隔夜複盤用 HKT 星期一至五 → 漏星期五、星期一出假報告
- **位置**：`export/2026-09-28/schedule.md`：`project-x-close-report` `0 5 * * 1-5`、`project-x-morning-briefing` `30 8 * * 1-5`。
- **問題**：星期五美股收市係星期六 04:00/05:00 HKT → 星期六冇 job → **星期五個市從來冇收市報告同隔夜複盤**。星期一 05:00 HKT 對應星期日美東（冇市），但照出報告，而且用 HKT 日期做標題。
- **證據**：repo B `git log` 由 2026-08-06 起：close report commit 星期一 8 次、星期二至五各 7 次、**星期六 0 次**；`data/close_report_2026-09-28.md`（星期一 05:00 HKT）入面 VIX 14.87、SPY $771.35 = 星期五 09-25 收市數據。
- **修正**：close = 17:00 ET、NYSE 交易日；morning = HKT 08:30、「前一日係美股交易日」（即星期二至六）；報告用美股交易日（ET）做 key。✅ `test_close_slot_hkt_both_seasons`、`test_morning_and_weekly_days`。

### S-04 🔴 B（同 A routine）：DST 未處理
- **問題**：B 全部 cron 寫死 HKT。2026-11-01 → 2027-03-14 冬令期間：21:30 HKT daily = 08:30 ET（開市前 1 小時，冇今日數據）；05:00 HKT close = 16:00 ET 收市一刻（價未定、after-hours 未完）。
- **修正**：ET 排程（`px/clock.py`，zoneinfo `America/New_York`）；close 窗口改為 16:50 ET 之後先准跑（`39173d4`），避免 HKT 超集 cron 嘅 05:00 行喺冬令提早跑。✅ `tests/test_crontab.py` 跨兩次 DST 驗證。

### S-05 🟠 B：21:30 HKT 啱啱開市一刻＋每晚 commit 兩次
- **問題**：21:30 HKT = 09:30:00 ET，開市第一分鐘，數據未有意義（見 I-04）。repo B commit 時間：21:30 有 66 個、21:31 有 36 個 → daily pipeline 一晚 push 兩次（`run_daily_pipeline.sh` 同 `push_daily_full.sh` 各自 commit）。
- **修正**：daily = 09:53 ET（開市後 23 分鐘）；每個 job 淨係喺最後 `--push` commit 一次。✅

### S-06 🟠 兩邊都冇漏跑偵測
- **問題**：job fail 或者冇跑，冇人知。例：B 冇 2026-09-18（星期五 05:00 HKT）嘅收市報告（xAI credit 問題期間），冇任何 alert。
- **修正**：`px/schedule.py` run ledger（`state/run_ledger.json`）＋ `python run.py check` watchdog：每個 slot 過咗 grace 仲未 ok → 喺 rerun 窗口內自動重跑最多 2 次；過咗窗口 → **每個 slot 只 send 1 條** 🛠 alert。第一次跑 check 只會「arm」（記低 watch_since），唔會為切換前嘅 slot 狂 send alert。收市報告尾有一行 🩺 health line。✅ `test_missing_slot_rerun_then_ok`、`test_alert_once_after_deadline`、`test_first_check_arms_only`。

### S-07 🟠 重跑會重複推送
- **問題**：A 舊 `telegram_push.py` 重跑就再 send；B 由 LLM cron deliver，重跑亦會再 send。
- **修正**：`px/guard.py`（`state/job_runs.json`，按美股交易日＋job＋訊息部分）；成功嘅 slot 係「sticky ok」，後面嘅重複／跳過唔會改佢狀態。✅ `test_duplicate_rerun_is_guarded`、`test_superset_cron_skip_keeps_ok`。

### S-08 🟡 冇完整美股假期／半日市日曆
- **修正**：`px/clock.py` 規則式 NYSE 日曆，已對 NYSE 官方 2026–2027 表（2026-11-27、2026-12-24、2027-11-26 半日市 13:00 ET）。✅ `test_nyse_2026_2027`、`test_early_closes`。Hermes 每年 12 月對一次官方表（HERMES_HANDOVER §3.5）。

---

## 3. LLM 依賴（L）

### L-01 🔴 排程靠 LLM
- **B**：4 個 PX cron 全部 `xai-oauth/grok-4.5`，由 LLM 行 shell script 再「deliver」到 Telegram；`telegram_push.py` 本身只係 print（`print(f"\n=== Part {i} …")`）。09-18 起 xAI credit 用完 → daily 同 mag7 job fail；09-21 Hermes 將 4 個 cron 設 `enabled=false`（「moved to gushen profile」），之後由 gushen profile 繼續跑同一條 pipeline（repo B 每日照有 commit）。
- **A**：Grok Bot routine 嘅「專業過濾」同 3 段教學由 LLM 寫；平台停就冇晒。
- **修正**：全部 job 係 `python run.py <job>`：數據、指標、gates、SL/TP、訊息全部 code 生成，直接用 Telegram Bot API send（文字＋圖）。LLM 只可以用嚟答 Roy 問題，唔准喺排程流程入面。✅ `tests/test_core.py::TestNoLLMAndConfigDriven`。

---

## 4. 數據同指標（I）

### I-01 🔴 A：假 MA50
- **位置**：`finnhub_api.get_tech_indicators` 用 `history(period="1mo")`（約 22 條 bar）。
- **證據**：2026-09-25：RKLB「MA50」65.98 vs 真 MA50 69.49；NVDA 221.37 vs 215.79。
- **修正**：`px/indicators.py` 用 1 年日線、最少 120 條 bar、真 MA20/MA50。✅ `test_T2_ma50_real_50_bars_and_min_bars`。

### I-02 🟠 A：MACD 退化
- **問題**：bar 少過 26 條時 `ema26 = closes[-1]`，signal line 用 `closes[0]` → histogram 冇意義，「MACD 看漲確認」係噪音。
- **修正**：標準 MACD 12/26/9，數據足先計。✅

### I-03 🟠 A：RSI 用簡單平均
- **修正**：Wilder RSI(14)／ATR(14)。✅ `test_T1_wilder_rsi`。（B 嘅 RSI 本身已經係 Wilder：`ewm(alpha=1/14)`，冇問題。）

### I-04 🟠 A＋B：用咗未收市嘅今日 bar（look-ahead／unfinished bar）
- **B 位置**：`data_fetcher.get_indicators` 用 `history(period="6mo")` 最後一行做 current／MA／RSI／成交量；21:30 HKT 跑 → 最後一行係啱啱開市、得 1 分鐘嘅 bar。註解話「align volume to last valid close row」，但冇剔走今日未完 bar → 量比約 0.05x。
- **A 位置**：22:00 HKT 用 1 個月數據，一樣包今日未完 bar。
- **修正**：指標只用**已收市**日 bar（`px/indicators.py` 剔走今日 bar）；即時價只用嚟做 SL/TP 同顯示。✅ `test_T3_completed_bars_only`。

### I-05 🟡 A：分析師／基本面數據全部空
- **證據**：`profiles.json` 全部「未知（0位分析師）」（yfinance `.info` 攞唔到）。
- **修正**：新網站唔再顯示空嘅基本面 tab；業績日改用 Finnhub 業績日曆（yfinance 後備），daily 訊息同網站都有「業績日」欄。✅（`686df1e`）

### I-06 🟡 A：`signals.json` 1.1 MB 越嚟越大
- **修正**：新網站唔再載入；只有 `classic.html`（舊版，保留做回退）用。⏳ 之後可以做月度分檔（低優先）。

---

## 5. 信號、信心、決策（C）

### C-01 🟠 A：無條件 +5 信心
- **位置**：舊 `analyzer` 最後一行 `confidence + 5`（「低VIX加成」），唔理 VIX。
- **修正**：取消；VIX 調整 NORMAL 0／CAUTION −10／DEFENSIVE −20。✅ `test_T4_no_unconditional_plus5`。

### C-02 🟠 A：信心門檻矛盾
- **證據**：`rules.min_confidence = 0.75`，但 `vix_guardrails.NORMAL.min_confidence = 0.70` → `daily_report.json`（2026-09-25）寫 0.70。
- **修正**：單一來源 `config/settings.json → rules.min_confidence = 0.75`（CAUTION 0.80、DEFENSIVE 0.85）。✅

### C-03 🟠 B：同一份報告入面，風控話要止損、分析話可以加
- **證據**：`close_report_2026-09-28.md`：「🚨 RKLB −11.34% · 距止損 −1.34pp」同一時間「RKLB: 上升趨勢 · 偏多持有/可分批佈局 (score +5)」。三隻股全部 score +5、全部「上升趨勢」。
- **原因**：`analyzer._trend_bias` 只睇價 vs MA、RSI、5 日變幅，完全唔知持倉虧損／止損；兩個模組各自出建議。
- **修正**：合併版先查出場（SL/TP），再做入場 gates；持倉穿 SL 就執行，唔會同時叫人加注。✅

### C-04 🟡 B：加注規則 = 攤平
- **證據**：`portfolio.json → add_position_rules.buy_signal`：「RSI<35 + 股價低於MA50 → 加 0.5 注」。同 Roy「唔攤平」規則衝突。
- **修正**：唔移植；`rules.allow_averaging_down = false`、`allow_add = false`，code 強制。✅

### C-05 🟡 A：「命中率」標籤誤導
- **問題**：舊網站「命中率」用信號記錄計，唔係用已平倉交易，長期顯示「— 需累積數據」。
- **修正**：新網站只顯示已平倉交易紀錄、權益 vs SPY 曲線同回測（有明確定義）。✅

---

## 6. 注碼、手續費、FX、回測（F／B-T）

### F-01 🔴 手續費低估（A）；完全冇計手續費（B）
- **位置**：A `ledger.fee()` 舊模型 `max(US$1, 0.5% × 金額)`；B `portfolio.json` P&L = 市值 − 成本，冇手續費。
- **富途香港美股收費（固定式，2026-09-28 查 futuhk.com 幫助中心）**：佣金 US$0.0049/股，每單最低 0.99；平台使用費 US$0.005/股，每單最低 1.00（0.5% 上限唔會低過最低收費）；交收費 US$0.003/股；賣出另加 TAF US$0.000195/股（最低 0.01）；SEC 費 0。→ **細單每張約 US$2.00，來回約 US$4.0（≈ HK$31）**。
- **影響**：
  - 今個時期（2026-09-13 起）已入帳 3 張單手續費 US$3.04；按富途收費約 US$6.08 → 紙上總 P&L 高估約 US$3（+11.81 → 約 +8.77，+0.92% → 約 +0.69%）。**舊交易冇追溯改**（帳本唔改歷史），喺呢度同網站講明。
  - 掃描嘅「手續費拖累」過濾之前用錯模型。
- **修正**：`px/ledger.py::fee(notional, shares, side)` 用富途固定式；`round_trip_fee()`；scan 同回測共用。手續費拖累上限由 2% 改 3%（用真實收費，US$150 一注來回已經 2.7%）。✅ `test_T5_fees`、`test_T8_stop_loss_execution`（`c6b61fc`）。
- **要 Roy 決定**：見 §10 D1。

### F-02 🟡 B：碎股（0.5 注）
- 唔移植：合併版用整股，同 Roy 富途落單一致、手續費清楚。

### F-03 🟡 FX 固定 7.8
- 港元聯繫匯率 7.75–7.85，最大誤差約 ±0.6%；Roy 同意用 7.8。保留。

### F-04 🟠 A：冇每筆風險上限／主題上限
- **修正**：每筆風險 ≤ 2% 權益、同主題最多 1 隻、每日最多 1 個新倉。✅ `test_no_averaging_down_risk_cap_cooldown`、`test_theme_and_one_entry_per_day`。

### B-T 回測（誠實版）🔴 產品風險
- **方法**：`scripts/backtest_scan.py`，yfinance 2 年日線，54 隻股票池，測試期 **2025-07-17 → 2026-09-24（300 個交易日）**；每日收市後排名，下一日開市價入場；SL／目標／30 日時間止損；組合模擬 US$1,280、最多 3 隻、每日最多 1 個新倉、富途真實手續費；結果存 `data/backtest/scan_backtest.json`、`scan_variants_2026-09-28.json`。
- **結果（live 設定：3×ATR 止損上限 20%、30 日時間止損、手續費拖累 ≤3%）**：

| 項目 | 次數 | 勝率 | 命中目標 | 平均 R | 最大回撤 |
|---|---|---|---|---|---|
| 每日 Top 1（信號層面，未計手續費） | 63 | 28.6% | 7.9% | −0.31R | −20.0R |
| 每日 Top 5 | 104 | — | — | −0.13R | — |
| 基準：所有流動股、同樣出場 | 718 | — | — | +0.01R | — |
| **組合模擬（計富途手續費）** | 38 單 | 26.3% | — | **−25.5%** | −27.3% |
| QQQ 買入持有 | — | — | — | **+31.9%** | −12.2% |
| SPY 買入持有 | — | — | — | +22.2% | −9.1% |
| 股票池平均買入持有 | — | — | — | +8.7% | — |

- **手續費**：已平倉 38 單手續費共 **US$153.75（≈ 本金 12%）**；未計手續費嘅交易盈虧都係 −US$162.71。
- **敏感度（全部同一數據、事前定好嘅變體）**：

| 變體 | 組合回報 | 最大回撤 | 單數 | 手續費 |
|---|---|---|---|---|
| live（真實收費、拖累 ≤3%） | −25.5% | −27.3% | 38 | US$154 |
| live_drag2（真實收費、拖累 ≤2%） | −14.2% | −19.0% | 15 | US$61 |
| live_oldfees（舊 US$1 收費、拖累 ≤2%＝修正前嗰次） | +3.4% | −24.3% | 42 | US$86 |
| v1_2atr（2×ATR、上限 15%、20 日） | −32.5% | −41.1% | 69 | US$281 |
| pullback_only（只做回踩 MA20） | −22.2% | −26.0% | 24 | US$97 |
| trend_trail（跌穿 MA20 走） | −39.0% | −39.7% | 79 | US$319 |

- **結論**：呢套掃描**冇證明到有優勢**。修正手續費之前嘅 +3.4% 主要係運氣同錯誤收費；用真實收費，所有變體都蝕錢、大幅跑輸 QQQ。live 設定係睇完結果先揀（in-sample），真實表現可能更差。限制：倖存者偏差（股票池係 2026-09 揀嘅）、冇模擬業績日禁區、日線入面止損同目標邊個先到未知（假設止損先）。
- **已做**：網站「機會掃描」頁同 Telegram 講明「Top 5 係研究名單，唔係買入訊號」、每張卡顯示來回手續費 %（要升過先打和）。
- **要 Roy 決定**：§10 D1–D3。

---

## 7. 止損／止盈執行同 P&L（P）

### P-01 🔴 B：止損從來冇執行
- **位置**：B `risk_manager.py`：跌到 −10% 只係設 `risk_flag = "STOP"` 同 print「🚨 STOP …」，冇賣出邏輯；`portfolio.json` 由 2026-07-08 開倉之後 `trade_log` 只有一行「OPEN PORTFOLIO」。
- **證據（用而家數據重新睇）**：RKLB 入場 83.41，由 2026-07-16 起一直低過 −10%，09-28 仲揸住（73.95，−11.34%）；TSLA 入場 402.90，07-30 最低 −24.7%，而家 −7.64%（372.11）。
- **事後睇**：喺呢個樣本，揸住 TSLA 比 −10% 止損好（反彈返）；RKLB 如果 −10% 走咗會少蝕少少。**呢個係事後孔明，唔係規則**：一條從來唔執行嘅止損等於冇止損，下次跌 −50% 都一樣唔會走。
- **修正**：合併版 SL/TP 自動紙上執行（open／hourly／daily／close 都會查；報價異常跳 >50% 唔執行）。✅ `test_T8_stop_loss_execution`、`test_T11_open_sends_once_and_executes_tp_once`。

### P-02 🟠 A：RKLB 盈利計錯
- **證據**：T003/T005 記錄淨盈利 19.06；正確 18.06（漏咗買入手續費 1.00，舊 `risk_manager.execute_action` bug）。
- **修正**：`d72a7c4` 更正，寫入 `portfolio.json → corrections[]`。✅

### P-03 🟠 A：`account.total_pnl_usd` 只計未實現
- **證據**：舊值 −5.25（只係 SOUN 未實現）。正確：已實現 +18.06、未實現 −5.25、未平倉買入費 1.00 → 總 +11.81（+0.92%）；現金 1,140.56、權益 1,291.81（HK$10,076）。
- **修正**：`ledger.recompute()`。✅ `test_T6_reconciliation_fixture`。

### P-04 🟡 A：SL 規則兩套
- `risk_manager` 用 ATR，但持倉記錄用固定 `stop_loss_price`。**修正**：單一來源（入場時定死，寫入帳本）。✅

---

## 8. 報告、網站、Telegram（R）

### R-01 🟠 A：Telegram 太多重複
- **證據**：每日約 15 條（12 段日報＋3 段教學）＋開市＋hourly 每晚 2 條狀態＋週報。
- **修正**（Roy：資訊多冇問題，刪重複同噪音）：open 1、daily 4（決策／信號＋業績日／Top 5／教學＋情境）、hourly 有事先 alert（每個交易時段第一次加 1 條狀態）、close 4＋1 張圖、morning 1、weekly 1。✅

### R-02 🟠 B：`telegram_push.py` 只 print
- 靠 LLM cron deliver；LLM fail 就冇推送。**修正**：`px/telegram.py` 直接用 Bot API（`sendMessage`、`sendPhoto`，timeout＋重試，錯誤訊息自動遮 token）。✅

### R-03 🟡 B：報告用 HKT 日期
- `close_report_2026-09-28` 其實係 09-25 美股。**修正**：報告以美股交易日（ET）命名。✅

### R-04 🟡 網站唔知數據過期
- **修正**：`js/px.js` freshness 警告（例：富途鏡像 2026-07-08 之後冇更新 → 黃色警告）。✅

### R-05 🟡 A：repo homepage 寫錯（soonoo.github.io）
- ✅ 已改做 `https://fung2222.github.io/project-x/`（2026-09-28 改名後；舊網址 redirect，見 HERMES_HANDOVER §9）。

---

## 9. Secrets（X）

### X-01 🔴 A：key／token 入咗 public repo
- **證據**：`finnhub_config.json`、`marketaux_config.json`、`telegram_config.json`（commit `9d9f8de` 起）；`PROJECT_X_BUILD_SPEC.md` 自 `584a752`（2026-07-08）寫住 Telegram token、chat id、Marketaux key 同另一個 API key。
- **修正**：`01a303e` 取消追蹤＋`.gitignore`＋`.env.example`；BUILD_SPEC 換成佔位符；`test_T16_no_secret_files_tracked`。**Git history 冇改寫**（Roy 規則：唔 force push）→ 舊值喺 history 仍然睇到。
- 🟡 **切換時一定要做**：Finnhub、Marketaux 換新 key；@Minimax0707bot token 用 BotFather `/revoke`（HERMES_HANDOVER §5）。

### X-02 🟡 B
- B repo 同 export 冇 secret（已掃描；export 入面 chat id 已 redact）。✅

---

## 10. 要 Roy 決定嘅事（未改預設）
- **D1 手續費 vs 細本金**：富途每張單約 US$2。US$150 一注來回要升 2.7% 先打和；US$320（25% 上限）一注要 1.25%。選擇：(a) 維持而家（每筆風險 2%、拖累上限 3%）；(b) 每注盡量接近 25% 上限、少啲交易；(c) 改用階梯式收費或者其他券商（Roy 自己查）。
- **D2 掃描點用**：回測冇 edge。建議 10 月開始真錢時：掃描只做「研究名單」，入場前 Roy 自己再判斷；紙上組合照跑，累積真實前瞻數據；每月喺週報比較 紙上組合 vs QQQ。
- **D3 止損闊度**：掃描嘅止損最闊 −20%（3×ATR）；風險由注碼控制（每筆 ≤2% 權益），但單一股跌 20% 先走，同「大跌硬性出場」嘅感覺可能唔同。可以改做上限 −10%（回測 v1_2atr 類似設定表現更差）。
- **D4 TP 模式**：`tp_mode: partial_trail`（+10% 先賣一半，剩低移止損到成本）已寫低做選項，未啟用。

## 11. 未修／低優先
- I-06 `signals.json` 分檔（🟡）。
- 回測加入歷史業績日禁區（冇可靠免費歷史數據）。
- `classic.html` 舊版頁保留一段時間做回退，之後可以刪。
