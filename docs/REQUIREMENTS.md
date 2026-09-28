# Project X — Roy 同意咗嘅要求（REQUIREMENTS）

> 版本：2026-09-28 HKT（合併版 v3）。解釋用繁體中文；code、路徑、指令用英文。
> 來源：Roy 同 古神（Grok Bot）之間傾好嘅要求，加上 Roy 2026-09-28 嘅最新指示。
> **呢份文件係「冇 Roy 批准唔准改」嘅規則清單。** Hermes 接手之後，任何一條要改（例如時間、注碼、止損、推送目的地），都要先問 Roy，Roy 答應咗先改 code 同呢份文件。
> 狀態符號：✅ 已實作＋有測試／驗證　🟡 已實作，但要 Roy／Hermes 喺切換時完成某一步　⏳ 未完成

## 1. 推送（Telegram）

| # | 要求 | 實作位置 | 點樣測試／驗證 | 狀態 |
|---|---|---|---|---|
| R1 | 每個排程 job 都要推 Telegram | `px/jobs/*.py` → `px/telegram.py`（`send` / `send_photo`） | `run.py <job> --dry-run` 逐個睇訊息（見 HERMES_HANDOVER §3.1 訊息數目表）；`tests/test_core.py::test_T11_open_sends_once_and_executes_tp_once` | ✅ |
| R1a | 開市監控：開市後約 5 分鐘（HKT 21:35 夏令／22:35 冬令），包 VIX | `px/jobs/open_monitor.py`，`settings.schedule.open` = 09:35 ET | `tests/test_schedule.py::test_dst_boundary_open_slot` | ✅ |
| R1b | 每日分析：開市後約 20–30 分鐘（HKT 約 21:53／22:53），有教學同情境預測（唔係保證） | `px/jobs/daily.py`（4 條：決策、信號＋業績日、Top 5、教學＋情境） | dry-run；訊息尾一定有「情境參考，唔係保證」 | ✅ |
| R1c | 交易時段內持倉監察：每小時，**淨係有事先 alert**（每個交易時段第一次另外 send 1 條狀態） | `px/jobs/hourly.py`，ET :06（10:06–16:06） | `test_hourly_alert_dedup`、`test_friday_overnight_hourly` | ✅ |
| R1d | 週報：星期一 HKT 約 09:30（而家 09:44） | `px/jobs/weekly.py`，`settings.schedule.weekly` | `test_morning_and_weekly_days` | ✅ |
| R1e | 收市報告 05:00 HKT（夏令）／06:00（冬令）＝ 17:00 ET | `px/jobs/close.py`（4 條＋1 張權益曲線圖） | `test_close_slot_hkt_both_seasons`；`tests/test_crontab.py` | ✅ |
| R1f | 隔夜複盤 08:30 HKT（美股交易日之後嗰朝，Tue–Sat） | `px/jobs/morning.py` | `test_morning_and_weekly_days` | ✅ |
| R2 | **所有推送（文字、alert、圖、週報）都去 Roy 個 Telegram 群組「Project X Nas」**（成員：Roy＋admin bot「Sono NAS」） | chat id 只由 env `TELEGRAM_CHAT_ID`（或 `PX_TELEGRAM_CHAT_ID`）決定，code 冇寫死 | `tests/test_core.py::TestNoLLMAndConfigDriven::test_no_hardcoded_chat_id_or_token`；切換時 `python run.py tgcheck`＋`tgtest --yes` | 🟡 切換時設定 |
| R2a | 用邊個 bot：Roy 指定 **@hermes_jwzow5tax572z2xt_bot**。未確認「Sono NAS」係咪同一個 bot；如果唔係，而且呢個 bot 唔喺群組 → 問 Roy：加佢入群組，定係改用 Sono NAS | `run.py tgcheck`（getMe＋getChat，唔會顯示 token） | HERMES_HANDOVER §5 步驟 1–5 | 🟡 |
| R2b | 支援 send 圖（chart） | `px/telegram.py::send_photo`；`px/charts.py`（純 Python PNG，冇 matplotlib 都得） | `run.py tgtest --dry-run`；close dry-run 有 `photo close/chart` | ✅ |
| R2c | 舊 @Minimax0707bot（Grok Bot 用）喺切換時退役，token 用 BotFather `/revoke` 撤銷（token 曾經入咗 public repo） | —— | HERMES_HANDOVER §5 步驟 9 | 🟡 Roy／Hermes 做 |
| R3 | 唔重複推送；重跑都唔會再 send 已經 send 咗嘅部分 | `px/guard.py`（`state/job_runs.json`）＋ `px/schedule.py` run ledger | `test_duplicate_rerun_is_guarded`、`test_T11_…` | ✅ |
| R4 | 資訊多啲冇問題，可以分幾條 send；淨係刪重複同噪音 | 訊息設計見 HERMES_HANDOVER §3.1 | dry-run | ✅ |

## 2. 時間

| # | 要求 | 實作位置 | 測試 | 狀態 |
|---|---|---|---|---|
| R5 | 所有時間用 HKT 顯示；美國 2026-11-01 轉冬令時之後自動推遲 1 小時（2027-03-14 再轉返） | 內部用 ET 排程（`px/clock.py`、`settings.schedule`），訊息顯示 HKT | `test_T9_dst`、`test_dst_boundary_open_slot`、`tests/test_crontab.py`（跨兩次 DST） | ✅ |
| R6 | 排程**唔可以錯、唔可以漏** | 美股假期／半日市日曆（`px/clock.py`，已對 NYSE 官方 2026–2027）、漏跑偵測 `run.py check`、health line | `test_nyse_2026_2027`、`test_early_closes`、`test_missing_slot_rerun_then_ok`、`test_alert_once_after_deadline`、`test_first_check_arms_only` | ✅（Hermes cron 設好之後頭 3 日照 HERMES_HANDOVER §7 核對） |

## 3. 語言同判斷

| # | 要求 | 實作位置 | 測試 | 狀態 |
|---|---|---|---|---|
| R7 | 廣東話／繁體中文 | `px/messages.py`、`px/jobs/*.py`、網站 | dry-run 人手睇 | ✅ |
| R8 | 專業判斷寫成規則（排程 job **唔用 LLM**） | `px/decide.py`（gates G1–G9）、`px/scan.py`、`px/ledger.py` | `TestNoLLMAndConfigDriven::test_no_llm_imports_or_hosts` | ✅ |

## 4. 資金同風控（全部 code 強制，`config/settings.json → rules`）

| # | 要求 | 實作位置 | 測試 | 狀態 |
|---|---|---|---|---|
| R9 | HKD 10,000 ≈ USD 1,280（富途）；FX 7.8 | `settings.account`（start 1,280.00，rebase 2026-09-13） | `test_T6_reconciliation_fixture`、`test_T6_repo_portfolio_json` | ✅ |
| R10 | 最多 3 隻 | `rules.max_positions = 3`；`ledger.enforce_entry_rules` | `test_theme_and_one_entry_per_day` 等 | ✅ |
| R11 | 每隻 ≤ 25% | `rules.max_position_pct = 0.25` | `test_levels_and_sizing_respect_rules` | ✅ |
| R12 | 現金 ≥ 20% | `rules.min_cash_pct = 0.20` | `test_gate_pass_setup_A_and_sizing` | ✅ |
| R13 | 最低信心 0.75 | `rules.min_confidence = 0.75`（唯一來源；VIX CAUTION 0.80、DEFENSIVE 0.85） | `test_regime_adjust`、`test_T4_no_unconditional_plus5` | ✅ |
| R14 | 每次入場都預先定好 SL／TP | `ledger.execute_entry`（冇 SL/TP 唔准入）；scan 每個候選都有入場區、止損、目標、R:R | `test_levels_and_sizing_respect_rules` | ✅ |
| R15 | 唔攤平（唔加注） | `rules.allow_averaging_down = false`、`allow_add = false` | `test_no_averaging_down_risk_cap_cooldown` | ✅ |
| R16 | 止盈後唔 FOMO 即刻追返 | `rules.cooldown_after_tp_days = 3`（止損後 5 日） | `test_no_averaging_down_risk_cap_cooldown` | ✅ |
| R17 | 大跌硬性出場 | SL 自動紙上執行（open／hourly／daily／close 都會查；裂口跌穿就用當時價執行）；單日大跌 ≥3% alert | `test_T8_stop_loss_execution` | ✅（注意：scan 入場嘅止損最闊可以去到 −20%（3×ATR），每注風險上限 2% 權益 → 見 AUDIT 待 Roy 決定事項） |
| R18 | 避免因為手續費而來回鋸（whipsaw） | 每日最多 1 個新倉、冷靜期、scan 手續費拖累過濾（來回手續費 > 3% 注碼就唔揀） | `test_theme_and_one_entry_per_day` | ✅ |
| R19 | P&L 包手續費同 FX 7.8 | `ledger.fee()`：**富途香港美股固定式收費**（佣金最低 0.99＋平台費最低 1.00＋交收費，賣出加 TAF，每張單約 US$2）；`recompute()` 計已實現／未實現／費用 | `test_T5_fees` | ✅（2026-09-28 之前嘅紙上交易用舊 US$1 模型入帳，冇追溯改；見 AUDIT F-01） |

## 5. 揀股同產品

| # | 要求 | 實作位置 | 測試 | 狀態 |
|---|---|---|---|---|
| R20 | 集中喺上升空間大、細資金買得起嘅高波幅股；巨頭（Mag7 類）只做大市參考 | `settings.scan.universe`（54 隻交易所上市中小型增長／動能股）；`min_shares = 2`（25% 上限要買得起 ≥2 股）；大市背景只用 SPY／QQQ／VIX | `test_unaffordable_rejected`、`test_penny_and_illiquid_rejected` | ✅ |
| R21 | **機會掃描係核心產品**：排好 Top 5，每隻有入場區、止損、目標、R:R、股數同 HKD 金額、「點解」；網站同 Telegram 都要顯眼 | `px/scan.py`；`opportunities.html`（首頁亦有）；daily 第 3 條、close 第 4 條訊息 | `tests/test_scan.py`；回測 `scripts/backtest_scan.py`（結果見 AUDIT §6） | ✅（**回測顯示未有 edge**，見 AUDIT） |
| R22 | 用情境講法，唔講保證；唔可以作數 | 所有訊息尾有「情境參考，唔係保證」；回測數字由 script 生成並存檔 `data/backtest/` | 人手睇 | ✅ |
| R23 | 每日報告有催化劑／業績日欄 | daily 信號訊息「📅 業績日（催化劑）」；網站 signals／opportunities 表有業績日欄；業績前 5 個交易日唔開新倉 | `test_earnings_blackout` | ✅ |
| R24 | 助手管紙上組合；真錢由 Roy 自己喺富途落單。富途倉人手鏡像、分開顯示 | `portfolio.json`（紙上）；`data/futu_positions.json`（人手鏡像，網站「Roy 富途倉（手動鏡像）」獨立一格，過期會出警告） | 網站檢查 | ✅（現有鏡像係 2026-07-08 嘅富途**模擬**戶口記錄，要 Roy 提供最新真倉先更新） |
| R25 | Mag7 觀察池 | **Roy 2026-09-28 取消（retired by Roy 2026-09-28）**：唔移植、網站同 Telegram 都冇 Mag7 部分 | HERMES_HANDOVER §5 步驟 8（Hermes 刪走 Mag7 jobs） | ✅ 已退役 |

## 6. 系統要求（Roy 2026-09-28 指示）

| # | 要求 | 實作位置 | 狀態 |
|---|---|---|---|
| R26 | 排程 job 唔可以靠 LLM（xAI credit 用完之後 Hermes 嘅 job 由 09-18 開始 fail 過） | 全部 job = `python run.py <job>`，純 Python | ✅ |
| R27 | Secrets 唔可以入 repo；舊 key 要換 | `.gitignore`、`.env.example`、`tests::test_T16_no_secret_files_tracked`；Finnhub／Marketaux key 要 rotate | 🟡 rotate 要 Roy 做 |
| R28 | Repo B（`fung2222/project-x-2026`）唯讀，Hermes 匯出檔保留做存檔 | 本 repo `data/legacy/hermes_project_x_2026/`（副本） | ✅ |
| R29 | Repo 改名做 `project-x`，舊名 `project-x-minimax` 淨係做 redirect | 見 HERMES_HANDOVER §9 | ✅ 2026-09-28 |

## 7. Hermes 唔准自己改嘅嘢（冇 Roy 批准）
1. 推送目的地（群組 Project X Nas）、推送時間、job 數目。
2. 資金、注碼、最多隻數、現金下限、信心門檻、SL／TP 規則、冷靜期、手續費模型。
3. 將任何 LLM 加入排程 job 嘅決策流程。
4. 自動落真單（永遠唔准；真錢只由 Roy 自己落）。
5. 重新開返 Mag7 或者任何已退役嘅 job。
6. 改寫已 push 嘅 git history、force push、刪 repo。
