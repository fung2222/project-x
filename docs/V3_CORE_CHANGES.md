# Project X v3-core 改動紀錄（2026-09-28 HKT）

> 狀態：**過渡版**。呢次只做咗同 Hermes 數據無關嘅部分（安全、指標、規則、帳目、Telegram、CLI）。
> 網站重做、`data/legacy/` 匯入、`HERMES_HANDOVER.md` 正式版、文件重寫 → **等 Hermes 匯出佢嘅 live pipeline／數據之後先做**。
> 解釋用繁體中文；指令、路徑用英文。所有時間 HKT，除非寫明 ET。

## 1. 入口（Hermes 之後只需要呢幾個指令）
```bash
python run.py status                 # 睇設定、secret 有冇（唔會顯示數值）、今日 guard 狀態、ET→HKT 時間
python run.py open    [--dry-run] [--force] [--push]
python run.py daily   [--dry-run] [--force] [--push]
python run.py hourly  [--dry-run] [--force] [--push]
python run.py weekly  [--dry-run] [--force] [--push]
python -m unittest discover -s tests -v   # 離線驗收測試
```
- `--dry-run`：唔 send Telegram、唔寫檔、唔改帳本、唔 push（只 print 訊息）。
- `--force`：略過假期／時間窗同防重複 guard（小心用）。
- `--push`：成功後 `git add` 數據檔 → commit → `pull --rebase` → push。
- Exit code：0 = ok／靜靜跳過（假期、時間窗外、已經 send 過）；1 = 出錯（會 send 一條 🛠 警告，每 job 每日最多 1 次）；2 = Telegram 失敗。

## 2. 時間表（ET 為準；code 入面已經識 DST 同美股假期）
| Job | ET | HKT（夏令 EDT，至 2026-11-01） | HKT（冬令 EST，2026-11-01 → 2027-03-14） | Telegram |
|---|---|---|---|---|
| `open` | 09:35（窗口 09:30–11:00） | 21:35 | 22:35 | 1 條（每個美股交易日一次） |
| `daily` | 10:00（窗口 09:45–16:30；15:00 後唔開新倉） | 22:00 | 23:00 | ≤3 條（決策／信號／教學＋情境） |
| `hourly` | 10:30, 11:30, 12:30, 13:30, 14:30, 15:30, 16:10（窗口 09:30–16:45） | 22:30 … 03:30, 04:10 | 23:30 … 04:30, 05:10 | 有 alert 先 send；每個交易時段第一次可以 send 1 條狀態 |
| `weekly` | —— | 星期一 09:45 | 星期一 09:45 | 1 條 |
- 休市日（例如 2026-11-26 感恩節、12-25 聖誕）同週末：`open/daily/hourly` 自動靜靜退出（exit 0）。半日市（11-27、12-24）13:00 ET 收市，窗口自動縮短。
- **注意**：Grok Bot 平台 routine 係按 HKT 寫死（21:35 等）。2026-11-01 之後 21:35 HKT = 08:35 ET（未開市）→ 新 code 會靜靜跳過 → 冇開市訊息。切換到 Hermes 之前如果仲用緊 Grok Bot，要將 routine 時間推遲 1 小時。

## 3. 防重複（duplicate-send guard）
- `state/job_runs.json`：按「美股交易日（ET）→ job → 已 send 嘅訊息部分」記錄。同一日重跑唔會再 send 已經 send 咗嗰部分；`daily` 嘅「每日最多 1 個新倉」由帳本強制執行，所以重跑都唔會重複開倉。
- `hourly` alert 每個交易日每隻股每種只 send 一次（NEAR_SL 再近 1pp 先再 send）。
- `weekly` 用嗰個星期一（HKT）做 key。

## 4. Secrets（只列名，永遠唔好 print value）
| 變數 | 用途 | Fallback（本機、已 gitignore） |
|---|---|---|
| `FINNHUB_API_KEY` | 報價 fallback＋新聞 | `finnhub_config.json` → `api_key` |
| `MARKETAUX_API_KEY` | 新聞 | `marketaux_config.json` → `api_key` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot（**純設定驅動**，Hermes 可以直接插自己個 bot） | `telegram_config.json` → `bot_token` |
| `TELEGRAM_CHAT_ID` | Roy 個 chat | `telegram_config.json` → `chat_id` |
- 讀取次序：環境變數 → repo root `.env`（gitignore）→ 舊 json 檔。範本：`.env.example`。
- 三個 `*_config.json` 已經 `git rm --cached`（本機檔保留，令 Grok Bot 今晚照跑）。**Git history 冇改寫** → 舊 key 喺 history 仍然睇得到，切換日一定要換（Finnhub、Marketaux；同埋用 BotFather `/revoke` 撤銷舊 Grok Bot Telegram token）。
- 另外發現：`PROJECT_X_BUILD_SPEC.md` 由 2026-07-08（commit 584a752）開始已經寫住真嘅 Telegram token、chat id、Marketaux key 同另一個 40 字元 API key → 已經喺 working tree 換成佔位符；history 仍有，所以同樣要換 key。

## 5. 指標／信號修正（`px/indicators.py`、`px/signals.py`）
- 1 年日線（最少 120 條 bar），**剔走今日未完嘅 bar**；Wilder RSI(14)、Wilder ATR(14)、真 MA20/MA50、正常 MACD 12/26/9、成交量比用最後一條**已收市** bar ÷ 前 20 日平均、trend score（−6..+6）。
- 取消無條件 +5 信心；VIX 調整：NORMAL 0／CAUTION −10／DEFENSIVE −20。
- `min_confidence` 單一來源：`config/settings.json → rules.min_confidence = 0.75`（regime 門檻：0.75／0.80／0.85）。

## 6. Code 強制規則（`px/ledger.py`、`px/decide.py`）
- 最多 3 隻、每隻 ≤25% 權益、開倉後現金 ≥20%、每筆風險 (entry−SL)×股數 ≤2% 權益、每日最多 1 個新倉、同主題最多 1 隻、唔攤平／唔加倉、止損後 5 個交易日／止盈後 3 個交易日冷靜期、`config/overrides.json`（pause／blocklist）。
- Gates G1–G9（setup A 升勢回調 / setup B 超賣反轉半注）；每個被拒候選都寫低原因。G7（業績日）未檢查（冇可靠免費數據）。
- SL/TP：新倉 `SL = max(entry−2×ATR, entry×0.90)` 而且 ≤ entry×0.95；`TP = entry×1.10`（固定）。現有 SOUN 沿用 5.76／6.89。
- `open/hourly/daily` 見到穿 SL/TP 會**自動紙上執行**（報價異常 >50% 跳動就唔執行）。
- 選項（要 Roy 決定，未實裝做預設）：`tp_mode: partial_trail`（+10% 先賣一半，剩低止損移去成本價再 trailing）。

## 7. 帳目更正（已對賬）
- RKLB T003/T005：淨盈利 **19.06 → 18.06**（之前漏咗買入手續費 1.00；舊 `risk_manager.execute_action` 嘅 bug，已修）。現金本身冇錯。
- `account.total_pnl_usd` = 已實現 + 未實現 − 未平倉買入手續費 = 權益 − 起始（之前只計 SOUN 未實現）。
- 2026-09-28（SOUN 6.05）：現金 **USD 1,140.56**（HK$8,896）、權益 **USD 1,291.81**（HK$10,076）、已實現 +18.06、未實現 −5.25、未平倉手續費 1.00、總 P&L **+11.81（+0.92%）**、本時期手續費 3.04；同期 SPY +0.92%。
- 更正記錄寫咗入 `portfolio.json → corrections[]`。

## 8. Telegram 精簡
- `daily`：由約 15 條 → **≤3 條**。過渡期（Grok Bot 仲跑緊）：`telegram_push.py` 只 send 1 條信號表，Grok Bot 自己再加 3 條決策／教學 → 大約 4 條。
- `open` 1 條；`hourly` 淨係有事先 send（+每個交易時段第一次 1 條狀態，以前係每個 HKT 日，即每晚 2 條）；`weekly` 1 條。
- 最終只留**一個** bot：建議用 Hermes 現有嘅 bot（token 冇公開過），退役 Grok Bot 嗰個（token 已外洩）。Code 只睇 `TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID`。

## 9. 舊入口（今晚 Grok Bot routine 照用，唔使改 prompt）
| 舊指令 | 而家 |
|---|---|
| `python _run_open_monitor.py` | 薄 wrapper → `run.py open` 引擎；同樣輸出 `_last_open_monitor.json`、`Reports/OpenMonitor_<date>.txt`、JSON/---MSG---/---TG--- |
| `python _run_hourly_check.py` | 薄 wrapper → `run.py hourly` 引擎；同樣寫 `_last_hourly_check.json`、`.last_hourly_quiet_hkt`、Grok Bot state 檔 |
| `python analyzer.py` | 用新引擎寫 `daily_report.json`／`signals.json`／`profiles.json`（網站照讀）；**唔會**自動開倉 |
| `python telegram_push.py` | 1 條信號表（每日一次） |
| `risk_manager.execute_action` | 經 `px.ledger`（正確手續費）；`ADD_POSITION` 一律拒絕 |
| `position_tracker.update_positions()` | 只做 MTM＋重算帳戶 |

## 10. 可選：GitHub Actions 後備 runner
`ops/github-actions/px-backup-runner.yml`（範本；要用時由 Roy 複製到 `.github/workflows/`，因為現有 push token 冇 `workflow` scope）：**只可以手動**（`workflow_dispatch`），schedule 段已註解。Secrets 名：`FINNHUB_API_KEY`、`MARKETAUX_API_KEY`、`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`。唔好同 Hermes／Grok Bot 同時開排程。

## 11. 未做（等 Hermes 匯出）
網站重做（權益曲線、報告存檔、HKD、learn 頁、縮細 signals.json、基本面 tab）、`data/legacy/` 匯入、`HERMES_HANDOVER.md`（含 H0 Hermes 自我盤點＋匯出、H1 合併檢討）、MERGE_PLAN／COMPARISON 搬去 `docs/` 同更新、README、舊文件標記 superseded。
