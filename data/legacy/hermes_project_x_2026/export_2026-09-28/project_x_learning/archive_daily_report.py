import json
from datetime import date
import subprocess
today=date.today().isoformat()
with open('portfolio.json') as f: p=json.load(f)
with open('daily_report.json') as f: r=json.load(f)
total=p.get('total_value_usd',0); pnl=p.get('total_pnl_pct',0); vix=r.get('vix',0)
out=subprocess.check_output(['python3','telegram_push.py','--kind','daily'], text=True)
open(f'data/daily_report_{today}.md','w').write(out)
html='<!DOCTYPE html><html lang=zh-HK><head><meta charset=UTF-8><meta name=viewport content="width=device-width,initial-scale=1"><title>開盤 '+today+'</title><style>body{font-family:-apple-system,sans-serif;padding:16px;line-height:1.6;background:#fafbfc}pre{white-space:pre-wrap;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px}a{display:inline-block;margin-bottom:12px;padding:8px 14px;background:#000;color:#fff;border-radius:8px;text-decoration:none}</style></head><body><a href=../reports.html>← 返回</a><pre>'+out.replace('<','&lt;')+'</pre></body></html>'
open(f'data/daily_report_{today}.html','w').write(html)
idx_path='data/reports_index.json'
try:
  idx=json.load(open(idx_path))
except Exception:
  idx={'reports':[]}
idx['reports']=[x for x in idx.get('reports',[]) if x.get('date')!=today]
idx['reports'].append({'date':today,'file':f'daily_report_{today}.html','summary':f'開盤趨勢 ·  ({pnl:+.2f}%) · VIX {vix}','pnl':pnl})
json.dump(idx, open(idx_path,'w'), ensure_ascii=False, indent=2)
print('archive ok', today)
