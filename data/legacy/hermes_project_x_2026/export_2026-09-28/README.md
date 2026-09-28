# Project X 2026 · Hermes 系統匯出（2026-09-28）

> **用途**：古神接手合併用。本 export 由 Hermes 於 2026-09-28 整理，完整反映當時運行狀態。
> **保留設定**：所有 cron job、portfolio 持倉、TG 推送配置、品牌資產、tertiary 行為全部 freeze，等古神讀完 + 寫 HERMES_HANDOVER.md 之後再決定停 / 改 / 合併。

---

## 📦 此 export 包含咩

```
export/2026-09-28/
├── README.md                           ← 本檔案
├── schedule.md                         ← 7 個 cron 嘅 schedule + 重啟指引
├── rules.md                            ← 投資規則、入市條件、風險管理
├── requirements.txt                    ← Python 依賴
├── project_x_learning/                 ← 模擬倉源碼（保留結構）
│   ├── analyzer.py                     ← MA/RSI/score/trend
│   ├── data_fetcher.py                 ← yfinance
│   ├── risk_manager.py                 ← P&L/止損/分級
│   ├── telegram_push.py                ← TG 文字生成（print-only）
│   ├── build_close_report.py
│   ├── gen_close_report.py
│   ├── archive_daily_report.py
│   ├── _gen_daily_index.py
│   ├── _gen_report.py
│   ├── _close_indexer.py
│   ├── run_daily_pipeline.sh
│   ├── run_close_pipeline.sh
│   ├── run_morning_pipeline.sh
│   ├── push_daily_full.sh
│   ├── push_close_full.sh
│   └── push_morning_only.sh
├── mag7_observer/                      ← 觀察池源碼（獨立 pipeline）
│   ├── mag7_data.py
│   ├── mag7_chart.py                   ← PIL 單股 chart
│   ├── mag7_dashboard.py               ← 2×4 grid dashboard
│   ├── mag7_push.py                    ← urllib + bot token 真 TG send
│   ├── mag7_report.py                  ← HTML 報表生成
│   └── run_pipeline.sh
├── portfolio/
│   ├── portfolio.json                  ← 持倉、現金、P&L、停損停利
│   └── futu_positions.json             ← Roy 手動富途倉（獨立）
└── reports/                            ← 最近 7 個交易日 TG 推文原文
    ├── reports_index.json              ← 索引
    ├── daily_report_2026-09-28.html    ← HTML wrapper
    ├── daily_report_2026-09-28.md      ← MD 原文
    ├── close_report_2026-09-28.html
    ├── close_report_2026-09-28.md
    ├── ...                            ← 共 24 份文件，7 個交易日
```

---

## 🏗️ 系統運作（簡版）

### 兩個獨立 pipeline

| Pipeline | 路徑 | 模擬倉？ | 輸出 |
|----------|------|---------|------|
| **Project X** 模擬倉 | `/opt/data/project_x_learning/` | ✅ 有（3 倉 + 現金） | 純文字 TG |
| **Mag7** 觀察池 | `/opt/data/mag7_observer/` | ❌ 無（純觀察） | 圖 + HTML + TG |

**重要**：兩個 pipeline 數據互相獨立。Mag7 嘅 NVDA / TSLA 唔影響 PX 嗰兩倉嘅計分。

### 數據源

| 用途 | API | 用途 |
|------|-----|------|
| 股價、歷史 K 線 | **yfinance** | 所有標的 1 年日 K |
| VIX 指數 | **yfinance** (^VIX) | 市場恐慌指標 |
| FX | 固定 7.8（HKD/USD 入場時 lock） | 唔實時更新 |
| 美股時間 | 系統 `date` 命令 | 夏令 / 冬令自動切 |

### 模擬 vs 真實

- 全部交易**模擬**，無真實 broker 接入
- fractional shares（0.5 / 0.5 / 1.0 注）
- P&L 計 portfolio.json `value_usd - cost_basis_usd`
- `futu_positions.json` 係 Roy **親手** 在富途 App 落嘅單，**獨立於** Hermes 自動追蹤

---

## 🧠 AI 模型路由（極重要）

| Job | Model | Provider | 原因 |
|-----|-------|----------|------|
| 所有 Project X cron (4 個) | `grok-4.5` | `xai-oauth` | 數據量大 + 模板固定，避免 drift |
| 所有 Mag7 cron (3 個) | `grok-4.5` | `xai-oauth` | 同上 |
| 投資 chat（非 cron） | `grok-4.6` | `xai-oauth` | 對話用更強模型 |
| 日常 Telegram | MiniMax-M3 | minimax-oauth | 成本低 |

⚠️ **未 pin 嘅 job 喺主模型切換時會 fail closed**：例如 `RuntimeError: HTTP 403 spending-limit`。

---

## 📊 當前持倉 (2026-09-28 snapshot)

| 標的 | 股數 | 成本 (USD) | 當前價 | 市值 (USD) | P&L % | 風險 | 距止損 % |
|------|------|-----------|--------|-----------|-------|------|---------|
| NVDA | 0.5 | 98.47 | 225.07 | 112.53 | +14.29 | OK | +24.29 |
| TSLA | 0.5 | 201.45 | 372.11 | 186.06 | -7.64 | **WARN** | +2.36 |
| RKLB | 1.0 | 83.41 | 73.95 | 73.95 | -11.34 | **STOP** ⚠️ | -1.34 |

- 總資產：USD 630.24
- 總 P&L：-USD 10.79 (-1.68%)
- 現金：USD 257.7
- **RKLB 已觸 STOP 但未平倉**（系統無自動下單機制）

完整 JSON 見 `portfolio/portfolio.json`。

---

## 🔧 排程（簡表）

詳細見 `schedule.md`。簡版：

| HKT 時間 | Cron | 用途 |
|---------|------|------|
| 08:30 | morning-briefing | 隔夜複盤（8月後嘅 main 推送） |
| 16:00 | mag7-premarket | 真盤前（觀察池） |
| 21:30 | project-x-daily + mag7-daily | 美股開市 |
| 05:00 | project-x-close | 收市後 |
| 05:05 | mag7-close | 收市後（觀察池） |
| 23:00 | data-integrity-check | 數據完整性 |

⚠️ **截至 2026-09-28，7 個 cron 全部 `enabled=false`**（paused 2026-09-21 19:03，原因 `moved to gushen profile; 古神 bot DM`）。即係話 9-21 之後呢 7 個 cron **冇自動跑**。當前推送服務由古神 bot (Project X Nas / Soonoo DM) 提供。

---

## 🚨 已知問題（必讀）

1. **2026-09-18 之後 daily + mag7-daily 失敗**：`HTTP 403 spending-limit` (xai 信用乾咗)。已 paused。
2. **RKLB STOP 觸發但無自動執行**：系統只會喺報告寫 `[STOP]` flag，**唔會** 真實平倉。所有交易仍是模擬。
3. **08:30 morning = 隔夜複盤 ≠ 盤前**：美股 09:30 ET = HKT 21:30，所以 08:30 對應美股 20:30 ET（已收市）。
4. **冬令時間**：11 月首週日之後美股開市改 HKT 22:30（差 13h）。Cron expr 仍係 `* * * 1-5`，但 HKT 相對時間變。
5. **bot token 喺 `/opt/data/.env`**：冇 export 出嚟（公開 repo 規範）。`mag7_push.py` 真 TG send；`telegram_push.py` 仍 print-only stub。

---

## 🔐 安全約定（已遵守）

- ❌ **冇任何 API key、Telegram bot token、chat_id 真實值、密碼喺此 export**
- ✅ `telegram chat_id` 真實值已 redact（保留 chat_name）
- ✅ Bot token 完全冇 export
- ✅ `.env` 唔 export
- ⚠️ 若古神合併時需要實測，要喺自己環境 recover token

---

## ❓ 未能確認 / 待澄清（請古神確認）

| 項目 | 狀態 | 為何標註 |
|------|------|---------|
| **2026-08-05 至 2026-09-28 之間嘅真實買賣紀錄** | **未能確認有否遺漏** | `portfolio.json` 嘅 `trade_log` 數組只有 1 行 `OPEN PORTFOLIO`（7-08）。即係話呢段時間**冇自動記錄嘅實際 trade**。可能 Roy 真係 hold 住無操作，亦可能有交易記錄喺其他地方而 Hermes 未複製。**古神可唔可以同 Roy 對返 `futu_positions.json` + 富途 App 對話記錄確認？** |
| 9-21 之後嘅 daily/close/morning 推送內容 | 在 `data/` 入面有直到 9-28 嘅 .md/.html 文件，但係 jobs.json paused 後，最後一批推送可能由古神 bot 取代 | 唔肯定邊啲由 Hermes 推、邊啲由古神推。建議睇 cron `output/` timestamp 同 `last_run_at` 對齊 |
| Network / Cron 環境 | 走 `/opt/data/.env` 同 `cronjobs.json` 路徑，新機器重啟需要重新建 | 古神合併時若轉移，環境可能要重灌 |
| VIX 來源 | 用 `yfinance ^VIX` ticker，但 2026 年 VIX 經常性大波動，**有冇實時 backup**？ | 未能確認 |
| 冬令時間切換 | Cron `* * * 1-5` 用 HKT 表達，11 月之後 HKT 16:00 仍然是 04:00 EST，所以 mag7-premarket 仍準確 | 但 daily 21:30 對冬令改 22:30，**有手動 adjust 過 expr 嗎**？ | 

---

## 📞 聯絡

- Hermes 主對話：Soonoo DM
- 古神 bot：Project X Nas group (待 setup)
- Roy 手動操作：富途 App / 直接調整 portfolio.json

---

## 版本

- Export 日期：2026-09-28
- Hermes 版本：MiniMax-M3 (default)
- 最近 cron 跑：2026-09-20 23:00 integrity check (`last_status: ok`)
- 最近數據更新：2026-09-28 08:30 (morning snapshot)
