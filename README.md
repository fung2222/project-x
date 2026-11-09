# Project X — 美股學習、模擬與風控系統（v3.2）

網站：https://fung2222.github.io/project-x/ ・ Repo：`fung2222/project-x`（2026-09-28 由 `project-x-minimax` 改名；舊網址自動跳轉，見 `docs/HERMES_HANDOVER.md §9`）

- **紙上組合**：HKD 10,000 ≈ US$1,280（2026-09-13 起），最多 3 隻、每隻 ≤25%、現金 ≥20%、信心 ≥0.75、每筆預設 SL/TP 並自動紙上執行、富途真實手續費、FX 7.8。
- **動能／突破研究**：Top 5 只係研究名單（入場區、止損、目標、R:R、模擬注碼）。回測未證明有優勢，唔係買入訊號（`docs/AUDIT.md §6`）。
- **大型藍籌回調研究**：45 隻藍籌、四條件、09:00 ET 主排程；完整零命中同數據失敗分開記錄（`docs/pullback_plan.md`）。
- **核心／衛星分層**：VOO 核心長線定投同其他個股衛星學習倉分開顯示；系統永遠唔會自動落真倉。
- **推送**：Telegram（開市、每日、盤中 alert、收市＋圖、隔夜複盤、週報），全部 code 生成，**冇 LLM**。真錢由 Roy 自己喺富途落單。
- Mag7 觀察池：retired by Roy 2026-09-28。

## 網站結構

`總覽 → 組合 → 信號 → 突破研究 → 回調研究 → 報告 → 學習`。首頁只保留真倉、關鍵風險、市場摘要同研究精選；完整掃描、交易紀錄、回測及 legacy 證據按需展開，冇刪走歷史資料。

## 文件

| 檔案 | 內容 |
|---|---|
| `docs/HERMES_HANDOVER.md` | **交接／營運手冊**：安裝、排程（cron）、切換步驟、核對表 |
| `docs/REQUIREMENTS.md` | Roy 同意咗嘅要求（冇 Roy 批准唔准改） |
| `docs/AUDIT.md` | 兩個系統嘅全面審計、修正、回測結果 |
| `docs/UPDATE_2026-11-09.md` | 可靠性、全站視覺整理及驗證紀錄 |
| `docs/SITE_UX_AUDIT_2026-11-09.md` | 原始全站專業評估 |
| `docs/COMPARISON.md`、`docs/V3_CORE_CHANGES.md`、`docs/archive/` | 歷史紀錄 |

舊 Grok Bot 根目錄文件、重複投資計劃、本機 Excel 生成器及已被 `run.py`／`px/` 取代嘅獨立啟動工具已喺 v3.2 移除；歷史仍可喺 Git 紀錄追查。

## 指令

```bash
python run.py status                 # 設定、secret 有冇（唔顯示數值）、今日排程
python run.py tick                   # cron 每分鐘跑（到期 job＋watchdog）
python run.py open|daily|hourly|pullback|close|morning|weekly [--dry-run] [--force] [--push]
python run.py scan                   # 印今日 Top 5（唔 send）
python -m unittest discover -s tests # 離線單元測試
```

Secrets 只放環境變數／`.env`（見 `.env.example`），永遠唔好 commit。

## 結構

`px/`（引擎）、`run.py`（唯一主入口）、`config/settings.json`（規則＋排程）、`ops/hermes/`（cron＋wrapper）、`tests/`、`scripts/`（回測等）、`data/`（網站數據、報告存檔、legacy）、七個主頁及共用 `css/style.css`／`js/px.js`。
