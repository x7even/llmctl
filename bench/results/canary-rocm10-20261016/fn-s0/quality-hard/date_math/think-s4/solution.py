import re

_RE_CAL_EXT = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_CAL_BASIC = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_ORD_EXT = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_ORD_BASIC = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_WEEK_EXT = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_WEEK_BASIC = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTH_CUM = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORDINAL = 3652059


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be of type int")


def _check_date(date, name='date'):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple")
    if len(date) != 3:
        raise TypeError(f"{name} must have exactly 3 elements")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be of type int")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range")
    dim = _MONTH_DAYS[m]
    if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        dim = 29
    if d < 1 or d > dim:
        raise ValueError(f"day {d} out of range for {y}-{m}")


def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range")
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    return _MONTH_DAYS[m]


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    y1 = y - 1
    days = 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
    days += _MONTH_CUM[m]
    if m > 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        days += 1
    days += d
    return days


def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError(f"ordinal {n} out of range")
    n -= 1
    y400 = n // 146097
    n %= 146097
    y100 = n // 36524
    if y100 == 4:
        y100 = 3
    n -= y100 * 36524
    y4 = n // 1461
    n %= 1461
    y1 = n // 365
    if y1 == 4:
        y1 = 3
    n -= y1 * 365
    y = y400 * 400 + y100 * 100 + y4 * 4 + y1 + 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    if n < 31:
        m = 1
        d = n + 1
    elif n < (60 if leap else 59):
        m = 2
        d = n - 31 + 1
    else:
        n_march = n - (60 if leap else 59)
        m_march = (n_march * 5 + 2) // 153
        m = (m_march + 2) % 12 + 1
        d = n_march - (153 * m_march + 2) // 5 + 1
    return (y, m, d)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    new_ord = to_ordinal(y, m, d) + n
    if new_ord < 1 or new_ord > _MAX_ORDINAL:
        raise OverflowError("result date out of range")
    return from_ordinal(new_ord)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    target_y = total // 12 + 1
    target_m = total % 12 + 1
    if target_y < 1 or target_y > 9999:
        raise OverflowError("target year out of range")
    target_d = d
    if target_m == 2:
        dim = 29 if (target_y % 4 == 0 and (target_y % 100 != 0 or target_y % 400 == 0)) else 28
    else:
        dim = _MONTH_DAYS[target_m]
    if target_d > dim:
        target_d = dim
    return (target_y, target_m, target_d)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if jan1_wd == 2 and (iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0)):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    thursday_ord = ord_val + (3 - wd)
    if thursday_ord < to_ordinal(y, 1, 1):
        iso_year = y - 1
    elif thursday_ord > to_ordinal(y, 12, 31):
        iso_year = y + 1
    else:
        iso_year = y
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    iso_wk = (thursday_ord - week1_monday) // 7 + 1
    iso_wd = wd + 1
    return (iso_year, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range")
    max_week = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError(f"week {week} out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target_ord = week1_monday + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise OverflowError("result date out of range")
    return from_ordinal(target_ord)


def _parse_week(iso_y, wk, wd):
    if iso_y < 1 or iso_y > 9999:
        raise ValueError("ISO year out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    if wk < 1 or wk > 53:
        raise ValueError("week out of range")
    max_wk = iso_weeks_in_year(iso_y)
    if wk > max_wk:
        raise ValueError("week out of range")
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target_ord = week1_monday + (wk - 1) * 7 + (wd - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise ValueError("date out of range")
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a string")
    match = _RE_CAL_EXT.fullmatch(s)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        _check_date_range(y, m, d)
        return (y, m, d)
    match = _RE_CAL_BASIC.fullmatch(s)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        _check_date_range(y, m, d)
        return (y, m, d)
    match = _RE_ORD_EXT.fullmatch(s)
    if match:
        y, doy = int(match.group(1)), int(match.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        ord_val = to_ordinal(y, 1, 1) + doy - 1
        return from_ordinal(ord_val)
    match = _RE_ORD_BASIC.fullmatch(s)
    if match:
        y, doy = int(match.group(1)), int(match.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        ord_val = to_ordinal(y, 1, 1) + doy - 1
        return from_ordinal(ord_val)
    match = _RE_WEEK_EXT.fullmatch(s)
    if match:
        iso_y, wk, wd = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return _parse_week(iso_y, wk, wd)
    match = _RE_WEEK_BASIC.fullmatch(s)
    if match:
        iso_y, wk, wd = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return _parse_week(iso_y, wk, wd)
    raise ValueError("invalid date format")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iso_y, iso_w, iso_d = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_d}"
    else:
        raise ValueError("invalid form")


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)
    a_ord = to_ordinal(ay, am, ad)
    b_ord = to_ordinal(by, bm, bd)
    if a_ord == b_ord:
        return (0, 0, 0)
    if a_ord > b_ord:
        years, months, days = diff(b, a)
        return (-years, -months, -days)
    lo, hi = 0, 120000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            shifted = add_months(a, mid)
            if to_ordinal(shifted) <= b_ord:
                lo = mid
            else:
                hi = mid - 1
        except OverflowError:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = b_ord - to_ordinal(shifted)
    return (years, months, days)
