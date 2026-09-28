#!/bin/bash
# Project X morning overnight review - atomic pipeline
# NOTE: 08:30 HKT = 美股已收市，係「隔夜複盤」唔係美股盤前
set -e

cd /opt/data/project_x_learning
source .venv/bin/activate

echo "=== Step 1/4: analyzer.py (trend data) ==="
python3 analyzer.py >/dev/null

echo "=== Step 2/4: risk_manager.py ==="
python3 risk_manager.py

echo "=== Step 3/4: market_snapshot.json ==="
python3 -c "
from data_fetcher import get_verified_quote, get_vix, get_fx_usdhkd
import json
from datetime import datetime

data = {
  'timestamp': datetime.now().isoformat(),
  'label': 'overnight_review',
  'vix': get_vix(),
  'fx': get_fx_usdhkd(),
  'quotes': {}
}
for t in ['SPY','NVDA','TSLA','RKLB']:
  q = get_verified_quote(t)
  if q: data['quotes'][t] = {
    'price': q['price'],
    'prev_close': q['prev_close'],
    'change_pct': q['change_pct']
  }

with open('data/market_snapshot.json','w',encoding='utf-8') as f:
  json.dump(data, f, ensure_ascii=False, indent=2)
print('Overnight snapshot saved')
"

echo "=== Step 4/4: Telegram morning review (hard data) ==="
python3 telegram_push.py --kind morning
