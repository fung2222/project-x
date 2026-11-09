#!/usr/bin/env python
"""掃描大型優質藍籌，搵「強勢回調（10-15%）」嘅靚買位。

邏輯（Roy 嘅「回調買入」學習）：
- 強勢：3 個月仲係升（ret_3m > 0）
- 回調：由 52 週高位跌咗 8%–18%（唞氣，唔係接刀）
- 支撐：而家喺 MA50 附近（ratio_ma50 0.95–1.05）

有命中就逐行 print 出嚟（供 cron 通知）；冇命中就 print 一句空。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yfinance as yf

UNIVERSE = [
    # 科技
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'AVGO', 'AMD', 'CRM',
    'ORCL', 'NOW', 'ADBE', 'INTU', 'QCOM', 'NFLX', 'TSLA',
    # 消費
    'COST', 'WMT', 'MCD', 'PEP', 'KO', 'NKE', 'SBUX', 'HD', 'PG',
    # 醫療
    'LLY', 'UNH', 'JNJ', 'ABBV', 'MRK', 'PFE', 'AMGN',
    # 金融
    'V', 'MA', 'JPM', 'GS', 'BAC', 'MS',
    # 工業 / 其他
    'GE', 'CAT', 'HON', 'RTX', 'BA', 'DE', 'LMT',
]

# 靚回調位標準
MIN_3M = 0.0          # 3 個月仲係升（強勢）
LO_DROP = -0.18       # 離高位最多跌 18%（唔好跌到接刀）
HI_DROP = -0.08       # 離高位最少跌 8%（唔好太淺）
MA50_RANGE = (0.95, 1.05)  # 價 / MA50 喺支撐位附近


def scan():
    hits = []
    for t in UNIVERSE:
        try:
            h = yf.Ticker(t).history(period='1y')
            if len(h) < 70:
                continue
            c = h['Close']
            last = float(c.iloc[-1])
            ret_3m = last / float(c.iloc[-63]) - 1
            high52 = float(c.max())
            drop = last / high52 - 1
            ma50 = float(c.rolling(50).mean().iloc[-1])
            ratio_ma50 = last / ma50
            if (ret_3m > MIN_3M and LO_DROP <= drop <= HI_DROP
                    and MA50_RANGE[0] <= ratio_ma50 <= MA50_RANGE[1]):
                hits.append((t, last, ret_3m * 100, drop * 100, ratio_ma50))
        except Exception:
            continue
    return hits


if __name__ == '__main__':
    hits = scan()
    if not hits:
        print('今日冇靚回調位', file=sys.stderr)
        sys.exit(0)
    print('今日靚回調位（強勢 + 回調 10-15%）：')
    for t, last, r3, drop, r50 in hits:
        print(f'• {t}  ${last:.2f} ｜ 3月 {r3:+.0f}% ｜ 離高 {drop:.0f}% ｜ 價/MA50 {r50:.2f}')
