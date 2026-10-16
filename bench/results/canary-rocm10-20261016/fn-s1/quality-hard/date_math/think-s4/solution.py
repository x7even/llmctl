import re

__all__ = [
    'is_leap', 'days_in_month', 'to_ordinal', 'from_ordinal', 'weekday',
    'add_days', 'add_months', 'iso_weeks_in_year', 'iso_week', 'from_iso_week',
    'parse', 'format_date', 'diff',
]

# --------------- internal helpers (no validation) ---------------

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_DAYS = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MONTH_DAYS[m]


def _to_ordinal(y, m, d):
    y1 = y - 1
    return (365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
            + _CUM_DAYS[m] + (1 if m > 2 and _is_leap(y) else 0) + d)


def _from_ordinal(n):
    n -= 1
    n400, n = divmod(n, 146097)
    n100, n = divmod(n, 36524)
    if n100 == 4:
        n100 = 3
        n += 36524
    n4, n = divmod(n, 1461)
    if n4 == 25:
        n4 = 24
        n += 1461
    n1, n = divmod(n, 365)
    if n1 == 4:
        n1 = 3
        n += 365
    year = n400 * 400 + n100 * 100 + n4 * 4 + n1 + 1
    leap = _is_leap(year)
    for m in range(1, 13):
        dim = 29 if (m == 2 and leap) else _MONTH_DAYS[m]
        if n < dim:
            return (year, m, n + 1)
        n -= dim
    return (year, 12, 31)


def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = min(d, _days_in_month(ty, tm))
    return (ty, tm, td)


def _iso_weeks_in_year(iso_year):
    jan1_wd = (_to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if jan1_wd == 2 and _is_leap(iso_year):
        return 53
    return 52


# --------------- validation helpers ---------------

def _check_int(*args):
    for x in args:
        if type(x) is not int:
            raise TypeError("arguments must be of type int")


def _check_date_arg(date, name="date"):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple")
    if len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError(f"{name} elements must be ints")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError("day out of range")


# --------------- public API ---------------

def is_leap(y):
    _check_int(y)
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, m)
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    _check_int(y, m, d)
    _check_date_range(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    _check_int(n)
    if n < 1 or n > 3652059:
        raise ValueError("ordinal out of range")
    return _from_ordinal(n)


def weekday(y, m, d):
    _check_int(y, m, d)
    _check_date_range(y, m, d)
    return (_to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_arg(date)
    _check_int(n)
    y, m, d = date
    _check_date_range(y, m, d)
    new_ord = _to_ordinal(y, m, d) + n
    if new_ord < 1 or new_ord > 3652059:
        raise OverflowError("result date out of range")
    return _from_ordinal(new_ord)


def add_months(date, n):
    _check_date_arg(date)
    _check_int(n)
    y, m, d = date
    _check_date_range(y, m, d)
    ty, tm, td = _add_months_raw(y, m, d, n)
    if ty < 1 or ty > 9999:
        raise OverflowError("result year out of range")
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    _check_int(y, m, d)
    _check_date_range(y, m, d)
    ord_ = _to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7
    thu_ord = ord_ - wd + 3
    iso_y = _from_ordinal(thu_ord)[0]
    jan1_ord = _to_ordinal(iso_y, 1, 1)
    wk = (thu_ord - jan1_ord) // 7 + 1
    return (iso_y, wk, wd + 1)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, week, weekday)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    max_week = _iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_wk1_ord = jan4_ord - jan4_wd
    target_ord = mon_wk1_ord + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError("result date out of range")
    return _from_ordinal(target_ord)


# --------------- parse / format ---------------

_PAT_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_PAT_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_PAT_WK_EXT  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_PAT_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_PAT_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_PAT_WK_BAS  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    m = _PAT_CAL_EXT.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _PAT_ORD_EXT.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if doy < 1 or doy > (366 if _is_leap(y) else 365):
            raise ValueError("day of year out of range")
        return _from_ordinal(_to_ordinal(y, 1, 1) + doy - 1)

    m = _PAT_WK_EXT.fullmatch(s)
    if m:
        iy, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if iy < 1 or iy > 9999:
            raise ValueError("iso_year out of range")
        if wk < 1 or wk > _iso_weeks_in_year(iy):
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        jan4_ord = _to_ordinal(iy, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        target = jan4_ord - jan4_wd + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > 3652059:
            raise ValueError("date out of range")
        return _from_ordinal(target)

    m = _PAT_CAL_BAS.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _PAT_ORD_BAS.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if doy < 1 or doy > (366 if _is_leap(y) else 365):
            raise ValueError("day of year out of range")
        return _from_ordinal(_to_ordinal(y, 1, 1) + doy - 1)

    m = _PAT_WK_BAS.fullmatch(s)
    if m:
        iy, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if iy < 1 or iy > 9999:
            raise ValueError("iso_year out of range")
        if wk < 1 or wk > _iso_weeks_in_year(iy):
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        jan4_ord = _to_ordinal(iy, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        target = jan4_ord - jan4_wd + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > 3652059:
            raise ValueError("date out of range")
        return _from_ordinal(target)

    raise ValueError("invalid date string")


def format_date(date, form):
    _check_date_arg(date)
    y, m, d = date
    _check_date_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid format")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    # week
    iy, wk, wd = iso_week(y, m, d)
    return f"{iy:04d}-W{wk:02d}-{wd}"


def diff(a, b):
    _check_date_arg(a, "a")
    _check_date_arg(b, "b")
    ya, ma, da = a
    yb, mb, db = b
    _check_date_range(ya, ma, da)
    _check_date_range(yb, mb, db)

    if a == b:
        return (0, 0, 0)

    if a > b:
        r = diff(b, a)
        return (-r[0], -r[1], -r[2])

    # a < b: find largest K >= 0 with _add_months_raw(a, K) <= b
    b_ord = _to_ordinal(yb, mb, db)
    lo = 0
    hi = (yb - ya) * 12 + (mb - ma) + 12

    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _add_months_raw(ya, ma, da, mid)
        if _to_ordinal(shifted[0], shifted[1], shifted[2]) <= b_ord:
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_raw(ya, ma, da, K)
    days = b_ord - _to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
