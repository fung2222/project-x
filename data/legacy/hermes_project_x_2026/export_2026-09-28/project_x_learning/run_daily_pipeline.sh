#!/bin/bash
# Project X daily report - atomic pipeline
# 必須順序執行，缺一不可

set -e  # 任何 step 失敗即停

cd /opt/data/project_x_learning
source .venv/bin/activate

echo "=== Step 1/4: analyzer.py (re-fetch + write daily_report.json) ==="
python3 analyzer.py
ls -la daily_report.json

echo "=== Step 2/4: risk_manager.py (update portfolio + alerts) ==="
python3 risk_manager.py
ls -la portfolio.json

echo "=== Step 3/4: Append to pnl_history.json ==="
python3 -c "
import json
from datetime import date
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
print(f'pnl_history: {len(hist)} entries')
"
ls -la data/pnl_history.json

echo "=== Step 4/4: Generate Telegram report from FRESH daily_report.json ==="
python3 telegram_push.py
