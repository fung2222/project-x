"""Roy's REAL Futu positions — a manual record. The system NEVER places orders; it only records
what Roy tells Hermes, marks prices, and alerts (SL / TP / big drops) in the Telegram reports.

File: data/futu_positions.json (env PX_REAL_POS_PATH overrides it, e.g. for temp tests).
Schema "real_positions_v2":
  real_start_date   first real trade date (set by the first `pos add`; start of the real-vs-paper-vs-QQQ review)
  positions[]       open lots {id, ticker, shares, entry_price, entry_date, stop_loss_price, take_profit_price,
                    entry_fee_usd, cost_usd, note, recorded_at, last_price, last_price_at}
  closed_trades[]   realized history {id, position_id, ticker, shares, entry/exit price+date, days_held, fees,
                    gross/net P&L USD, net_pnl_pct, net_pnl_hkd, exit_reason STOP_LOSS|TAKE_PROFIT|MANUAL, ...}
  archived          pointer to the backup of the old (July 2026 Futu *paper-sim*) record

CLI (via run.py):
  python run.py pos add SYMBOL QTY PRICE --sl X --tp Y [--date YYYY-MM-DD] [--fee 2] [--note "..."]
  python run.py pos close SYMBOL PRICE [QTY] [--date YYYY-MM-DD] [--fee 2] [--note "..."]
  python run.py pos set SYMBOL [--sl X] [--tp Y]
  python run.py pos list
All write commands accept --dry-run (validate + print, no write) and --push (git pull first, then commit + push
ONLY the positions file; never force). Writes are atomic and file-locked."""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import tempfile
from contextlib import contextmanager

from . import clock
from .config import load_settings, path

SCHEMA = "real_positions_v2"
DEFAULT_PATH = path("data", "futu_positions.json")
ARCHIVE_NOTE = "data/legacy/futu_positions_2026-07-08_paper_sim.json"
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9]{0,5}([.\-][A-Z]{1,2})?$")


class RealPosError(ValueError):
    pass


def file_path():
    return os.environ.get("PX_REAL_POS_PATH") or DEFAULT_PATH


def cfg():
    c = {"start_capital_hkd": 10000, "start_capital_usd": 1280.0, "max_positions": 3, "max_position_pct": 0.25,
         "min_cash_pct": 0.2, "risk_per_trade_pct": 0.02, "default_fee_usd": 2.0, "near_sl_alert_pct": 2.0,
         "big_drop_alert_pct": 5.0}
    c.update({k: v for k, v in load_settings().get("real_account", {}).items() if not k.startswith("_")})
    return c


def empty_book():
    c = cfg()
    return {
        "schema": SCHEMA,
        "platform": "Futu / Moomoo",
        "account_type": "美股真錢戶口（Roy 手動落單）",
        "owner": "Roy Chan",
        "note": "Roy 喺富途親手落單後，由 Hermes 用 `python run.py pos ...` 記錄；系統只記錄同提醒，永遠唔會自動落單。",
        "start_capital_hkd": c["start_capital_hkd"],
        "start_capital_usd": c["start_capital_usd"],
        "real_start_date": None,
        "last_synced": None,
        "positions": [],
        "closed_trades": [],
        "archived": {"file": ARCHIVE_NOTE,
                     "note": "2026-07-08 富途模擬戶口舊記錄（NVDA ×1 @194，練習落單），已封存，唔計入真倉。"},
    }


# ---------------------------------------------------------------- file io
def load(p=None):
    """Load the real book. Missing file or the legacy (pre-v2) schema -> empty book (no real positions)."""
    p = p or file_path()
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return empty_book()
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        b = empty_book()
        b["legacy_unmigrated"] = True
        return b
    data.setdefault("positions", [])
    data.setdefault("closed_trades", [])
    return data


def save(book, p=None):
    p = p or file_path()
    d = os.path.dirname(os.path.abspath(p))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".realpos.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(book, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def locked(p=None):
    """Exclusive lock (sidecar .lock file) around a read-modify-write of the real book."""
    p = p or file_path()
    lp = os.path.join(os.path.dirname(os.path.abspath(p)), "." + os.path.basename(p) + ".lock")
    fh = open(lp, "a+")
    try:
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except ImportError:  # non-POSIX: best effort
            pass
        yield
    finally:
        fh.close()


# ---------------------------------------------------------------- validation
def _num(x, name, lo=None, hi=None, allow_zero=False):
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise RealPosError(f"{name} 唔係數字：{x!r}")
    if not math.isfinite(v):
        raise RealPosError(f"{name} 唔係有效數字：{x!r}")
    if v < 0 or (v == 0 and not allow_zero):
        raise RealPosError(f"{name} 要大過 0：{x!r}")
    if lo is not None and v < lo:
        raise RealPosError(f"{name} 太細：{v}")
    if hi is not None and v > hi:
        raise RealPosError(f"{name} 太大：{v}")
    return v


def norm_symbol(sym):
    s = str(sym or "").strip().upper()
    if not SYMBOL_RE.match(s):
        raise RealPosError(f"股票代號唔啱：{sym!r}（例：IONQ、BRK.B）")
    return s


def norm_qty(q):
    v = _num(q, "股數", hi=1_000_000)
    if abs(v - round(v)) < 1e-9:
        return int(round(v))
    if abs(v * 10000 - round(v * 10000)) > 1e-6:
        raise RealPosError(f"碎股最多 4 個小數位：{q!r}")
    return round(v, 4)


def norm_price(x, name="價錢"):
    return round(_num(x, name, hi=1_000_000), 4)


def norm_date(d, today=None):
    today = today or clock.now_hkt().date()
    if d in (None, ""):
        return today.isoformat()
    try:
        v = dt.date.fromisoformat(str(d))
    except ValueError:
        raise RealPosError(f"日期格式要 YYYY-MM-DD：{d!r}")
    if v > today:
        raise RealPosError(f"日期唔可以喺將來：{v}")
    if v.year < 2020:
        raise RealPosError(f"日期太舊：{v}")
    return v.isoformat()


def default_fee(price, qty, side="buy"):
    """Existing Futu HK fixed-plan model (px.ledger.fee): ~US$2.00 per small order."""
    try:
        from .ledger import fee
        return fee(price * qty, max(1, int(math.ceil(qty))), side)
    except Exception:
        return float(cfg()["default_fee_usd"])


def _fmt_qty(q):
    return str(int(q)) if float(q).is_integer() else f"{float(q):g}"


def _next_id(book, prefix):
    n = 0
    items = book.get("positions", []) + book.get("closed_trades", [])
    for it in items:
        for key in ("id", "position_id"):
            v = str(it.get(key) or "")
            if v.startswith(prefix) and v[len(prefix):].isdigit():
                n = max(n, int(v[len(prefix):]))
    return f"{prefix}{n + 1:03d}"


def find(book, symbol):
    return next((p for p in book.get("positions", []) if p["ticker"] == symbol), None)


def _r2(x):
    return round(float(x) + 0.0, 2)


# ---------------------------------------------------------------- operations (pure; operate on a book dict)
def add_position(book, symbol, qty, price, sl, tp, date=None, fee=None, note="", allow_add=False, now=None):
    """Record a real BUY. Returns (position, warnings). Raises RealPosError on invalid input."""
    now = now or clock.now_hkt()
    sym = norm_symbol(symbol)
    qty = norm_qty(qty)
    price = norm_price(price, "買入價")
    sl = norm_price(sl, "止蝕價")
    tp = norm_price(tp, "止賺價")
    if not sl < price:
        raise RealPosError(f"止蝕 {sl} 要低過買入價 {price}")
    if not tp > price:
        raise RealPosError(f"止賺 {tp} 要高過買入價 {price}")
    date = norm_date(date, now.date())
    fee_v = default_fee(price, qty, "buy") if fee is None else round(_num(fee, "手續費", hi=100, allow_zero=True), 2)
    c = cfg()
    warns = []
    ex = find(book, sym)
    if ex and not allow_add:
        raise RealPosError(f"已經有 {sym} 真倉（{_fmt_qty(ex['shares'])} 股 @ {ex['entry_price']}）。規則唔鼓勵加倉／攤平；"
                           f"如果真係加咗倉，用 --allow-add 合併記錄")
    ev_before = evaluate(book, {}, None, now.date())
    if ex:
        tot = float(ex["shares"]) + qty
        avg = (float(ex["entry_price"]) * float(ex["shares"]) + price * qty) / tot
        ex.update({"shares": norm_qty(round(tot, 4)), "entry_price": round(avg, 4),
                   "entry_fee_usd": _r2(float(ex.get("entry_fee_usd") or 0) + fee_v),
                   "cost_usd": _r2(avg * tot), "stop_loss_price": sl, "take_profit_price": tp,
                   "recorded_at": now.isoformat(timespec="seconds")})
        ex.setdefault("adds", []).append({"date": date, "shares": qty, "price": price, "fee_usd": fee_v})
        if avg > price:
            warns.append("⚠️ 加倉喺低過平均成本嘅價 = 攤平，違反紀律；請確認係咪刻意")
        pos = ex
    else:
        pos = {"id": _next_id(book, "R"), "ticker": sym, "shares": qty, "entry_price": price, "entry_date": date,
               "stop_loss_price": sl, "take_profit_price": tp, "entry_fee_usd": fee_v, "cost_usd": _r2(price * qty),
               "note": str(note or "")[:200], "recorded_at": now.isoformat(timespec="seconds"),
               "last_price": price, "last_price_at": now.isoformat(timespec="seconds")}
        book.setdefault("positions", []).append(pos)
    if not book.get("real_start_date") or date < book["real_start_date"]:
        book["real_start_date"] = date
    book["last_synced"] = now.isoformat(timespec="minutes")
    # rule checks (warnings only — this is a record of what Roy already did)
    eq = ev_before["equity_usd"]
    cost = price * qty
    if len(book["positions"]) > c["max_positions"]:
        warns.append(f"⚠️ 真倉 {len(book['positions'])} 隻 > 上限 {c['max_positions']} 隻")
    if float(pos["entry_price"]) * float(pos["shares"]) > c["max_position_pct"] * eq + 0.01:
        warns.append(f"⚠️ {sym} 佔本金 {float(pos['entry_price']) * float(pos['shares']) / eq * 100:.0f}% > 上限 {c['max_position_pct'] * 100:.0f}%")
    cash_after = ev_before["cash_usd"] - cost - fee_v
    if cash_after < c["min_cash_pct"] * eq - 0.01:
        warns.append(f"⚠️ 估算現金得返 US${cash_after:.0f}（{cash_after / eq * 100:.0f}%）< 下限 {c['min_cash_pct'] * 100:.0f}%")
    risk = (price - sl) * qty
    if risk > c["risk_per_trade_pct"] * eq + 0.01:
        warns.append(f"ℹ️ 呢注風險 US${risk:.0f}（{risk / eq * 100:.1f}% 本金）> {c['risk_per_trade_pct'] * 100:.0f}% 指引")
    return pos, warns


def close_position(book, symbol, price, qty=None, date=None, fee=None, note="", now=None):
    """Record a real SELL (full or partial). Returns (closed_trade, warnings)."""
    now = now or clock.now_hkt()
    sym = norm_symbol(symbol)
    price = norm_price(price, "賣出價")
    pos = find(book, sym)
    if not pos:
        raise RealPosError(f"冇 {sym} 真倉可以平（用 `pos list` 睇持倉）")
    held = float(pos["shares"])
    q = held if qty in (None, "") else norm_qty(qty)
    if q > held + 1e-9:
        raise RealPosError(f"賣出 {_fmt_qty(q)} 股 > 持有 {_fmt_qty(held)} 股")
    date = norm_date(date, now.date())
    if date < str(pos.get("entry_date", "")):
        raise RealPosError(f"賣出日期 {date} 早過買入日期 {pos.get('entry_date')}")
    exit_fee = default_fee(price, q, "sell") if fee is None else round(_num(fee, "手續費", hi=100, allow_zero=True), 2)
    entry = float(pos["entry_price"])
    frac = q / held
    entry_fee = _r2(float(pos.get("entry_fee_usd") or 0) * frac)
    gross = (price - entry) * q
    net = gross - entry_fee - exit_fee
    basis = entry * q + entry_fee
    try:
        days = (dt.date.fromisoformat(date) - dt.date.fromisoformat(pos["entry_date"])).days
    except Exception:
        days = None
    sl, tp = pos.get("stop_loss_price"), pos.get("take_profit_price")
    reason = "STOP_LOSS" if sl and price <= float(sl) else ("TAKE_PROFIT" if tp and price >= float(tp) else "MANUAL")
    fx = _fx_default()
    trade = {"id": _next_id(book, "RC"), "position_id": pos["id"], "ticker": sym, "shares": norm_qty(round(q, 4)),
             "entry_price": entry, "exit_price": price, "entry_date": pos.get("entry_date"), "exit_date": date,
             "days_held": days, "entry_fee_usd": entry_fee, "exit_fee_usd": exit_fee, "fees_usd": _r2(entry_fee + exit_fee),
             "gross_pnl_usd": _r2(gross), "net_pnl_usd": _r2(net), "net_pnl_pct": _r2(net / basis * 100) if basis else None,
             "net_pnl_hkd": _r2(net * fx), "fx_usdhkd": fx, "stop_loss_price": sl, "take_profit_price": tp,
             "exit_reason": reason, "note": str(note or "")[:200], "recorded_at": now.isoformat(timespec="seconds")}
    book.setdefault("closed_trades", []).append(trade)
    remain = round(held - q, 4)
    if remain <= 1e-9:
        book["positions"] = [p for p in book["positions"] if p is not pos]
    else:
        pos["shares"] = norm_qty(remain)
        pos["entry_fee_usd"] = _r2(float(pos.get("entry_fee_usd") or 0) - entry_fee)
        pos["cost_usd"] = _r2(entry * remain)
    book["last_synced"] = now.isoformat(timespec="minutes")
    warns = []
    if reason == "MANUAL" and sl and tp:
        warns.append(f"ℹ️ 賣出價 {price} 喺止蝕 {sl}／止賺 {tp} 之間（人手提早離場）")
    return trade, warns


def set_levels(book, symbol, sl=None, tp=None, now=None):
    now = now or clock.now_hkt()
    sym = norm_symbol(symbol)
    pos = find(book, sym)
    if not pos:
        raise RealPosError(f"冇 {sym} 真倉")
    if sl is None and tp is None:
        raise RealPosError("要俾 --sl 或者 --tp")
    new_sl = norm_price(sl, "止蝕價") if sl is not None else pos.get("stop_loss_price")
    new_tp = norm_price(tp, "止賺價") if tp is not None else pos.get("take_profit_price")
    if new_sl and new_tp and not float(new_sl) < float(new_tp):
        raise RealPosError(f"止蝕 {new_sl} 要低過止賺 {new_tp}")
    pos["stop_loss_price"], pos["take_profit_price"] = new_sl, new_tp
    pos.setdefault("level_changes", []).append({"at": now.isoformat(timespec="minutes"), "sl": new_sl, "tp": new_tp})
    book["last_synced"] = now.isoformat(timespec="minutes")
    return pos


def _fx_default():
    return float(load_settings()["account"].get("fx_fallback_usdhkd", 7.8))


# ---------------------------------------------------------------- valuation
def evaluate(book, quotes=None, fx=None, today=None):
    """Mark the real book. quotes: {ticker: marketdata.quote()}; falls back to last_price, then entry.
    Returns dict with rows + totals (equity is an estimate: start capital + realized + unrealized)."""
    c = cfg()
    quotes = quotes or {}
    fx = float(fx or _fx_default())
    today = today or clock.now_hkt().date()
    near = float(c["near_sl_alert_pct"])
    rows = []
    value = cost_open = unreal = 0.0
    for p in book.get("positions", []):
        t = p["ticker"]
        q = quotes.get(t) or {}
        live = bool(q.get("ok") and q.get("price"))
        px = float(q["price"]) if live else float(p.get("last_price") or p["entry_price"])
        sh = float(p["shares"])
        entry = float(p["entry_price"])
        efee = float(p.get("entry_fee_usd") or 0)
        pnl = (px - entry) * sh - efee
        basis = entry * sh + efee
        sl, tp = p.get("stop_loss_price"), p.get("take_profit_price")
        d_sl = (px - float(sl)) / px * 100 if sl else None
        d_tp = (float(tp) - px) / px * 100 if tp else None
        try:
            days = (today - dt.date.fromisoformat(p["entry_date"])).days
        except Exception:
            days = None
        if sl and px <= float(sl):
            status = "SL_HIT"
        elif tp and px >= float(tp):
            status = "TP_HIT"
        elif d_sl is not None and d_sl < near:
            status = "NEAR_SL"
        else:
            status = "OK"
        rows.append({"id": p.get("id"), "ticker": t, "shares": p["shares"], "entry": entry, "px": round(px, 4),
                     "live": live, "source": q.get("source"), "chg_vs_prev": q.get("change_pct") if live else None,
                     "sl": sl, "tp": tp, "entry_fee": efee, "pnl_usd": _r2(pnl), "pnl_hkd": _r2(pnl * fx),
                     "pnl_pct": _r2(pnl / basis * 100) if basis else None, "value_usd": _r2(px * sh),
                     "dist_sl_pct": _r2(d_sl) if d_sl is not None else None,
                     "dist_tp_pct": _r2(d_tp) if d_tp is not None else None, "days_held": days, "status": status,
                     "entry_date": p.get("entry_date")})
        value += px * sh
        cost_open += entry * sh + efee
        unreal += pnl
    closed = book.get("closed_trades", [])
    realized = sum(float(t.get("net_pnl_usd") or 0) for t in closed)
    start = float(book.get("start_capital_usd") or c["start_capital_usd"])
    cash = start + realized - cost_open
    equity = cash + value
    wins = [t for t in closed if float(t.get("net_pnl_usd") or 0) > 0]
    return {"rows": rows, "n_open": len(rows), "max_positions": int(c["max_positions"]), "fx": fx,
            "start_capital_usd": start, "real_start_date": book.get("real_start_date"),
            "value_usd": _r2(value), "unrealized_usd": _r2(unreal), "realized_usd": _r2(realized),
            "cash_usd": _r2(cash), "equity_usd": _r2(equity), "cash_pct": _r2(cash / equity * 100) if equity else None,
            "return_usd": _r2(equity - start), "return_pct": _r2((equity - start) / start * 100) if start else None,
            "n_closed": len(closed), "n_wins": len(wins), "n_losses": len(closed) - len(wins),
            "win_rate_pct": _r2(len(wins) / len(closed) * 100) if closed else None}


def quotes_for(book):
    from . import marketdata
    return {p["ticker"]: marketdata.quote(p["ticker"]) for p in book.get("positions", [])}


def suggest_shares(ev, entry, stop):
    """Whole-share size for Roy's real account: <= max_position_pct of equity, keep >= min_cash_pct cash,
    risk <= risk_per_trade_pct, slots left under max_positions. Returns (shares, budget_usd, reason)."""
    c = cfg()
    eq = ev["equity_usd"]
    if ev["n_open"] >= c["max_positions"]:
        return 0, 0.0, f"真倉已滿 {ev['n_open']}/{c['max_positions']} 隻"
    cap_pos = c["max_position_pct"] * eq
    cap_cash = ev["cash_usd"] - c["min_cash_pct"] * eq - float(c["default_fee_usd"])
    risk_ps = (entry - stop) if stop else 0
    cap_risk = c["risk_per_trade_pct"] * eq / risk_ps * entry if risk_ps > 0 else cap_pos
    budget = max(0.0, min(cap_pos, cap_cash, cap_risk))
    sh = int(budget // entry) if entry > 0 else 0
    why = "" if sh else ("現金唔夠（要留 ≥20%）" if cap_cash < entry else "每股太貴，超出單注上限")
    return sh, _r2(budget), why


def mark_prices(prices, now=None, p=None):
    """Persist last live prices for the website (locked read-modify-write; no-op without positions)."""
    now = now or clock.now_hkt()
    p = p or file_path()
    if not prices:
        return False
    with locked(p):
        book = load(p)
        if book.get("legacy_unmigrated") or not book.get("positions"):
            return False
        changed = False
        for pos in book["positions"]:
            v = prices.get(pos["ticker"])
            if v:
                pos["last_price"] = round(float(v), 4)
                pos["last_price_at"] = now.isoformat(timespec="minutes")
                changed = True
        if changed:
            save(book, p)
        return changed


# ---------------------------------------------------------------- plain confirmations (Roy 2026-09-28)
def _usd(x):
    return f"US${float(x):,.2f}"


def _hk(x, fx):
    return f"HK${float(x) * float(fx):,.0f}"


def _cash_line(book):
    ev = evaluate(book, {}, None)
    return f"剩低現金約 {_usd(ev['cash_usd'])}（{ev['cash_pct']:.0f}%）· 而家揸 {ev['n_open']}/{ev['max_positions']} 隻", ev["fx"]


def confirm_add(book, pos):
    cash, fx = _cash_line(book)
    sh, e = float(pos["shares"]), float(pos["entry_price"])
    cost = sh * e + float(pos.get("entry_fee_usd") or 0)
    sl, tp = float(pos["stop_loss_price"]), float(pos["take_profit_price"])
    risk, gain = (e - sl) * sh, (tp - e) * sh
    return (f"✅ 記低咗：買入 {pos['ticker']} {_fmt_qty(sh)} 股，每股 ${e:,.2f}（連手續費用咗 {_usd(cost)} ≈ {_hk(cost, fx)}，{pos['entry_date']}）\n"
            f"　止蝕 ${sl:,.2f}：跌到就賣，大約蝕 {_usd(risk)}（{_hk(risk, fx)}）\n"
            f"　止賺 ${tp:,.2f}：升到可以賣，大約賺 {_usd(gain)}（{_hk(gain, fx)}）\n"
            f"　{cash}。開市時系統每 5 分鐘幫你睇住，到價會提你；落單要你自己喺富途做。")


def confirm_close(book, tr):
    cash, fx = _cash_line(book)
    word = "賺" if tr["net_pnl_usd"] >= 0 else "蝕"
    return (f"✅ 記低咗：賣出 {tr['ticker']} {_fmt_qty(tr['shares'])} 股，每股 ${float(tr['exit_price']):,.2f}（買入價 ${float(tr['entry_price']):,.2f}）\n"
            f"　扣埋手續費淨{word} {_usd(abs(tr['net_pnl_usd']))}（HK${abs(tr['net_pnl_hkd']):,.0f}，{tr['net_pnl_pct']:+.1f}%）· 揸咗 {tr['days_held']} 日\n"
            f"　{cash}。")


def confirm_set(book, pos):
    return (f"✅ 改好咗 {pos['ticker']}：止蝕 ${float(pos['stop_loss_price']):,.2f}（跌到就賣）· "
            f"止賺 ${float(pos['take_profit_price']):,.2f}（升到可以賣）。之後會用新價錢提你。")


# ---------------------------------------------------------------- CLI
def _print_list(book, quotes=None):
    ev = evaluate(book, quotes or {}, None)
    from .messages import real_section
    from .archive import strip_html
    print(strip_html("\n".join(real_section(ev, stale_note=bool(quotes)))))
    if book.get("closed_trades"):
        print("\n已平倉（最近 10 筆）：")
        for t in book["closed_trades"][-10:]:
            print(f"  {t['id']} {t['ticker']} {_fmt_qty(t['shares'])}股 {t['entry_date']}→{t['exit_date']} "
                  f"${t['entry_price']}→${t['exit_price']} 淨 {t['net_pnl_usd']:+.2f} USD（{t.get('net_pnl_pct')}%）{t['exit_reason']}")
    print(f"\n檔案：{file_path()}")


def cli(argv=None):
    ap = argparse.ArgumentParser(prog="run.py pos", description="Record Roy's REAL Futu trades (never places orders)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_add = sub.add_parser("add", help="record a real buy")
    a_add.add_argument("symbol")
    a_add.add_argument("qty")
    a_add.add_argument("price")
    a_add.add_argument("--sl", required=True, help="stop-loss price (required)")
    a_add.add_argument("--tp", required=True, help="take-profit price (required)")
    a_add.add_argument("--date", help="trade date YYYY-MM-DD (default today HKT)")
    a_add.add_argument("--fee", help="fee USD (default Futu model ~2.00)")
    a_add.add_argument("--note", default="")
    a_add.add_argument("--allow-add", action="store_true", help="merge into an existing position (adding)")
    a_add.add_argument("--dry-run", action="store_true")
    a_add.add_argument("--push", action="store_true", help="git pull first, then commit + push ONLY the positions file")
    a_cl = sub.add_parser("close", help="record a real sell (full or partial)")
    a_cl.add_argument("symbol")
    a_cl.add_argument("price")
    a_cl.add_argument("qty", nargs="?", default=None)
    a_cl.add_argument("--date")
    a_cl.add_argument("--fee")
    a_cl.add_argument("--note", default="")
    a_cl.add_argument("--dry-run", action="store_true")
    a_cl.add_argument("--push", action="store_true", help="git pull first, then commit + push ONLY the positions file")
    a_set = sub.add_parser("set", help="change stop-loss / take-profit")
    a_set.add_argument("symbol")
    a_set.add_argument("--sl")
    a_set.add_argument("--tp")
    a_set.add_argument("--dry-run", action="store_true")
    a_set.add_argument("--push", action="store_true", help="git pull first, then commit + push ONLY the positions file")
    a_ls = sub.add_parser("list", help="show real positions + closed trades")
    a_ls.add_argument("--live", action="store_true", help="fetch live quotes (network)")
    a = ap.parse_args(argv)
    p = file_path()
    push = bool(getattr(a, "push", False)) and not getattr(a, "dry_run", False)
    if push and os.path.abspath(p) != os.path.abspath(DEFAULT_PATH):
        print("❌ --push 只可以用喺 repo 嘅 data/futu_positions.json（PX_REAL_POS_PATH 已設定）", file=sys.stderr)
        return 1
    if push:
        from . import gitops
        if not gitops.pull():
            print("⚠️ git pull 失敗；照用本地版本（之後 push 會再 rebase）")
    if a.cmd == "list":
        book = load(p)
        _print_list(book, quotes_for(book) if a.live else None)
        return 0
    try:
        with locked(p):
            book = load(p)
            if book.get("legacy_unmigrated"):
                raise RealPosError(f"{p} 仲係舊格式（7 月模擬記錄）；請先封存再用 pos 指令")
            if a.cmd == "add":
                pos, warns = add_position(book, a.symbol, a.qty, a.price, a.sl, a.tp, a.date, a.fee, a.note, a.allow_add)
                msg = confirm_add(book, pos)
            elif a.cmd == "close":
                tr, warns = close_position(book, a.symbol, a.price, a.qty, a.date, a.fee, a.note)
                msg = confirm_close(book, tr)
            else:
                pos = set_levels(book, a.symbol, a.sl, a.tp)
                warns = []
                msg = confirm_set(book, pos)
            if not a.dry_run:
                save(book, p)
    except RealPosError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    print(("（dry-run，冇寫入）" if a.dry_run else "") + msg)
    for w in warns:
        print(w)
    if not a.dry_run and push:
        from . import gitops
        summary = " ".join(str(x) for x in (argv or sys.argv[2:]) if x != "--push")
        ok = gitops.commit_paths_and_push([os.path.relpath(p, gitops.BASE_DIR)], f"real pos: {summary}"[:120])
        print("✅ 已 commit + push" if ok else "❌ git push 失敗：請睇 git status，再人手 push（唔好 force push）")
        return 0 if ok else 3
    if not a.dry_run:
        print(f"已寫入 {p}。記得 commit + push（或者下次加 --push；見 docs/HERMES_HANDOVER.md §12）。")
    return 0
