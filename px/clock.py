"""Time helpers: HKT/ET, NYSE trading calendar (holidays + early closes), job windows.

No third-party calendar dependency: NYSE full-day holidays and 13:00 ET early
closes are computed by rule (valid for the current NYSE holiday set, incl.
Juneteenth). DST is handled by zoneinfo (America/New_York).
"""
import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

HKT = ZoneInfo("Asia/Hong_Kong")
ET = ZoneInfo("America/New_York")
MARKET_OPEN = dt.time(9, 30)
MARKET_CLOSE = dt.time(16, 0)
EARLY_CLOSE = dt.time(13, 0)


def now_hkt():
    return dt.datetime.now(HKT)


def now_et():
    return dt.datetime.now(ET)


def to_et(t):
    return t.astimezone(ET)


def to_hkt(t):
    return t.astimezone(HKT)


def _easter(year):
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def _nth_weekday(year, month, weekday, n):
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(year, month, weekday):
    d = dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 else dt.date(year, 12, 31)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d, saturday_to_friday=True):
    if d.weekday() == 5:
        return d - dt.timedelta(days=1) if saturday_to_friday else None
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


@lru_cache(maxsize=16)
def nyse_holidays(year):
    h = {}
    ny = _observed(dt.date(year, 1, 1), saturday_to_friday=False)  # NYSE: no Fri obs. for Sat New Year
    if ny:
        h[ny] = "New Year's Day"
    h[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    h[_nth_weekday(year, 2, 0, 3)] = "Presidents' Day"
    h[_easter(year) - dt.timedelta(days=2)] = "Good Friday"
    h[_last_weekday(year, 5, 0)] = "Memorial Day"
    if year >= 2022:
        h[_observed(dt.date(year, 6, 19))] = "Juneteenth"
    h[_observed(dt.date(year, 7, 4))] = "Independence Day"
    h[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    h[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving Day"
    h[_observed(dt.date(year, 12, 25))] = "Christmas Day"
    return h


def holiday_name(d):
    return nyse_holidays(d.year).get(d)


def is_trading_day(d):
    return d.weekday() < 5 and d not in nyse_holidays(d.year)


def is_early_close(d):
    if not is_trading_day(d):
        return False
    thanksgiving = _nth_weekday(d.year, 11, 3, 4)
    if d == thanksgiving + dt.timedelta(days=1):
        return True
    if d.month == 12 and d.day == 24 and d.weekday() < 4:
        return True
    if d.month == 7 and d.day == 3 and d.weekday() < 4:
        return True
    return False


def close_time(d):
    return EARLY_CLOSE if is_early_close(d) else MARKET_CLOSE


def previous_trading_day(d):
    d = d - dt.timedelta(days=1)
    while not is_trading_day(d):
        d -= dt.timedelta(days=1)
    return d


def trading_days_between(a, b):
    """Number of trading days in (a, b] (a exclusive)."""
    if b <= a:
        return 0
    n, d = 0, a
    while d < b:
        d += dt.timedelta(days=1)
        if is_trading_day(d):
            n += 1
    return n


def session_date(now=None):
    """US trading session (ET calendar date) that `now` belongs to."""
    now = now or now_et()
    return to_et(now).date()


def market_is_open(now=None):
    now = to_et(now or now_et())
    d = now.date()
    if not is_trading_day(d):
        return False
    return MARKET_OPEN <= now.time() < close_time(d)


def session_closed(now=None):
    """True if today's regular session is finished (or today is not a trading day)."""
    now = to_et(now or now_et())
    d = now.date()
    return (not is_trading_day(d)) or now.time() >= close_time(d)


def _t(s):
    hh, mm = s.split(":")
    return dt.time(int(hh), int(mm))


def in_window(window, now=None):
    now = to_et(now or now_et())
    start, end = _t(window[0]), _t(window[1])
    # respect early close: shrink end to close+45min
    ct = close_time(now.date())
    if ct == EARLY_CLOSE and start < ct:  # intraday windows shrink on half days; post-close windows don't
        end = min(end, dt.time(13, 45))
    return start <= now.time() <= end


def et_to_hkt_str(et_hhmm, on_date):
    """Convert an ET HH:MM on a given ET date to HKT HH:MM (+1 if next day)."""
    t = dt.datetime.combine(on_date, _t(et_hhmm), tzinfo=ET).astimezone(HKT)
    plus = " (+1)" if t.date() > on_date else ""
    return t.strftime("%H:%M") + plus


def in_window_hkt(window, now=None):
    now = to_hkt(now or now_hkt())
    return _t(window[0]) <= now.time() <= _t(window[1])
