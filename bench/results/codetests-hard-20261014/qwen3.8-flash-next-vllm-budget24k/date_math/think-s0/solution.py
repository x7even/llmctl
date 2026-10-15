"""Proleptic-Gregorian calendar arithmetic for years 1 through 9999.

No imports of datetime, calendar, time, dateutil, or email.utils.
All arithmetic is plain integer math.
"""

import re as _re

# Cumulative days before month m (0-indexed month: index 0 = before Jan, etc.)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

_MIN_ORD = 1
_MAX_ORD = 3652059


# --------------- internal helpers (no type/range checks) ---------------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _DAYS_IN_MONTH[m - 1]


def _to_ordinal(y, m, d):
    y1 = y - 1
    o = 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
    if _is_leap(y) and m > 2:
        o += _CUM_LEAP[m - 1]
    else:
        o += _CUM[m - 1]
    return o + d


def _year_from_ordinal(n):
    """Return the year whose Jan-1 ordinal is <= n < next year's Jan-1 ordinal."""
    y = (n - 1) * 400 // 146097 + 1
    if _to_ordinal(y, 1, 1) > n:
        y -= 1
    elif _to_ordinal(y + 1, 1, 1) <= n:
        y += 1
    return y


def _from_ordinal_raw(n):
    """Convert ordinal to (y, m, d). Assumes 1 <= n <= 3652059."""
    y = _year_from_ordinal(n)
    jan1 = _to_ordinal(y, 1, 1)
    doy = n - jan1 + 1  # 1-based day of year
    cum = _CUM_LEAP if _is_leap(y) else _CUM
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if cum[mid - 1] < doy:
            lo = mid
        else:
            hi = mid - 1
    m = lo
    d = doy - cum[m - 1]
    return (y, m, d)


def _add_months_raw(y, m, d, n):
    """Shift by n months, clamp day once. No range check on result year."""
    tm = (m - 1) + n
    ny = y + tm // 12
    nm = tm % 12 + 1
    max_d = _days_in_month(ny, nm)
    nd = d if d <= max_d else max_d
    return (ny, nm, nd)


# --------------- type / range checking helpers ---------------

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _check_date(d, name):
    if type(d) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(d) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, x in enumerate(d):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(x).__name__}")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


# --------------- public API ---------------

def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if n < _MIN_ORD or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ordinal_raw(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (_to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    new_ord = _to_ordinal(y, m, d) + n
    if new_ord < _MIN_ORD or new_ord > _MAX_ORD:
        raise OverflowError("result date out of supported range")
    return _from_ordinal_raw(new_ord)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    tm = (m - 1) + n
    ny = y + tm // 12
    if ny < 1 or ny > 9999:
        raise OverflowError("target year out of range 1..9999")
    nm = tm % 12 + 1
    max_d = _days_in_month(ny, nm)
    nd = d if d <= max_d else max_d
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = (_to_ordinal(iso_year, 1, 1) - 1) % 7  # Monday=0
    if jan1_wd == 3:
        return 53
    if jan1_wd == 2 and _is_leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    o = _to_ordinal(y, m, d)
    wd = (o - 1) % 7  # Monday=0 .. Sunday=6
    thursday_ord = o - wd + 3
    iso_yr = _year_from_ordinal(thursday_ord)
    jan4_ord = _to_ordinal(iso_yr, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    week_num = (thursday_ord - week1_monday) // 7 + 1
    iso_wd = wd + 1  # Monday=1 .. Sunday=7
    return (iso_yr, week_num, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target_ord = week1_monday + (week - 1) * 7 + (weekday - 1)
    if target_ord < _MIN_ORD or target_ord > _MAX_ORD:
        raise OverflowError("result date out of supported range")
    return _from_ordinal_raw(target_ord)


# --------------- parse / format ---------------

_DIGIT_RE = _re.compile(r'^[0-9]+$')


def _parse_digits(s, start, length):
    """Return int of s[start:start+length] if all ASCII digits, else None."""
    for i in range(start, start + length):
        c = s[i]
        if c < '0' or c > '9':
            return None
    return int(s[start:start + length])


def _parse_calendar_ext(s):
    """YYYY-MM-DD (10 chars)"""
    y = _parse_digits(s, 0, 4)
    m = _parse_digits(s, 5, 2)
    d = _parse_digits(s, 8, 2)
    if y is None or m is None or d is None:
        raise ValueError("invalid date string")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError("day out of range")
    return (y, m, d)


def _parse_calendar_basic(s):
    """YYYYMMDD (8 chars)"""
    y = _parse_digits(s, 0, 4)
    m = _parse_digits(s, 4, 2)
    d = _parse_digits(s, 6, 2)
    if y is None or m is None or d is None:
        raise ValueError("invalid date string")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError("day out of range")
    return (y, m, d)


def _parse_ordinal_ext(s):
    """YYYY-DDD (8 chars)"""
    y = _parse_digits(s, 0, 4)
    doy = _parse_digits(s, 5, 3)
    if y is None or doy is None:
        raise ValueError("invalid date string")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    max_doy = 366 if _is_leap(y) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError("day of year out of range")
    return _from_ordinal_raw(_to_ordinal(y, 1, 1) + doy - 1)


def _parse_ordinal_basic(s):
    """YYYYDDD (7 chars)"""
    y = _parse_digits(s, 0, 4)
    doy = _parse_digits(s, 4, 3)
    if y is None or doy is None:
        raise ValueError("invalid date string")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    max_doy = 366 if _is_leap(y) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError("day of year out of range")
    return _from_ordinal_raw(_to_ordinal(y, 1, 1) + doy - 1)


def _parse_week_ext(s):
    """YYYY-Www-D (10 chars)"""
    y = _parse_digits(s, 0, 4)
    wk = _parse_digits(s, 6, 2)
    wd = _parse_digits(s, 9, 1)
    if y is None or wk is None or wd is None:
        raise ValueError("invalid date string")
    return _iso_week_to_date(y, wk, wd)


def _parse_week_basic(s):
    """YYYYWwwD (8 chars)"""
    y = _parse_digits(s, 0, 4)
    wk = _parse_digits(s, 5, 2)
    wd = _parse_digits(s, 7, 1)
    if y is None or wk is None or wd is None:
        raise ValueError("invalid date string")
    return _iso_week_to_date(y, wk, wd)


def _iso_week_to_date(iso_yr, wk, wd):
    if iso_yr < 1 or iso_yr > 9999:
        raise ValueError("iso year out of range")
    max_wk = iso_weeks_in_year(iso_yr)
    if wk < 1 or wk > max_wk:
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    jan4_ord = _to_ordinal(iso_yr, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target_ord = week1_monday + (wk - 1) * 7 + (wd - 1)
    if target_ord < _MIN_ORD or target_ord > _MAX_ORD:
        raise ValueError("resulting date out of range")
    return _from_ordinal_raw(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    n = len(s)
    if n == 10:
        if s[4] == '-' and s[5] == 'W' and s[8] == '-':
            return _parse_week_ext(s)
        elif s[4] == '-' and s[7] == '-':
            return _parse_calendar_ext(s)
        else:
            raise ValueError("invalid date string")
    elif n == 8:
        if s[4] == '-':
            return _parse_ordinal_ext(s)
        elif s[4] == 'W':
            return _parse_week_basic(s)
        else:
            return _parse_calendar_basic(s)
    elif n == 7:
        return _parse_ordinal_basic(s)
    else:
        raise ValueError("invalid date string")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iso_yr, wk, wd = iso_week(y, m, d)
        return f"{iso_yr:04d}-W{wk:02d}-{wd}"


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ya, ma, da = a
    yb, mb, db = b
    _check_date_range(ya, ma, da)
    _check_date_range(yb, mb, db)
    ord_a = _to_ordinal(ya, ma, da)
    ord_b = _to_ordinal(yb, mb, db)
    if ord_a <= ord_b:
        return _diff_leq(ya, ma, da, yb, mb, db, ord_b)
    else:
        y, m, d = _diff_leq(yb, mb, db, ya, ma, da, ord_a)
        return (-y, -m, -d)


def _diff_leq(ya, ma, da, yb, mb, db, ord_b):
    """Compute diff where a <= b (by ordinal). ord_b is ordinal of b."""
    K0 = (yb - ya) * 12 + (mb - ma)
    if K0 < 0:
        K0 = 0
    shifted = _add_months_raw(ya, ma, da, K0)
    if _to_ordinal(*shifted) <= ord_b:
        K = K0
    else:
        K = K0 - 1
    years, months = divmod(K, 12)
    shifted_K = _add_months_raw(ya, ma, da, K)
    days = ord_b - _to_ordinal(*shifted_K)
    return (years, months, days)
