import json, re
from datetime import date
today = date.today().isoformat()
total_value = 0; total_pnl_pct = 0; vix = 0
try:
    with open('portfolio.json', 'r') as f: port = json.load(f)
    total_value = port.get('total_value_usd', 0)
    total_pnl_pct = port.get('total_pnl_pct', 0)
except: pass
try:
    with open('data/market_snapshot.json', 'r') as f: snap = json.load(f)
    vix = snap.get('vix', 0)
except: pass

md = f"""🌙 **Project X 收市報告** | {today}
💼 總值：US${total_value:.2f} ({total_pnl_pct:+.2f}%)
🌡️ VIX：{vix}
(完整 4 段報告已喺 Telegram push)
#ProjectX #收市報告
"""
with open(f'data/close_report_{today}.md', 'w', encoding='utf-8') as f: f.write(md)
md_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', md)
md_html = md_html.replace('\n', '<br>\n')
html = f"""<!DOCTYPE html><html lang='zh-HK'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>收市 {today}</title><link rel='stylesheet' href='../css/style.css'><style>body{{font-family:-apple-system,sans-serif;line-height:1.7;background:#fafbfc;padding:16px}}.back-link{{display:inline-block;margin-bottom:16px;padding:8px 16px;background:#000;color:#fff;border-radius:8px;text-decoration:none;font-weight:600}}.md-content{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px;white-space:pre-wrap;font-size:14px}}.md-content strong{{color:#0f766e}}</style></head><body><a href='../reports.html' class='back-link'>← 返回報告列表</a><div class='md-content'>{md_html}</div></body></html>"""
with open(f'data/close_report_{today}.html', 'w', encoding='utf-8') as f: f.write(html)

idx_path = 'data/reports_index.json'
try:
    with open(idx_path, 'r') as f: idx = json.load(f)
except: idx = {'reports': []}
idx.setdefault('reports', [])
idx['reports'] = [r for r in idx['reports'] if r.get('date') != today]
idx['reports'].append({'date': today, 'file': f'close_report_{today}.html', 'summary': f'收市報告 · 總值 ${total_value:.2f} ({total_pnl_pct:+.2f}%) · VIX {vix}', 'pnl': total_pnl_pct})
with open(idx_path, 'w') as f: json.dump(idx, f, ensure_ascii=False, indent=2)
print(f'close_report_{today}.html + index updated')
