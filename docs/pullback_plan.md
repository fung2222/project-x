# 回調位掃描計劃（Roy 學習用）

## 背景

Roy 係投資新手，主線係 VOO（標普 500 ETF）每月定投。佢想用細錢（每次 HK$1,000–1,500）學「回調買入」——即係唔追高，等強勢股唞氣（回調）先買。

Roy 明確拒絕「突破追高」（例如 Unity 三日升 21% 嗰種），因為佢唔想賭，想要低風險嘅入場位。

## 目標

每日自動掃描大型優質藍籌，搵出「強勢 + 回調 10–15%」嘅靚買位，有先通知 Roy，冇就靜靜地唔出聲。

## 整個流程

1. 每週一至五 HKT 22:00（美股開市前 30 分鐘），Hermes cron 觸發
2. cron 跑 `pullback_scan.sh`（wrapper，用 project-x 嘅 venv python）
3. venv python 跑 `pullback_scan.py`（掃描邏輯）
4. script 用 yfinance 攞 45 隻藍籌嘅 1 年歷史數據
5. 篩選符合三條標準嘅股
6. 有命中 → stdout 輸出 → cron 送到 Roy 嘅 Telegram DM
7. 冇命中 → 輸出到 stderr → cron 唔 send（watchdog 模式，靜靜地）

## 標準（靚位定義）

一隻股要同時符合三條：

1. **強勢**：3 個月回報 > 0%（仲係升緊，唔係一路跌嘅垃圾）
2. **回調**：離 52 週高位跌咗 8%–18%（唞氣，唔係接刀）
3. **支撐**：現價 / MA50 喺 0.95–1.05（喺 50 日平均線支撐位附近）

## Universe（45 隻藍籌）

- 科技（16）：AAPL, MSFT, NVDA, GOOGL, AMZN, META, AVGO, AMD, CRM, ORCL, NOW, ADBE, INTU, QCOM, NFLX, TSLA
- 消費（9）：COST, WMT, MCD, PEP, KO, NKE, SBUX, HD, PG
- 醫療（7）：LLY, UNH, JNJ, ABBV, MRK, PFE, AMGN
- 金融（6）：V, MA, JPM, GS, BAC, MS
- 工業（7）：GE, CAT, HON, RTX, BA, DE, LMT

## 檔案位置

- 掃描邏輯：`/opt/data/project-x/scripts/pullback_scan.py`
- Cron wrapper：`/opt/data/profiles/gushen/scripts/pullback_scan.sh`
- Cron job：job_id `26c47646dcaf`（schedule `0 22 * * 1-5`，timezone `Asia/Hong_Kong`，`no_agent` 模式）

## 設計考慮

- **no_agent watchdog**：唔經 LLM，直接跑 script，stdout 有嘢先 deliver，空就唔 send（慳 token + 唔騷擾 Roy）
- **HKT 22:00**：美股開市前 30 分鐘，Roy 見到靚位可以「今晚開市」準備
- **8–18% 回調**：太淺（<8%）係「高位」唔係「回調」，太深（>18%）係「接刀」唔係「回調」
- **只掃大型藍籌**：Roy 要低風險，所以排除小型動量股（嗰啲太波動）

## 現況

2026-11-09 建立，當日測試「今日冇靚回調位」（市場兩極：防禦股喺高位、科技股接刀，中間健康回調位暫缺）。
