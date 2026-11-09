# 回調位掃描：執行與可靠性設計

## 定位

呢個係獨立嘅大型藍籌回調研究工具，唔係「核心產品」，亦唔係買入訊號。佢同機會掃描嘅動能／突破模型係兩套唔同策略；突破名單唔會被包裝成回調買位。VOO 核心長線定投同其他衛星個股學習倉分開理解。

## 規則（保持原參數）

一隻股票要同時符合四條：

1. **強勢**：最近 63 個交易日回報 > 0%。
2. **回調**：最新收市價離 52 週日線高位 −8% 至 −18%。
3. **趨勢**：MA50 高過 10 個交易日前。
4. **支撐**：收市價／MA50 介乎 1.00–1.05。

Universe 維持 45 隻大型藍籌；全部名單及門檻以 `config/settings.json` 嘅 `pullback` 為單一來源。回測未證明穩定優勢，唔應為改善歷史數字而調參。

## 主排程

- 唯一入口：`python run.py pullback`；部署上由每分鐘 `ops/hermes/px_job.sh tick` 自動觸發。
- 時間：每個 NYSE 交易日 **09:00 ET**，即常規開市前 30 分鐘；HKT 會跟 DST 自動轉換，唔再寫死 22:00。
- 假期由 `px/clock.py` 處理；重試窗口至 10:30 ET，最多三次嘗試，失敗由現有 watchdog 告警。
- 舊外部 `pullback_scan.sh` cron 應停用，避免雙重掃描或重複通知。`scripts/pullback_scan.py` 只保留為相容入口。

## 狀態語義

| 情況 | 網站／ledger | Telegram |
|---|---|---|
| 完整掃描、有命中 | `ok`，寫入命中及 bar date | 發送一次，有 duplicate guard |
| 完整掃描、零命中 | `ok`，`hit_count: 0` | 靜默 |
| 任何股票數據不足、舊 bar 或請求失敗 | `failed`，列明失敗股票；今次唔當完整名單 | watchdog 重試／告警 |
| 從未執行 | `pending` | 唔當零命中 |
| 通知失敗 | `telegram_failed` | watchdog 重試 |

每次結果寫入 `data/pullback.json`，包括開始／完成時間、最近成功時間、預期及實際 bar date、掃描數、命中數、失敗清單同規則。日間強制執行會剔走未完成嘅當日 bar。

## 驗證

```bash
python run.py pullback --dry-run
python -m unittest tests.test_pullback tests.test_schedule
python run.py status
```

正式部署後先由主排程產生真實結果；repository 入面嘅 `pending` 檔只係初始狀態，唔係偽造掃描。
