# Project X — A vs B 對比（2026-09-28 HKT，合併前狀態）

> 呢份係合併**之前**兩個系統嘅對比，用嚟解釋點解咁合併。合併後嘅現況睇 `docs/HERMES_HANDOVER.md`；問題同修正睇 `docs/AUDIT.md`。

| 項目 | **A：`fung2222/project-x-minimax`**（Grok Bot routine） | **B：`fung2222/project-x-2026`**（Hermes，gushen profile 每日跑緊） | 合併決定 |
|---|---|---|---|
| 網址 | https://fung2222.github.io/project-x-minimax/ | https://fung2222.github.io/project-x-2026/ | A 做 base（之後改名 `project-x`，舊名做 redirect） |
| 活動 | 每個交易日有推送（開市、每日、hourly、週報） | **活躍**：2026-08-06 起 141 個 commit（05:00 收市、08:30 晨早、21:30 日報），最新 2026-09-28 | 兩邊都係現役；合併後由 Hermes 跑合併版 |
| Code | Python 喺 repo 入面 | Pipeline 喺 Hermes（`/opt/data/project_x_learning`）；2026-09-28 匯出去 repo B `export/2026-09-28/` | B 嘅輸出同好嘅部分移植去 `px/` |
| 排程 | Grok Bot 平台，寫死 HKT（hourly `6 21-23,0-4 * * 1-5` → 漏星期五下半場） | Hermes cron 寫死 HKT（close／morning `1-5` → 漏星期五；DST 未處理）；PX cron 09-21 起 default profile `enabled=false`，由 gushen profile 繼續 | ET 排程＋NYSE 日曆＋watchdog；`run.py tick` |
| LLM | 教學／專業過濾由 Grok Bot LLM 寫 | cron 用 `xai-oauth/grok-4.5`；09-18 起 credit 用完 → daily、mag7 fail | 排程完全唔用 LLM |
| 數據 | yfinance＋Finnhub＋Marketaux | yfinance | yfinance 主，Finnhub 後備＋業績日 |
| 指標 | 假 MA50（約 22 日）、MACD 退化、簡單 RSI、+5 信心 | 真 MA20/MA50、Wilder RSI、trend score；但用未收市 bar | 已收市 bar、Wilder、真 MA、trend score |
| 止損 | 有執行（RKLB 09-21 TP） | **從來冇執行**（RKLB 07-16 起低過 −10% 照揸；TSLA 最低 −24.7%） | 每筆預設 SL/TP，自動紙上執行 |
| 手續費 | `max(US$1, 0.5%)`（低估富途） | 冇計 | 富途香港美股固定式（每單約 US$2） |
| 資金 | HKD 10k ≈ US$1,280（2026-09-13 起） | HKD 5k ≈ US$641（2026-07-08 起，碎股） | HKD 10k book；B 存 `data/legacy/` |
| 組合（09-25／09-28） | 現金 1,140.56、SOUN ×25、權益 1,291.81（+0.92%，舊手續費模型） | NVDA 0.5／TSLA 0.5／RKLB 1.0，總值 630.24（−1.68%） | 唔合併倉位 |
| Telegram | 每日約 15 條（重複多） | 日報 5 段＋收市 4 段（LLM deliver 去 DM） | 每類 1–4 條，全部去群組「Project X Nas」 |
| 網站 | 單頁、冇權益曲線、1.1 MB `signals.json` | 多頁、P&L 圖、報告存檔、學習中心 | B 嘅版面＋A 嘅數據＋機會掃描頁 |
| Mag7 | —— | 獨立觀察池（圖＋報告） | **retired by Roy 2026-09-28** |
| Secrets | key／token 入咗 public repo | 冇 | 已移除；要 rotate／revoke |

## B 嘅內容點處理
- **保留（呈現方式）**：收市報告、隔夜複盤、P&L 曲線、報告存檔、距止損 % 同 risk flag、倉位比例 bar、HKD 換算、學習中心、富途鏡像。
- **唔要**：碎股、加注（攤平）規則、唔執行嘅止損、LLM deliver、一晚兩次 commit、Mag7（Roy 取消）。
