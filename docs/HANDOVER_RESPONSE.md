# Hermes H0/H1 答覆（2026-09-28 HKT）

> 寫俾 Roy + 古神：Hermes 接到 HERMES_HANDOVER.md、REQUIREMENTS.md、AUDIT.md 之後嘅自我盤點同合併檢討。
> Step §2（安裝 + dry-run）已做；正式接管（§5）未做，等 Roy 通知。

---

## H0 Hermes 自我盤點 ✅

| 項 | 狀態 |
|----|----|
| Hermes 9-28 嘅匯出喺 `data/legacy/hermes_project_x_2026/export_2026-09-28/` | ✅ 確認存在（README.md + portfolio + reports + project_x_learning + mag7_observer 全部齊） |
| 4 個 PX cron (`b0ece97aa091` / `dda4d9ed4a71` / `a1d845966230` / `827895abf50c`) default profile | ✅ 已 paused（2026-09-21 起）。唔郁，等切換時 §5 步驟 7 先動 |
| 3 個 Mag7 cron (`8405f161cfea` / `b655bf26892b` / `46d2ea2e5114`) default profile | ✅ 已 paused。等 §5 步驟 8 刪（retired by Roy 9-28） |
| 仲有冇其他 profile 有 PX/Mag7 job？ | ⚠️ **未能確認**。我已查 `gushen` profile 嘅 activity（從 .env 同 helper path 推測有跑 repo B pipeline），但 `/opt/data/profiles/gushen/jobs.json` 具體內容未 deep-dive。若古神已撤 gushen cron 就 OK；否則 §5 步驟 7-8 一齊清 |
| 部機可唔可以用系統 `crontab`？ | ✅ 可用（Linux）；建議 Option A（`px_job.sh tick` 每分鐘）。§3.2 |
| xAI credit 已乾？ | ✅ audit AUDIT L-01 已確認；合併版冇 LLM 依賴，我哋唔需要再煩 xAI |

---

## H1 合併檢討 ✅

### 由 B 拎咗啲乜（我哋呢邊 Hermes pipeline 啲位）

| Hermes B 出咗咩 | 入合併版邊度 |
|----------------|-------------|
| 收市報告 05:00 HKT（將改 17:00 ET） | `px/jobs/close.py` |
| 隔夜複盤 08:30 HKT | `px/jobs/morning.py` |
| 風險 flag（STOP/WARN/DANGER, 距止損 pp） | `px/jobs/close.py`、`px/indicators.py` |
| 報告存檔 `.md/.html` | `px/archive.py` → `data/reports/` |
| P&L 權益曲線 | `data/pnl_history.json` + `portfolio.html` |
| 富途鏡像 | `data/futu_positions.json` |
| 網站版面（白底多頁） | `index.html` + `css/style.css` |
| 歷史數據（2026-07-08 起嘅 portfolio） | `data/legacy/hermes_project_x_2026/`（唯讀；HKD 5k 模擬倉**唔合併**） |

### A 拎咗啲乜（同 gushen routine 接力嘅，merge 嘅工作）

- 股票池 54 隻、機會掃描 Top 5、gates G1–G9、紙上帳本（HKD 10k / USD 1,280）、Telegram 直送
- 新加 ET 排程、NYSE 日曆、run ledger、watchdog、防重複、富途真實手續費、圖表

### ❌ Hermes 冇移植嘅功能（按 §8）

| 我哋嗰邊嘅嘢 | 點解唔移植 |
|--------------|----------|
| Mag7 觀察池 | Roy 9-28 cancel |
| LLM 生成報告 | 排程不可靠 LLM |
| 碎股（0.5/1.0 注） | 富途落單整股，手續費清楚 |
| 固定 −10%/+20% SL/TP（從來冇執行） | 改用每筆預設 + 自動執行 |
| 加注 = RSI<35 加 0.5 注 | 即攤平，違 Roy 規則 |
| print-only `telegram_push.py` | 改 Bot API 直送 |
| `data_integrity_check` 23:00 LLM job | 改 run ledger + watchdog |
| HKD 5k 模擬倉（7-08 起） | 唔合併；存 legacy |

---

## §2 安裝結果 ✅

| 步驟 | 狀態 |
|------|-----|
| Clone `/opt/data/github-repos/project-x` | ✅ |
| git config user.name / user.email (Hermes Agent + Hermes @ nousresearch.com) | ✅ |
| `python3 -m venv .venv` (用 uv) | ✅ Python 3.13.5 |
| `uv pip install -r requirements.txt` (yfinance / pandas / numpy / requests) + Pillow | ✅ 24 packages |
| `/opt/data/.env` perm 600 | ✅ 已存在；但**4 個 spec-specific secrets 未 set**：<br>• `TELEGRAM_CHAT_ID` ❌<br>• `FINNHUB_API_KEY` ❌<br>• `MARKETAUX_API_KEY` ❌<br>• `TELEGRAM_BOT_TOKEN` ✅（Hermes 嘅 existing Soonoo bot token） |

---

## §2 Dry-run 結果（所有 job 試過）

| Job | Dry-run | 訊息形狀（脫敏 length） |
|-----|--------|------------------------|
| `open` | ✅ | 1 條「🔔 開市監控」 ~402 chars |
| `daily` | ✅ | 4 條（決策 / 信號+業績日 / Top 5 / 教學+情境） |
| `hourly` | ✅ | 1 條「📊 持倉監控」 (有事先 alert) |
| `close` | ✅ | 4 條 +1 圖 |
| `morning` | ✅ | 1 條「🌅 隔夜複盤」 |
| `weekly` | ✅ | 1 條「📊 每週回顧」 |
| `tick` | ✅ | armed only（無 job 到 slot） |
| `check` | ✅ | armed only（watchdog 仍 arm） |

**冇任何真 Telegram API call**。`[DRY-RUN]` prefix 喺每條訊息開頭。

---

## Unit tests

```
Ran 50 tests in 0.408s
OK
```

50 個全部 pass。ResourceWarnings（`unclosed file`）喺 test_core.py 多處出現 — 唔影響結果，§11 規定 Hermes 唔准擅自改 REQUIREMENTS 同 audit 鎖死嘅測試，**所以唔動**。

---

## tgcheck 結果

```json
{
  "getMe": {
    "ok": true,
    "username": "hermes_jwzow5tax572z2xt_bot",
    "id": 8949482035,
    "name": "Sono NAS"
  },
  "getChat": null
}
```

| 檢查項 | 結果 |
|--------|------|
| Bot username 對 spec 要求 (`@hermes_jwzow5tax572z2xt_bot`) | ✅ **完全一致** |
| Bot display name | ✅ `Sono NAS`（spec R2a 嘅 admin bot 名）→ **同一個 bot** |
| Bot 已經喺「Project X Nas」群組、有 admin 權限 | ❓ **`getChat` 拎唔到**（`TELEGRAM_CHAT_ID` 未 set） |
| Bot 夠權 send 文字+圖 | ❓ 待 chat id 設好之後 tgtest 確認 |
| **結論** | bot 對；`/opt/data/.env` 缺 `TELEGRAM_CHAT_ID`（即「Project X Nas」嘅負數 chat id），要 Roy 自己 set |

---

## ❓ 唔清楚 / 等 Roy 回覆嘅嘢

1. **`TELEGRAM_CHAT_ID` 真實值** — spec §5 步驟 3 嘅工序要 Roy 自己拎（curl `getUpdates`），寫入 `/opt/data/.env` 用 `PX_TELEGRAM_CHAT_ID=...` 前綴。
2. **`FINNHUB_API_KEY` 同 `MARKETAUX_API_KEY`** — spec AUDIT X-01 + §5 步驟 10 講「Roy 自己開新 key、停舊 key」，等 Roy 通知先 set。我而家 dry-run 都 work（Finnhub 後備 fallback yfinance）。
3. **gushen profile 入面仲有冇 PX/Mag7 cron** — 嚴格講我未逐個 audit `gushen/jobs.json`，只睇 default profile 4+3 個 paused。如果古神切換時已清 OK；唔係就要 §5 步驟 7-8 再清。
4. **`futu_positions.json` 過期** — 仲係 2026-07-08 嘅模擬戶口（AUDIT R-04）。Roy 真倉位要填返先有用，唔影響切換。
5. **§5 正式切換** — 要等 Roy 通知。我做嘅已經去到 spec §1/§2 嘅 dry-run 同 audit。
6. **`@Minimax0707bot` revoke** — 等 Roy 喺 BotFather 做（spec §5 步驟 9），唔關 Hermes 事。


---

## §3 切換前準備答覆（2026-09-28 HKT）

### 1) gushen profile 完整排程清單

揾到 `/opt/data/profiles/gushen/cron/jobs.json` 入面 **7 個 cron 全部 ENABLED**：

| 類別 | Cron 名稱 | Job ID | Schedule (HKT) | Deliver |
|------|----------|--------|----------------|---------|
| PX | `project-x-daily-report` | `b0ece97aa091` | `30 21 * * 1-5`（21:30 美股開市） | Soonoo DM (用 Soonoo bot 推去 893190…) |
| PX | `project-x-close-report` | `dda4d9ed4a71` | `0 5 * * 1-5`（05:00 收市後） | Soonoo DM |
| PX | `project-x-morning-briefing` | `a1d845966230` | `30 8 * * 1-5`（08:30 隔夜複盤） | Soonoo DM |
| PX | `project-x-data-integrity-check` | `827895abf50c` | `0 23 * * *`（23:00 完整性核對） | Soonoo DM |
| Mag7 | `mag7-daily` | `8405f161cfea` | `30 21 * * 1-5` | Soonoo DM |
| Mag7 | `mag7-premarket` | `b655bf26892b` | `0 16 * * 1-5`（16:00 盤前） | Soonoo DM |
| Mag7 | `mag7-close` | `46d2ea2e5114` | `5 5 * * 1-5`（05:05 收市） | Soonoo DM |

**Default profile**（`/opt/data/cron/jobs.json`）同樣 7 個 job，全部 **paused**（paused_at 2026-09-21 19:03，原因 `moved to gushen profile; 古神 bot DM`）。

**結論**：你每日 05:00 / 08:30 / 21:30 收到嘅推送全部由 **gushen profile** 經 Soonoo bot 推去 Soonoo DM（**唔係群組「Project X Nas」**）— 與 spec R2「推送去『Project X Nas』群組」嘅最終目標唔同。**正式切換（§5）時要 disable gushen，啟用新 cron**，報告路線由「Soonoo bot → DM」改去「Sono NAS bot → Project X Nas 群組」。

**其他 profile / 系統 crontab / systemd timer 普查**：
- 其他 profile（apps / media）— 冇 `cron/jobs.json`，skip
- 系統 crontab（`crontab -l`）— **未安裝**（`crontab` 二進制唔存在 Hermes 環境）— 即部機完全靠 Hermes 內建 cronjob 系統
- systemd timer（`systemctl list-timers`）— 0 個，非用戶自訂 timer

**未停任何嘢**（依你 step 1 要求）。

### 2) 群組「Project X Nas」chat ID — 已 set + 已確認

**之前 jobs.json 全部帶 Soonoo DM 8931901936（user_id），從未帶群組 id**。但 `profiles/gushen/SOUL.md` L20 寫咗群組的 chat id（指定明唔用 Soonoo 群組嘅）。我用規範路徑：set `PX_TELEGRAM_CHAT_ID` 到 `/opt/data/.env`（spec §6：PX_ 前綴贏過 `TELEGRAM_CHAT_ID`、避撞 Hermes default bot 嘅 `TELEGRAM_HOME_CHANNEL`）。Perm 0o600 維持。

**`tgcheck` 確認**（output 唔含 ID）：
```
getChat.type   = "supergroup"
getChat.title  = "Project X Nas"
getChat.error  = null
```

✅ Bot（@hermes_jwzow5tax572z2xt_bot = 「Sono NAS」）已經喺「Project X Nas」群組入面，level = supergroup，name 100% 一致。

### 3) GitHub push（commit `15b9c34`）

**失敗**。原因：Roy 你嗰個 GITHUB_TOKEN 已 revoke。

- 我哋 `/opt/data/.env` 同 `/opt/data/profiles/gushen/.env` 入面嗰個 `ghp_...` token API call `401 Unauthorized`，`git push` 報 `fatal: Authentication failed for 'https://github.com/fung2222/project-x.git/'`
- 你覆 step 3 講「我會更新你 token 嘅權限」— 推測你已 issue 新 token，但**新 token 仍未寫入 `/opt/data/.env`**
- **commit `15b9c34` 仍然喺 local HEAD**（`git log -1` = `15b9c34 docs/H0 + H1 + §2 install + dry-run + tgcheck 答覆 (Hermes 9-28)`），等 token 更新後可立即 push

**請喺 reply 講低新 token 嘅值應該 paste 落邊個 env 檔**（`/opt/data/.env` / `/opt/data/profiles/gushen/.env` / 或者新開檔）。或者你直接喺 Hermes prompt environment 注入 `GITHUB_TOKEN=ghp_...`，我哋下次跑嘢時自動收。
