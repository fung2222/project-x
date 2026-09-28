# Project X + Mag7 Cron 排程表（2026-09-28 snapshot）

**所有時間均為 HKT（香港時間，UTC+8）。所有 cron 使用 Hermes 內建 cronjob 系統（`/opt/data/cron/jobs.json`），非系統 crontab。**

---

## Project X 模擬倉（4 個 cron）

| Cron 名稱 | Job ID | Schedule (cron expr) | HKT 時間 | 用途 | 模型 |
|----------|--------|----------------------|----------|------|------|
| `project-x-daily-report` | `b0ece97aa091` | `30 21 * * 1-5` | **21:30** 每交易日 | 美股開市報告 | xai-oauth/grok-4.5 |
| `project-x-close-report` | `dda4d9ed4a71` | `0 5 * * 1-5` | **05:00** 每交易日 | 收市後報告 | xai-oauth/grok-4.5 |
| `project-x-morning-briefing` | `a1d845966230` | `30 8 * * 1-5` | **08:30** 每交易日 | 隔夜複盤 | xai-oauth/grok-4.5 |
| `project-x-data-integrity-check` | `827895abf50c` | `0 23 * * *` | **23:00** 每日 | 數據完整性核對 | xai-oauth/grok-4.5 |

### 排程方法

- **系統**：Hermes cronjob manager
- **配置檔**：`/opt/data/cron/jobs.json`
- **手動操作**：
  ```bash
  cronjob list
  cronjob action=run job_id=<id>
  cronjob action=enable job_id=<id>
  cronjob action=pause job_id=<id>
  ```
- **狀態**：截至 2026-09-28，4 個 PX cron **全部 `enabled=false`**（paused 2026-09-21 19:03，原因：`moved to gushen profile; 古神 bot DM`）
- **歷史**：53 次 daily/close/morning 跑過（`repeat.completed: 53`），76 次 integrity

### Daily Pipeline 詳細步驟（`run_daily_pipeline.sh`）

```
1. cd /opt/data/project_x_learning && source .venv/bin/activate
2. python3 data_fetcher.py         # 拉 yfinance 數據
3. python3 analyzer.py             # 計算 MA/RSI/score
4. python3 risk_manager.py         # 風險分級
5. python3 telegram_push.py --kind daily   # 產生 TG 文字（print-only）
6. bash push_daily_full.sh         # 用 git push 將 .md/.html 推到 GH Pages
```

### Close/Morning Pipeline 結構相同，telegram kind 唔同

### 推送目標（`deliver`）

- Telegram chat ID REDACTED_TELEGRAM_CHAT_ID（Soonoo DM）

⚠️ **chat_id 同 bot token 已喺 jobs.json 入面 redact**。古神合併時需要自備：
- Telegram bot token（從 `/opt/data/.env`）
- Telegram chat ID（真實值要喺 export 入面 redact）

---

## Mag7 觀察池（3 個 cron · 獨立 pipeline）

| Cron 名稱 | Job ID | Schedule | HKT 時間 | 用途 | 模型 |
|----------|--------|----------|----------|------|------|
| `mag7-premarket` | `b655bf26892b` | `0 16 * * 1-5` | **16:00** 每交易日 | 真盤前報告 | xai-oauth/grok-4.5 |
| `mag7-daily` | `8405f161cfea` | `30 21 * * 1-5` | **21:30** 每交易日 | 美股開市 | xai-oauth/grok-4.5 |
| `mag7-close` | `46d2ea2e5114` | `5 5 * * 1-5` | **05:05** 每交易日 | 收市後 | xai-oauth/grok-4.5 |

### 排程方法

同 PX — Hermes cronjob，jobs.json 內。

### Mag7 Pipeline 詳細步驟（`run_pipeline.sh <kind>`）

```bash
bash /opt/data/mag7_observer/run_pipeline.sh daily|premarket|close
```

此 script：
1. `mag7_data.py` — yfinance 拉 7 隻大科技數據
2. `mag7_chart.py` — 畫 7 張單股 chart PNG (PIL)
3. `mag7_dashboard.py` — 畫 1 張 7-up dashboard PNG (2×4 grid)
4. `mag7_report.py` — 生 HTML 報表
5. `mag7_push.py` — 用 urllib + bot token 送摘要去 TG

### 推送目標

- Telegram chat ID REDACTED_TELEGRAM_CHAT_ID (Soonoo DM)

---

## 時間對照表（美股 ↔ HKT）

| 美股事件 | 美東時間 | 夏令 EDT (Mar-Nov) HKT | 冬令 EST (Nov-Mar) HKT |
|---------|---------|------------------|------------|
| 開市 | 09:30 | 21:30 | 22:30 |
| 收市 | 16:00 | 翌日 04:00 | 翌日 05:00 |
| 收市後定稿 | ~17:00 | 翌日 05:00 | 翌日 06:00 |
| 真盤前 | 04:00 | 16:00 | 16:00 |

**08:30 HKT 對美股 = 隔夜已收市**，所以 morning 叫「隔夜複盤」唔叫「盤前」。

---

## 並行限制

- ✅ PX 模擬倉 cron 同 Mag7 觀察池 cron **可以並行跑**（獨立 process）
- ❌ 同時間多過 2 個 Mag7 chart 渲染 job 跑會搶 CPU
- ⚠️ yfinance rate limit：每分鐘 ~30 個 call；PX daily 同 Mag7 daily 都喺 21:30 跑，但 PX 3 隻 + Mag7 7 隻 = 10 隻，喺 limit 內

---

## 重啟指引（古神接手後）

```bash
# 1. 啟用所有 cron
for id in b0ece97aa091 dda4d9ed4a71 a1d845966230 827895abf50c \
          8405f161cfea b655bf26892b 46d2ea2e5114; do
  cronjob action=enable job_id=$id
done

# 2. 手動跑一次測試
bash /opt/data/project_x_learning/run_daily_pipeline.sh
bash /opt/data/project_x_learning/push_daily_full.sh
bash /opt/data/mag7_observer/run_pipeline.sh daily
```

⚠️ 注意：enable 之前先確認 jobs.json `model/provider` 仍係 `xai-oauth/grok-4.5`，否則會 fail closed（drift detection）。
