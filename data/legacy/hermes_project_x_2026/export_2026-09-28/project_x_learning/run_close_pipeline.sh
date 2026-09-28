#!/bin/bash
# Project X close report - atomic pipeline
set -e

cd /opt/data/project_x_learning
source .venv/bin/activate

echo "=== Step 1/4: analyzer.py ==="
python3 analyzer.py >/dev/null
ls -la daily_report.json

echo "=== Step 2/4: risk_manager.py ==="
python3 risk_manager.py

echo "=== Step 3/4: snapshot + pnl_history ==="
python3 -c "
import json
from datetime import date, datetime
from data_fetcher import get_verified_quote, get_vix, get_fx_usdhkd

data = {
    'timestamp': datetime.now().isoformat(),
    'vix': get_vix(),
    'fx': get_fx_usdhkd(),
    'quotes': {}
}
for t in ['NVDA','TSLA','RKLB','AMD','MSFT','SPY']:
    q = get_verified_quote(t)
    if q: data['quotes'][t] = q
with open('data/market_snapshot.json','w',encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

with open('portfolio.json','r',encoding='utf-8') as f: port = json.load(f)
hist_path = 'data/pnl_history.json'
try:
    with open(hist_path,'r',encoding='utf-8') as f: hist = json.load(f)
except: hist = []
today_str = date.today().isoformat()
hist = [h for h in hist if h.get('date') != today_str]
hist.append({
    'date': today_str,
    'total_value_usd': port.get('total_value_usd', 0),
    'total_pnl_pct': port.get('total_pnl_pct', 0),
    'total_pnl_usd': port.get('total_pnl_usd', 0),
    'cash_usd': port.get('cash_usd', 0),
    'positions': [{'ticker':p['ticker'],'pnl_pct':p.get('pnl_pct',0),'value_usd':p.get('value_usd',0)} for p in port.get('positions',[])]
})
with open(hist_path,'w',encoding='utf-8') as f: json.dump(hist, f, ensure_ascii=False, indent=2)
print(f'Snapshot + pnl_history ({len(hist)} entries) updated')
"

echo "=== Step 4/4: Telegram close report (hard data) ==="
python3 telegram_push.py --kind close
