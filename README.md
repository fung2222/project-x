# Project X — AI 美股模擬投資系統（合併版 v3）

網站：https://fung2222.github.io/project-x-minimax/ （計劃改名做 https://fung2222.github.io/project-x/，見 `docs/HERMES_HANDOVER.md §9`）

- **紙上組合**：HKD 10,000 ≈ US$1,280（2026-09-13 起），最多 3 隻、每隻 ≤25%、現金 ≥20%、信心 ≥0.75、每筆預設 SL/TP 並自動紙上執行、富途真實手續費、FX 7.8。
- **核心產品**：高潛力機會掃描 Top 5（入場區、止損、目標、R:R、股數、HKD、點解）。⚠️ 回測未證明有優勢，只係研究名單，唔係買入訊號（`docs/AUDIT.md §6`）。
- **推送**：Telegram（開市、每日、盤中 alert、收市＋圖、隔夜複盤、週報），全部 code 生成，**冇 LLM**。真錢由 Roy 自己喺富途落單。
- Mag7 觀察池：retired by Roy 2026-09-28。

## 文件
| 檔案 | 內容 |
|---|---|
| `docs/HERMES_HANDOVER.md` | **交接／營運手冊**：安裝、排程（cron）、切換步驟、核對表 |
| `docs/REQUIREMENTS.md` | Roy 同意咗嘅要求（冇 Roy 批准唔准改） |
| `docs/AUDIT.md` | 兩個系統嘅全面審計、修正、回測結果 |
| `docs/COMPARISON.md` | 合併前 A vs B 對比 |
| `docs/V3_CORE_CHANGES.md`、`docs/archive/` | 歷史紀錄 |
| 根目錄 `PROJECT_X_*.md`、`GROK_BOT_SYSTEM_PROMPT.md` | 舊 Grok Bot 時期文件（過渡期 routine 仲會讀，切換後作廢） |

## 指令
```bash
python run.py status                 # 設定、secret 有冇（唔顯示數值）、今日排程
python run.py tick                   # cron 每分鐘跑（到期 job＋watchdog）
python run.py open|daily|hourly|close|morning|weekly [--dry-run] [--force] [--push]
python run.py scan                   # 印今日 Top 5（唔 send）
python -m unittest discover -s tests # 50 個離線測試
```
Secrets 只放環境變數／`.env`（見 `.env.example`），永遠唔好 commit。

## 結構
`px/`（引擎）、`run.py`（入口）、`config/settings.json`（規則＋排程）、`ops/hermes/`（cron＋wrapper）、`tests/`、`scripts/`（回測等）、`data/`（網站數據、報告存檔、legacy）、網站 `index.html` 等（`classic.html` = 舊版頁）。
