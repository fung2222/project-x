"""One-off: copy the Grok Bot era text reports (Reports/*.txt) into the site archive data/reports/."""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from px import archive  # noqa: E402

MAP = {"DailyBrief": "daily", "OpenMonitor": "open", "WeeklySummary": "weekly"}
for f in sorted(glob.glob(archive.path("Reports", "*.txt"))):
    m = re.match(r"(\w+)_(\d{4}-\d{2}-\d{2})\.txt$", os.path.basename(f))
    if not m or m.group(1) not in MAP:
        continue
    txt = open(f, encoding="utf-8").read()
    first = re.sub(r"<[^>]+>", "", next((l.strip() for l in txt.splitlines() if l.strip()), ""))[:80]
    archive.save_report(MAP[m.group(1)], m.group(2), [archive.html.escape(txt)], summary=f"（Grok Bot 時期）{first}")
    print("imported", f)
