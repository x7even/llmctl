"""
Proleptic-Gregorian calendar arithmetic for years 1-9999.
Pure integer arithmetic; no datetime/calendar/time/dateutil imports.
"""

_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MAX_ORD = 3652059

import re as _re

_EXT_CAL = _re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
_EXT_ORD = _re.compile(r'^[0-9]{4}-[0-9]{3}$')
_EXT_WK  = _re.compile(r'^[0-9]{4}-W[0-9]{2}-[0-9]$')
_BAS_CAL = _re.compile(r'^[0-9]{8}$')
_BAS_ORD = _re.compile(r'^[0-9]{7}$')
_BAS_WK  = _re.compile(r'^[0-9]{4}W[0-9]{2}[0-9]$')


def _check_int(name, val):
    if type(val) is not int:
        raise TypeError(f"{name} must be int, got {type(val).__name__}")


def _check_date(name, date):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(v).__name__}")


def _check_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")


def is_leap(y):
    _check_int("y", y)
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def days_in_month(y, m):
    _check_int("y", y)
    _check_int("m", m)
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if m == 2 and is_leap(y):
        return 29
    return _MONTH_DAYS[m - 1]


def to_ordinal(y, m, d):
    _check_int("y", y)
    _check_int("m", m)
    _check_int("d", d)
    _check_range(y, m, d)
    y1 = y - 1
    days = 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
    days += _CUM[m - 1]
    if m > 2 and is_leap(y):
        days += 1
    days += d
    return days


def from_ordinal(n):
    _check_int("n", n)
    if n < 1 or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    n0 = n - 1
    n400, n0 = divmod(n0, 146097)
    n100, n0 = divmod(n0, 36524)
    n4, n0 = divmod(n0, 1461)
    n1, n0 = divmod(n0, 365)
    y = n400 * 400 + n100 * 100 + n4 * 4 + n1 + 1
    if n100 == 4 or n1 == 4:
        y -= 1
        n0 = 365
    # n0 is 0-based day within year y
    if is_leap(y) and n0 >= 59:
        n0 += 1
    # binary search for month in _CUM (non-leap table, now n0 adjusted)
    lo, hi = 0, 11
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _CUM[mid] <= n0:
            lo = mid
        else:
            hi = mid - 1
    m = lo + 1
    d = n0 - _CUM[lo] + 1
    return (y, m, d)


def weekday(y, m, d):
    _check_int("y", y)
    _check_int("m", m)
    _check_int("d", d)
    _check_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date("date", date)
    _check_int("n", n)
    _check_range(date[0], date[1], date[2])
    ord_val = to_ordinal(date[0], date[1], date[2]) + n
    if ord_val < 1 or ord_val > _MAX_ORD:
        raise OverflowError("result date out of range")
    return from_ordinal(ord_val)


def add_months(date, n):
    _check_date("date", date)
    _check_int("n", n)
    _check_range(date[0], date[1], date[2])
    y, m, d = date
    total = (m - 1) + n
    ny = y + total // 12
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("result year out of range")
    nd = min(d, days_in_month(ny, nm))
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int("iso_year", iso_year)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7  # Mon=0..Sun=6
    if jan1_wd == 3:  # Thursday
        return 53
    if is_leap(iso_year) and jan1_wd == 2:  # Wednesday in leap year
        return 53
    return 52


def iso_week(y, m, d):
    _check_int("y", y)
    _check_int("m", m)
    _check_int("d", d)
    _check_range(y, m, d)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7  # Mon=0..Sun=6
    thu_ord = ord_val + (3 - wd)
    iso_yr = from_ordinal(thu_ord)[0]
    jan4_ord = to_ordinal(iso_yr, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    wk1_mon_ord = jan4_ord - jan4_wd
    iso_wk_num = (thu_ord - wk1_mon_ord) // 7 + 1
    iso_wd = wd + 1  # Mon=1..Sun=7
    return (iso_yr, iso_wk_num, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int("iso_year", iso_year)
    _check_int("week", week)
    _check_int("weekday", weekday)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    nw = iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7  # Mon=0..Sun=6
    wk1_mon_ord = jan4_ord - jan4_wd
    target_ord = wk1_mon_ord + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORD:
        raise OverflowError("result date out of range")
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    if _EXT_CAL.match(s):
        y = int(s[0:4]); m = int(s[5:7]); d = int(s[8:10])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if m < 1 or m > 12:
            raise ValueError("month out of range")
        if d < 1 or d > days_in_month(y, m):
            raise ValueError("day out of range")
        return (y, m, d)
    if _EXT_ORD.match(s):
        y = int(s[0:4]); ddd = int(s[5:8])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_d = 366 if is_leap(y) else 365
        if ddd < 1 or ddd > max_d:
            raise ValueError("ordinal day out of range")
        return from_ordinal(to_ordinal(y, 1, 1) + ddd - 1)
    if _EXT_WK.match(s):
        y = int(s[0:4]); wk = int(s[6:8]); wd = int(s[9])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if wk < 1 or wk > 53:
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        if wk > iso_weeks_in_year(y):
            raise ValueError("week out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")
    if _BAS_CAL.match(s):
        y = int(s[0:4]); m = int(s[4:6]); d = int(s[6:8])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if m < 1 or m > 12:
            raise ValueError("month out of range")
        if d < 1 or d > days_in_month(y, m):
            raise ValueError("day out of range")
        return (y, m, d)
    if _BAS_ORD.match(s):
        y = int(s[0:4]); ddd = int(s[4:7])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_d = 366 if is_leap(y) else 365
        if ddd < 1 or ddd > max_d:
            raise ValueError("ordinal day out of range")
        return from_ordinal(to_ordinal(y, 1, 1) + ddd - 1)
    if _BAS_WK.match(s):
        y = int(s[0:4]); wk = int(s[5:7]); wd = int(s[7])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if wk < 1 or wk > 53:
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        if wk > iso_weeks_in_year(y):
            raise ValueError("week out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")
    raise ValueError("invalid date string")


def format_date(date, form):
    _check_date("date", date)
    _check_range(date[0], date[1], date[2])
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    y, m, d = date
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _check_date("a", a)
    _check_date("b", b)
    _check_range(a[0], a[1], a[2])
    _check_range(b[0], b[1], b[2])
    ord_a = to_ordinal(a[0], a[1], a[2])
    ord_b = to_ordinal(b[0], b[1], b[2])
    if ord_a > ord_b:
        ny, nm, nd = diff(b, a)
        return (-ny, -nm, -nd)
    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    lo, hi = 0, 120000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        shift_date = add_months(a, mid)
        if to_ordinal(*shift_date) <= ord_b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shift_date = add_months(a, K)
    days = ord_b - to_ordinal(*shift_date)
    return (years, months, days)
