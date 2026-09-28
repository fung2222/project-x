# Project X — 交接俾 Hermes（HERMES_HANDOVER）

> 版本：2026-09-28 HKT（合併版 v3 最終交接）。寫俾：**Hermes**（Linux 環境：`/opt/data/.env`、shell script、自己嘅 `cron/jobs.json`）同 Roy Chan。
> 語言：解釋用繁體中文；code、路徑、指令用英文。所有時間寫明 HKT 或 ET（美東）。
> 規則：`docs/REQUIREMENTS.md` 係 Roy 同意咗嘅要求，**冇 Roy 批准唔准改**（§11）。審計同修正：`docs/AUDIT.md`。
> Repo：真正嘅 repo 係 **`fung2222/project-x`**（2026-09-28 由 `project-x-minimax` 改名；舊名而家係淨係做 redirect 嘅細 repo，見 §9）。Repo B `fung2222/project-x-2026` 保持唯讀存檔。

## 目錄
- H0 Hermes 自我盤點（短）
- H1 合併檢討（由 B 攞咗乜、由 A 保留乜）
- §1 系統一覽
- §2 安裝（Linux）
- **§3 排程（最重要）**：總表、cron 寫法、DST、假期、防重複、漏跑偵測、timeout、health line
- §4 由 Grok Bot routine 過渡
- §5 切換步驟（Telegram 群組、停舊 job、刪 Mag7、撤銷舊 bot、換 key）
- §6 環境變數
- §7 頭 3 個真實交易日核對表
- §8 冇移植嘅 Hermes 功能同原因
- §9 Repo 改名
- §10 日常操作手冊
- §11 Hermes 唔准自己改嘅嘢
- **§12 真倉記錄（Roy 富途真錢；2026-09-28 起報告以真倉為先）**
- **§13 真倉 5 分鐘監察（realwatch）、點停、每日 API 用量**

---

## H0 Hermes 自我盤點（短）
Hermes 2026-09-28 嘅匯出（repo B `export/2026-09-28/`，本 repo 副本 `data/legacy/hermes_project_x_2026/export_2026-09-28/`）已經夠用，**唔需要再匯出**：
- **gushen profile** 行緊嘅就係呢個 export 入面嗰條 PX pipeline（`run_daily_pipeline.sh` 等）；repo B 每日 05:00／08:30／21:30 仲有 commit，Roy 第二個 bot 收到嘅推送就係佢。切換後停（§5 步驟 7）。
- 4 個 PX cron（`b0ece97aa091` daily、`dda4d9ed4a71` close、`a1d845966230` morning、`827895abf50c` integrity）喺 default profile 係 `enabled=false`（2026-09-21 起）。
- **xAI 依賴已經移除**：新系統冇任何 LLM 步驟；Hermes 唔需要 xAI credit 去跑排程。
- Mag7 觀察池：**retired by Roy 2026-09-28**（§5 步驟 8 刪除）。
- Hermes 要確認嘅嘢（切換前答 Roy）：(1) `/opt/data/.env` 入面 Telegram token 屬於邊個 bot（`python run.py tgcheck` 會話你 username）；(2) 仲有冇其他 profile 有 PX／Mag7 job；(3) 部機可唔可以用系統 `crontab`（建議）。

## H1 合併檢討
| 來源 | 拎咗乜入合併版 | 喺邊度 |
|---|---|---|
| B | 05:00 收市報告（改做 17:00 ET，冬令 06:00 HKT） | `px/jobs/close.py` |
| B | 08:30「隔夜複盤」（改做美股交易日之後嗰朝，Tue–Sat） | `px/jobs/morning.py` |
| B | 風險 flag（距止損 %、🟢🟠🚨）、趨勢分（MA20/MA50 結構） | `px/jobs/close.py`、`px/indicators.py` |
| B | 報告存檔（每份推送都有 .md／.html） | `px/archive.py` → `data/reports/`、`reports.html` |
| B | P&L／權益曲線 | `data/pnl_history.json`、`portfolio.html`、收市報告圖 |
| B | 富途倉人手鏡像（獨立顯示） | `data/futu_positions.json`、`portfolio.html` |
| B | 網站版面（白底 teal、多頁、學習中心） | `index.html` 等、`css/style.css` |
| B | 歷史數據 | `data/legacy/hermes_project_x_2026/`（唯讀；B 嘅 HKD 5k 模擬倉唔合併） |
| A | 股票池、機會掃描 Top 5、gates、紙上帳本（HKD 10k）、Telegram 直送 | `px/` |
| 新 | ET 排程＋NYSE 日曆、run ledger＋watchdog、防重複、富途真實手續費、send 圖 | `px/schedule.py`、`px/clock.py`、`px/guard.py`、`px/ledger.py`、`px/telegram.py` |

---

## §1 系統一覽
```
cron (每分鐘) ──> ops/hermes/px_job.sh tick ──> python run.py tick
                     │ flock（唔會兩個 job 同時跑）、timeout 900s、log 去 logs/
                     ├─ 有到期嘅 slot → 跑 job（open/daily/hourly/close/morning/weekly）
                     │     ├─ yfinance（主）＋ Finnhub（真倉 5 分鐘報價、報價後備、業績日、新聞）＋ Marketaux（新聞後備，每日 ≤60）
                     │     ├─ 寫 portfolio.json、daily_report.json、data/*.json、data/reports/、state/
                     │     └─ Telegram Bot API → 群組「Project X Nas」（文字＋圖）
                     ├─ realwatch（2026-09-28）：開市時每 5 分鐘睇 Roy 真倉（冇真倉＝0 call；唔 commit；見 §13）
                     ├─ watchdog：漏咗／fail → 窗口內重跑；過咗窗口 → 1 條 🛠 alert
                     └─ git commit + push → GitHub Pages 網站自動更新
```
- 全部係 Python，**冇 LLM**。Hermes 嘅角色：operator（裝、監察、答 Roy、人手更新富途鏡像）。
- 網站：https://fung2222.github.io/project-x/（舊網址 https://fung2222.github.io/project-x-minimax/ 會自動跳過嚟）。

## §2 安裝（Linux）
```bash
# 1. clone（用有 push 權限嘅 token／SSH key；唔好將 token 寫入 repo）
cd /opt/data
git clone https://github.com/fung2222/project-x.git project-x     # 唔好 clone project-x-minimax（嗰個淨係 redirect 頁）
cd project-x
git config user.name  "Hermes Agent"
git config user.email "hermes@nousresearch.com"

# 2. venv（Python 3.11+；已測 3.13）
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt       # yfinance, pandas, numpy, requests（Pillow 可選：圖會靚啲）

# 3. secrets：放喺 /opt/data/.env（或者 repo 根目錄 .env，已 gitignore）。名見 §6
#    如果 /opt/data/.env 已經有 TELEGRAM_CHAT_ID 指住其他 chat（例如 DM），用 PX_TELEGRAM_CHAT_ID 覆蓋
chmod 600 /opt/data/.env

# 4. 檢查（全部唔會 send Telegram）
export PX_ENV_FILE=/opt/data/.env
.venv/bin/python run.py status                   # secret 有冇（唔顯示數值）、今日排程、run ledger
.venv/bin/python -m unittest discover -s tests   # 應該 50 個測試全部 OK
.venv/bin/python run.py daily --dry-run --force  # 睇 4 條每日訊息（唔 send、唔寫檔）
.venv/bin/python run.py tgcheck                  # bot username＋群組資料（唔 send）
chmod +x ops/hermes/px_job.sh
```

---

## §3 排程（最重要：唔可以錯、唔可以漏）

### 3.1 總表（每個 job）
美股時間以 **America/New_York** 為準。夏令 EDT（至 2026-10-31、由 2027-03-14 起）HKT = ET + 12 小時；冬令 EST（2026-11-01 → 2027-03-13）HKT = ET + 13 小時。

| Job | 用途 | ET | HKT（夏令 EDT） | HKT（冬令 EST） | 幾時跑 | 指令 | 訊息（數目／標題） | 更新檔案 |
|---|---|---|---|---|---|---|---|---|
| `open` | 開市監控：VIX 市況、SPY/QQQ、持倉 vs SL/TP、自動執行觸發咗嘅 SL/TP | 09:35 | 21:35 | 22:35 | NYSE 交易日（ET 星期一至五，唔包假期；半日市照跑） | `python run.py open --push` | **1**：「🔔 美股開市」（淺白：大市、真倉、資金、紙上倉一行） | `portfolio.json`、`_last_open_monitor.json`、`Reports/OpenMonitor_*.txt`、`data/reports/open_report_<ET日期>.*`、`state/` |
| `daily` | 每日分析：決策、信號、業績日、機會掃描 Top 5、教學＋情境；最多 1 個紙上新倉 | 09:53 | 21:53 | 22:53 | NYSE 交易日 | `python run.py daily --push` | **1**：「📘 每日報告 日期」（真倉→資金→買賣信號→潛力股→大市→今日學一樣→紙上倉一行→網站）；信號表、Top 5 數字、教學＋情境喺網站 | `daily_report.json`、`signals.json`、`profiles.json`、`portfolio.json`、`data/scan.json`、`data/reports/daily_report_*`、`state/` |
| `hourly` | 盤中持倉監察（alert-only）＋自動 SL/TP | 10:06, 11:06, 12:06, 13:06, 14:06, 15:06, 16:06（半日市只到 13:06） | 22:06 → 翌日 04:06 | 23:06 → 翌日 05:06 | NYSE 交易日；**星期五嘅 12:06–16:06 ET = 星期六 00:06–04:06 HKT（冬令 01:06–05:06）** | `python run.py hourly --push` | 平時 **0**；有事先 send「🚨 真倉警報」／「⚠️ 市況警報」（真倉跌穿止蝕／到止賺／近止蝕／急跌／急升、大市情緒轉變、紙上倉 SL/TP 已執行）；每個交易時段第一次 send **1** 條「📊 持倉監控」；每個 slot 最多 1 條 | `portfolio.json`、`_last_hourly_check.json`、`state/` |
| `close` | 收市報告：持倉結算、趨勢、明日觀察 Top 5、權益曲線圖、🩺 health line | 17:00 | 翌日 05:00 | 翌日 06:00 | NYSE 交易日（包半日市） | `python run.py close --push` | **1＋1 圖**：「🌙 收市報告 日期」（大市、真倉、資金、買賣信號、明日潛力股、紙上倉一行、🩺 health line）、圖（紙上倉權益 vs SPY） | `portfolio.json`、`data/pnl_history.json`、`data/scan.json`、`data/reports/close_report_*`、`data/charts/equity_*.png`、`state/` |
| `morning` | 隔夜複盤（香港早晨，唔係盤前） | —— | 08:30 | 08:30 | HKT 星期二至六，而且前一個美股日係交易日（例：2026-11-27 早上唔跑，因為 11-26 感恩節休市） | `python run.py morning --push` | **1**：「🌅 早晨｜美股 日期 收市回顧」 | `portfolio.json`、`data/reports/morning_report_*`、`state/` |
| `weekly` | 每週回顧 | —— | 星期一 09:44 | 星期一 09:44 | 每個 HKT 星期一（美國假期都照跑） | `python run.py weekly --push` | **1**：「📊 每週回顧」 | `Reports/WeeklyReport_*.json`、`Reports/WeeklySummary_*.txt`、`data/reports/weekly_report_*`、`state/` |
| `realwatch` | 真倉 5 分鐘監察（**唔係排程 slot**，由 `tick` 喺排程之前叫；watchdog 唔管；唔 commit） | 開市時每 5 分鐘 | 21:30–04:00 | 22:30–05:00 | NYSE 開市時段 | （自動，經 `tick`） | 平時 **0**；真倉觸發條件先 send「🚨 真倉即時警報」（每次最多 1 條） | `state/realwatch.json`、`state/job_runs.json`（`real` 去重） |
| `tick` | **建議嘅唯一 cron 入口**：先跑 realwatch，再到期就跑上面嘅 job，再做 watchdog | —— | 每分鐘 | 每分鐘 | 永遠 | `ops/hermes/px_job.sh tick` | 冇（除非 watchdog alert） | 同上 |
| `check` | watchdog（淨係漏跑偵測）；用 Option B/C 先需要 | —— | 每 30 分鐘 | 每 30 分鐘 | 永遠 | `ops/hermes/px_job.sh check` | 漏跑過咗窗口：每個 slot **最多 1 條**「🛠 Project X 漏跑/失敗」 | `state/run_ledger.json` |

**一個普通美股交易日（夏令）嘅推送次序（HKT）**：21:35 開市（1）→ 21:53 每日（1）→ 22:06 第一次 hourly（1 條狀態＋有事先 alert）→ 23:06 … 04:06（有事先 alert）→ 05:00 收市（1＋圖）→ 08:30 隔夜複盤（1）。開市期間真倉有事 realwatch 隨時（每 5 分鐘檢查）send「🚨 真倉即時警報」。星期一另加 09:44 週報（1）。冬令全部美股 job 遲 1 小時；08:30、09:44 唔變。

**窗口（寫死喺 `config/settings.json`）**：

| Job | 准跑窗口 | grace（過咗先當漏） | 自動重跑期限 |
|---|---|---|---|
| open | 09:30–11:00 ET | 20 分鐘 | 10:45 ET |
| daily | 09:45–16:30 ET（15:00 ET 後唔開新倉） | 25 分鐘 | 15:00 ET |
| hourly | 09:30–16:45 ET（半日市 13:45） | 20 分鐘 | slot 後 50 分鐘 |
| close | 16:50–23:59 ET（要收市之後） | 25 分鐘 | 20:30 ET |
| morning | 07:00–12:00 HKT | 25 分鐘 | 11:30 HKT |
| weekly | 星期一 | 30 分鐘 | 13:00 HKT |

### 3.2 Cron 寫法（揀一個；檔案：`ops/hermes/crontab.txt`）
> **唔好用 Hermes 嘅 LLM cronjob 去跑呢啲 job**（佢哋以前用 `xai-oauth/grok-4.5`，credit 用完就 fail）。用 Linux 系統 `crontab`（或者 systemd timer）。如果 Hermes 自己嘅 `/opt/data/cron/jobs.json` 支援「直接行 shell command、唔經 model」，都可以用，但入面**唔可以有 model/provider**。
> 同一時間只可以有**一個** runner（Hermes crontab、Grok Bot routine、GitHub Actions 三揀一）。防重複 guard 會令意外雙跑都唔會重複 send，但唔好靠佢。

**Option A（建議）— 一行，任何主機時區都啱，DST／假期／星期幾自動處理：**
```cron
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
PX_HOME=/opt/data/project-x
PX_ENV_FILE=/opt/data/.env
* * * * * /opt/data/project-x/ops/hermes/px_job.sh tick
```
- `tick` 每分鐘好快（約 0.1 秒，冇到期就乜都唔做、唔寫 log）。到期嘅 slot 喺 slot 時間嗰一分鐘開始跑（最遲 grace 內）。
- 已經有測試證明：開市 21:35（夏令）／22:35（冬令）只跑一次、星期五下半場喺星期六 HKT 有跑、感恩節冇跑、星期一冇隔夜複盤但有週報（`tests/test_schedule.py::TestTick`）。
- 第一次跑 `tick` 會「arm」watchdog（記低 `watch_since`），之前嘅 slot 唔會 alert。

**Option B — 明確 ET 時間（cron 要支援 `CRON_TZ`，例如 cronie）：**
```cron
CRON_TZ=America/New_York
35 9 * * 1-5      /opt/data/project-x/ops/hermes/px_job.sh open
53 9 * * 1-5      /opt/data/project-x/ops/hermes/px_job.sh daily
6 10-16 * * 1-5   /opt/data/project-x/ops/hermes/px_job.sh hourly
0 17 * * 1-5      /opt/data/project-x/ops/hermes/px_job.sh close
CRON_TZ=Asia/Hong_Kong
30 8 * * *        /opt/data/project-x/ops/hermes/px_job.sh morning
44 9 * * 1        /opt/data/project-x/ops/hermes/px_job.sh weekly
20,50 * * * *     /opt/data/project-x/ops/hermes/px_job.sh check
```
（美國假期由 `run.py` 自己靜靜跳過；`morning` 喺星期日／一會自己跳過。）

**Option C — 主機時區係 Asia/Hong_Kong、冇 CRON_TZ：「DST 超集」**（夏令同冬令時間都寫，每日都跑；時間窗外 `run.py` 靜靜跳過；已由 `tests/test_crontab.py` 跨 2026-11-01、2027-03-14 驗證）：
```cron
35 21,22 * * *              /opt/data/project-x/ops/hermes/px_job.sh open
53 21,22 * * *              /opt/data/project-x/ops/hermes/px_job.sh daily
6 22,23,0,1,2,3,4,5 * * *   /opt/data/project-x/ops/hermes/px_job.sh hourly
0 5,6 * * *                 /opt/data/project-x/ops/hermes/px_job.sh close
30 8 * * *                  /opt/data/project-x/ops/hermes/px_job.sh morning
44 9 * * 1                  /opt/data/project-x/ops/hermes/px_job.sh weekly
20,50 * * * *               /opt/data/project-x/ops/hermes/px_job.sh check
```

**Option D — 兩套 HKT 時間，按日期人手切換（唔建議；只係俾唔可以用 A/B/C 嘅情況）：**

| 期間 | open | daily | hourly | close |
|---|---|---|---|---|
| 夏令：至 2026-10-31，及由 2027-03-14 起 | `35 21 * * 1-5` | `53 21 * * 1-5` | `6 22,23 * * 1-5` ＋ `6 0-4 * * 2-6` | `0 5 * * 2-6` |
| 冬令：2026-11-01 → 2027-03-13 | `35 22 * * 1-5` | `53 22 * * 1-5` | `6 23 * * 1-5` ＋ `6 0-5 * * 2-6` | `0 6 * * 2-6` |
| 兩季一樣 | morning `30 8 * * 2-6`、weekly `44 9 * * 1`、check `20,50 * * * *` | | | |

- 切換日：**2026-11-01（星期日）** 同 **2027-03-14（星期日）**，喺嗰個星期六或星期日（HKT 10:00–20:00）改 crontab。美國轉鐘係星期日，所以唔會撞到交易日。
- **注意星期幾**：hourly 嘅 00:00–05:06 HKT 同 close 係 HKT **星期二至六**（`2-6`），因為係前一晚美股嘅延續。舊 A 嘅 bug 就係寫咗 `1-5`（AUDIT S-01），舊 B 嘅 close／morning 都係（S-03）。

### 3.3 DST 重點日子
| 日子 | 發生咩事 |
|---|---|
| 2026-10-30（五）美股 | 最後一個夏令交易日；收市報告 2026-10-31（六）05:00 HKT |
| 2026-11-01（日） | 美國轉冬令（02:00 ET） |
| 2026-11-02（一） | 開市 22:30 HKT；open 22:35、daily 22:53、hourly 23:06 起、close 翌日 06:00 |
| 2027-03-14（日） | 美國轉返夏令 |
| 2027-03-15（一） | 開市 21:30 HKT；open 21:35、daily 21:53、close 翌日 05:00 |

### 3.4 美股假期／半日市（NYSE 官方 2026–2027，已寫入 `px/clock.py`）
| 美東日期 | 事件 | 對推送嘅影響（HKT） |
|---|---|---|
| 2026-11-26（四） | 感恩節休市 | 11-26 晚冇 open/daily/hourly；11-27（五）冇 close（06:00）、冇 morning（08:30） |
| 2026-11-27（五） | 半日市，13:00 ET 收市 | hourly 只有 10:06–13:06 ET（23:06–02:06 HKT）；close 照 17:00 ET（11-28 六 06:00 HKT）；11-28 08:30 有 morning |
| 2026-12-24（四） | 半日市 13:00 ET | 同上；close 12-25（五）06:00 HKT |
| 2026-12-25（五） | 聖誕休市 | 12-25 晚冇美股 job；12-26（六）冇 close、冇 morning |
| 2027-01-01（五） | 元旦休市 | 01-01 晚冇；01-02（六）冇 close／morning |
| 2027-01-18（一） | 馬丁路德金紀念日 | 01-18 晚冇；01-19（二）冇 close／morning；週報照出 |
| 2027-02-15（一） | 總統日 | 同上 |
| 2027-03-26（五） | 耶穌受難日 | 03-26 晚冇；03-27（六）冇 close／morning |
| 2027-05-31（一） | 陣亡將士紀念日 | 05-31 晚冇；06-01（二）冇 close／morning |
| 2027-06-18（五） | 六月節（補假） | 06-18 晚冇；06-19（六）冇 |
| 2027-07-05（一） | 獨立日（補假） | 07-05 晚冇；07-06（二）冇 |
| 2027-09-06（一） | 勞動節 | 09-06 晚冇；09-07（二）冇 |
| 2027-11-25（四） | 感恩節 | 11-25 晚冇；11-26（五）冇 close／morning |
| 2027-11-26（五） | 半日市 13:00 ET | hourly 10:06–13:06 ET |
| 2027-12-24（五） | 聖誕（補假）休市 | 12-24 晚冇；12-25（六）冇 |
- 每年 12 月：Hermes 去 https://www.nyse.com/trade/hours-calendars 對下一年，唔同就改 `px/clock.py` 同 `tests/test_schedule.py::test_nyse_2026_2027`（要 Roy 知）。臨時休市（例如國喪）→ 喺 `px/clock.py` 加日子，或者嗰日暫停 crontab。
- 查某日：`python run.py status`（顯示今日係咪交易日、半日市、每個 job 嘅 slot 同狀態）。

### 3.5 防重複（duplicate guard）
- `state/job_runs.json`：按「美股交易日（ET）→ job → 訊息部分」記錄已 send；重跑只會補 send 未 send 嘅部分。週報用 HKT 星期一做 key。
- `state/run_ledger.json`：每個 slot 嘅狀態（ok／duplicate／skipped／failed／telegram_failed／missing）、嘗試次數、歷史。一個 slot 一旦 `ok`，之後嘅重複／跳過都唔會改佢（sticky）。
- `daily` 每日最多 1 個紙上新倉（帳本強制），重跑唔會重複開倉；SL/TP 執行後持倉已經冇咗，唔會重複賣。
- `--force` 會略過 guard：**只可以喺 Roy 要求或者確定冇 send 過先用**。
- （2026-09-28）job 開始**之前**先喺 run ledger 記「running」＋嘗試次數：就算俾 900s timeout 殺咗，都計一次，watchdog 唔會無限重跑（每 slot 最多 3 次）。
- hourly 每個 slot 最多 push 1 次（`state/job_runs.json` 入面 `hourly.sent.slot@HH:MM`），send 成功即刻記低，之後先做其他嘢。
- 真倉警報（止蝕／止賺／近止蝕／急跌／急升）hourly 同 realwatch 共用一個去重記錄（`state/job_runs.json → <交易日> → real → alerts`），同一個條件每個交易時段只會報一次（再跌多一級、或者改咗止蝕／止賺先會再報）。
- daily／close 由 4 條改做 1 條：如果某個交易日已經用舊版 send 過（decision/signals/scan/teaching 或 summary/positions/trend/scan），新版唔會再 send。

### 3.6 漏跑偵測（watchdog）
- `tick`（Option A）每分鐘已經包；Option B/C 用 `check` 每 30 分鐘（:20、:50）。
- 每個 slot 過咗 grace 仲未 ok → 喺「自動重跑期限」內自動重跑（最多 2 次，`PX_RERUN=1` 只會略過時間窗，guard 照用）；過咗期限仲唔得 → send **1 條**「🛠 Project X 漏跑/失敗：job slot（HKT）狀態…」，同一個 slot 唔會再 send。
- job 本身出錯（exception，`tick` 或者人手跑都一樣）→ 即時 send 1 條「🛠 Project X 系統警告」（每 job 每個美股交易日最多 1 次），然後 watchdog 會喺窗口內重試。

### 3.7 API timeout／重試
- yfinance：每隻股每個 process 只攞一次 2 年日線（其他 period 用切片；`quote()` 用同一份數據，唔再另外 call）；失敗最多試 2 次，中間等 1.5s，**最後一次之後唔再等**。
- **Yahoo 限流**（YFRateLimitError／429／Too Many Requests）：即刻停晒今個 process 嘅 Yahoo request，寫 15 分鐘冷卻（`state/api_state.json`）。冷卻期間 `tick` 將 open／daily／close／morning／weekly **延後**（`deferred`，唔計嘗試次數，冷卻完 watchdog 再跑）；job 跑到一半先撞到就回 `data_wait`，**唔會推一份有窿嘅報告**。hourly 同 realwatch 照跑（用 Finnhub 報價）。
- **Finnhub**：每個 call 經 `px/finnhub.py`：429 → 按 `X-Ratelimit-Reset` 冷卻（冇 header 就 60s，最長 15 分鐘），剩 ≤2 個 call 就自動暫停到 reset；每個錯誤都寫 log；每日計數喺 `state/api_state.json`。quote 10s timeout；業績日曆 20s。
- Telegram：`sendMessage` 15s、`sendPhoto` 30s timeout；失敗會喺 2s、5s、10s 後再試（400／401／403 唔重試）；token 喺任何錯誤訊息都會遮住。
- 整個 job：`px_job.sh` 用 `timeout 900`（15 分鐘）；超時會寫 log，watchdog 之後重跑。
- 冇數據就唔開新倉（fail safe）；SL/TP 報價異常跳 >50% 唔執行。

### 3.8 每晚 health line
- 收市報告第一條尾：「🩺 系統健康：全部準時｜open✅ · daily✅ · hourly 7/7✅」或者「🩺 系統健康：1 項有問題｜… hourly 5/7⚠️」。
- `python run.py status` 會列出今日每個 slot 嘅狀態。

---

## §4 由 Grok Bot routine 過渡（切換之前）
- 2026-09-28 為止，**Grok Bot 平台 routine 仲係 runner**（喺 Grok Bot box 嘅 `/workspace/project-x-minimax` 資料夾跑，remote 已改做 `fung2222/project-x`，舊 wrapper 已經指去新引擎）：開市監控 21:35 HKT、每日約 21:53 HKT（`analyzer.py`＋`telegram_push.py`，2 條訊息＋Grok Bot 自己嘅教學）、hourly `:06`、星期一 09:44 週報。**冇 close／morning**（呢兩個由 B pipeline 繼續 send 去 gushen DM，直至切換）。
- **2026-11-01 之後 Grok Bot 21:35 HKT 會早過開市**（code 會靜靜跳過 → 冇開市訊息）。所以切換最好喺 **2026-10-30 之前**完成；如果做唔到，Roy 要將 Grok Bot routine 推遲 1 小時。
- Grok Bot routine 運行期間**唔好**開 Hermes crontab（會兩邊跑）。切換當日：先停 Grok Bot routine，再開 Hermes crontab（§5）。

## §5 切換步驟（照次序；揀一個美股休市時段做，例如平日 10:00–20:00 HKT 或者週末）
1. **Telegram bot 身份**：`python run.py tgcheck` → 睇 `getMe.username`。Roy 指定用 **@hermes_jwzow5tax572z2xt_bot**；如果 `/opt/data/.env` 嘅 token 唔係呢個 bot，停，問 Roy。
2. **確認 bot 喺群組「Project X Nas」**（成員：Roy＋admin bot「Sono NAS」）：未確認 Sono NAS 係咪同一個 bot。如果 @hermes_jwzow5tax572z2xt_bot 唔喺群組 → **問 Roy**：(a) Roy 將佢加入群組（要可以 send 訊息同圖），或者 (b) 改用 Sono NAS 嘅 token。唔好自己決定。
3. **設 chat id**：群組 id 係負數（例如 `-100…`）。攞法：Roy 喺群組 send 一句嘢之後，`curl -s "https://api.telegram.org/bot$TOKEN/getUpdates"` 睇 `chat.id`（唔好將 token 或者輸出貼去任何地方）。寫入 `/opt/data/.env`：`PX_TELEGRAM_CHAT_ID=-100…`（用 PX_ 前綴，避免同 Hermes 其他用途撞）。再跑 `python run.py tgcheck` → `getChat.type` 應該係 `supergroup`／`group`、title 係「Project X Nas」。
4. **測試（全個切換只做呢一次真 send）**：`python run.py tgtest --yes` → send 1 條文字＋1 張圖。
5. **Roy 確認**兩樣都喺「Project X Nas」見到。未確認唔好行落去。
6. **停 Grok Bot routine**（Roy／Grok Bot 做）：開市監控、每日分析、hourly、週報 4 個 routine 全部停。然後**開 Hermes crontab**（§3.2 Option A）：`crontab -l | cat - ops/hermes/crontab.txt | crontab -`（crontab.txt 入面 B/C 已註解）。跑一次 `ops/hermes/px_job.sh tick`（會 arm watchdog）同 `python run.py status`。
7. **停 Hermes 舊 PX pipeline**：等合併版完整跑完一個循環（open → daily → hourly → close → morning）而且 Roy 確認之後：
   - default profile：`cronjob action=pause` 然後刪除 `b0ece97aa091`（project-x-daily-report）、`dda4d9ed4a71`（project-x-close-report）、`a1d845966230`（project-x-morning-briefing）、`827895abf50c`（project-x-data-integrity-check）。
   - **gushen profile**：停同刪除行緊 `run_daily_pipeline.sh`／`run_close_pipeline.sh`／`run_morning_pipeline.sh`／`push_*.sh` 嘅所有 job（repo B 之後唔會再有新 commit；repo B 本身保留唯讀）。
8. **刪 Mag7（retired by Roy 2026-09-28）**：
   - 停同刪除 `b655bf26892b`（mag7-premarket）、`8405f161cfea`（mag7-daily）、`46d2ea2e5114`（mag7-close），同埋任何 profile 入面其他 Mag7 job（mag7 daily／push／chart 等）。
   - 將 `/opt/data/mag7_observer/`（`run_pipeline.sh`、`mag7_push.py`、`mag7_chart.py`、`mag7_dashboard.py`、`mag7_report.py`、`mag7_data.py`）移出排程路徑（例如搬去 `/opt/data/archive/mag7_observer_retired_2026-09-28/`）或者刪除，確保冇嘢會再 call 佢。
   - repo B `export/2026-09-28/schedule.md` 嘅「重啟指引」（會重新 enable Mag7 同舊 PX cron）**作廢，唔好跑**。
   - 確認：之後 2 個美股交易日「Project X Nas」同 Roy 嘅 DM **冇再出現任何 Mag7 圖／訊息**，然後話俾 Roy 知。
9. **撤銷舊 bot**：Grok Bot routine 停咗之後，Roy 喺 BotFather 對 **@Minimax0707bot** 做 `/revoke`（token 曾經入咗 public repo）。之後 Grok Bot box 嘅 `telegram_config.json` 冇用。
10. **換 key**：Roy 喺 Finnhub 同 Marketaux 網站開新 key、停舊 key（舊 key 喺 git history：`9d9f8de` 起嘅 `*_config.json`、`584a752`（2026-07-08）起嘅 `PROJECT_X_BUILD_SPEC.md`）。新 key 寫入 `/opt/data/.env`（`FINNHUB_API_KEY`、`MARKETAUX_API_KEY`），`python run.py status` 確認 present。
11. 將切換結果（日期、bot username、群組 title、邊啲 job 已刪）寫入本文件尾「切換紀錄」，commit + push。

## §6 環境變數（只寫名；永遠唔好 print／commit 數值）
| 變數 | 用途 | 必要？ |
|---|---|---|
| `TELEGRAM_BOT_TOKEN`（或 `PX_TELEGRAM_BOT_TOKEN`） | 推送用 bot（@hermes_jwzow5tax572z2xt_bot 或 Roy 揀嘅 bot） | 必要 |
| `TELEGRAM_CHAT_ID`（或 `PX_TELEGRAM_CHAT_ID`） | 群組「Project X Nas」嘅負數 id | 必要 |
| `FINNHUB_API_KEY` | 報價後備、業績日曆、新聞 | 建議 |
| `MARKETAUX_API_KEY` | 持倉新聞 | 可選 |
| `PX_ENV_FILE` | 額外讀邊個 env 檔（預設 `px_job.sh` 用 `/opt/data/.env`） | 可選 |
| `PX_DRY_RUN=1` | 唔 send、唔寫檔 | 測試用 |
| `PX_TELEGRAM_DISABLED=1` | 照跑照寫檔，但唔 send | 維修用 |
| `PX_HOME`、`PX_VENV`、`PX_LOG_DIR`、`PX_TIMEOUT` | `px_job.sh` 設定 | 可選 |
| `PX_REALWATCH_DISABLED=1` | 臨時停 realwatch（永久停用改 settings，見 §13） | 可選 |
| `PX_STATE_DIR`、`PX_REASONS_PATH`、`PX_NETWORK_OFF=1` | 測試／樣本用：state 目錄、`data/reasons.json` 位置、完全離線 | 測試用 |
- 讀取次序：真環境變數 → `PX_ENV_FILE` → repo `.env` → 舊 `*_config.json`（Grok Bot box 先有）。`PX_` 前綴永遠贏。
- GitHub push：用 Hermes 自己嘅 SSH key 或者 fine-grained token（只需要呢個 repo 嘅 contents:write），唔好寫入 repo。

## §7 頭 3 個真實交易日核對表（每日做，結果話俾 Roy）
| 時間（夏令 HKT；冬令 +1 小時） | 核對 |
|---|---|
| 21:36 | 群組有「🔔 開市監控」1 條；VIX 數字合理；`logs/<日期>_tick.log` 有 open ok |
| 21:55 | 4 條每日訊息（決策、信號＋📅 業績日、Top 5、教學）；網站 `opportunities.html` 同首頁日期更新 |
| 22:07 | 1 條「📊 持倉監控」；之後每小時冇事就唔應該有訊息 |
| 05:01 | 收市 4 條＋1 張圖；第一條尾嘅 🩺 health line 係「全部準時」 |
| 08:31 | 1 條「🌅 隔夜複盤」 |
| 星期一 09:45 | 1 條「📊 每週回顧」 |
| 任何時候 | 冇重複訊息；冇 Mag7；冇訊息去舊 DM；`git log` 每個 job 一個 commit；`python run.py status` 冇 failed／missing |
- 第 1 日另外：`cat state/run_ledger.json` 睇每個 slot `status: ok`；網站 `reports.html` 有新報告。
- 有問題：唔好改規則；照 §10 重跑，並話俾 Roy 知。

## §8 冇移植嘅 Hermes（B）功能同原因
| 功能 | 點解唔移植 |
|---|---|
| Mag7 觀察池（premarket／daily／close、7 張圖＋dashboard） | **Roy 2026-09-28 取消**（retired by Roy 2026-09-28）；大市背景只用 SPY/QQQ/VIX |
| LLM（grok-4.5）生成／deliver 報告 | 排程唔可以靠 LLM（xAI credit 用完 09-18 起 fail 過）；而家全部 code 生成 |
| 碎股（0.5／1.0 注） | 整股先同 Roy 富途落單一致，手續費清楚 |
| 固定 −10% 止損／+20% 止盈（而且從來冇執行） | 改用每筆預設、自動執行嘅 SL/TP（AUDIT P-01） |
| 加注規則「RSI<35＋低過 MA50 → 加 0.5 注」 | 即係攤平，違反 Roy 規則 |
| 08:30 淨 snapshot 推送 | 換成有內容嘅「隔夜複盤」（morning job） |
| print-only `telegram_push.py` | 換成直接 Bot API（文字＋圖） |
| `data_integrity_check`（23:00 LLM job） | 換成 run ledger＋watchdog＋health line |
| 一晚 commit 兩次（21:30／21:31） | 每個 job 一個 commit |
| HKD 5k 模擬倉（2026-07-08 起） | 唔合併；存喺 `data/legacy/`，網站「Legacy」摺埋顯示 |
| HKT 日期命名報告 | 改用美股交易日（ET） |

## §9 Repo 改名（最後一步）
- 目標：真 repo = **`fung2222/project-x`**，網站 https://fung2222.github.io/project-x/ 。舊名 `fung2222/project-x-minimax` 會係一個**新開嘅細 repo，淨係做 redirect**（`index.html`、`404.html` 跳去新網址，保留路徑同 #hash）。**唔好掂 `fung2222.github.io`。**
- 改名之後：`git remote set-url origin https://github.com/fung2222/project-x.git`（所有 clone 都要）；`config/settings.json → telegram.site_url`、`js/px.js → PX.site`、README、docs 都要用新網址。
- 狀態：**2026-09-28 已完成**（見文件尾「改名紀錄」）。Hermes clone 要用 `https://github.com/fung2222/project-x.git`；**唔好**喺 `project-x-minimax` 放任何 code／數據。

## §10 日常操作手冊
- **睇狀態**：`python run.py status`；log：`logs/<日期>_<job>.log`（保留 30 日）。
- **人手重跑漏咗嘅 job**：`ops/hermes/px_job.sh daily`（有 guard，唔會重複 send）。只有 Roy 要求先用 `--force`。
- **暫停開新倉**：`config/overrides.json → "pause_new_entries": true`（要 Roy 指示），commit + push。封鎖某隻股：`"blocklist": ["TICKER"]`。
- **暫停全部推送**：`PX_TELEGRAM_DISABLED=1`（寫入 env），或者 `crontab -e` 註解 tick 行。
- **停真倉 5 分鐘監察**：見 **§13**（`real_account.intraday_watch.enabled=false` 或 env `PX_REALWATCH_DISABLED=1`）。
- **記錄 Roy 真倉**：唔好再人手改 `data/futu_positions.json`，一律用 `python run.py pos ...`（見 **§12**）。舊 2026-07-08 富途**模擬**記錄（NVDA ×1 @194）已封存去 `data/legacy/futu_positions_2026-07-08_paper_sim.json`，唔計入真倉。**系統永遠唔會自動落真單。**
- **Telegram fail**：`python run.py tgcheck`；bot 俾人踢出群組／token 失效 → 話俾 Roy 知。
- **數據源 fail**（yfinance 冇數）：job 會 fail safe（唔開新倉），watchdog 會重試；持續就話俾 Roy 知。
- **升級 code**：喺 branch 改 → `python -m unittest discover -s tests` 全過 → `run.py <job> --dry-run --force` → 美股休市時段先 merge。

## §11 Hermes 唔准自己改嘅嘢（要 Roy 批准）
見 `docs/REQUIREMENTS.md §7`：推送目的地／時間／job 數目、資金同風控規則、手續費模型、加 LLM 入排程、自動落真單、重開 Mag7 或者其他退役 job、改寫 git history／force push／刪 repo。

## §12 真倉記錄（Roy 富途真錢戶口，約 HKD 10,000 ≈ US$1,280）
**2026-09-28 起所有 Telegram 報告同網站都以 Roy 嘅真倉為先**（價、成本、股數、P&L USD＋HKD、%、距止蝕／止賺、持倉日數；冇倉就一句「真倉：暫時冇持倉（買入後叫 Hermes 記錄）」）。hourly／close／open 嘅止蝕、止賺、急跌警報**先睇真倉**，寫明「真倉」— Roy 自己喺富途手動落單，系統只提醒。紙上倉照舊自動運行（ledger／回測／掃描全部保留），報告入面縮成一段「🧪 紙上倉（對照組）」。週報有「⚖️ 三方比較」：真倉 vs 紙上倉 vs QQQ／SPY（由第一筆真倉日期起計）＋真倉交易筆數同勝率（目標 20–30 筆先檢討）。

**Roy 講咗買賣之後，你要做（永遠唔好幫佢落單）：**

| Roy 講 | 你行 |
|---|---|
| 「買咗 IONQ 3 股 @44.5，止蝕 37，止賺 50」 | `python run.py pos add IONQ 3 44.5 --sl 37 --tp 50` |
| （唔係今日買）「琴日買咗…」 | 加 `--date YYYY-MM-DD`（香港日期） |
| 富途手續費唔係約 US$2 | 加 `--fee 1.99`（預設用現有富途固定式收費模型，細單約 US$2／單） |
| 「賣咗 IONQ @48」 | `python run.py pos close IONQ 48`（全部賣） |
| 「賣咗 IONQ 1 股 @48」 | `python run.py pos close IONQ 48 1`（部分） |
| 「IONQ 止蝕改 40」 | `python run.py pos set IONQ --sl 40`（`--tp` 同理） |
| 「我而家有咩倉？」 | `python run.py pos list`（`--live` 攞即時價） |

步驟：
1. 唔肯定數字（股數／價／止蝕／止賺）就**先問 Roy**，唔好估。買入一定要有止蝕同止賺（CLI 會拒絕：止蝕要低過買入價、止賺要高過買入價、日期唔可以喺將來、股數要 > 0）。可以先加 `--dry-run` 試。
2. 行指令；CLI 會印 ✅ 同埋規則提示（超過 3 隻、單隻 >25%、現金 <20%、風險 >2%）——提示唔會阻止記錄（佢已經買咗），但要照轉述俾 Roy。
3. 推上 GitHub：最簡單係指令後面加 `--push`（先 `git pull --rebase`，再**淨係** commit＋push `data/futu_positions.json`，唔會 force push）。同 tick job 用同一把鎖，避免同時搞 git：
   `cd /opt/data/project-x && flock -w 600 .px.lock .venv/bin/python run.py pos add IONQ 3 44.5 --sl 37 --tp 50 --push`
   （人手做都得：`git pull --rebase` → `git add data/futu_positions.json` → `git commit -m "real pos: add IONQ 3 @44.5"` → `git push`；如果話 nothing to commit，即係 tick job 已經順手 push 咗，`git log -1 -- data/futu_positions.json` 核對。唔好 force push、唔好改 history。）
4. 回覆 Roy：**直接轉述 CLI 印出嚟嘅 ✅ 確認**（2026-09-28 起已經係淺白廣東話：買咗幾多股、用咗幾多錢 US$＋HK$、止蝕跌到會蝕幾多、止賺升到會賺幾多、剩低現金）。賣出嗰條有淨賺蝕（US$／HK$／%）同揸咗幾多日。有規則提示（⚠️）就照轉述。

檔案：`data/futu_positions.json`（schema `real_positions_v2`：`positions[]` 持倉、`closed_trades[]` 已實現紀錄——**唔好刪**，20–30 筆檢討要用、`real_start_date` 第一筆真倉日）。寫入係 atomic＋file lock；jobs 會自動更新 `last_price`（畀網站用）。唔好人手改呢個檔。

## §13 真倉 5 分鐘監察（realwatch）＋ API 用量（2026-09-28）

**做咩**：美股開市期間，`run.py tick`（每分鐘）喺跑排程之前叫 `px/jobs/realwatch.py`。距離上次 ≥5 分鐘先真係做嘢（`state/realwatch.json`）。
- **冇真倉 ＝ 0 個 API call**（只讀 `data/futu_positions.json`）。
- 有真倉：每隻用 Finnhub `/quote`（>15 分鐘舊嘅報價唔用、比昨收跳 >50% 唔用）；Finnhub 唔得先用 yfinance（要係今日 bar）；兩個都唔得就 send 一次「報價攞唔到，請自己喺富途睇住止蝕」— **唔會用估計價**。
- 條件（`config/settings.json → real_account.intraday_watch`）：跌穿止蝕、到止賺、止蝕上面 2% 內、比昨收跌 ≥5%（再到 10／15／20% 再報）、升 ≥8%（再到 15／25% 再報）。每個條件每隻每個交易時段報一次（同 hourly 共用去重）；改咗止蝕／止賺會重新 arm。
- 每次最多 1 條 Telegram（「🚨 真倉即時警報」，每個警報有一句原因）；**send 成功先記低**（失敗 5 分鐘後會再試）；唔寫 `futu_positions.json`、唔 commit、唔 push。
- 出錯唔會影響 tick（`run.py` 包住 exception）。

**點停**：
- 永久：`config/settings.json → real_account.intraday_watch.enabled = false`（要 Roy 批准；commit＋push）。
- 臨時：env `PX_REALWATCH_DISABLED=1`（寫入 `/opt/data/.env`）。
- 改門檻（`near_sl_pct`、`drop_steps_pct`、`surge_steps_pct`、`interval_min`、`max_quote_age_min`）一樣要 Roy 批准。

**每日 API 用量（估算，美股交易日）**：

| 來源 | 上限（免費） | 而家估計用量 | 備註 |
|---|---|---|---|
| Finnhub | 60 call／分鐘（+30／秒） | 業績日曆 ~10–15（每日一次，唔完整每粒鐘重試）＋ 公司新聞 ≤120 上限（實際 ~15–25，cache 6 粒鐘）＋ 大市新聞 ~4 ＋ realwatch 每隻真倉 ≤78（6.5 粒鐘 × 12 次；3 隻 = ≤234）＋ 報價後備少量 | 冇真倉：~30–45／日；3 隻真倉：~260–280／日，每分鐘最多 ~3–4 個，遠低過 60／分鐘 |
| Marketaux | 100 request／日 | **硬上限 60／日**（`api_budget.marketaux_per_day`，`state/api_state.json` 計數）；實際通常 <10（淨係 Finnhub 冇新聞先用） | 429 → 冷卻 1 粒鐘 |
| Yahoo（非官方） | 冇公開上限；撞 429 就停 15 分鐘 | 約 200–260 request／交易日（以前 400–510）：每隻股每個 process 一次 2 年日線；daily ≈ 核心＋機會＋掃描 54 隻＋SPY/QQQ/VIX＋板塊 ETF＋舊版 profiles（9 隻 info／news）＋業績後備 ~5 | realwatch 平時唔用 Yahoo |

新 state 檔（全部 gitignore，唔會 commit）：`state/api_state.json`（冷卻＋計數）、`state/earnings_cache.json`、`state/news_cache.json`、`state/realwatch.json`；`state/lesson_history.json`（今日學一樣，30 日唔重複）。網站讀 `data/reasons.json`（原因）。

---
## 切換紀錄
- （未切換）

## 改名紀錄
- 2026-09-28 約 11:33 HKT：`gh repo rename project-x`（`fung2222/project-x-minimax` → `fung2222/project-x`）；Grok Bot box `/workspace/project-x-minimax` 嘅 origin 已改做 `https://github.com/fung2222/project-x.git`（今晚 routine 由呢度 push）。
- `config/settings.json → telegram.site_url`、`js/px.js → PX.site`、README、docs 已改新網址；repo homepage = https://fung2222.github.io/project-x/ ；加咗 `.nojekyll`（純靜態網站）。
- 新網址已驗證：`/`、`opportunities.html`、`signals.html`、`portfolio.html`、`reports.html`、`learn.html` 全部 200、冇 JS error。
- 新開 public repo `fung2222/project-x-minimax`（**淨係 redirect**：`index.html`＋`404.html`，JS 保留路徑／query／#hash，meta refresh 後備），Pages 已開；驗證：舊網址 `/`、`/portfolio.html`、`/opportunities.html#top`、`/reports.html?x=1` 全部跳去 `https://fung2222.github.io/project-x/…` 對應頁。
