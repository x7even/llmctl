import re

__all__ = [
    'is_leap', 'days_in_month', 'to_ordinal', 'from_ordinal', 'weekday',
    'add_days', 'add_months', 'iso_weeks_in_year', 'iso_week', 'from_iso_week',
    'parse', 'format_date', 'diff',
]

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_DAYS = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)

_EXT_CAL_RE = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_EXT_WEEK_RE = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_EXT_ORD_RE = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_BASIC_WEEK_RE = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')
_BASIC_CAL_RE = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_BASIC_ORD_RE = re.compile(r'^([0-9]{4})([0-9]{3})$')


def _is_int(x):
    return type(x) is int


def _check_date_vals(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, day must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")


def _check_date_tuple(t):
    if type(t) is not tuple or len(t) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    if not all(_is_int(x) for x in t):
        raise TypeError("date must be a tuple of 3 ints")
    _check_date_vals(t[0], t[1], t[2])


def is_leap(y):
    if not _is_int(y):
        raise TypeError("year must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("year and month must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if m == 2 and is_leap(y):
        return 29
    return _MONTH_DAYS[m]


def to_ordinal(y, m, d):
    _check_date_vals(y, m, d)
    y1 = y - 1
    days = 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
    days += _CUM_DAYS[m - 1]
    if m > 2 and is_leap(y):
        days += 1
    days += d
    return days


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be int")
    if n < 1 or n > 3652059:
        raise ValueError("ordinal out of range")
    n -= 1
    n400, n = divmod(n, 146097)
    n100, n = divmod(n, 36524)
    n4, n = divmod(n, 1461)
    n1, n = divmod(n, 365)
    year = 400 * n400 + 100 * n100 + 4 * n4 + n1 + 1
    if n100 == 4 or n1 == 4:
        year -= 1
        n += 365
    month, day = _doy_to_md(n, year)
    return (year, month, day)


def _doy_to_md(doy, year):
    if doy < 31:
        return 1, doy + 1
    doy -= 31
    feb = 29 if is_leap(year) else 28
    if doy < feb:
        return 2, doy + 1
    doy -= feb
    _ml = (31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    for i in range(10):
        if doy < _ml[i]:
            return i + 3, doy + 1
        doy -= _ml[i]
    return 12, doy + 1


def weekday(y, m, d):
    _check_date_vals(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date)
    if not _is_int(n):
        raise TypeError("n must be int")
    ord_val = to_ordinal(date[0], date[1], date[2]) + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(ord_val)


def add_months(date, n):
    _check_date_tuple(date)
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("target year out of range")
    dim = days_in_month(ty, tm)
    td = d if d <= dim else dim
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if jan1_wd == 2 and is_leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _check_date_vals(y, m, d)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    iso_wd = wd + 1
    thu_ord = ord_val + (3 - wd)
    iso_year = from_ordinal(thu_ord)[0]
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    iso_wk = (thu_ord - monday_w1) // 7 + 1
    return (iso_year, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year) or not _is_int(week) or not _is_int(weekday):
        raise TypeError("iso_year, week, weekday must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    if week < 1 or week > iso_weeks_in_year(iso_year):
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target_ord = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    m = _EXT_CAL_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _EXT_WEEK_RE.match(s)
    if m:
        return _parse_week(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _EXT_ORD_RE.match(s)
    if m:
        return _parse_ordinal(int(m.group(1)), int(m.group(2)))

    m = _BASIC_WEEK_RE.match(s)
    if m:
        return _parse_week(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _BASIC_CAL_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _BASIC_ORD_RE.match(s)
    if m:
        return _parse_ordinal(int(m.group(1)), int(m.group(2)))

    raise ValueError("invalid date string")


def _parse_week(y, w, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if w < 1 or w > iso_weeks_in_year(y):
        raise ValueError("week out of range")
    if d < 1 or d > 7:
        raise ValueError("weekday out of range")
    jan4_ord = to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target_ord = monday_w1 + (w - 1) * 7 + (d - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise ValueError("date out of range")
    return from_ordinal(target_ord)


def _parse_ordinal(y, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    max_doy = 366 if is_leap(y) else 365
    if d < 1 or d > max_doy:
        raise ValueError("day of year out of range")
    jan1_ord = to_ordinal(y, 1, 1)
    return from_ordinal(jan1_ord + d - 1)


def format_date(date, form):
    _check_date_tuple(date)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    y, m, d = date
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _check_date_tuple(a)
    _check_date_tuple(b)
    if a == b:
        return (0, 0, 0)
    if a < b:
        return _diff_forward(a, b)
    else:
        neg = _diff_forward(b, a)
        return (-neg[0], -neg[1], -neg[2])


def _diff_forward(a, b):
    ya, ma, da = a
    yb, mb, db = b
    K = (yb - ya) * 12 + (mb - ma)
    shifted = add_months(a, K)
    if shifted > b:
        K -= 1
        shifted = add_months(a, K)
    years, months = divmod(K, 12)
    days = to_ordinal(b[0], b[1], b[2]) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
