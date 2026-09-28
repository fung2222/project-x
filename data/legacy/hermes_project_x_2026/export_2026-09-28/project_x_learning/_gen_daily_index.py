
import json, re
from datetime import date
today = date.today().isoformat()
total_value = 0
total_pnl_pct = 0
vix = 0
try:
    with open("portfolio.json", "r") as f:
        port = json.load(f)
    total_value = port.get("total_value_usd", 0)
    total_pnl_pct = port.get("total_pnl_pct", 0)
except Exception:
    pass
try:
    with open("daily_report.json", "r") as f:
        rep = json.load(f)
    vix = rep.get("vix", 0)
except Exception:
    pass

md_lines = []
md_lines.append("Project X 每日開盤報告 | " + today)
md_lines.append("總值：US$%s (%+.2f%%)" % (f"{total_value:.2f}", total_pnl_pct))
md_lines.append("VIX：%s" % vix)
md_lines.append("(完整 6 段報告已喺 Telegram push)")
md_lines.append("#ProjectX #開盤報告")
md = "
".join(md_lines) + "
"
md_path = "data/daily_report_" + today + ".md"
with open(md_path, "w", encoding="utf-8") as f:
    f.write(md)
md_html = re.sub(r"\*\*(.+?)\*\*", r"<strong></strong>", md)
md_html = md_html.replace("
", "<br>
")
style_block = "body{font-family:-apple-system,sans-serif;line-height:1.7;background:#fafbfc;padding:16px}.back-link{display:inline-block;margin-bottom:16px;padding:8px 16px;background:#000;color:#fff;border-radius:8px;text-decoration:none;font-weight:600}.md-content{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px;white-space:pre-wrap;font-size:14px}.md-content strong{color:#0f766e}"
html = (
    "<!DOCTYPE html><html lang="zh-HK"><head><meta charset="UTF-8">"
    "<meta name="viewport" content="width=device-width, initial-scale=1.0">"
    "<title>開盤 " + today + "</title>"
    "<link rel="stylesheet" href="../css/style.css">"
    "<style>" + style_block + "</style></head><body>"
    "<a href="../reports.html" class="back-link">返回報告列表</a>"
    "<div class="md-content">" + md_html + "</div></body></html>"
)
html_path = "data/daily_report_" + today + ".html"
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

idx_path = "data/reports_index.json"
try:
    with open(idx_path, "r") as f:
        idx = json.load(f)
except Exception:
    idx = {"reports": []}
idx.setdefault("reports", [])
idx["reports"] = [r for r in idx["reports"] if r.get("date") != today]
summary = "開盤報告 · 總值 $%s (%+.2f%%) · VIX %s" % (f"{total_value:.2f}", total_pnl_pct, vix)
idx["reports"].append({"date": today, "file": "daily_report_" + today + ".html", "summary": summary, "pnl": total_pnl_pct})
with open(idx_path, "w") as f:
    json.dump(idx, f, ensure_ascii=False, indent=2)
print("Generated + index: " + str(len(idx["reports"])) + " reports")
