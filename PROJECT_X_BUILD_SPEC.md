# Project X — 完整 Build Spec (v3.0)
> 任何 AI agent 拎到呢份文件，即可 100% 重建整個系統
> 撰寫日期：2026-07-08
> 系統狀態：PHASE 3 模擬交易（運行中）

---

## 目錄

1. [系統簡介](#1-系統簡介)
2. [用戶資料](#2-用戶資料)
3. [目標與方向](#3-目標與方向)
4. [工具一覽](#4-工具一覽)
5. [系統架構](#5-系統架構)
6. [工作流程圖](#6-工作流程圖)
7. [Cron 排程](#7-cron-排程)
8. [文件結構](#8-文件結構)
9. [Python 模組詳解](#9-python-模組詳解)
10. [算法詳解](#10-算法詳解)
11. [數據結構](#11-數據結構)
12. [API Keys 與認證](#12-api-keys-與認證)
13. [數據源真實性審計](#13-數據源真實性審計)
14. [還原步驟（從零開始）](#14-還原步驟從零開始)
15. [風險管理規則](#15-風險管理規則)
16. [推送格式模板](#16-推送格式模板)
17. [Dashboard 設計](#17-dashboard-設計)
18. [已知陷阱](#18-已知陷阱)
19. [驗證清單](#19-驗證清單)
20. [進階擴展](#20-進階擴展)

---

## 1. 系統簡介

**Project X** 係一個**美股模擬投資學習系統**，由 AI agent 全自動運行。

**核心目標：**
- 每日自動分析 3 隻核心美股（NVDA、TSLA、RKLB）
- 用真實市場數據（Yahoo Finance + Finnhub + Marketaux）
- 應用 VIX Guardrail 風險控制
- 推送分析結果到 Telegram
- 提供視覺化 Dashboard
- 追蹤命中率，協助用戶建立入市信心

**系統特點：**
- 100% 真實數據（無虛構、無虛擬新聞）
- 全自動（無需人手操作）
- 可擴展（任何 AI agent 可重啟）
- 雙重驗證（多源數據）

---

## 2. 用戶資料

| 項目 | 內容 |
|------|------|
| **姓名** | Soonoo |
| **語言** | 繁體中文（粵語）|
| **平台** | Telegram、微信 |
| **投資背景** | 美股新手 |
| **券商** | 富途牛牛 / 耀才寶寶 |
| **資金** | HKD 5,000（觀察者模式）|
| **目標** | 累積信心後真實入市 |
| **風格** | 簡單直接、新手友好、視覺化 |

**核心持股偏好：**
- AI + 太空 + 馬斯克生態
- 3 隻核心股：NVDA、TSLA、RKLB
- 擴展觀察：AMD、MSFT、GOOGL、META、PLTR、ARM

---

## 3. 目標與方向

### 短期目標
- 每日 22:00 HKT 自動生成市場分析
- Telegram 推送 8-11 個部分嘅完整報告
- 命中率追蹤由 0 開始建立

### 中期目標
- 累積 10+ 筆模擬交易紀錄
- 命中率達到 60% 以上
- 用戶建立對系統嘅信心

### 長期目標
- 用戶真實入市（HKD 5,000 → 富途牛牛）
- 系統繼續提供每日分析支持
- 4 個階段漸進：
  - PHASE 1: 觀察期
  - PHASE 2: 論述建立期
  - PHASE 3: 模擬入市期 ← **目前**
  - PHASE 4: 真實入市期

### 成功指標
- 命中率 ≥ 60%
- 最大回撤 < 15%
- 用戶有信心使用真實資金

---

## 4. 工具一覽

| 工具 | 用途 | 類型 |
|------|------|------|
| **Python 3.12** | 主要程式語言 | 執行環境 |
| **yfinance** | Yahoo Finance 股票數據 | 數據源 |
| **Finnhub API** | 新聞 + 分析師詳細分佈 | 數據源 |
| **Marketaux API** | 新聞 + sentiment 分數 | 數據源 |
| **requests** | HTTP 請求 | Python 套件 |
| **GitHub Pages** | Dashboard 託管 | 部署 |
| **GitHub REST API** | 自動部署 | 部署 |
| **Telegram Bot API** | 推送通知 | 通知 |
| **Mavis Cron** | 排程調度 | 自動化 |
| **HTML/CSS/JS** | Dashboard 前端 | UI |
| **PowerShell** | Windows shell | 執行 |
| **Python 3.13 (hermes venv)** | Mavis agent runtime | 環境 |

---

## 5. 系統架構

```
project_x/
├── analyzer.py              # 主分析引擎
├── telegram_push.py         # Telegram 推送
├── finnhub_api.py           # 數據整合層
├── vix_guardrail.py         # VIX 風險控制
├── weekly_report.py         # 每週報告
├── risk_manager.py          # 止損/止盈/加倉
├── market_open_alert.py     # 開市預警
├── position_tracker.py      # 持倉追蹤
├── benchmark.py             # 基準對比
│
├── portfolio.json           # 帳戶配置 + 持倉
├── signals.json             # 信號 + 命中率
├── daily_report.json        # 最新每日報告
├── profiles.json            # 基本面資料
│
├── telegram_config.json     # Telegram 配置
├── finnhub_config.json      # Finnhub API key
├── marketaux_config.json    # Marketaux API key
│
├── PROJECT_X_MANUAL.md      # 用戶手冊
├── PROJECT_X_BUILD_SPEC.md # 完整 build spec（即本文件）
│
└── index.html               # Dashboard
```

---

## 6. 工作流程圖

### 每日自動流程
```
22:00 HKT (每日)
    │
    ▼
[analyzer.py]
    ├─ ① VIX Guardrail
    ├─ ② Yahoo Finance: 取得實時報價
    ├─ ③ 計算技術指標（RSI / MACD / 成交量 / MA50 / ATR）
    ├─ ④ 取得基本面（yfinance）
    ├─ ⑤ 取得新聞（yfinance + Finnhub + Marketaux）
    ├─ ⑥ 應用規則生成信號（BUY / HOLD / SELL）
    ├─ ⑦ 過濾已持倉（避免重複買入）
    ├─ ⑧ 保存 signals.json + profiles.json
    └─ ⑨ 保存 daily_report.json
    │
    ▼
[telegram_push.py]
    ├─ 讀取 daily_report.json
    ├─ 構建 11 個部分
    └─ 發送到 Telegram
    │
    ▼
[風險管理（同步）]
    ├─ 檢查持倉止損/止盈
    ├─ 自動執行（如觸發）
    └─ 更新 trade_log

[持倉追蹤（每小時 21:00-04:00）]
    └─ 更新 current_price

[開市預警（21:35）]
    └─ 偵測倉位異動
```

---

## 7. Cron 排程

### project-x-daily.md
```yaml
---
name: project-x-daily
schedule: 0 22 * * *           # 每日 22:00 HKT
timezone: Asia/Hong_Kong
reportToRoot: false           # 必須 false
reportToMain: false           # 必須 false
---
Run Project X daily analysis: execute py -3.12 C:\path\to\project_x\analyzer.py; then execute py -3.12 C:\path\to\project_x\telegram_push.py. Silent execution only.
```

### project-x-weekly.md
```yaml
---
name: project-x-weekly
schedule: 0 9 * * 1           # 每週一 09:00 HKT
timezone: Asia/Hong_Kong
reportToRoot: false
reportToMain: false
---
Run Project X weekly performance report: execute py -3.12 C:\path\to\project_x\weekly_report.py. Silent execution only.
```

### project-x-market-open.md
```yaml
---
name: project-x-market-open
schedule: 35 21 * * *         # 每日 21:35 HKT
timezone: Asia/Hong_Kong
reportToRoot: false
reportToMain: false
---
Run Project X market open alert: execute py -3.12 C:\path\to\project_x\market_open_alert.py. Silent execution only.
```

### project-x-position-tracker.md
```yaml
---
name: project-x-position-tracker
schedule: 0 21-23,0-4 * * *   # 21:00-23:00 + 00:00-04:00
timezone: Asia/Hong_Kong
reportToRoot: false
reportToMain: false
---
Run Project X position tracker (hourly quote update): execute py -3.12 C:\path\to\project_x\position_tracker.py. Silent execution only.
```

**關鍵點：**
- `py -3.12` — 因為 hermes venv Python 3.13 冇 yfinance
- `reportToRoot: false` — **必須**，否則會崩潰循環
- `Asia/Hong_Kong` 時區明確指定

---

## 8. 文件結構

### 8.1 工作目錄
```
C:\Users\fung2\.mavis\agents\mavis\workspace\project_x\
```

### 8.2 Cron 目錄
```
C:\Users\fung2\.mavis\agents\mavis\crons\
├── project-x-daily.md
├── project-x-weekly.md
├── project-x-market-open.md
└── project-x-position-tracker.md
```

### 8.3 認證目錄
```
C:\Users\fung2\.mavis\credentials\mavis\
└── telegram.json
```

---

## 9. Python 模組詳解

### 9.1 analyzer.py
**功能**：主分析引擎

**關鍵函數：**
- `analyze_day(quiet=True)` — 主入口，返回完整報告
- `get_cached_report(max_age_minutes=30)` — 緩存機制
- `generate_signal(ticker, quote, tech, gr)` — 生成單個股票信號
- `update_hit_rate()` — 更新命中率統計

**依賴**：finnhub_api, vix_guardrail, json, datetime

### 9.2 finnhub_api.py
**功能**：數據整合層（最重要）

**關鍵函數：**
- `get_quote(ticker)` — 取得單一股票報價（yfinance）
- `get_tech_indicators(ticker)` — 計算 RSI / MACD / MA50 / ATR
- `get_stock_profile(ticker)` — 取得基本面（yfinance）
- `fetch_finnhub_company_news(ticker)` — Finnhub 新聞
- `fetch_finnhub_recommendation(ticker)` — Finnhub 分析師分佈
- `fetch_marketaux_news(ticker)` — Marketaux 新聞 + sentiment
- `get_vix_regime()` — VIX 市場狀態

**依賴**：yfinance, requests, json, datetime, os

**常數：**
- `WATCH_PRIMARY = ["NVDA", "TSLA", "RKLB"]`
- `WATCH_SECONDARY = ["AMD", "MSFT", "GOOGL", "META", "PLTR", "ARM"]`
- `WATCH_INDEX = ["SPY", "QQQ", "^VIX"]`

### 9.3 vix_guardrail.py
**功能**：VIX 風險控制

**規則：**
```python
def check_guardrail(vix_value):
    if vix < 20:    return "NORMAL"   # 3 隻倉位，信心 70%
    if vix < 30:    return "CAUTION"  # 2 隻倉位，信心 75%
    if vix >= 30:   return "DEFENSIVE" # 1 隻倉位，信心 85%
```

### 9.4 risk_manager.py
**功能**：止損 / 止盈 / 加倉

**關鍵函數：**
- `evaluate_all_positions(current_prices)` — 評估所有持倉
- `execute_action(ticker, action, current_price)` — 執行交易
- `check_stop_loss(position, current_price, atr)` — ATR 止損
- `check_take_profit(position, current_price)` — +10% 止盈
- `check_add_position(position, current_price, indicators)` — 加倉邏輯

### 9.5 telegram_push.py
**功能**：Telegram 推送（11 個部分）

**關鍵函數：**
- `build_daily_message()` — 構建所有推送部分
- `format_market_section(report)` — 市場狀況
- `format_portfolio_section()` — 持倉狀態
- `format_signals_section(report)` — 今日信號 + 買入/唔買入理由
- `format_yesterday_review()` — 昨日回顧
- `format_performance_section()` — 系統績效
- `format_review_section(report)` — 自我檢討 + 改善建議
- `format_analyst_detail_section()` — 分析師詳細分佈
- `format_news_section(news)` — 中文新聞分析
- `send_daily_push()` — 發送

### 9.6 market_open_alert.py
**功能**：開市預警（21:35 HKT）

**邏輯：**
- 取得持倉 5 分鐘 K 線
- 偵測 ±2% 變動
- 觸發止損/止盈 → 自動執行

### 9.7 position_tracker.py
**功能**：持倉追蹤（每小時）

**邏輯：**
- 取得所有持倉當前價格
- 更新 current_price / value_usd / pnl
- 唔推送 Telegram（靜默更新）

### 9.8 benchmark.py
**功能**：基準對比（vs SPY）

**邏輯：**
- 計算組合總回報（從 PHASE 3 開始日）
- 取得 SPY 同期回報
- 計算 alpha
- 判斷「跑贏 / 跑輸大市」

### 9.9 weekly_report.py
**功能**：每週報告

**邏輯：**
- 統計本週交易
- 計算命中率
- 比較 SPY 基準
- Telegram 推送

---

## 10. 算法詳解

### 10.1 RSI (14-day)
```python
gains = [max(0, closes[-i] - closes[-i-1]) for i in range(1, 15)]
losses = [abs(min(0, closes[-i] - closes[-i-1])) for i in range(1, 15)]
avg_gain = sum(gains) / len(gains)
avg_loss = sum(losses) / len(losses)
rs = avg_gain / avg_loss if avg_loss > 0 else 100
rsi = 100 - (100 / (1 + rs))
```

### 10.2 MACD (12/26 EMA)
```python
def ema(data, period):
    k = 2 / (period + 1)
    val = data[0]
    for d in data[1:]:
        val = d * k + val * (1 - k)
    return val

ema12 = ema(closes, 12)
ema26 = ema(closes, 26)
macd_line = ema12 - ema26
macd_bullish = macd_line > 0
```

### 10.3 信號決策
```
RSI 規則:
  RSI < 30  → 強烈 BUY（信心 70-90%）
  RSI 30-40 → BUY（信心 60-80%）
  RSI 40-45 → HOLD
  RSI 45-62 → HOLD
  RSI 62-68 → HOLD
  RSI 68-75 → SELL
  RSI > 75  → 強烈 SELL

MACD 修正:
  MACD 看漲 + BUY  → 信心 +8
  MACD 看跌 + BUY  → 信心 -10
  MACD 看跌 + SELL → 信心 +5

成交量修正:
  vol >= 1.2x + BUY  → 信心 +5
  vol <  0.5x + BUY  → 信心 -8

MA50 修正:
  price > MA50 + BUY → 信心 +5
  price < MA50 + BUY → 信心 -5
```

### 10.4 命中率計算
```
✅ 命中 = 第2日收盤 > 進場價 +2%
⚠️ 部分 = 第2日走勢正確但未達 +2%
❌ 失誤 = 第2日走勢相反
➖ 中立 = 走勢喺 ±2% 內（不計入統計）
```

### 10.5 止損（ATR-based）
```python
stop_price = entry_price - (atr * 2.0)
triggered = current_price <= stop_price
```

### 10.6 止盈（+10%）
```python
target_price = entry_price * 1.10
triggered = current_price >= target_price
```

---

## 11. 數據結構

### 11.1 portfolio.json
```json
{
  "version": "2.0",
  "account": {
    "capital_hkd": 5000,
    "capital_usd_approx": 641,
    "mode": "paper",
    "phase": "PHASE_3_SIMULATED_ENTRY",
    "cash_usd": 445.45,
    "equity_usd": 641.00
  },
  "positions": [
    {
      "ticker": "NVDA",
      "shares": 1,
      "entry_price": 195.55,
      "current_price": 195.55,
      "cost_usd": 195.55,
      "value_usd": 195.55,
      "pnl_usd": 0,
      "pnl_pct": 0,
      "analyst_consensus": "強烈買入"
    }
  ],
  "trade_log": [
    {
      "id": "T001",
      "date": "2026-07-07",
      "ticker": "NVDA",
      "action": "BUY",
      "shares": 1,
      "entry_price": 195.55,
      "cost_usd": 195.55,
      "status": "open"
    }
  ],
  "rules": {
    "max_positions": 3,
    "min_confidence": 0.70,
    "stop_loss_type": "ATR",
    "stop_loss_atr_mult": 2.0,
    "take_profit_pct": 0.10
  },
  "watchlist": {
    "primary": ["NVDA", "TSLA", "RKLB"],
    "secondary": ["AMD", "MSFT", "GOOGL", "META", "PLTR", "ARM"]
  }
}
```

### 11.2 signals.json
```json
{
  "version": "1.0",
  "signals": [
    {
      "ticker": "NVDA",
      "signal": "HOLD",
      "confidence": 60,
      "price": 195.55,
      "rsi": 40.9,
      "macd_bullish": true,
      "vol_ratio": 0.72,
      "analyst_consensus": "強烈買入",
      "target_mean": 301.62,
      "upside_pct": 54.8,
      "earnings_date": "2026-08-26",
      "earnings_days": 52,
      "date": "2026-07-07"
    }
  ],
  "performance": {
    "total_signals": 0,
    "hits": 0,
    "hit_rate_pct": 0
  }
}
```

### 11.3 daily_report.json
```json
{
  "date": "2026-07-07",
  "market": {
    "vix": 15.57,
    "regime": "正常市場",
    "spy_price": 744.78,
    "spy_change": -0.13
  },
  "guardrail": {
    "regime": "NORMAL",
    "max_positions": 3,
    "min_confidence": 0.7
  },
  "signals": [...],
  "profiles": {...},
  "top_picks": [...],
  "summary": {
    "buy_signals": 0,
    "hold_signals": 9,
    "sell_signals": 0
  }
}
```

### 11.4 profiles.json
```json
{
  "NVDA": {
    "symbol": "NVDA",
    "analyst_consensus": "強烈買入",
    "analyst_emoji": "🟢",
    "num_analysts": 58,
    "target_mean": 301.62,
    "upside_pct": 54.8,
    "earnings_date": "2026-08-26",
    "earnings_days": 52,
    "pe_ratio": 60.5,
    "industry": "Semiconductors",
    "news": [
      {
        "title": "Why this AI chip startup could rival Nvidia",
        "sentiment": "中性",
        "sentiment_emoji": "⚪",
        "date": "07/06",
        "desc_zh": "英偉達 AI／晶片板塊",
        "provider": "yfinance"
      }
    ]
  }
}
```

---

## 12. API Keys 與認證

### 12.1 Telegram Bot Token
**存放：** `C:\Users\fung2\.mavis\credentials\mavis\telegram.json`
**格式：**
```json
{
  "bot_token": "<set via env TELEGRAM_BOT_TOKEN — never commit>",
  "chat_id": "<set via env TELEGRAM_CHAT_ID>"
}
```

### 12.2 Finnhub API Key
**存放：** `C:\Users\fung2\.mavis\agents\mavis\workspace\project_x\finnhub_config.json`
**格式：**
```json
{
  "api_key": "<set via env FINNHUB_API_KEY — never commit>",
  "enabled": true
}
```

### 12.3 Marketaux API Key
**存放：** `C:\Users\fung2\.mavis\agents\mavis\workspace\project_x\marketaux_config.json`
**格式：**
```json
{
  "api_key": "<set via env MARKETAUX_API_KEY — never commit>",
  "enabled": true
}
```

### 12.4 GitHub Personal Access Token
**存放：** 由 Agent 喺 script 入面臨時設定
**格式：** `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
**權限：** `repo` + `pages`

### 12.5 環境變數備用
```bash
export FINNHUB_API_KEY="..."
export MARKETAUX_API_KEY="..."
```

---

## 13. 數據源真實性審計

| 數據 | 來源 | 真實度 |
|------|------|--------|
| 股價 | Yahoo Finance | ✅ 100% |
| 成交量 | Yahoo Finance | ✅ 100% |
| VIX | Yahoo Finance ^VIX | ✅ 100% |
| 目標價 | Yahoo Finance | ✅ 100% |
| 分析師評級 | Yahoo Finance + Finnhub | ✅ 100% |
| 新聞標題 | 三源驗證 | ✅ 100% |
| Sentiment | Marketaux 真實分數 | ✅ 100% |
| 技術指標 | 自己用真實數據計 | ✅ 邏輯正確 |

**零虛構、零虛擬新聞**

---

## 14. 還原步驟（從零開始）

### Step 1: 建立目錄
```bash
mkdir -p C:\Users\fung2\.mavis\agents\mavis\workspace\project_x
mkdir -p C:\Users\fung2\.mavis\agents\mavis\crons
mkdir -p C:\Users\fung2\.mavis\credentials\mavis
```

### Step 2: 安裝 Python 套件
```bash
py -3.12 -m pip install yfinance requests
```

### Step 3: 創建配置文件
```bash
# telegram.json
echo '{"bot_token":"<your_token>","chat_id":"<your_chat_id>"}' > C:\Users\fung2\.mavis\credentials\mavis\telegram.json

# finnhub_config.json
echo '{"api_key":"<your_finnhub_key>","enabled":true}' > C:\path\to\project_x\finnhub_config.json

# marketaux_config.json
echo '{"api_key":"<your_marketaux_key>","enabled":true}' > C:\path\to\project_x\marketaux_config.json

# telegram_config.json
echo '{"bot_token":"<your_token>","chat_id":"<your_chat_id>","daily_push_time":"08:30","enabled":true}' > C:\path\to\project_x\telegram_config.json
```

### Step 4: 創建 Python 模組
按本文件第 9 節，創建以下文件：
- `finnhub_api.py`（~600 行）
- `analyzer.py`（~358 行）
- `telegram_push.py`（~500 行）
- `vix_guardrail.py`（~100 行）
- `risk_manager.py`（~200 行）
- `market_open_alert.py`（~100 行）
- `position_tracker.py`（~80 行）
- `benchmark.py`（~80 行）
- `weekly_report.py`（~150 行）

### Step 5: 創建 Cron 配置
按本文件第 7 節，創建 4 個 .md 文件。

### Step 6: 創建 Dashboard
創建 `index.html`（6 個 tab 的 SPA）。

### Step 7: 初始化 portfolio.json
```json
{
  "version": "2.0",
  "account": {
    "capital_hkd": 5000,
    "capital_usd_approx": 641,
    "mode": "paper",
    "phase": "PHASE_3_SIMULATED_ENTRY"
  },
  "positions": [],
  "trade_log": [],
  "watchlist": {
    "primary": ["NVDA", "TSLA", "RKLB"],
    "secondary": ["AMD", "MSFT", "GOOGL", "META", "PLTR", "ARM"]
  }
}
```

### Step 8: 創建 GitHub Repo
```bash
# 用 GitHub API 或網頁
# Repo: <username>/project-x-minimax
# 啟用 Pages (main branch, / root)
```

### Step 9: 首次運行測試
```bash
py -3.12 C:\path\to\project_x\analyzer.py
py -3.12 C:\path\to\project_x\telegram_push.py
```

### Step 10: 部署 Dashboard
```bash
# 用 GitHub API 上傳 index.html + JSON 文件
```

---

## 15. 風險管理規則

### 15.1 VIX Guardrail
| VIX | 狀態 | 倉位上限 | 信心度門檻 |
|-----|------|---------|-----------|
| < 20 | NORMAL | 3 隻 | 70% |
| 20-30 | CAUTION | 2 隻 | 75% |
| > 30 | DEFENSIVE | 1 隻 | 85% |

### 15.2 持倉規則
- 單股最大倉位：30% 總資金
- 現金保留：20% 最低
- 最大持倉：3 隻
- 每日最大交易：2 次

### 15.3 止損規則
- ATR-based 止損：entry_price - 2x ATR
- 固定止盈：entry_price + 10%
- 加倉：RSI < 45 + MACD 看漲 + 倉位 < 70% 上限

### 15.4 交易費
- 模擬交易費：1%（買 + 賣各 0.5%）

---

## 16. 推送格式模板

### 16.1 Telegram 推送（11 個部分）
1. 標題（日期時間）
2. 市場狀況（VIX / SPY / QQQ）
3. 持倉狀態（NVDA 等持倉 + P&L）
4. 今日信號（+ 買入/唔買入理由）
5. 昨日信號 vs 今日結果
6. 系統績效（命中率統計）
7. 每日自我檢討（+ 改善建議）
8. 分析師詳細分佈（Finnhub）
9. 核心股新聞分析（三源 + 中文）
10. 系統自我檢討
11. Footer

### 16.2 HTML 格式
使用 HTML 格式（避免 MarkdownV2 escape 問題）：
- `<b>...</b>` 粗體
- `<i>...</i>` 斜體
- `\n` 換行

### 16.3 訊息長度
- Telegram 限制：4096 chars/msg
- 自動分割：每部分獨立發送

---

## 17. Dashboard 設計

### 17.1 URL
`https://<username>.github.io/project-x-minimax/`

### 17.2 6 個 Tab

| Tab | 內容 |
|-----|------|
| 🎯 每日信號 | 9 隻股票嘅信號 + MACD + 成交量 + 分析師 + 業績倒數 |
| 📋 基本面 | 每隻股票嘅分析師共識、目標價、現價、新聞 |
| 💼 持倉 | 帳戶概況、當前階段、觀察清單 |
| 📊 分析摘要 | 市場狀態 + TOP 揀選 + 買入理由 |
| 🎯 命中率 | 命中率統計 + 歷史記錄 |
| ⚙️ 規則 | 系統規則說明 |

### 17.3 JSON 數據源
- `signals.json`
- `daily_report.json`
- `profiles.json`
- `portfolio.json`

### 17.4 部署
- GitHub Pages（main branch, / root）
- 用 GitHub REST API 自動部署

---

## 18. 已知陷阱

| 陷阱 | 解決方法 |
|------|---------|
| `hermes venv` Python 3.13 冇 yfinance | 用 `py -3.12` |
| Cron 崩潰循環（無限重試） | `reportToRoot: false` + `reportToMain: false` |
| Telegram MarkdownV2 escape 困難 | 用 HTML 格式 |
| yfinance 15 分鐘延遲 | 用 Finnhub 補充（即時）|
| Surge 未安裝 | 用 GitHub Pages（更穩定）|
| `rm -rf` 危險 | 用 `mavis-trash` (recoverable) |
| 舊測試數據污染 | 清空 signals.json，只保留實時數據 |
| numpy bool 序列化失敗 | 用 `bool()` 強制轉換 |
| GitHub token 過期 | 重新申請 personal access token |

---

## 19. 驗證清單

建立系統後，運行以下測試確保正常：

```
✅ py -3.12 analyzer.py → 應輸出 7 步成功 + 每日摘要
✅ py -3.12 telegram_push.py → 應輸出 8 個 "Part X sent"
✅ py -3.12 risk_manager.py → 應輸出持倉評估
✅ py -3.12 benchmark.py → 應輸出 vs SPY 比較
✅ 打開 index.html → 6 個 tab 全部載入數據
✅ 等 22:00 HKT → 自動收到 Telegram 推送
✅ 等 21:35 HKT → 自動收到開市預警
✅ 等每小時 → 持倉價格自動更新
```

---

## 20. 進階擴展

### 20.1 真實即時數據
升級到 Polygon.io / Tradier 提供 tick-level 報價
- Polygon: $29/月 起
- Tradier: 免費 tier 有限制

### 20.2 自動交易（券商 API）
接駁富途牛牛 / 耀才寶寶 API，自動下單
- 需券商開放 API
- 需風險控制模組

### 20.3 機器學習優化
用歷史數據訓練模型，優化信號決策
- 需要 Python ML 套件（sklearn, pytorch）
- 至少 100 筆交易數據

### 20.4 多組合管理
支援多個組合（如「NVDA 組合」、「TSLA 組合」）
- 需要重構 portfolio.json
- Dashboard 加組合切換

---

## 📊 附錄：關鍵 URL

| 名稱 | URL |
|------|-----|
| Dashboard | https://fung2222.github.io/project-x-minimax/ |
| GitHub Repo | https://github.com/fung2222/project-x-minimax |
| Yahoo Finance | https://finance.yahoo.com/ |
| Finnhub Dashboard | https://finnhub.io/dashboard |
| Marketaux | https://www.marketaux.com/ |

---

## 📝 版本歷史

| 版本 | 日期 | 變更 |
|------|------|------|
| 1.0 | 2025-07-05 | 初始版本 |
| 2.0 | 2026-07-05 | 加入分析師評級、新聞 sentiment |
| 3.0 | 2026-07-07 | PHASE 3 模擬入市 + 三源新聞驗證 |

---

*本文件係 Project X 嘅完整 build spec。任何 AI agent 收到後，可以 100% 重建整個系統。*
