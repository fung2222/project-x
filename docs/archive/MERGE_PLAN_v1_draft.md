# Project X 合併計劃 + 營運規格（MERGE_PLAN v1.0）

> ⚠️ **已被取代（superseded）— 只作歷史參考。** 呢份係 2026-09-28 早上嘅設計草稿（v1.0）。實際實作同最新規則以 `docs/HERMES_HANDOVER.md`、`docs/REQUIREMENTS.md`、`docs/AUDIT.md` 為準。
> 草稿之後嘅更正：(1) Repo B **係活躍嘅**（2026-08-06 起 141 個 commit，每日 05:00／08:30／21:30；Hermes 2026-09-28 匯出咗 pipeline code 去 `export/2026-09-28/`）；(2) Hermes 係 Linux 環境（`/opt/data/…`），唔係 Windows；(3) 排程改用 `run.py tick`（Hermes 系統 crontab），唔係 GitHub Actions dispatcher（push token 冇 workflow scope，Actions 只留範本 `ops/github-actions/`）；(4) 設定檔係 `config/settings.json`（唔係 YAML）；(5) repo B **唔 archive、唔改 redirect**，保持唯讀；A 改名做 `project-x`；(6) Mag7 **retired by Roy 2026-09-28**；(7) 手續費改用富途真實收費；(8) Telegram 最終去群組「Project X Nas」。


> 撰寫：Grok Bot（executor），2026-09-28 HKT  
> 讀者：**Hermes agent**（Roy 部 Windows 桌面機上面嘅 AI）同 Roy Chan  
> 語言：解釋用繁體中文（廣東話都睇得明）；code、路徑、指令用英文  
> 時區：所有時間都係 **HKT（UTC+8）**，除非寫明 ET（美東時間）  
> 狀態：**設計文件。未 commit 落任何 repo。** 所有對外動作（push、archive、換 key、send Telegram）都要 Roy 批准先做。

---

## 0. 一頁摘要（TL;DR）

1. **Repo B 身份**：`fung2222/project-x-2026`（public），Pages：https://fung2222.github.io/project-x-2026/ ，Hermes 每日 05:00／08:30／21:30 commit（2026-08-06 起 141 個 commit，最新 2026-09-28），author `Hermes Agent <hermes@nousresearch.com>`。Repo 本身係靜態網站＋`data/`；pipeline code 由 Hermes 喺 2026-09-28 匯出到 `export/2026-09-28/`。
2. **Base repo**：用 **A = `fung2222/project-x-minimax`**（原因：有 code、組合仲活緊、有機會掃描、有 Telegram、網址 Roy 已經用開）。Repo 名同網址**唔改**（改名會令 Pages 網址斷，GitHub 唔會幫 Pages 做 redirect）。
3. **排程**：A 而家靠 Grok Bot 平台 automation 跑，**Grok Bot 訂閱完咗就會停**。新設計：`.github/workflows/px-scheduler.yml` 每 30 分鐘叫一次 dispatcher，dispatcher 按 **ET 時間表**決定跑邊個 job，自動處理夏令/冬令時同美股假期。Hermes 做 operator（監察、解答、手動覆核），**唔需要**部機 24 小時開住。
4. **保留**：A 嘅股票池、機會掃描、風控規則、紙上帳本、Telegram、週報；B 嘅 P&L 曲線、報告存檔、trend score / MA20-MA50 結構、止損距離 flag、多頁網站版面、學習中心、富途真倉鏡像。
5. **一定要修**：A 嘅 MA50 bug（其實係約 22 日均線）、MACD bug、無條件 +5 信心、PnL 欄位計錯、`signals.json` 越嚟越大、**secret commit 咗落 public repo**、兩個未 commit 嘅 runner script。
6. **紙上組合**：沿用 A 嘅 HKD 10k book（起始 USD 1,280.00，2026-09-13 重設）。B 嘅 HKD 5k book 唔合併，只存做 `data/legacy/`。
7. **B 嘅處理**：將 B 嘅 data＋export 複製入 A 做 legacy；repo B 保持唯讀，唔 archive、唔改 redirect（Roy 決定）。

---

## 1. 現況盤點（2026-09-28 10:00 HKT 查到嘅）

### 1.1 Repo A — `fung2222/project-x-minimax`
- Pages：https://fung2222.github.io/project-x-minimax/（legacy build，branch `main`，路徑 `/`）。
- ⚠️ Repo 設定入面嘅 homepage 欄位寫錯咗做 `https://soonoo.github.io/project-x-minimax`，要改返 fung2222。
- 最後 commit：`0ea34e2 2026-09-25 22:03 HKT Daily update: 2026-09-25`。
- 本機 clone：`/workspace/project-x-minimax`（Grok Bot 部 box；**訂閱完咗就會冇**）。
- 未 commit / 未 track 嘅檔案（**Grok Bot 停之前一定要保存**）：
  - `_run_hourly_check.py`、`_run_open_monitor.py`（hourly job 同開市 job 嘅真正 runner！）
  - `portfolio.json`、`_last_hourly_check.json`（2026-09-28 04:15 HKT MTM）
  - `Reports/WeeklyReport_2026-09-28.json`、`Reports/WeeklySummary_2026-09-28.txt`、`Reports/_daily_vars_2026-09-25.json`
- `_run_hourly_check.py` 入面寫死咗 Grok Bot box 路徑：`STATE_PATH = "/home/box/sand-data/agents/.../position_tracker_state.json"`，搬走之後要刪。
- 排程係 Grok Bot automation prompt（唔係 cron，亦唔係 GitHub Actions）。Repo 冇 workflow（淨係 GitHub 自動產生嘅 `pages-build-deployment`）。

### 1.2 Repo B — `fung2222/project-x-2026`
- 建立：2026-07-08。活躍：2026-08-06 起 141 個 commit（總共 252），差唔多全部係 `Hermes Agent data: ...`，最新 2026-09-28。
- 內容：`index.html signals.html portfolio.html learn.html reports.html css/ js/ img/ data/`。
- 排程（由 commit 時間推斷）：05:00 收市報告、08:30 晨早 snapshot、21:30 日報（**每晚 push 兩次**）。
- Pipeline code 喺 Hermes（Linux，`/opt/data/project_x_learning`），2026-09-28 匯出到 repo B `export/2026-09-28/`（本 repo 副本：`data/legacy/hermes_project_x_2026/export_2026-09-28/`）。
- Repo 冇 Actions secret，亦冇 commit secret。

### 1.3 兩邊嘅數據差異（要知道，唔好混淆）
| 項目 | A | B |
|---|---|---|
| 起始資金 | USD 1,280（2026-09-13 重設，HKD 10k）；舊時期 07-07 至 09-12 係 HKD 5k | USD 641.03（HKD 5k，2026-07-08） |
| 同期 NVDA | T001 買 1 股 @195.55（07-07），T002 08-05 TP 賣 @218.27（淨 +21.63） | 0.5 股 @196.93（07-08），08-05 時仲揸住 @211.94 |
| 富途 | —— | `futu_positions.json`：Roy 富途**模擬**戶口 NVDA 1 股 @194.00（2026-07-08 18:37），另有一張錯落嘅限價單 @100；之後冇再同步 |
| 止損執行 | 有（RKLB 09-21 TP 喺 hourly check 執行） | 冇（TSLA、RKLB flag=STOP 都冇賣） |
| 最新數據 | 2026-09-25 收市／09-28 MTM | 2026-09-28（每日更新） |
| 指標數值 | RKLB「MA50」= 66.06（其實係約 22 日均線；真 MA50 = 69.49，09-25） | 用真 MA50 |
| A 內部文件 | HANDOFF 寫 T001 @117.32 / T002 @128.40、資金 HKD 5k、09:00 排程 ← **全部過時／錯** | —— |
| A PnL 欄位 | `account.total_pnl_usd = −5.25`（只計 SOUN 未實現盈虧） | —— |

**A 真實帳目（已核對）**：現金 1,280.00 − 189.85（RKLB 3×62.95＋1.00 手續費）− 157.50（SOUN 25×6.26＋1.00）＋ 207.91（RKLB 賣出淨額）= **1,140.56** ✅。權益 = 1,140.56 + 25×6.05 = **1,291.81** ✅，對 1,280 = **+11.81（+0.92%）**。同期 SPY 764.29 → 771.35 = **+0.92%**（同大市打和）。RKLB 來回扣晒兩邊手續費嘅淨盈利係 **+18.06**（A 記錄嘅 19.06 冇計買入嗰 1.00 手續費）。

---

## 2. 重要發現（按嚴重程度排）

1. 🔴 **Secret 外洩**：`finnhub_config.json`、`marketaux_config.json`、`telegram_config.json`（入面有真嘅 key，長度分別係 40 / 40 / 46 字元，chat_id 10 位）喺 commit `9d9f8de` 已經入咗 **public** repo A。**所有 key 同 Telegram bot token 都要換。** 單靠刪檔唔夠，因為 git history 仍然有；換咗 key 之後，舊 key 喺 history 就冇用。
2. 🔴 **排程會死**：A 嘅 4 個 job 靠 Grok Bot automation，訂閱完咗就停；runner script 仲未 commit。
3. 🟠 **A 指標 bug**（`finnhub_api.get_tech_indicators`）：
   - `history(period="1mo")` 大約得 22 條 bar，所以「MA50」其實係約 22 日均線（已用 yfinance 驗證：RKLB 65.98 vs 真 MA50 69.49；NVDA 221.37 vs 215.79）。
   - bar 少過 26 條時 `ema26` 退化做 `closes[-1]`，signal line 亦用 `closes[0]` → MACD histogram 冇意義，所謂「MACD 看漲確認」其實係噪音。
   - 最後一行 `confidence + 5`（「低VIX加成」）**無條件**加，唔理 VIX 幾多。
   - RSI 用簡單平均，唔係 Wilder。
   - 成交量比用咗今日未完嘅 bar（A 喺 22:00、B 喺 21:30 計，一樣有問題）。
4. 🟠 **規則矛盾**：`rules.min_confidence = 0.75`，但 `vix_guardrails.NORMAL.min_confidence = 0.70`，所以 daily_report 用咗 0.70；`risk_manager` 用 ATR 止損，但持倉記錄用固定 `stop_loss_price`；手續費有時 flat $1、有時 0.5%。
5. 🟡 **數據衛生**：`signals.json` 1.1 MB 而且只會越嚟越大（網站要成個載入）；`profiles.json` 啲分析師數據全部係「未知（0位分析師）」（yfinance `.info` 攞唔到）→ 網站個「基本面」tab 同 Telegram 嘅分析師部分其實係空嘅。
6. 🟡 **Telegram 太多**：每日約 15 條（12 段日報＋3 段教學），仲未計開市、hourly、週報。
7. 🟡 **B 嘅問題**：唔執行止損、碎股、成交量比 bug（未收市 bar）、HKT 星期幾排程漏星期五、重複 commit、靠 LLM deliver。
8. ⚪ **DST**：美國 2026-11-01 轉冬令時。A 寫死 21:35 / 22:00 HKT，冬令時就會變成開市前；B 嘅 05:00 收市報告冬令時就啱啱撞正收市。一定要用 ET 計。

---

## 3. 合併後嘅目標系統

```
                ┌──────────── GitHub (fung2222/project-x-minimax, branch main) ────────────┐
 cron (UTC)     │ .github/workflows/px-scheduler.yml                                         │
 every 30 min ─▶│   python scripts/px_dispatch.py  ──▶ px/jobs/{open_monitor,daily,hourly,   │
 + weekly/health│                                           eod,weekly,health}.py            │
                │        │ reads config/settings.yaml, data/*.json, state/*.json             │
                │        │ fetches yfinance (+Finnhub quote fallback, Marketaux news)        │
                │        ├─▶ writes data/*.json, data/reports/*.md, state/*.json             │
                │        ├─▶ Telegram (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)                 │
                │        └─▶ git commit + push (GITHUB_TOKEN) ──▶ GitHub Pages rebuild        │
                │ index.html signals.html portfolio.html reports.html learn.html (static)   │
                └────────────────────────────────────────────────────────────────────────────┘
 Hermes (Roy desktop): clone + venv；監察 Actions 有冇失敗、回答 Roy、寫 veto/override、
 手動 workflow_dispatch、每週覆核、更新富途真倉鏡像。Hermes 只會喺 Roy 叫佢嘅時候改規則。
```

設計原則：
- **確定性優先**：所有交易決定都用 code（gates）做，唔靠 LLM 心情。Hermes 可以 **veto**（否決／暫停），但唔可以繞過硬規則。
- **一個 scheduler**：`config/settings.yaml → runtime.scheduler_owner` 係 `github_actions`（預設）或者 `hermes`。dispatcher 如果發現 `PX_RUNNER` 同 owner 唔夾就直接退出，防止兩邊同時跑、重複落單。
- **冪等（idempotent）**：`state/job_runs.json` 記住每個 job 每個美股交易日跑過未，重跑都唔會重複落單或者重複 send 訊息。
- **失敗就安全**：攞唔到數據就唔開新倉；SL/TP 都照用 Finnhub 報價執行；有問題就 send 一條 ⚠️ 訊息。

---

## 4. 保留／移植／放棄 清單

### 4.1 由 A 保留（改寫過）
| 功能 | 原檔 | 新位置 | 備註 |
|---|---|---|---|
| 報價、歷史數據 | `finnhub_api.py`（get_quote、get_all_quotes、get_vix_regime） | `px/data.py` | 加 retry、cache，Finnhub `/quote` 做 fallback |
| 技術指標 | `finnhub_api.get_tech_indicators` | `px/indicators.py` | **重寫**（見 §5.2） |
| 信號＋信心 | `finnhub_api`＋`analyzer.generate_signal` | `px/signals.py` | 保留 RSI 分區同調整結構，修好 bug |
| 機會掃描 | `analyzer.build_opportunity_picks` | `px/signals.py` | 保留 10 隻股，股價上限 = 25% 權益 |
| VIX guardrail | `vix_guardrail.py` | `px/risk.py` | 統一門檻（§5.1） |
| 紙上交易 / SL/TP | `risk_manager.py`、`_run_hourly_check.py` | `px/portfolio.py`、`px/jobs/hourly.py` | 自動執行、統一手續費 |
| 開市監控 | `_run_open_monitor.py` | `px/jobs/open_monitor.py` | 保留教學句同要睇嘅價位 |
| Telegram 發送 | `telegram_push.send_telegram_message` | `px/telegram.py` | 加分段、silent、retry |
| 新聞 | `finnhub_api.fetch_*news`、`telegram_push.get_today_news` | `px/news.py` | 只要持倉＋當日候選，最多 3 條 |
| 週報 | `weekly_report.py` | `px/jobs/weekly.py` | 「總交易 38 筆」改名做「信號命中率樣本」 |
| 命中率 | `analyzer.update_hit_rate` | `px/hitrate.py` | 規則不變（第 2 日 ±2%） |
| 基準比較 | `benchmark.py` | `px/portfolio.py` | 對比 SPY（由重設日開始計） |
| 決策簡報 / 教學 | `_latest_decision_brief.json`、Grok Bot 寫嘅教學 | `data/daily_report.json → decisions/teaching/scenarios` | 用範本生成；Hermes 可以加一段註解 |

### 4.2 由 B 移植（按輸出格式重寫，因為冇 source）
| 功能 | B 嘅來源 | 新位置 |
|---|---|---|
| P&L／權益曲線（lightweight-charts 4.1.3） | `js/pnl_chart.js`、`data/pnl_history.json` | `assets/js/charts.js`、`data/pnl_history.json`（加 SPY 基準線） |
| 報告存檔 | `reports.html`、`data/reports_index.json`、`data/*_report_*.md/html` | `reports.html`、`data/reports/index.json`、`data/reports/YYYY-MM-DD_<job>.md` |
| trend score＋MA20/MA50 結構＋5 日/20 日變幅 | `daily_report.signals[].indicators` | `px/indicators.py` |
| 距離止損 / 止盈（pp）＋ risk_flag | `portfolio.positions[]` | `data/portfolio.json positions[]` |
| 倉位比例 bar、HKD 換算 | `portfolio.html`、`index.html` | 新 `portfolio.html`、`index.html` |
| 每隻股嘅「點解」同術語速查 | `signals.html` | 新 `signals.html` |
| 學習中心 | `learn.html` | 新 `learn.html`（改成 25% / 20% / SL 規則，刪走碎股同 −10%/+20% 講法） |
| 收市 snapshot（EOD） | 05:00 收市報告 | `px/jobs/eod.py`（ET 16:20，靜音 Telegram） |
| 富途真倉鏡像 | `data/futu_positions.json` | `data/futu_live.json`（淨係人手更新，永遠唔會自動落單） |
| 共用 JS（loadJSON 加 cache-bust、format） | `js/common.js` | `assets/js/common.js` |

### 4.3 放棄
| 項目 | 原因 |
|---|---|
| A 嘅「基本面」tab、Telegram 分析師詳情、「增強指標」（板塊輪動 / 宏觀 / 多時框） | 數據係空，或者對 3 隻倉嘅細戶口冇行動價值；只會令訊息更長 |
| A 嘅 12 段日報格式 | 改成 ≤3 段 |
| hourly 每日第一次嘅「正常」heartbeat | 開市監控已經有；hourly 只係有事先 send |
| `signals.json`（1.1 MB 單一檔案） | 改成 `data/signals_history/YYYY-MM.jsonl`（按月分檔），網站唔使載 |
| `ProjectX_Portfolio.xlsx`、`create_portfolio.py`、`run_dashboard.py`、`start_server.bat`、`market_open_alert.py`、`enhanced_indicators.py` | 冇人用、重複或者只係裝飾；搬去 `docs/archive/legacy_code/` |
| B 嘅 08:30 晨早 snapshot | 冇新資訊 |
| B 嘅碎股 / 「0.5–1 注」 | 同富途整股執行、25% 上限唔夾 |
| B 嘅 −10% / +20% SL/TP | Roy 已經定咗 +10% TP、SL 5–10%（§5.3） |
| B 嘅 PWA icon 組（`img/icon-*.png/svg`、`icon-generator.html`） | 只係裝飾；favicon 留一個就夠 |
| 舊文件 `PROJECT_X_HANDOFF.md`、`GROK_BOT_SYSTEM_PROMPT.md`、`PROJECT_X_MANUAL.md`、`PROJECT_X_BUILD_SPEC.md`、`PROJECT_X_INVESTMENT_PLAN.*` | 過時；搬去 `docs/archive/`，頂部加一句「已被 MERGE_PLAN 取代」 |

---

## 5. 統一規則（Roy 嘅規則為準）

### 5.1 帳戶同 VIX guardrail
| 參數 | 值 |
|---|---|
| 模式 | `paper`（觀察模式）。**真錢永遠由 Roy 自己喺富途落單** |
| 資金 | HKD 10,000；`start_equity_usd = 1280.00`；`rebase_date = 2026-09-13` |
| 最多持倉 | NORMAL 3 / CAUTION 2 / DEFENSIVE 1 |
| 每隻上限 | 權益 25% |
| 最低現金 | 權益 20%（開倉**之後**都要做到） |
| 最低信心 | NORMAL **0.75** / CAUTION 0.80 / DEFENSIVE 0.85（0.75 係最低，唔准再低） |
| 單筆風險 | (entry − SL) × shares ≤ 權益 2%（大約 USD 25） |
| 每日新開倉 | 最多 1 次（平倉唔計） |
| 同主題 | 每個主題最多揸 1 隻（主題見 §5.5） |
| VIX 分級 | `<20 NORMAL`、`20–30 CAUTION`、`>30 DEFENSIVE`（用 `^VIX` 最新價） |
| DEFENSIVE | 唔會自動全部平倉；原有 SL/TP 照舊；只准信心 ≥0.85 嘅 setup A；每條訊息頂部加 🔴 |
| 做空 | 永遠唔做。冇持倉嘅 SELL 信號只係做提示 |

### 5.2 指標（`px/indicators.py`）
- 數據：`yfinance.Ticker(t).history(period="1y", interval="1d", auto_adjust=False)`，最少要 120 條 bar，唔夠就唔出信號。
- **Completed bars**：如果 ET 而家仲未到 16:00，而最後一條 bar 係今日 → 計指標時要剔走佢。即時價淨係用嚟做 SL/TP 同顯示。
- `rsi14`：Wilder —— `gain.ewm(alpha=1/14, adjust=False).mean()`，`loss` 一樣計法。
- `ma20`、`ma50`：簡單移動平均（SMA）。`ma200` 可選（只作顯示）。
- `macd`：`ema12 − ema26`（`adjust=False`），`signal = ema9(macd)`，`hist = macd − signal`；`hist_rising = hist[-1] > hist[-2]`。
- `atr14`：Wilder TR 平均。
- `vol_ratio`：最後一日**已收市**嘅成交量 ÷ 之前 20 日平均。
- `chg_5d_pct`、`chg_20d_pct`、`price_vs_ma20_pct`、`price_vs_ma50_pct`、`ma20_vs_ma50_pct`。
- `trend_score`（參考 B 嘅思路，範圍 −6..+6）：
  - 價 vs MA50：>0 → +2；0 至 −10% → −1；<−10% → −2
  - 價 vs MA20：>0 → +1；<0 → −1
  - MA20 vs MA50：>+1% → +1；<−1% → −1
  - RSI：50–70 → +1；<35 → −1；其他 → 0
  - 5 日變幅：>+3% → +1；<−3% → −1
  - 標籤：≥+3「上升趨勢」、−2..+2「中性震盪」、≤−3「下降趨勢」

### 5.3 信號同信心（`px/signals.py`）
沿用 A 嘅 RSI 分區（Roy 已經習慣），修好 bug：
```
RSI<30 → BUY, conf=min(90, 70+(30-rsi)*2)
30≤RSI<40 → BUY, conf=min(80, 60+(40-rsi))
40≤RSI<45 → HOLD 55 ; 62<RSI≤68 → HOLD 55 ; 45≤RSI≤62 → HOLD 50
68<RSI≤75 → SELL, conf=min(80, 55+(rsi-68)) ; RSI>75 → SELL, conf=min(90, 60+(rsi-75)*2)
BUY adjustments: macd hist>0 → +8 else −10 ; vol_ratio≥1.2 → +5 ; vol_ratio<0.5 → −8
                 close>ma50 → +5 else −5 ; trend_score≥3 → +5 ; trend_score≤−3 → −10
SELL adjustments: macd hist<0 → +5
Regime: CAUTION −10 ; DEFENSIVE −20        (NO unconditional +5)
Owned ticker with BUY → HOLD (唔重複買) ; clamp 20..95
```

### 5.4 專業過濾 gates（`px/decide.py`，取代 LLM 判斷）
BUY 候選（核心＋次要＋機會）一定要**全部過晒**先會開紙上倉：
| Gate | 條件 |
|---|---|
| G1 信心 | `confidence ≥ regime_min×100` |
| G2 setup | **A「升勢回調」**：close ≥ MA50 且 30 ≤ RSI ≤ 45 → 最多 25% 權益；或者 **B「超賣反轉」**：RSI ≤ 30 且 `hist_rising` 且 close > 前一日 close → 最多 12.5% 權益（半注） |
| G3 成交量 | setup A：vol_ratio ≥ 0.8；setup B：vol_ratio ≥ 1.0 |
| G4 趨勢 | trend_score > −4 |
| G5 組合 | 持倉數 < regime 上限；同主題冇持倉；今日未開過新倉 |
| G6 金額 | `shares = floor(min(0.25·eq·size_factor, cash − 0.20·eq, 0.02·eq/(entry−SL)) / price)`；要 ≥1 股，而且金額 ≥ USD 50 |
| G7 事件 | 業績公布唔喺未來 3 個交易日（數據攞唔到就放行，但要寫低備註） |
| G8 冷靜期 | 5 個交易日內冇試過 SL 離場；3 個交易日內冇 TP 平過（對應「唔好 FOMO 追返」） |
| G9 Override | 唔喺 `config/overrides.yaml → blocklist`；`pause_new_entries: false` |
同時有幾個候選過晒 → 揀信心最高嗰個（同分就揀 vol_ratio 高啲嘅）。**每日最多 1 個。**
每個被拒嘅候選都要喺 `daily_report.decisions.skipped` 寫低第一個唔過嘅 gate（例如「SOFI 70%：G1 信心不足；G2 低於 MA50」）。網站同 Telegram 會顯示呢啲原因（呢個係 A 嘅教學強項）。

### 5.5 主題對照（G5 用）
`AI_SPEECH: SOUN, BBAI` · `SPACE: RKLB, ASTS, LUNR` · `QUANTUM: IONQ` · `FINTECH: SOFI, HOOD` · `EV: TSLA, RIVN` · `EVTOL: JOBY` · `AI_INFRA: NVDA, AMD, SMCI, ARM` · `MEGA_SOFT: MSFT, GOOGL, META` · `DATA_AI: PLTR`

### 5.6 止損 / 止盈 / 出場
- 開倉嗰陣：`SL = max(entry − 2×ATR14, entry×0.90)`，但 SL 最少要同 entry 差 5%（即係 SL ≤ entry×0.95）。`TP = entry×1.10`。
- 每次 job（open / daily / hourly / eod）都要檢查：`last ≤ SL` → 以 last 價紙上賣出（reason `STOP_LOSS`）；`last ≥ TP` → `TAKE_PROFIT`。**會自動執行**（B 就係冇做到呢樣）。
- 持有 ≥15 個交易日，而且 PnL 喺 −3% 至 +3% 之間 → 喺訊息加「REVIEW」提示（唔會自動賣）。
- 加倉：**預設關閉**（`rules.allow_add: false`）。A 個加倉邏輯同「唔攤平」教學有矛盾。
- （要 Roy 決定）部分止盈：`rules.tp_mode: fixed`（預設）或者 `partial_trail`（≥2 股時 +10% 先賣一半，剩低嘅 SL 移去成本價）。
- 手續費：每邊 `fee = max(1.00, round(0.005 × notional, 2))` USD（同 A 歷史記錄完全吻合）。
- 匯率：`HKD=X`（yfinance），攞唔到就用 7.80。

---

## 6. 統一時間表（以 ET 為準，HKT 自動跟 DST）

美股時間：夏令時（EDT，**到 2026-11-01**，以及 2027-03-14 之後）09:30–16:00 ET = **21:30–04:00 HKT**；冬令時（EST，2026-11-01 → 2027-03-14）= **22:30–05:00 HKT**。

| Job | ET | HKT（夏令時） | HKT（冬令時） | 做乜 | Telegram |
|---|---|---|---|---|---|
| `open_monitor` | 09:35 | 21:35 | 22:35 | VIX/regime、持倉對昨收、SL/TP 檢查＋執行、今晚要睇嘅價位、開市教學句 | **一定 send** 1 條 |
| `daily` | 10:00 | 22:00 | 23:00 | 全股票池指標／信號、gates、紙上開倉（最多 1 個）、SL/TP、決策／教學／情境、報告存檔、網站數據 | ≤3 條 |
| `hourly` | 10:30, 11:30, 12:30, 13:30, 14:30, 15:30 | 22:30 … 03:30 | 23:30 … 04:30 | 持倉 MTM、SL/TP 執行、近止損（<2%）、大波動（對上次 ≥3%）、regime 變化 | **有事先 send** |
| `eod` | 16:20 | 04:20 | 05:20 | 收市價 MTM、SL/TP（收市價）、`pnl_history` 加一行、命中率、收市報告 md、網站 | 1 條**靜音** |
| `weekly` | —— | 逢星期一 09:30 | 逢星期一 09:30 | 7 日回顧、交易、命中率、對比 SPY、教學重點 | 1–2 條 |
| `health` | —— | 星期二至六 09:05 | 星期二至六 09:05 | 檢查上一個交易日 open/daily/eod 有冇跑到、數據新唔新鮮、Actions 有冇失敗 | **有問題先 send** |

- 美股假期同半日市：用 `exchange_calendars`（`XNYS`）判斷；休市日所有美股 job 都唔跑（weekly 照跑）。2026 年仲有嘅假期：11-26 感恩節（11-27 半日市，13:00 ET 收市，eod 改 13:20 ET）、12-25（12-24 半日市）。
- **dispatcher 邏輯**（`scripts/px_dispatch.py`）：
  1. `now_et = now(ZoneInfo("America/New_York"))`；如果今日唔係 XNYS 交易日，就只考慮 weekly/health。
  2. 逐個 job：`due = session_date + job_time_et`；條件係 `due ≤ now_et ≤ due + max_late`（open 45 分鐘、daily 90 分鐘、hourly 40 分鐘、eod 180 分鐘），而且 `state/job_runs.json[session_date][job]` 未有記錄 → 就跑。
  3. 一次最多跑 2 個 job（例如 daily＋hourly）；跑完寫低 `{status, started, finished, commit}`。
  4. 有任何 exception → 寫低 `status: failed`＋發 ⚠️ Telegram（每個 job 每日最多 1 次），然後 exit 1，令 Actions 顯示紅色。
- **GitHub Actions cron（UTC）**：`7,37 13-21 * * 1-5`（覆蓋夏令同冬令時嘅 ET 09:07–17:37 / 08:07–16:37）；weekly＋health：`5,35 1 * * 1-6`。揀 :07/:37 係為咗避開整點嘅排隊延遲。
- 預期延遲：Actions 排程有時會遲 5–30 分鐘，dispatcher 嘅 `max_late` 已經預留咗。

---

## 7. Telegram 規格（`px/messages.py`）

通用：`parse_mode=HTML`、`disable_web_page_preview=true`；每條 ≤3,500 字元（超過就自動分段）；eod 用 `disable_notification=true`；失敗 retry 3 次（等 2s/5s/10s）。每條訊息最尾都有一行「紙上模擬；真錢落單由你喺富途執行。」＋網站連結。

### 7.1 open_monitor（一定 send，1 條）
```
<b>🔔 開市監控</b> {YYYY-MM-DD HH:MM} HKT（ET {HH:MM}）
{🟢/🟡/🔴} 市況：<b>{正常市場/謹慎/防禦}</b>（VIX {vix} / {REGIME}）
SPY {spy} ({spy_chg:+.2f}%) · QQQ {qqq} ({qqq_chg:+.2f}%)
權益 USD {equity}（HK${equity_hkd}）· 現金 {cash_pct}%

<b>📍 今晚要睇嘅價位</b>
• {TICKER} 止損 ${sl} / 止盈 ${tp}（而家 ${px}，距SL {dist_sl}%）
<b>📦 持倉</b>
• <b>{TICKER}</b> x{shares} @ ${px}（{pnl_pct:+.2f}%｜vs昨收 {chg:+.1f}%｜{HOLD/STOP_LOSS 已執行/TAKE_PROFIT 已執行}）
{if executed: ✅ 紙上已{止損/止盈}：{TICKER} x{n} @ ${px}，淨 {pnl_usd:+.2f}}
📚 {開市教學一句}
```

### 7.2 daily（最多 3 條）
**第 1 條：決策**
```
<b>📘 Project X 每日決策 — {date}</b>（{regime_emoji} VIX {vix}）
<b>✅ 今日動作</b>
• {e.g. 紙上買入 IONQ x2 @ $44.9（setup A，信心 78%，SL $41.2 / TP $49.4，佔 7.0%）}
• {e.g. HOLD SOUN @ 6.05（距SL 4.8%）}
• {e.g. 冇新倉：最高 SOFI 70% → G1 信心不足、G2 低於 MA50}
<b>💼 組合</b> 權益 USD {eq}（{ret:+.2f}% vs 起始；SPY {spy_ret:+.2f}%）· 現金 {cash_pct}% · 持倉 {n}/{max}
```
**第 2 條：信號表**（核心＋次要一行一隻；機會掃描只列 BUY 候選同 top 3）
```
<b>📊 信號</b>
NVDA  $225.1  RSI 44  趨勢 +3  HOLD 60%
RKLB  $74.0   RSI 68  趨勢 +4  SELL 65%（冇持倉，唔做空）
…
<b>💡 機會</b> SOFI $16.6 BUY 70% ✗G1 ✗G2 · IONQ …
<b>📰 持倉新聞</b>（最多 3 條，每條一行）
```
**第 3 條：教學＋情境**（範本生成；Hermes 可以喺 22:30 前用 `px_note.py` 補充）
```
<b>🎓 今日教學</b> {一段 ≤300 字}
<b>🔮 情境</b> 基準：… ／ 樂觀：… ／ 悲觀：…
<b>⛔ 失效條件</b> {e.g. SOUN 收市 < 5.76 → 紙上止損}
```

### 7.3 hourly（有 alert 先 send）
Alert 種類：`STOP_LOSS 已執行`、`TAKE_PROFIT 已執行`、`NEAR_SL（<2%）`、`BIG_MOVE（對上次 ≥3%）`、`VIX_REGIME 變化`。每種 alert 每隻股每個交易日最多 send 1 次（NEAR_SL 如果再跌多 1pp 可以再 send）。
```
<b>⚠️ 持倉警報</b> {HH:MM} HKT
• ✅ 紙上止盈 RKLB x3 @ $69.65（入 62.95，淨 +18.06 / +9.5%）
• ⚠️ SOUN 距止損 1.6%（$5.85 vs SL $5.76）
權益 USD {eq} · 現金 {cash_pct}%
```

### 7.4 eod（靜音，1 條）
```
<b>🌙 收市</b> {session_date} ET ｜ 權益 USD {eq}（今日 {day_pnl:+.2f}，累計 {ret:+.2f}%）｜ SPY {spy_day:+.2f}%
{持倉一行一隻：TICKER close / pnl% / 距SL}
今日交易：{none | 列表} ｜ 報告：{site}/reports.html
```

### 7.5 weekly（星期一 09:30）
沿用 A 嘅 `WeeklySummary` 結構：市場概覽 → 本週交易（每筆一行）→ 組合 vs SPY → 信號統計（改名做「信號命中率（樣本 N）」，**唔好**叫做「總交易」）→ 5 個教學重點 → 下週觀察名單。

### 7.6 health / 失敗
```
<b>🛠 Project X 系統警告</b> {job} 喺 {session_date} {未有跑／失敗}：{error 一行}
Actions：https://github.com/fung2222/project-x-minimax/actions
```

---

## 8. 網站規格（GitHub Pages，純靜態，root 目錄）

共用：`assets/css/style.css`（用 B 嘅白底 teal 風格）、`assets/js/common.js`（B 嘅 `loadJSON(path)`＋`?t=Date.now()`、formatUSD/HKD/Pct、escapeHTML）、頂部 nav 5 個 link、頁腳免責聲明。每頁都顯示「更新時間」；如果 `data/meta.json.last_success` 已經超過 1 個交易日 → 頂部出紅色 banner「數據已過時」。

| 頁面 | 內容（由上至下） | 用嘅數據 |
|---|---|---|
| `index.html` 總覽 | 今日動作卡（decisions.actions）→ 4 格 KPI（權益 USD+HKD、累計回報 vs SPY、現金 %、VIX/regime）→ 持倉卡（進度條顯示價位喺 SL 同 TP 之間邊度）→ 迷你權益曲線（近 30 日）→ 機會候選＋被拒原因 → 風險提醒 | `daily_report.json`、`portfolio.json`、`pnl_history.json`、`meta.json` |
| `signals.html` 訊號 | 核心＋次要＋機會卡：價、變幅、信號、信心、trend score＋標籤、RSI、MA20/MA50 差距、vol_ratio、ATR、「點解」原因、gates ✓/✗、建議 SL/TP → 信號命中率（hit/partial/miss bar）→ 術語速查 | `daily_report.json`、`hit_rate.json` |
| `portfolio.html` 組合 | 權益曲線 vs SPY（lightweight-charts 4.1.3）→ KPI（起始 1,280、已實現、未實現、手續費）→ 持倉表 → 倉位比例 bar → 交易帳本（新嘅喺上面）→ 規則卡（§5）→ 富途真倉鏡像（寫明「人手更新，最後同步 {date}」）→ 摺埋嘅「舊時期記錄」（HKD 5k 時期＋Hermes 舊 book） | `portfolio.json`、`pnl_history.json`、`futu_live.json`、`legacy/*.json` |
| `reports.html` 報告 | 報告列表（日期、job、一句摘要、當日 P&L）→ 撳入去睇 md（前端用 `marked` render） | `reports/index.json`、`reports/*.md` |
| `learn.html` 學習 | B 嘅術語＋富途操作步驟＋新手錯誤；原則改成 25% / 20% 現金 / SL 5–10% / TP 10%；學習階段改成 A 嘅 PHASE_4_LIVE_PREP | 靜態 |

唔需要後端。唔好加 PWA／service worker（會 cache 舊數據）。加一個 `.nojekyll`。

---

## 9. 數據 schema v3（全部放 `data/`，UTF-8，`ensure_ascii=False`，indent 2）

### 9.1 `data/portfolio.json`
```json
{
  "schema": "px.portfolio.v3",
  "updated_at": "2026-09-28T04:15:22+08:00",
  "account": {
    "mode": "paper", "phase": "PHASE_4_LIVE_PREP",
    "capital_hkd": 10000, "start_equity_usd": 1280.00, "rebase_date": "2026-09-13",
    "cash_usd": 1140.56, "equity_usd": 1291.81, "fx_usdhkd": 7.83,
    "realized_pnl_usd": 18.06, "unrealized_pnl_usd": -5.25, "fees_open_positions_usd": 1.00,
    "total_return_usd": 11.81, "total_return_pct": 0.92,
    "fees_total_usd": 3.04, "cash_pct": 88.3, "deployed_pct": 11.7
  },
  "positions": [{
    "ticker": "SOUN", "bucket": "opportunity", "theme": "AI_SPEECH", "setup": "legacy",
    "shares": 25, "entry_price": 6.26, "entry_date": "2026-09-13", "open_trade_id": "T004",
    "entry_fee_usd": 1.00, "stop_loss": 5.76, "take_profit": 6.89,
    "last_price": 6.05, "last_price_at": "2026-09-28T04:15:22+08:00", "price_source": "yfinance",
    "value_usd": 151.25, "unrealized_pnl_usd": -5.25, "unrealized_pnl_pct": -3.35,
    "dist_to_sl_pct": 4.79, "dist_to_tp_pct": 13.88, "risk_flag": "OK",
    "held_trading_days": 10, "thesis": "tactical oversold satellite; AI voice small-cap"
  }],
  "trades": [ /* §13 ledger rows */ ],
  "rules_ref": "config/settings.yaml"
}
```
`risk_flag`：`OK` | `NEAR_SL`（<2%）| `NEAR_TP`（<2%）| `REVIEW`（時間止損）。（`STOP` 永遠唔會長期存在，因為一穿就即刻執行。）

### 9.2 Ledger row（`trades[]`）
```json
{"id":"T005","era":"hkd10k","ts":"2026-09-21T23:57:11+08:00","session_date":"2026-09-21",
 "ticker":"RKLB","side":"SELL","shares":3,"price":69.65,"fee_usd":1.04,
 "reason":"TAKE_PROFIT","link_id":"T003","realized_pnl_usd":18.06,"realized_pnl_pct":9.51,
 "note":"hourly check: 69.65 ≥ TP 69.25"}
```
`era`：`hkd5k_v1`（2026-07-07 → 09-12，唔計入現時權益）| `hkd10k`（現行）。`reason`：`ENTRY_A` | `ENTRY_B` | `STOP_LOSS` | `TAKE_PROFIT` | `MANUAL` | `LEGACY`。

### 9.3 `data/daily_report.json`
```json
{
  "schema": "px.daily.v3", "session_date": "2026-09-25", "generated_at": "2026-09-25T22:01:38+08:00",
  "job": "daily", "data_note": "指標用已收市日 bar；即時價只作 SL/TP 及顯示",
  "market": {"vix": 15.24, "regime": "NORMAL", "regime_zh": "正常市場", "spy": 769.05, "spy_chg_pct": 0.24,
             "qqq": 743.92, "qqq_chg_pct": 0.38, "fx_usdhkd": 7.83},
  "guardrail": {"max_positions": 3, "min_confidence": 0.75},
  "signals": [{
    "ticker": "NVDA", "name": "NVIDIA", "bucket": "core", "theme": "AI_INFRA",
    "price": 225.09, "change_pct": 0.23, "signal": "HOLD", "confidence": 60,
    "indicators": {"rsi14": 43.9, "ma20": 221.65, "ma50": 215.79, "price_vs_ma20_pct": 1.6,
                   "price_vs_ma50_pct": 4.3, "ma20_vs_ma50_pct": 2.7, "macd_hist": 0.8, "hist_rising": true,
                   "atr14": 5.1, "vol_ratio": 0.92, "chg_5d_pct": 1.2, "chg_20d_pct": 3.0,
                   "trend_score": 3, "trend_label": "上升趨勢"},
    "reasons": ["RSI 44 中性偏低", "價高於 MA50"], "suggested_sl": 214.9, "suggested_tp": 247.6,
    "gates": {"G1": false, "G2": true, "...": "..."}, "owned": false, "news": []
  }],
  "opportunity": [ /* same shape, bucket = "opportunity" */ ],
  "decisions": {"actions": ["HOLD SOUN @ 6.09 …"], "entries": [], "exits": [],
                "skipped": [{"ticker": "SOFI", "confidence": 70, "failed": ["G1", "G2"], "why": "低於 MA50＋量不足"}]},
  "portfolio_summary": {"equity_usd": 1292.81, "cash_pct": 88.2, "positions": 1, "total_return_pct": 1.0, "spy_return_pct": 0.62},
  "teaching": "…", "scenarios": {"base": "…", "bull": "…", "bear": "…"}, "invalidation": ["…"],
  "hermes_note": null
}
```

### 9.4 其他檔案
| 檔案 | 格式 |
|---|---|
| `data/pnl_history.json` | `[{"date":"2026-09-14","equity_usd":1282.05,"cash_usd":932.65,"total_return_pct":0.16,"spy_close":760.88,"spy_return_pct":-0.45,"positions":[{"ticker":"RKLB","close":62.55,"value_usd":187.65}]}]`（eod 每個交易日加一行，同日重跑就覆蓋） |
| `data/market_snapshot.json` | 最近一次 job 嘅 VIX/SPY/QQQ/FX＋持倉報價（`label` = job 名） |
| `data/hit_rate.json` | `{"rules":{…},"total":38,"hits":16,"partials":13,"misses":9,"neutrals":9,"hit_rate_pct":42.1,"by_month":{…}}` |
| `data/signals_history/YYYY-MM.jsonl` | 每行一個 signal（精簡欄位：date,ticker,signal,confidence,price,rsi14,ma50,trend_score,outcome） |
| `data/reports/index.json` | `{"reports":[{"date":"2026-09-25","job":"daily","file":"2026-09-25_daily.md","summary":"…","equity_usd":1292.81,"day_pnl_pct":0.1}]}` |
| `data/reports/YYYY-MM-DD_<job>.md` | Telegram 內容嘅 Markdown 版本（唔好有 HTML tag） |
| `data/futu_live.json` | `{"source":"manual","last_synced":null,"stale":true,"account":"Futu live","positions":[],"note":"由 Roy 提供；Hermes 人手更新；永不自動落單"}` |
| `data/meta.json` | `{"last_success":{"open_monitor":"…","daily":"…","hourly":"…","eod":"…","weekly":"…"},"version":"3.0.0"}` |
| `data/legacy/hermes_project_x_2026/` | B 嘅 `data/*` 原封不動複製（唯讀） |
| `data/legacy/minimax_v1/` | A 舊嘅 `signals.json`、`profiles.json`、`Reports/*`（HKD 5k 時期＋09-13 至 09-28 嘅 Grok Bot 報告） |
| `state/job_runs.json` | `{"2026-09-25":{"open_monitor":{"status":"ok","finished":"…"},"daily":{…}}}`（保留 30 日） |
| `state/alerts_sent.json` | 用嚟去重（alert key → 時間） |

---

## 10. 目標 repo 結構＋舊檔對照

```
project-x-minimax/
├── README.md                      # 5 行簡介 + 連結去 docs/MERGE_PLAN.md
├── .nojekyll
├── .gitignore                     # .env, *_config.json, __pycache__/, .venv/, venv/, *.pyc
├── .env.example                   # 淨係變數名，冇 value
├── requirements.txt
├── config/
│   ├── settings.yaml              # 規則、股票池、主題、時間表、Telegram 開關、runtime
│   └── overrides.yaml             # pause_new_entries / blocklist / notes（Hermes 按 Roy 指示改）
├── px/
│   ├── __init__.py  config.py  clock.py  data.py  indicators.py  signals.py
│   ├── decide.py  portfolio.py  risk.py  hitrate.py  news.py
│   ├── telegram.py  messages.py  reports.py  sitedata.py
│   └── jobs/ __init__.py open_monitor.py daily.py hourly.py eod.py weekly.py health.py
├── scripts/
│   ├── px_dispatch.py             # 排程入口（Actions / Hermes 都係叫呢個）
│   ├── migrate_v3.py              # 一次性：舊 A → v3，匯入 B 做 legacy
│   ├── backfill_pnl_history.py    # 一次性：由 2026-09-14 補返權益曲線
│   ├── px_manual.py               # 人手平倉／開倉（要 Roy 批准）
│   ├── px_note.py                 # Hermes 為當日報告加註解
│   ├── px_override.py             # pause/resume/block/unblock
│   ├── px_futu.py                 # 更新富途真倉鏡像
│   └── selftest.py                # 驗收測試（§16）
├── tests/  test_indicators.py test_ledger.py test_clock.py test_decide.py
├── data/   (§9)
├── state/  job_runs.json alerts_sent.json last_run_label.txt
├── index.html signals.html portfolio.html reports.html learn.html
├── assets/ css/style.css  js/common.js  js/charts.js  img/favicon.svg
├── docs/   MERGE_PLAN.md  COMPARISON.md  archive/ (舊文件 + legacy_code/)
└── .github/workflows/ px-scheduler.yml  px-selftest.yml
```

| 舊（A root） | 新 | 點處理 |
|---|---|---|
| `finnhub_api.py` | `px/data.py`、`px/indicators.py`、`px/signals.py`、`px/news.py` | 拆開；指標重寫 |
| `analyzer.py` | `px/jobs/daily.py`、`px/signals.py`、`px/hitrate.py` | 移植 |
| `risk_manager.py`、`position_tracker.py` | `px/portfolio.py`、`px/risk.py` | 移植＋統一手續費／SL |
| `vix_guardrail.py` | `px/risk.py` | 門檻用 §5.1 |
| `_run_open_monitor.py`、`_run_hourly_check.py` | `px/jobs/open_monitor.py`、`px/jobs/hourly.py` | 移植；刪走 box 路徑 |
| `telegram_push.py` | `px/telegram.py`、`px/messages.py` | 精簡格式 |
| `weekly_report.py`、`benchmark.py` | `px/jobs/weekly.py`、`px/portfolio.py` | 移植 |
| `portfolio.json`、`daily_report.json`、`signals.json`、`profiles.json` | `data/…` | 用 `migrate_v3.py` 轉 |
| `Reports/*` | `data/legacy/minimax_v1/Reports/` + `data/reports/` 索引 | 複製 |
| `_last_*.json`、`_latest_decision_brief.json`、`.last_hourly_quiet_hkt` | `state/` / 刪 | 轉換 |
| `*_config.json` | **刪**（改用 env） | 先換 key |
| `index.html`（A 單頁） | 5 頁新網站 | 重寫（用 B 版面） |
| 其他（xlsx、create_portfolio、run_dashboard、start_server.bat、market_open_alert、enhanced_indicators） | `docs/archive/legacy_code/` | 存檔 |

### 10.1 `config/settings.yaml`（完整初始內容）
```yaml
version: 3
account: {mode: paper, phase: PHASE_4_LIVE_PREP, capital_hkd: 10000, start_equity_usd: 1280.00, rebase_date: "2026-09-13", fx_fallback: 7.80}
rules:
  max_position_pct: 0.25
  min_cash_pct: 0.20
  risk_per_trade_pct: 0.02
  max_new_entries_per_day: 1
  min_notional_usd: 50
  sl_atr_mult: 2.0
  sl_min_pct: 0.05
  sl_max_pct: 0.10
  tp_pct: 0.10
  tp_mode: fixed            # fixed | partial_trail（要 Roy 批准先改）
  allow_add: false
  near_sl_alert_pct: 2.0
  big_move_alert_pct: 3.0
  time_review_days: 15
  cooldown_after_sl_days: 5
  cooldown_after_tp_days: 3
  earnings_blackout_days: 3
  fee: {min_usd: 1.00, rate: 0.005}
regimes:
  NORMAL:    {vix_max: 20, max_positions: 3, min_confidence: 0.75}
  CAUTION:   {vix_max: 30, max_positions: 2, min_confidence: 0.80}
  DEFENSIVE: {vix_max: 999, max_positions: 1, min_confidence: 0.85, setups: [A]}
universe:
  core: [NVDA, TSLA, RKLB]
  secondary: [AMD, MSFT, GOOGL, META, PLTR, ARM]
  opportunity: [SOUN, BBAI, IONQ, ASTS, LUNR, SOFI, HOOD, RIVN, JOBY, SMCI]
  index: [SPY, QQQ, "^VIX"]
  fx: "HKD=X"
themes:
  AI_SPEECH: [SOUN, BBAI]
  SPACE: [RKLB, ASTS, LUNR]
  QUANTUM: [IONQ]
  FINTECH: [SOFI, HOOD]
  EV: [TSLA, RIVN]
  EVTOL: [JOBY]
  AI_INFRA: [NVDA, AMD, SMCI, ARM]
  MEGA_SOFT: [MSFT, GOOGL, META]
  DATA_AI: [PLTR]
schedule_et:                 # America/New_York；dispatcher 用 XNYS 日曆
  open_monitor: {time: "09:35", max_late_min: 45}
  daily:        {time: "10:00", max_late_min: 90}
  hourly:       {times: ["10:30","11:30","12:30","13:30","14:30","15:30"], max_late_min: 40}
  eod:          {time: "16:20", early_close_time: "13:20", max_late_min: 180}
schedule_hkt:
  weekly: {weekday: MON, time: "09:30"}
  health: {weekdays: [TUE, WED, THU, FRI, SAT], time: "09:05"}
telegram:
  enabled: true
  site_url: "https://fung2222.github.io/project-x-minimax/"
  eod_silent: true
  hourly_only_on_alert: true
  max_daily_messages: 3
news: {enabled: true, max_items: 3, only_owned_and_candidates: true}
runtime:
  scheduler_owner: github_actions   # github_actions | hermes（一次只可以有一個）
  git_push: true
```

### 10.2 Secrets／環境變數（淨係名，永遠唔好 print value）
| 名 | 用途 | 放喺邊 |
|---|---|---|
| `FINNHUB_API_KEY` | Finnhub quote fallback＋公司新聞 | GitHub Actions secret；Hermes 本機 `.env` |
| `MARKETAUX_API_KEY` | 補充新聞 | 同上 |
| `TELEGRAM_BOT_TOKEN` | 發 Telegram | 同上 |
| `TELEGRAM_CHAT_ID` | Roy 個 chat | 同上 |
| `GITHUB_TOKEN` | Actions 自動提供，用嚟 push | 唔使設定（workflow `permissions: contents: write`） |
| `PX_RUNNER` | `github_actions` / `hermes` | workflow env / Hermes 本機 |
| `PX_DRY_RUN` | `1` = 唔 send Telegram、唔 push | 測試用 |
Code 只可以由 `os.environ` 讀（`python-dotenv` 會讀本機 `.env`）；缺咗就 fail，唔可以默默跳過。**唔准再用 `*_config.json`。**

### 10.3 `.github/workflows/px-scheduler.yml`
```yaml
name: px-scheduler
on:
  schedule:
    - cron: "7,37 13-21 * * 1-5"   # US session window (EDT & EST)
    - cron: "5,35 1 * * 1-6"       # 09:05/09:35 HKT: health (Tue-Sat) + weekly (Mon)
  workflow_dispatch:
    inputs:
      job:     {description: "force: none|open_monitor|daily|hourly|eod|weekly|health", default: "none"}
      dry_run: {description: "true = no Telegram, no push", default: "false"}
permissions:
  contents: write
concurrency:
  group: px-main
  cancel-in-progress: false
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      PX_RUNNER: github_actions
      FINNHUB_API_KEY:    ${{ secrets.FINNHUB_API_KEY }}
      MARKETAUX_API_KEY:  ${{ secrets.MARKETAUX_API_KEY }}
      TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
      TELEGRAM_CHAT_ID:   ${{ secrets.TELEGRAM_CHAT_ID }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12", cache: pip}
      - run: pip install -r requirements.txt
      - name: dispatch
        run: python scripts/px_dispatch.py --force "${{ inputs.job || 'none' }}" --dry-run "${{ inputs.dry_run || 'false' }}"
      - name: commit & push
        if: always() && (inputs.dry_run || 'false') != 'true'
        run: |
          git config user.name  "px-bot"
          git config user.email "px-bot@users.noreply.github.com"
          git add -A data state
          git diff --cached --quiet && exit 0
          git commit -m "px: $(cat state/last_run_label.txt 2>/dev/null || echo run)"
          for i in 1 2 3; do git pull --rebase origin main && git push origin main && break; sleep 5; done
```
`px-selftest.yml`：`on: [push, pull_request]`，只跑 `pytest -q` 同 `python scripts/selftest.py --offline`。

`requirements.txt`：`yfinance>=0.2.54`、`pandas>=2.2`、`numpy`、`requests`、`pyyaml`、`exchange_calendars>=4.5`、`python-dotenv`、`pytest`。

---

## 11. 遷移步驟（照次序做；每個階段都要過咗驗收先做下一個）

> 🔒 = 對外／改 repo 嘅動作，**一定要 Roy 明確批准**先做。

### 階段 0 — 保存現況（Grok Bot 停之前，今日做）🔒
1. 喺 `/workspace/project-x-minimax`（Grok Bot box）開一個 archive branch，**唔包 secret**：
   ```bash
   git switch -c archive/grokbot-2026-09-28
   git add _run_hourly_check.py _run_open_monitor.py portfolio.json _last_hourly_check.json Reports/
   git commit -m "archive: Grok Bot runner scripts + state as of 2026-09-28"
   git push -u origin archive/grokbot-2026-09-28
   git tag pre-merge-2026-09-28 && git push origin pre-merge-2026-09-28
   ```
2. 驗收：`gh api repos/fung2222/project-x-minimax/branches/archive/grokbot-2026-09-28` 應該 200；GitHub 上面見到 `_run_hourly_check.py`。

### 階段 1 — 安全（第一個工作日做）🔒
1. Roy 自己去換 key（Hermes 唔好接觸或者覆述 value）：
   - Finnhub：https://finnhub.io/dashboard → regenerate API key。
   - Marketaux：https://www.marketaux.com/account/dashboard → reset API token。
   - Telegram：@BotFather → `/revoke` → 揀返同一個 bot → 攞新 token（chat_id 唔變）。
2. 設定 secrets（會 prompt 你輸入，value 唔會入 shell history）：
   ```powershell
   gh secret set FINNHUB_API_KEY    -R fung2222/project-x-minimax
   gh secret set MARKETAUX_API_KEY  -R fung2222/project-x-minimax
   gh secret set TELEGRAM_BOT_TOKEN -R fung2222/project-x-minimax
   gh secret set TELEGRAM_CHAT_ID   -R fung2222/project-x-minimax
   gh secret list -R fung2222/project-x-minimax   # 應該見到 4 個名
   ```
3. Hermes 本機 `.env`（喺 repo root，已經 gitignore）：同樣 4 個變數。
4. 喺 `merge/v3` branch：`git rm --cached finnhub_config.json marketaux_config.json telegram_config.json`，同時更新 `.gitignore`。
5. 修正 repo homepage：`gh repo edit fung2222/project-x-minimax --homepage https://fung2222.github.io/project-x-minimax/` 🔒
6. 驗收：用舊 Telegram token call `getMe` 應該 401；喺新 branch，`git ls-files | Select-String '_config\.json$'` 應該冇結果，`git grep -nE '[0-9]{8,10}:[A-Za-z0-9_-]{30,}'`（Telegram token 格式）都應該冇結果。

### 階段 2 — Hermes 本機環境（Windows PowerShell）
```powershell
cd $env:USERPROFILE
git clone https://github.com/fung2222/project-x-minimax.git
cd project-x-minimax
git switch -c merge/v3
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # requirements.txt 喺階段 3 建立；未有就先 pip install 上面列嘅套件
git clone https://github.com/fung2222/project-x-2026.git ..\project-x-2026-readonly
```
驗收：`python -c "import yfinance, exchange_calendars, yaml; print('ok')"`。

### 階段 3 — 搭骨架＋移植 code（branch `merge/v3`）
1. 建立 §10 嘅目錄同 `config/settings.yaml`、`config/overrides.yaml`（`pause_new_entries: false`、`blocklist: []`）、`.env.example`、`requirements.txt`、`.nojekyll`。
2. 按 §10 對照表移植模組：
   - `px/config.py`：讀 YAML＋env；`get_secret(name)` 缺咗就 raise。
   - `px/clock.py`：`now_hkt()`、`now_et()`、`session_date()`、`is_trading_day(d)`、`is_early_close(d)`、`due_jobs(now)`（用 `exchange_calendars.get_calendar("XNYS")`）。
   - `px/data.py`：`history(ticker, period="1y")`（retry 3 次、同一次 run 入面有 cache）、`live_price(ticker)`（yfinance `fast_info.last_price` → history 最後 close → Finnhub `/quote` 嘅 `c`）、`fx_usdhkd()`、`vix()`。
   - `px/indicators.py`：§5.2（剔走未完嘅 bar）。
   - `px/signals.py`：§5.3；`build_signals(universe)` 回傳核心＋機會。
   - `px/decide.py`：§5.4 gates；回傳 `entries[]`、`skipped[]`。
   - `px/portfolio.py`：`load()/save()`、`mtm(prices)`、`execute_exit(ticker, price, reason)`、`execute_entry(sig, shares, sl, tp)`、`fee(notional)`、`equity()`、`spy_return_since(rebase)`；ledger 只可以加，唔可以改。
   - `px/risk.py`：regime、guardrail、`check_sl_tp(position, price)`。
   - `px/messages.py`：§7 範本。`px/telegram.py`：`send(text, silent=False)`，`PX_DRY_RUN=1` 時只 print。
   - `px/reports.py`：寫 md＋更新 `data/reports/index.json`。`px/sitedata.py`：寫 `meta.json`、`market_snapshot.json`。
   - `px/jobs/*.py`：每個都有 `run(ctx) -> dict`，而且要 idempotent（先查 `state/job_runs.json`）。
3. 驗收：`pytest -q` 全部過（§16 T1–T8）。

### 階段 4 — 數據遷移（`scripts/migrate_v3.py`，喺 branch 跑）
1. 讀舊 root `portfolio.json` → 寫 `data/portfolio.json`（§13 對賬數字必須完全一樣）。
2. `signals.json.signals[]` → `data/signals_history/2026-07.jsonl … 2026-09.jsonl`；`performance` → `data/hit_rate.json`。
3. 舊 `signals.json`、`profiles.json`、`Reports/`、`_latest_decision_brief.json` → `data/legacy/minimax_v1/`。
4. 複製 `..\project-x-2026-readonly\data\*` → `data/legacy/hermes_project_x_2026/`，加 `README.md`：「Hermes 舊系統 2026-07-08→08-05，HKD 5k book，止損冇執行，唯讀」。
5. `futu_positions.json` → `data/futu_live.json`，`stale: true`，保留 07-08 嗰筆記錄做 `history`，`positions: []`，等 Roy 提供最新真倉。
6. `scripts/backfill_pnl_history.py` → `data/pnl_history.json` 由 2026-09-14 開始（預期值見 §13.3）。
7. 由 `Reports/DailyBrief_*.txt`、`OpenMonitor_*.txt`、`WeeklySummary_*.txt` 建立 `data/reports/index.json`（2026-09-14 → 09-28），檔案複製做 `.md`。
8. 驗收：`python scripts/selftest.py --check-migration`。

### 階段 5 — 網站（§8）
1. 用 B 嘅 `css/style.css`、`js/common.js`、`js/pnl_chart.js` 做起點，放入 `assets/`，路徑統一 `data/`。
2. 寫 5 頁；A 舊 `index.html` 搬去 `docs/archive/legacy_code/index_v2.html`。
3. 本機預覽：`python -m http.server 8080` → 打開 http://localhost:8080/ 逐頁睇，DevTools console 唔可以有 error。
4. 驗收 §16 T12–T14。

### 階段 6 — 並行試跑（最少 2 個美股交易日）
1. 喺 Hermes 本機，美股時段內跑：`$env:PX_DRY_RUN="1"; python scripts/px_dispatch.py --force daily`，對比同晚 Grok Bot（如果仲運作）嘅輸出：同一個 SOUN 價、SL/TP 判斷、差唔多嘅信號。
2. 檢查 dry-run 印出嚟嘅 Telegram 長度、數量（daily ≤3）。

### 階段 7 — 切換（週末或者平日 20:00 HKT 前）🔒
1. **Roy 先喺 Grok Bot 關晒 4 個 Project X automation**（否則兩邊會同時 push 同 send）。
2. 開 PR `merge/v3 → main`，Roy review 後 merge：`gh pr create -R fung2222/project-x-minimax -B main -H merge/v3 -t "Project X v3 merge" -F docs/MERGE_PLAN.md`
3. 手動試一次：`gh workflow run px-scheduler.yml -R fung2222/project-x-minimax -f job=health -f dry_run=true`，然後 `gh run watch`。
4. 下一個交易日 21:35 / 22:00 HKT 要收到 open＋daily；網站 5 分鐘內更新。
5. 驗收 §16 T9–T11、T15。

### 階段 8 — 退役 B（§14）🔒

---

## 12. Hermes 做 operator 嘅權限

| 可以自己做 | 要 Roy 批准 | 永遠唔做 |
|---|---|---|
| 睇 Actions 狀態、log；`gh workflow run` 補跑 missed job；`px_note.py` 加教學註解；答 Roy 問題；寫週報補充 | 改 `settings.yaml` 規則、`px_manual.py` 人手開倉／平倉、`px_override.py block/pause`、更新 `futu_live.json`、push code、archive repo、換 key | 真錢落單；print／覆述任何 secret；喺 dispatcher 以外自己加 cron（避免重複跑）；改寫或者刪除 ledger 舊記錄 |

---

## 13. 紙上組合對賬（migrate_v3 必須得出完全一樣嘅數）

### 13.1 Ledger（`data/portfolio.json → trades[]`）
| id | era | 日期 | 股票 | 買賣 | 股數 | 價 | 手續費 | reason | 已實現 |
|---|---|---|---|---|---|---|---|---|---|
| T001 | hkd5k_v1 | 2026-07-07 | NVDA | BUY | 1 | 195.55 | 0.00（舊記錄冇寫） | LEGACY | — |
| T002 | hkd5k_v1 | 2026-08-05 | NVDA | SELL | 1 | 218.27 | 1.09 | TAKE_PROFIT | +21.63（保留原數） |
| R000 | hkd10k | 2026-09-13 | — | REBASE | — | — | — | REBASE | 現金設為 1,280.00 |
| T003 | hkd10k | 2026-09-13 | RKLB | BUY | 3 | 62.95（09-11 收市價） | 1.00 | LEGACY（setup 未分類） | — |
| T004 | hkd10k | 2026-09-13 | SOUN | BUY | 25 | 6.26（09-11 收市價） | 1.00 | LEGACY | — |
| T005 | hkd10k | 2026-09-21 | RKLB | SELL | 3 | 69.65 | 1.04 | TAKE_PROFIT（link T003） | **+18.06**（= 20.10 − 1.00 − 1.04） |
（新 id 由 T006 開始；reason 列表要加埋 `REBASE`。）

### 13.2 帳戶數字（用 SOUN = 6.05，即 2026-09-25 收市價）
- 現金 = 1280.00 − (188.85+1.00) − (156.50+1.00) + (208.95−1.04) = **1,140.56**
- 持倉 SOUN 25 × 6.05 = 151.25 → 未實現 **−5.25**（−3.35%）
- 權益 **1,291.81**；總回報 **+11.81 / +0.92%**；已實現 +18.06；未平倉嘅買入手續費 1.00；現時時期手續費總數 3.04
- SOUN：SL 5.76 / TP 6.89（沿用；migration 唔好用 §5.6 公式重算）；距 SL 4.79%，距 TP 13.88%
- 基準：SPY 764.29（09-11）→ 771.35（09-25）= +0.92%

### 13.3 `pnl_history.json` 預期值（backfill，收市價）
| 日期 | 權益 | 回報% | | 日期 | 權益 | 回報% |
|---|---|---|---|---|---|---|
| 09-14 | 1282.05 | +0.16 | | 09-21 | 1294.81 | +1.16 |
| 09-15 | 1277.05 | −0.23 | | 09-22 | 1293.56 | +1.06 |
| 09-16 | 1272.00 | −0.62 | | 09-23 | 1290.81 | +0.84 |
| 09-17 | 1286.11 | +0.48 | | 09-24 | 1293.06 | +1.02 |
| 09-18 | 1274.61 | −0.42 | | 09-25 | 1291.81 | +0.92 |
（09-21 起 RKLB 已經平倉，所以權益 = 1,140.56 + 25 × SOUN 收市價。Yahoo 之後修正數據的話，可以有 ±0.05 誤差。）

### 13.4 B 嘅 book（唔合併）
NVDA 0.5 @196.93、TSLA 0.5 @402.90、RKLB 1.0 @83.41、現金 257.70，08-05 總值 601.83（−6.12%）。只放喺 `data/legacy/hermes_project_x_2026/`，網站摺埋顯示，並註明「止損未執行，數字唔具參考性」。**唔好**計入權益曲線或者命中率。

---

## 14. Repo B（`fung2222/project-x-2026`）— 已改決定

> 草稿原本建議將 B 換成 redirect 同 archive。**Roy 決定唔做**：repo B 保持唯讀存檔（唔 push、唔 archive、唔刪），Hermes 匯出檔（`export/2026-09-28/`）原封不動。B 嘅 data＋export 已經複製入本 repo `data/legacy/hermes_project_x_2026/`。Hermes 喺切換後停同刪除所有 PX／Mag7 job（見 `docs/HERMES_HANDOVER.md §5`）。

---

## 15. 每日運作 SOP（逐個 job 做乜；Hermes 睇乜）

### 15.1 `open_monitor`（ET 09:35）
1. 讀 portfolio → 攞 VIX、SPY、QQQ、FX、每隻持倉嘅即時價同昨收。
2. `risk.check_sl_tp` → 有穿位就 `portfolio.execute_exit`（紙上，按即時價）。
3. 寫 `state/last_open.json`、`data/market_snapshot.json`、`data/reports/<date>_open.md`，更新 `meta.json`。
4. Telegram §7.1（一定 send）。
Hermes 檢查：22:00 HKT（夏令時）前有冇收到開市訊息；冇就睇 Actions log（§15.7）。

### 15.2 `daily`（ET 10:00）
1. 算全股票池指標（completed bars）→ 信號（§5.3）→ 機會掃描。
2. 用即時價 MTM → SL/TP。
3. `decide.run_gates` → 最多 1 個紙上開倉（價 = 即時價；SL/TP 按 §5.6）。
4. 生成 decisions / teaching / scenarios / invalidation（範本）→ `data/daily_report.json`；signals 加入 `signals_history/YYYY-MM.jsonl`。
5. 報告 md＋index；Telegram §7.2（≤3 條）。
Hermes（可選，22:30 HKT 前）：睇 `data/daily_report.json`，想補充教學就 `python scripts/px_note.py daily "…"`（會寫入 `hermes_note`，並加 send 1 條「🧠 Hermes 補充」）。

### 15.3 `hourly`（ET 10:30–15:30）
MTM → SL/TP 執行 → alert 規則（§7.3）同去重 → 冇 alert 就唔 send → 寫 `state/last_hourly.json`。

### 15.4 `eod`（ET 16:20；半日市 13:20）
收市價 MTM → SL/TP（按收市價）→ `pnl_history` 加一行（同日就覆蓋）→ 更新前幾日信號嘅命中率 outcome（第 2 日規則）→ `hit_rate.json` → 收市報告 md → Telegram §7.4（靜音）。

### 15.5 `weekly`（星期一 09:30 HKT）
7 日交易／權益變化／SPY／信號統計／教學 → `data/reports/<date>_weekly.md` → Telegram §7.5。Hermes 可以讀完之後喺 Telegram 補一段「本週反思」。

### 15.6 `health`（星期二至六 09:05 HKT）
檢查上一個 XNYS 交易日 `state/job_runs.json` 有冇 open/daily/eod 嘅 `ok`；`meta.json.last_success.eod` 應該 < 20 小時；`gh`／Actions API 最近 24 小時有冇 failure。有問題先 send §7.6。

### 15.7 出事點算
| 症狀 | 處理 |
|---|---|
| Actions 紅色：yfinance 429 / timeout | dispatcher 已經 retry 過；Hermes 等 30 分鐘睇下一次 cron；仲唔得就 `gh workflow run px-scheduler.yml -f job=<job>` |
| daily 過咗 max_late 未跑 | `gh workflow run px-scheduler.yml -f job=daily`。如果 ET 已過 15:00，會照做 SL/TP，但**唔會開新倉**（code 保證） |
| push conflict | workflow 已經自動 pull --rebase retry 3 次；仍然失敗就 Hermes 本機 `git pull --rebase` 然後睇 `state/` 有冇衝突，冇嘢就重跑 |
| Telegram 401 | token 失效／已換 → Roy 更新 `TELEGRAM_BOT_TOKEN` secret |
| 數據明顯錯（價格 0、跳 90%） | `data.py` sanity check：同昨收比 >50% 就當無效，唔會執行 SL/TP，會出 ⚠️；Hermes 通知 Roy |
| 想暫停開新倉（例如業績季、大事件） | Roy 同意之後：`python scripts/px_override.py pause --reason "…"` → commit/push |
| Roy 喺富途真係買咗／賣咗 | `python scripts/px_futu.py add --ticker X --shares N --price P --date YYYY-MM-DD`（淨係鏡像，唔會影響紙上 book） |
| 要轉用 Hermes 跑排程（例如 Actions 壞咗） | 改 `runtime.scheduler_owner: hermes` 並 push；Hermes 設定**唯一一個**本機排程：每 30 分鐘 `PX_RUNNER=hermes python scripts/px_dispatch.py`，跑完 `git add data state; git commit; git pull --rebase; git push`。Actions 見到 owner 唔啱就會自己退出 |

---

## 16. 驗收清單（`pytest` + `scripts/selftest.py`）

| # | 測試 | 通過條件 |
|---|---|---|
| T1 | Wilder RSI | 用固定序列（例如 closes 1..30 加 noise，寫死 fixture）同 `ta` 參考值差 < 0.1 |
| T2 | MA50 用真 50 bar | 60 條 bar fixture：`ma50 == mean(last 50)`；少過 120 bar → 唔出信號 |
| T3 | Completed bars | ET 11:00 時，今日 bar 唔會用嚟計指標；vol_ratio 用尋日成交量 |
| T4 | 信心冇無條件 +5 | NORMAL、RSI 50 → HOLD 50（唔係 55） |
| T5 | 手續費 | `fee(188.85)=1.00`、`fee(208.95)=1.04`、`fee(218.27)=1.09` |
| T6 | Ledger 對賬 | migration 後：cash 1140.56、SOUN@6.05 權益 1291.81、realized 18.06、return +0.92% |
| T7 | Gates | 09-25 SOFI fixture（RSI 30、低於 MA50、量不足、70%）→ 拒絕，failed 包含 G1 |
| T8 | SL 執行 | SOUN 價 5.70 → 生成 SELL STOP_LOSS 25 @5.70，fee 1.00，現金 +141.50，冇晒持倉 |
| T9 | DST | 2026-10-30（EDT）open_monitor 喺 21:35 HKT 到期；2026-11-02（EST）喺 22:35 HKT 到期 |
| T10 | 假期 | 2026-11-26 冇美股 job；2026-11-27 eod 喺 13:20 ET 到期 |
| T11 | 冪等 | 同一日 daily 跑兩次 → 只有 1 個開倉、Telegram 只 send 一次 |
| T12 | 網站 | 5 頁載入冇 console error；權益曲線有 ≥10 點；手機寬度 375px 睇得到 |
| T13 | 過時 banner | 將 `meta.json.last_success.daily` 改做 3 日前 → 出紅色 banner |
| T14 | Legacy | portfolio 頁「舊時期記錄」見到 B 嘅 601.83 同 A 嘅 T001/T002，而且冇計入 KPI |
| T15 | 上線 | 切換後第一個交易日：open＋daily 都收到（daily ≤3 條）、Pages 30 分鐘內更新、Actions 全綠 |
| T16 | Secret | repo 冇 `*_config.json`；Telegram token regex 喺 `git grep` 冇結果；log 冇 print secret |

---

## 17. Hermes 系統提示（可以直接貼）

```
你係 Project X 營運助手（Hermes）。對象：Roy Chan（香港，講廣東話，HKT UTC+8）。
系統：GitHub repo fung2222/project-x-minimax（唯一 repo），網站 https://fung2222.github.io/project-x-minimax/。
規格：docs/MERGE_PLAN.md（第 5 節規則、第 6 節時間表、第 15 節 SOP、第 12 節權限）。有衝突一律以規格為準。
模式：觀察模式 paper trading。HKD 10,000 ≈ USD 1,280。最多 3 隻、每隻 ≤25%、現金 ≥20%、信心 ≥0.75、TP +10%、SL 5–10%。
Roy 鍾意高波動、升幅大嘅細價股多過 mega-cap。真錢永遠由 Roy 自己喺富途落單。你永遠唔落真單，亦唔會叫佢 all-in。
排程由 GitHub Actions 行（scheduler_owner=github_actions）。你唔好自己再開另一個 cron。
你每日要做：(1) 夏令時 22:00 / 冬令時 23:00 HKT 前確認收到開市＋每日訊息；冇收到就睇 Actions，按 SOP 補跑。
(2) 有需要就用 scripts/px_note.py 補一段教學（廣東話，≤300 字，唔好重複範本）。(3) 週一 09:30 週報之後，補一段本週反思。
你唔可以：print 或覆述任何 API key/token；未經 Roy 同意改規則、人手落紙上單、push code、archive/刪 repo；改寫 ledger 舊記錄。
回答 Roy 時：先講結論，再講原因；價錢寫 USD，同時附 HKD；時間一律寫 HKT。
```

---

## 18. 要 Roy 決定／批准嘅事

1. 🔒 **即刻換** Finnhub、Marketaux、Telegram bot token（已經喺 public repo 公開咗）。
2. 🔒 批准階段 0：push `archive/grokbot-2026-09-28` branch＋tag（保存 Grok Bot runner script）。
3. 排程：GitHub Actions（**建議**，唔使開機）定 Hermes 本機 cron？
4. TP 模式：固定 +10%（現時規則，**預設**）定部分止盈＋trailing？（RKLB 止盈後升到約 75，固定 +10% 會蝕咗後面嗰段升幅）
5. 🔒 批准 B 退役：redirect → archive（唔刪）。
6. A、B 係咪用同一個 Telegram bot／chat？（Hermes 本機見到有 Telegram gateway lock；如果係同一個 bot，換 token 之後 Hermes gateway 都要更新。）
7. 提供富途最新真倉（如果有），用嚟初始化 `data/futu_live.json`；冇就保持空白，標示 stale。
8. Repo 名繼續用 `project-x-minimax`（建議，網址唔變）；想用新名就要接受舊網址失效。
9. 🔒 修正 repo A 嘅 homepage（而家指住 soonoo.github.io）。

---

## 附錄 A：美股假期同 DST（以 `exchange_calendars` XNYS 為準；呢度只係參考）
- DST：2026-11-01 轉 EST（HKT 開市 22:30）；2027-03-14 轉返 EDT（21:30）；2027-11-07 再轉 EST。
- 2026 年剩低：11-26（休市）、11-27（13:00 ET 收市）、12-24（13:00 ET 收市）、12-25（休市）。
- 2027 年：01-01、01-18、02-15、03-26（Good Friday）、05-31、06-18（Juneteenth 補假）、07-05、09-06、11-25（休市），11-26（半日市）。其餘半日市以 library 為準。

## 附錄 B：由 B 反推出嚟嘅輸出格式（因為冇 source，只作參考）
- B 每隻股 `indicators`：`price, ma50, ma20, price_vs_ma50_pct, price_vs_ma20_pct, ma20_vs_ma50_pct, chg_5d_pct, chg_20d_pct, rsi14, volume_ratio, trend, rsi_zone`，加 `trend_score`、`signal`（中文：偏多持有/可分批佈局、防禦/避免新倉、觀望為主）、`stop_loss_suggested`（−10%）、`take_profit_suggested`（+20%）。
- B positions：`dist_to_sl_pp, dist_to_tp_pp, risk_flag (OK|STOP)`。
- B 報告：`close_report_YYYY-MM-DD.md`（=== Part n === 分段，即係 Telegram 分段）、`daily_report_YYYY-MM-DD.md`，加埋一份簡單 HTML 包住嘅版本。
- v3 已經吸收咗有用嘅欄位（§9.3 `indicators`、§9.1 `dist_to_*`／`risk_flag`）。
