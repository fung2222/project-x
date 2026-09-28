# Project X — Roy 同意咗嘅要求（REQUIREMENTS）

> 版本：2026-09-28 HKT（合併版 v3；同日加 §6a 淺白推送＋realwatch）。解釋用繁體中文；code、路徑、指令用英文。
> 來源：Roy 同 古神（Grok Bot）之間傾好嘅要求，加上 Roy 2026-09-28 嘅最新指示。
> **呢份文件係「冇 Roy 批准唔准改」嘅規則清單。** Hermes 接手之後，任何一條要改（例如時間、注碼、止損、推送目的地），都要先問 Roy，Roy 答應咗先改 code 同呢份文件。
> 狀態符號：✅ 已實作＋有測試／驗證　🟡 已實作，但要 Roy／Hermes 喺切換時完成某一步　⏳ 未完成

## 1. 推送（Telegram）

| # | 要求 | 實作位置 | 點樣測試／驗證 | 狀態 |
|---|---|---|---|---|
| R1 | 每個排程 job 都要推 Telegram | `px/jobs/*.py` → `px/telegram.py`（`send` / `send_photo`） | `run.py <job> --dry-run` 逐個睇訊息（見 HERMES_HANDOVER §3.1 訊息數目表）；`tests/test_core.py::test_T11_open_sends_once_and_executes_tp_once` | ✅ |
| R1a | 開市監控：開市後約 5 分鐘（HKT 21:35 夏令／22:35 冬令），包 VIX | `px/jobs/open_monitor.py`，`settings.schedule.open` = 09:35 ET | `tests/test_schedule.py::test_dst_boundary_open_slot` | ✅ |
| R1b | 每日分析：開市後約 20–30 分鐘（HKT 約 21:53／22:53），有教學同情境預測（唔係保證） | `px/jobs/daily.py`（**2026-09-28 起 1 條淺白報告**：真倉→資金→買賣信號→潛力股→大市→今日學一樣→紙上倉一行→網站連結；教學同情境詳細版喺網站／`daily_report.json`） | dry-run；訊息尾一定有「情境參考，唔係保證」 | ✅ |
| R1c | 交易時段內持倉監察：每小時，**淨係有事先 alert**（每個交易時段第一次另外 send 1 條狀態） | `px/jobs/hourly.py`，ET :06（10:06–16:06）；每個 slot 最多 push 1 次（`slot@HH:MM`）；真倉警報同 realwatch 共用去重（R31） | `test_hourly_alert_dedup`、`test_friday_overnight_hourly`、`test_same_slot_never_pushes_twice` | ✅ |
| R1d | 週報：星期一 HKT 約 09:30（而家 09:44） | `px/jobs/weekly.py`，`settings.schedule.weekly` | `test_morning_and_weekly_days` | ✅ |
| R1e | 收市報告 05:00 HKT（夏令）／06:00（冬令）＝ 17:00 ET | `px/jobs/close.py`（**2026-09-28 起 1 條淺白報告＋1 張權益曲線圖**） | `test_close_slot_hkt_both_seasons`；`tests/test_crontab.py` | ✅ |
| R1f | 隔夜複盤 08:30 HKT（美股交易日之後嗰朝，Tue–Sat） | `px/jobs/morning.py` | `test_morning_and_weekly_days` | ✅ |
| R2 | **所有推送（文字、alert、圖、週報）都去 Roy 個 Telegram 群組「Project X Nas」**（成員：Roy＋admin bot「Sono NAS」） | chat id 只由 env `TELEGRAM_CHAT_ID`（或 `PX_TELEGRAM_CHAT_ID`）決定，code 冇寫死 | `tests/test_core.py::TestNoLLMAndConfigDriven::test_no_hardcoded_chat_id_or_token`；切換時 `python run.py tgcheck`＋`tgtest --yes` | 🟡 切換時設定 |
| R2a | 用邊個 bot：Roy 指定 **@hermes_jwzow5tax572z2xt_bot**。未確認「Sono NAS」係咪同一個 bot；如果唔係，而且呢個 bot 唔喺群組 → 問 Roy：加佢入群組，定係改用 Sono NAS | `run.py tgcheck`（getMe＋getChat，唔會顯示 token） | HERMES_HANDOVER §5 步驟 1–5 | 🟡 |
| R2b | 支援 send 圖（chart） | `px/telegram.py::send_photo`；`px/charts.py`（純 Python PNG，冇 matplotlib 都得） | `run.py tgtest --dry-run`；close dry-run 有 `photo close/chart` | ✅ |
| R2c | 舊 @Minimax0707bot（Grok Bot 用）喺切換時退役，token 用 BotFather `/revoke` 撤銷（token 曾經入咗 public repo） | —— | HERMES_HANDOVER §5 步驟 9 | 🟡 Roy／Hermes 做 |
| R3 | 唔重複推送；重跑都唔會再 send 已經 send 咗嘅部分 | `px/guard.py`（`state/job_runs.json`）＋ `px/schedule.py` run ledger；job 開始前先記「running」（900s timeout 都計一次嘗試）；舊版訊息部分（decision/signals/…）已 send 過嘅交易日唔會再 send 新版報告 | `test_duplicate_rerun_is_guarded`、`test_T11_…`、`test_running_marker_counts_attempt_before_job` | ✅ |
| R4 | 資訊多啲冇問題，可以分幾條 send；淨係刪重複同噪音 | **Roy 2026-09-28 更新：推送要短、淺白（見 R30）**；詳細數字留喺網站。訊息設計見 HERMES_HANDOVER §3.1 | dry-run；`/workspace/px-samples/` 樣本 | ✅ |

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
| R21 | **機會掃描係核心產品**：排好 Top 5，每隻有入場區、止損、目標、R:R、股數同 HKD 金額、「點解」；網站同 Telegram 都要顯眼 | `px/scan.py`；`opportunities.html`（首頁亦有，完整 Top 5＋數字）；Telegram（daily／close／morning／weekly）顯示「⭐ 潛力股」頭 1–3 隻＋一句淺白原因，冇就老實講冇 | `tests/test_scan.py`；回測 `scripts/backtest_scan.py`（結果見 AUDIT §6） | ✅（**回測顯示未有 edge**，見 AUDIT） |
| R22 | 用情境講法，唔講保證；唔可以作數 | 所有訊息尾有「情境參考，唔係保證」；回測數字由 script 生成並存檔 `data/backtest/` | 人手睇 | ✅ |
| R23 | 每日報告有催化劑／業績日欄 | 潛力股每隻寫「業績 MM-DD」或「業績日未知」；網站 signals／opportunities 表有業績日欄；業績前 5 個交易日唔開新倉；業績日：Finnhub 每 7 日一段查（每日 cache）＋ yfinance 後備，**兩個都答唔到＝業績日未知 → 唔開紙上新倉、唔建議真倉買**（R34） | `test_earnings_blackout`、`TestEarnings` | ✅ |
| R24 | 真錢由 Roy 自己喺富途落單；**2026-09-28 起報告同網站以真倉為先**，紙上組合自動運行做對照組 | `data/futu_positions.json`（`run.py pos add/close/set/list` 記錄，schema real_positions_v2，保留已平倉紀錄）；`portfolio.json`（紙上）；舊 07-08 模擬記錄封存於 `data/legacy/` | `tests/test_realpos.py`＋dry-run | ✅ |
| R25 | Mag7 觀察池 | **Roy 2026-09-28 取消（retired by Roy 2026-09-28）**：唔移植、網站同 Telegram 都冇 Mag7 部分 | HERMES_HANDOVER §5 步驟 8（Hermes 刪走 Mag7 jobs） | ✅ 已退役 |

## 6. 系統要求（Roy 2026-09-28 指示）

| # | 要求 | 實作位置 | 狀態 |
|---|---|---|---|
| R26 | 排程 job 唔可以靠 LLM（xAI credit 用完之後 Hermes 嘅 job 由 09-18 開始 fail 過） | 全部 job = `python run.py <job>`，純 Python | ✅ |
| R27 | Secrets 唔可以入 repo；舊 key 要換 | `.gitignore`、`.env.example`、`tests::test_T16_no_secret_files_tracked`；Finnhub／Marketaux key 要 rotate | 🟡 rotate 要 Roy 做 |
| R28 | Repo B（`fung2222/project-x-2026`）唯讀，Hermes 匯出檔保留做存檔 | 本 repo `data/legacy/hermes_project_x_2026/`（副本） | ✅ |
| R29 | Repo 改名做 `project-x`，舊名 `project-x-minimax` 淨係做 redirect | 見 HERMES_HANDOVER §9 | ✅ 2026-09-28 |

## 6a. 2026-09-28 Roy 批准：「整個流程都係合情合理有用冇錯數據」

| # | 要求 | 實作位置 | 測試 | 狀態 |
|---|---|---|---|---|
| R30 | **所有推送用淺白廣東話（繁體）**：真倉先（今日升跌、買入至今 % + US$ + HK$、趨勢 上升／橫行／下跌、一句原因）→ 資金（本金、用咗、剩低現金、總賺蝕）→ 買賣信號（「考慮買入 X，建議買 N 股約 US$…，止蝕…止賺…」按真倉 US$1,280 計；「揸住」／「考慮賣出」＋原因）→ 潛力股 1–3 隻（冇就老實講）→ 大市 1–3 句（恐慌指數 18，正常）→ 今日學一樣（淨係 daily）→ 紙上倉一行 → 網站連結。推送唔出 RSI／ATR／MACD／Sharpe／分數（留喺網站） | `px/plain.py`、`px/messages.py`、`px/jobs/*.py`、`px/realpos.py`（`pos` 確認訊息） | `test_plain_blocks_have_no_jargon_and_fit_telegram`、`TestHourlyRendering` | ✅ |
| R31 | **真倉 5 分鐘監察（realwatch）**：開市時每 5 分鐘；條件：跌穿止蝕、到止賺、止蝕上面 2% 內（預警）、比昨收跌 ≥5%（再跌到 10/15/20% 再報）、升 ≥8%（15/25% 再報）；每個條件每隻每個交易時段報一次，改止蝕／止賺會重新 arm；Telegram send 成功先記低；每次最多 1 條；唔 commit | `px/jobs/realwatch.py`（`run.py tick` 喺 `schedule.tick` 之前叫；唔係排程 slot、watchdog 唔管）；設定 `real_account.intraday_watch` | `TestRealwatch` | ✅ |
| R32 | realwatch 冇真倉 = 0 個 API call；Finnhub `/quote` 先（>15 分鐘舊報價唔用、跳 >50% 唔用），Finnhub 唔得先用 yfinance（要係今日 bar）；兩個都唔得 → 講「報價攞唔到」，**唔會用估計價** | 同上 | `test_zero_api_calls_without_positions`、`test_stale_finnhub_falls_back_to_yfinance_else_no_fake_price` | ✅ |
| R33 | **永遠唔作數**：攞唔到就寫「數據暫缺」或者唔講；VIX 攞唔到 → 市況 `UNKNOWN`（⚪ VIX 數據暫缺），**唔會當 NORMAL**，唔開紙上新倉、唔建議真倉買；舊數據要標明「上個交易日（MM-DD）」；匯率攞唔到用 7.8 並寫明「估算」 | `px/marketdata.py`（`regime_for`、`quote`、`fx_info`）、`config/settings.json regimes.UNKNOWN`、`px/ledger.py` | `test_vix_missing_means_unknown_never_normal`、`test_day_word_never_mislabels_old_session` | ✅ |
| R34 | 業績日：Finnhub `/calendar/earnings` 每 7 日一段（撞 1500 行上限就逐日再查），每個 HKT 日 cache 一次（`state/earnings_cache.json`，唔完整就每粒鐘重試）；yfinance `.calendar` 只做後備；兩個都答唔到 = 「業績日未知」，保守處理（唔入、唔建議） | `px/earnings.py`、`px/scan.py`、`px/jobs/daily.py`、`px/plain.py` | `TestEarnings` | ✅ |
| R35 | API 限流：Finnhub 429 → 按 `X-Ratelimit-Reset` 冷卻（`state/api_state.json`，最長 15 分鐘），所有錯誤都寫 log（唔會靜靜雞當「冇數據」）；Yahoo 限流（YFRateLimitError／429）→ 即刻停晒 Yahoo request、冷卻 15 分鐘，報告類 job（open/daily/close/morning/weekly）延後（唔計嘗試次數）而唔係推一份有窿嘅報告；最後一次重試之後唔再 sleep | `px/finnhub.py`、`px/apistate.py`、`px/marketdata.py`、`run.py`、`px/schedule.py` | `TestFinnhub`、`TestYahooAndAttempts` | ✅ |
| R36 | 真倉同潛力股每隻有一句「原因」（冇 LLM）：最相關近期新聞（Finnhub company-news；冇先用 Marketaux，**每日硬上限 60 次**＋cache 6 粒鐘）＋ 同 QQQ／板塊 ETF 比較（「跟大市跌」／「似係個股消息」）；冇相關新聞就寫「冇特別新聞，似係跟大市／板塊波動」；標題只會截短，唔會作原因 | `px/reasons.py`；網站 `js/px.js`（`realCard`、`oppCard` 讀 `data/reasons.json`、`scan.json reason_plain`） | `test_move_class`、`test_reason_never_invents_a_cause`、`test_marketaux_hard_daily_budget`、`test_generic_headlines_filtered` | ✅ |
| R37 | 今日學一樣：daily 一條實用教學，揀自 40 條精選，30 日內唔重複 | `px/lessons.py`（`state/lesson_history.json`） | `test_lessons_no_repeat_30_days` | ✅ |
| R38 | Roy 最優先：**唔可以錯、漏、重複推送** — 每個 slot 最多推一次（hourly `slot@HH:MM`、其他 job 按交易日＋部分）；真倉警報 hourly／realwatch 共用一個去重記錄；send 成功即刻記低 | `px/guard.py`（`real_alerted`／`save_real_alerted`）、`px/jobs/hourly.py`、`px/jobs/realwatch.py` | `test_same_slot_never_pushes_twice`、`test_hourly_and_realwatch_share_alert_store`、`test_marked_only_after_successful_send` | ✅ |

## 7. Hermes 唔准自己改嘅嘢（冇 Roy 批准）
1. 推送目的地（群組 Project X Nas）、推送時間、job 數目。
2. 資金、注碼、最多隻數、現金下限、信心門檻、SL／TP 規則、冷靜期、手續費模型。
3. 將任何 LLM 加入排程 job 嘅決策流程。
4. 自動落真單（永遠唔准；真錢只由 Roy 自己落）。
5. 重新開返 Mag7 或者任何已退役嘅 job。
6. 改寫已 push 嘅 git history、force push、刪 repo。
7. realwatch 條件／門檻（`real_account.intraday_watch`）、Marketaux 每日上限（`api_budget`）、「業績日未知就唔入」（`earnings.unknown_blocks_entry`）。
