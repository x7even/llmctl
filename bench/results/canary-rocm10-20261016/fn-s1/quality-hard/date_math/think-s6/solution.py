import re

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_DAYS = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)

_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_BASIC_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_BASIC_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_EXT_WEEK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_BASIC_WEEK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def _is_int(x):
    return type(x) is int


def _validate_date_tuple(d):
    if type(d) is not tuple or len(d) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    if not (_is_int(d[0]) and _is_int(d[1]) and _is_int(d[2])):
        raise TypeError("date must be a tuple of 3 ints")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError("day out of range")


def _is_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def _days_in_month(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MONTH_DAYS[m]


def _to_ordinal(y, m, d):
    yy = y - 1
    days = 365 * yy + yy // 4 - yy // 100 + yy // 400
    days += _CUM_DAYS[m]
    if m > 2 and _is_leap(y):
        days += 1
    days += d
    return days


def _from_ordinal(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _to_ordinal(mid, 1, 1) <= n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    remaining = n - _to_ordinal(y, 1, 1)
    for m in range(1, 13):
        dim = _days_in_month(y, m)
        if remaining < dim:
            return (y, m, remaining + 1)
        remaining -= dim
    raise ValueError("invalid ordinal")


def _weekday(y, m, d):
    return (_to_ordinal(y, m, d) - 1) % 7


def _iso_weeks_in_year(y):
    wd = _weekday(y, 1, 1)
    if wd == 3 or (wd == 2 and _is_leap(y)):
        return 53
    return 52


def _shift(date, k):
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + k
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        return None
    td = min(d, _days_in_month(ty, tm))
    return (ty, tm, td)


# ─── Public API ────────────────────────────────────────────────────────────────


def is_leap(y):
    if not _is_int(y):
        raise TypeError("year must be an int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap(y)


def days_in_month(y, m):
    if not (_is_int(y) and _is_int(m)):
        raise TypeError("year and month must be ints")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    if not (_is_int(y) and _is_int(m) and _is_int(d)):
        raise TypeError("year, month, day must be ints")
    _check_date_range(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be an int")
    if n < 1 or n > 3652059:
        raise ValueError("ordinal out of range")
    return _from_ordinal(n)


def weekday(y, m, d):
    if not (_is_int(y) and _is_int(m) and _is_int(d)):
        raise TypeError("year, month, day must be ints")
    _check_date_range(y, m, d)
    return _weekday(y, m, d)


def add_days(date, n):
    _validate_date_tuple(date)
    if not _is_int(n):
        raise TypeError("n must be an int")
    _check_date_range(date[0], date[1], date[2])
    new_ord = _to_ordinal(date[0], date[1], date[2]) + n
    if new_ord < 1 or new_ord > 3652059:
        raise OverflowError("result out of range")
    return _from_ordinal(new_ord)


def add_months(date, n):
    _validate_date_tuple(date)
    if not _is_int(n):
        raise TypeError("n must be an int")
    _check_date_range(date[0], date[1], date[2])
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("target year out of range")
    td = min(d, _days_in_month(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be an int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    if not (_is_int(y) and _is_int(m) and _is_int(d)):
        raise TypeError("year, month, day must be ints")
    _check_date_range(y, m, d)
    ord_val = _to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    thursday_ord = ord_val - wd + 3
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _to_ordinal(mid, 1, 1) <= thursday_ord:
            lo = mid
        else:
            hi = mid - 1
    iso_yr = lo
    jan4_ord = _to_ordinal(iso_yr, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    week = (thursday_ord - monday_w1) // 7 + 1
    iso_wd = wd + 1
    return (iso_yr, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not (_is_int(iso_year) and _is_int(week) and _is_int(weekday)):
        raise TypeError("iso_year, week, weekday must be ints")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    max_wk = _iso_weeks_in_year(iso_year)
    if week < 1 or week > max_wk:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return _from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    m = _EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _EXT_WEEK.fullmatch(s)
    if m:
        return _parse_week(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _BASIC_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _EXT_ORD.fullmatch(s)
    if m:
        return _parse_ordinal(int(m.group(1)), int(m.group(2)))

    m = _BASIC_WEEK.fullmatch(s)
    if m:
        return _parse_week(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _BASIC_ORD.fullmatch(s)
    if m:
        return _parse_ordinal(int(m.group(1)), int(m.group(2)))

    raise ValueError("invalid date string")


def _parse_ordinal(y, doy):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    max_doy = 366 if _is_leap(y) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError("day of year out of range")
    remaining = doy - 1
    for m in range(1, 13):
        dim = _days_in_month(y, m)
        if remaining < dim:
            return (y, m, remaining + 1)
        remaining -= dim
    raise ValueError("invalid day of year")


def _parse_week(iso_year, week, wd):
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    max_wk = _iso_weeks_in_year(iso_year)
    if week < 1 or week > max_wk:
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target = monday_w1 + (week - 1) * 7 + (wd - 1)
    if target < 1 or target > 3652059:
        raise ValueError("date out of range")
    return _from_ordinal(target)


def format_date(date, form):
    _validate_date_tuple(date)
    _check_date_range(date[0], date[1], date[2])
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    y, m, d = date
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iso_yr, wk, wd = iso_week(y, m, d)
        return f"{iso_yr:04d}-W{wk:02d}-{wd}"


def diff(a, b):
    _validate_date_tuple(a)
    _validate_date_tuple(b)
    _check_date_range(a[0], a[1], a[2])
    _check_date_range(b[0], b[1], b[2])

    if a == b:
        return (0, 0, 0)

    if a < b:
        return _diff_forward(a, b)
    else:
        y, m, d = _diff_forward(b, a)
        return (-y, -m, -d)


def _diff_forward(a, b):
    b_ord = _to_ordinal(b[0], b[1], b[2])
    lo, hi = 0, 120000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _shift(a, mid)
        if shifted is not None and _to_ordinal(shifted[0], shifted[1], shifted[2]) <= b_ord:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    shifted = _shift(a, K)
    years, months = divmod(K, 12)
    days = b_ord - _to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
