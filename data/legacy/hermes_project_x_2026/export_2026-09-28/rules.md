# Project X 投資規則（規則手冊 · 2026-08 修訂）

## 投資標的（股票池）

| 角色 | 代碼 | 入場股數 | 入場日 | 入場價 (USD) | 備註 |
|------|------|---------|--------|------------|------|
| AI 龍頭 | NVDA | 0.5 | 2026-07-08 | 196.93 | 平均分第一注 |
| 情緒+基本面 | TSLA | 0.5 | 2026-07-08 | 402.90 | 學情緒對股價影響 |
| 高波動教學 | RKLB | 1.0 | 2026-07-08 | 83.41 | 學止損執行 |

**注意：3 隻標的均為「分注」入場（fractional shares），非整股。**

## 指標清單（data_fetcher.py + analyzer.py 計算）

| 指標 | 說明 | 用途 |
|------|------|------|
| MA20 | 20 日均線 | 短線趨勢 |
| MA50 | 50 日均線 | 中線趨勢 |
| MA200 | 200 日均線 | 長線趨勢 |
| RSI(14) | 相對強弱指標 | 0-100，<30 超賣，>70 超買 |
| 5 日動能 | (close[-1] - close[-5])/close[-5] * 100 | 短期動能 |
| 量能比 | 今日量 / 20 日均量 | 量縮/量增 |
| VIX | 恐慌指數 | 市場風險 |

### 趨勢 Score 公式 (analyzer.py)

```python
score = 0
# 價 vs MA50
if close > ma50 * 1.02: score += 2
elif close > ma50: score += 1
elif close < ma50 * 0.98: score -= 2
else: score -= 1

# 價 vs MA20
if close > ma20: score += 1
else: score -= 1

# MA20 vs MA50 (黃金/死亡交叉)
if ma20 > ma50: score += 1
else: score -= 1

# RSI
if rsi < 30: score += 1   # 超賣，可能反彈
elif rsi > 70: score -= 1  # 超買

# 5 日動能
if momentum > 5: score += 2
elif momentum > 0: score += 1
elif momentum < -5: score -= 2
else: score -= 1

# 量能
if vol_ratio > 1.5: score += 1
elif vol_ratio < 0.5: score -= 1
```

### Score → 趨勢標籤

| Score | 標籤 | Action |
|-------|------|--------|
| ≥ 6 | 上升 | 持有 / 加注 |
| 2-5 | 偏多 | 持有 |
| -1 to 1 | 中性 | 觀望 |
| -5 to -2 | 偏空 | 減注 / 警戒 |
| ≤ -6 | 下降 | 止損檢查 |

## 入市條件

| 信號 | 條件 | 動作 |
|------|------|------|
| BUY | RSI<35 AND 股價 < MA50*0.97 | 加 0.5 注（如現金 > 20% 總資產） |
| HOLD | 趨勢=中性/偏多 | 維持 |
| CAUTION | RSI>65 | 唔加，可能減 0.25 注 |
| STOP | 觸及止損價 | 即平倉 |

## 風險管理

| 規則 | 參數 | 說明 |
|------|------|------|
| 單股倉位上限 | 30% | 任何單一標的不超過組合 30% |
| 止損 | -10% | 入場價 -10% |
| 止盈 | +20% | 入場價 +20% |
| 預警 | -7% | WARN 級別 |
| 危險 | -8.5% | DANGER 級別 |
| 止損觸發 | -10% | STOP，自動平倉 |
| 現金下限 | 30% | 任何時點保留 ≥30% 現金 |
| 最大單日交易 | 2 注 | 防止過度交易 |

### 風險分級 (risk_manager.py 輸出)

```python
if pnl_pct >= 20:    flag = "TP"
elif pnl_pct <= -10: flag = "STOP"   # 觸發平倉
elif pnl_pct <= -8.5: flag = "DANGER"
elif pnl_pct <= -7:   flag = "WARN"
else:                flag = "OK"
```

## 資金規模

| 參數 | 值 |
|------|------|
| 初始資金 | HKD 5,000 (≡ USD 641.03 @ FX 7.8) |
| 開倉日 | 2026-07-08 |
| 三倉注數 | 0.5 / 0.5 / 1.0 |
| 當前總資產 (USD) | ~$630（見 portfolio.json） |
| 當前現金 (USD) | $257.7 |
| 模擬注結構 | fractional shares |

## 階段分層 (PHASE)

| Phase | 目標 | 狀態 |
|-------|------|------|
| PHASE 1 | 觀察+模擬；趨勢報告服務入市準備 | ✅ 當前 |
| PHASE 2 | 15+ 筆模擬 + 書面論述 | ❌ 未到 |
| PHASE 3 | 小資金真錢 HKD 1–2k + 嚴格止損 | ❌ 未到 |

## 報告模板

### Daily (21:30 HKT 開市)

```
{HEADER}
📊 市場狀態:VIX {vix}
組合:{total_value_usd} ({pnl_pct}%)
────────────────────────────────
{STOCK_LIST}   # 每隻:價 變幅% 趨勢 action 止損距
────────────────────────────────
{ALERTS}      # DANGER/STOP/WARN 名字置頂
{RISK_RULES}  # 硬規則 1-3 行
```

### Close (05:00 HKT 收市)

```
🌙 {DATE} 收市
總 P&L : {total_pnl_pct}%
持倉結算 :
  {STOCK_LIST}  # 收市價 結算損益
趨勢狀態 : {ACTIONS}
最強/最弱 : {TOP_BOTTOM}  # 1 + 1
聽日動作 : {PLAN}
```

### Morning (08:30 HKT 隔夜複盤)

```
☀️ {DATE} 隔夜複盤
持倉快睇 :
  {HOLDINGS}    # 盤前氣氛
趨勢指引 : {TREND_ACTIONS}
風險清單 : {FLAGS}
```

## Mag7 觀察池（獨立 pipeline）

7 隻美股大科技觀察（**不污染 PX 模擬倉 P&L**）：

| 代碼 | 角色 |
|------|------|
| AAPL | Apple |
| MSFT | Microsoft |
| GOOGL | Alphabet |
| AMZN | Amazon |
| META | Meta |
| NVDA | Nvidia（同名但屬觀察池；PX 嗰隻算倉） |
| TSLA | Tesla（同名；PX 嗰隻算倉） |

觀察池 cron 獨立（3 個 job），唔影響 PX 模擬倉計分。
