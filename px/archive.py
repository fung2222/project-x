"""Website data outputs under data/ (report archive, equity history, scan, futu mirror).

data/reports/<kind>_report_<date>.md|.html  — plain-text copy of every pushed report
data/reports_index.json                      — {"reports": [{date, kind, file, md, summary, pnl}]}
data/pnl_history.json                        — one row per US session (close job), paper book
data/scan.json                               — latest opportunity scan (Top 5 + near misses)
"""
import datetime as dt
import html
import json
import os
import re

from . import clock
from .config import path  # noqa: F401 (re-exported)

DATA = path("data")
REPORTS = os.path.join(DATA, "reports")
INDEX = os.path.join(DATA, "reports_index.json")
PNL = os.path.join(DATA, "pnl_history.json")
SCAN = os.path.join(DATA, "scan.json")

KIND_ZH = {"open": "開市監控", "daily": "每日分析", "close": "收市報告", "morning": "隔夜複盤", "weekly": "週報", "hourly": "盤中警報"}


def _load(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, p)


def strip_html(t):
    return html.unescape(re.sub(r"<[^>]+>", "", t or ""))


def save_report(kind, date_str, messages, summary="", pnl=None):
    """Archive a pushed report (list of Telegram HTML messages) as .md + .html and index it."""
    os.makedirs(REPORTS, exist_ok=True)
    text = "\n\n".join(strip_html(m) for m in messages)
    base = f"{kind}_report_{date_str}"
    with open(os.path.join(REPORTS, base + ".md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    page = ("<!DOCTYPE html><html lang='zh-HK'><head><meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
            f"<title>{KIND_ZH.get(kind, kind)} {date_str}</title><link rel='stylesheet' href='../../css/style.css'></head>"
            "<body><main><a class='back-link' href='../../reports.html'>← 返回報告列表</a>"
            f"<div class='card md-content' style='white-space:pre-wrap'>{html.escape(text)}</div></main></body></html>")
    with open(os.path.join(REPORTS, base + ".html"), "w", encoding="utf-8") as f:
        f.write(page)
    idx = _load(INDEX, {"reports": []})
    idx["reports"] = [r for r in idx.get("reports", []) if not (r.get("date") == date_str and r.get("kind") == kind)]
    idx["reports"].append({"date": date_str, "kind": kind, "kind_zh": KIND_ZH.get(kind, kind),
                           "file": f"reports/{base}.html", "md": f"reports/{base}.md",
                           "summary": summary, "pnl": pnl, "source": "px",
                           "generated_at": clock.now_hkt().isoformat(timespec="seconds")})
    idx["reports"].sort(key=lambda r: (r.get("date", ""), r.get("kind", "")))
    idx["updated"] = clock.now_hkt().isoformat(timespec="seconds")
    _save(INDEX, idx)
    return base


def append_pnl(session, acct, positions, spy_close=None, qqq_close=None, real=None):
    hist = _load(PNL, [])
    hist = [h for h in hist if h.get("date") != session]
    hist.append({"date": session, "equity_usd": acct["equity_usd"], "cash_usd": acct["cash_usd"],
                 "total_pnl_usd": acct["total_pnl_usd"], "total_return_pct": acct["total_return_pct"],
                 "realized_pnl_usd": acct["realized_pnl_usd"], "unrealized_pnl_usd": acct["unrealized_pnl_usd"],
                 "fx_usdhkd": acct.get("fx_usdhkd"), "equity_hkd": round(acct["equity_usd"] * (acct.get("fx_usdhkd") or 7.8), 2),
                 "spy_close": spy_close, "qqq_close": qqq_close,
                 "positions": [{"ticker": p["ticker"], "shares": p["shares"], "price": p.get("current_price"),
                                "pnl_pct": p.get("pnl_pct")} for p in positions]}
                | ({"real": real} if real else {}))
    hist.sort(key=lambda h: h["date"])
    _save(PNL, hist)
    return hist


def load_pnl():
    return _load(PNL, [])


def save_scan(result):
    slim = dict(result)
    slim["all"] = [{k: x.get(k) for k in ("ticker", "score", "pass", "fail", "close", "rsi", "rr", "setup", "theme",
                                           "earnings_date", "ex_qqq_20d_pp", "ex_qqq_60d_pp", "dollar_vol20_musd")}
                   for x in result.get("all", [])]
    _save(SCAN, slim)


def path_chart(name):
    d = os.path.join(DATA, "charts")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def load_scan():
    return _load(SCAN, {})
