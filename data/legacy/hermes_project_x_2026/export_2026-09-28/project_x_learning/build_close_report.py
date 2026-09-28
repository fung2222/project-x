import json, re
from datetime import date

today = date.today().isoformat()
total_value = 0
total_pnl_pct = 0
vix = 0

try:
    with open('portfolio.json', 'r') as f:
        port = json.load(f)
    total_value = port.get('total_value_usd', 0)
    total_pnl_pct = port.get('total_pnl_pct', 0)
except Exception:
    pass

try:
    with open('data/market_snapshot.json', 'r') as f:
        snap = json.load(f)
    vix = snap.get('vix', 0)
except Exception:
    pass

md_lines = []
md_lines.append('Project X Close Report | ' + today)
md_lines.append('Total: US$' + format(total_value, '.2f') + ' (' + format(total_pnl_pct, '+.2f') + '%)')
md_lines.append('VIX: ' + str(vix))
md_lines.append('(Full 4-section report pushed to Telegram)')
md_lines.append('#ProjectX #CloseReport')
md = chr(10).join(md_lines)

with open('data/close_report_' + today + '.md', 'w', encoding='utf-8') as f:
    f.write(md)

md_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', md)
md_html = md_html.replace(chr(10), '<br>' + chr(10))

html_parts = []
html_parts.append("<!DOCTYPE html><html lang='zh-HK'><head><meta charset='UTF-8'>")
html_parts.append("<meta name='viewport' content='width=device-width, initial-scale=1.0'>")
html_parts.append("<title>Close " + today + "</title>")
html_parts.append("<link rel='stylesheet' href='../css/style.css'>")
html_parts.append("<style>body{font-family:-apple-system,sans-serif;line-height:1.7;background:#fafbfc;padding:16px}")
html_parts.append(".back-link{display:inline-block;margin-bottom:16px;padding:8px 16px;background:#000;color:#fff;border-radius:8px;text-decoration:none;font-weight:600}")
html_parts.append(".md-content{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px;white-space:pre-wrap;font-size:14px}")
html_parts.append(".md-content strong{color:#0f766e}</style></head><body>")
html_parts.append("<a href='../reports.html' class='back-link'>Back to Reports</a>")
html_parts.append("<div class='md-content'>" + md_html + "</div></body></html>")
html = ''.join(html_parts)

with open('data/close_report_' + today + '.html', 'w', encoding='utf-8') as f:
    f.write(html)

idx_path = 'data/reports_index.json'
try:
    with open(idx_path, 'r') as f:
        idx = json.load(f)
except Exception:
    idx = {'reports': []}
idx.setdefault('reports', [])
idx['reports'] = [r for r in idx['reports'] if r.get('date') != today]
idx['reports'].append({
    'date': today,
    'file': 'close_report_' + today + '.html',
    'summary': 'Close Report - Total $' + format(total_value, '.2f') + ' (' + format(total_pnl_pct, '+.2f') + '%) - VIX ' + str(vix),
    'pnl': total_pnl_pct,
})
with open(idx_path, 'w') as f:
    json.dump(idx, f, ensure_ascii=False, indent=2)
print('close_report_' + today + '.html + index updated')