import re

__all__ = [
    'is_leap', 'days_in_month', 'to_ordinal', 'from_ordinal', 'weekday',
    'add_days', 'add_months', 'iso_weeks_in_year', 'iso_week', 'from_iso_week',
    'parse', 'format_date', 'diff',
]

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MAX_ORD = 3652059


def _is_int(x):
    return type(x) is int


def _is_date(d):
    return type(d) is tuple and len(d) == 3 and all(type(x) is int for x in d)


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")


def is_leap(y):
    if not _is_int(y):
        raise TypeError("year must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("year and month must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if m == 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        return 29
    return _MONTH_DAYS[m]


def to_ordinal(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, day must be int")
    _check_date_range(y, m, d)
    if m <= 2:
        y_m = y - 1
        m_m = m + 9
    else:
        y_m = y
        m_m = m - 3
    return 365 * y_m + y_m // 4 - y_m // 100 + y_m // 400 + (153 * m_m + 2) // 5 + d - 306


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be int")
    if n < 1 or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    t = n + 305
    era = t // 146097
    day_of_era = t - era * 146097
    year_in_era = (day_of_era - day_of_era // 1460 + day_of_era // 36524) // 365
    if year_in_era > 399:
        year_in_era = 399
    year_start = 365 * year_in_era + year_in_era // 4 - year_in_era // 100
    doy = day_of_era - year_start
    m_m = (5 * doy + 2) // 153
    d = doy - (153 * m_m + 2) // 5 + 1
    y_m = era * 400 + year_in_era
    if m_m >= 10:
        y = y_m + 1
        m = m_m - 9
    else:
        y = y_m
        m = m_m + 3
    return (y, m, d)


def weekday(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, day must be int")
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > _MAX_ORD:
        raise OverflowError("result date out of range")
    return from_ordinal(ord_val)


def add_months(date, n):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError("result year out of range")
    new_d = d
    if m == 2 and new_m == 2:
        pass
    else:
        dim = _MONTH_DAYS[new_m]
        if new_m == 2 and new_y % 4 == 0 and (new_y % 100 != 0 or new_y % 400 == 0):
            dim = 29
        if new_d > dim:
            new_d = dim
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    jan1_ord = to_ordinal(iso_year, 1, 1)
    wd = (jan1_ord - 1) % 7
    if wd == 3 or (wd == 2 and iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0)):
        return 53
    return 52


def iso_week(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, day must be int")
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    thursday_ord = ord_val - wd + 3
    iso_y = from_ordinal(thursday_ord)[0]
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    iso_wk = (ord_val - monday_w1) // 7 + 1
    iso_wd = wd + 1
    return (iso_y, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year) or not _is_int(week) or not _is_int(weekday):
        raise TypeError("iso_year, week, weekday must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    if week < 1:
        raise ValueError("week out of range")
    max_wk = iso_weeks_in_year(iso_year)
    if week > max_wk:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target_ord = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORD:
        raise OverflowError("result date out of range")
    return from_ordinal(target_ord)


_EXT_CAL_RE = re.compile(r'\A([0-9]{4})-([0-9]{2})-([0-9]{2})\Z')
_EXT_WEEK_RE = re.compile(r'\A([0-9]{4})-W([0-9]{2})-([0-9])\Z')
_BASIC_WEEK_RE = re.compile(r'\A([0-9]{4})W([0-9]{2})([0-9])\Z')
_EXT_ORD_RE = re.compile(r'\A([0-9]{4})-([0-9]{3})\Z')
_BASIC_CAL_RE = re.compile(r'\A([0-9]{4})([0-9]{2})([0-9]{2})\Z')
_BASIC_ORD_RE = re.compile(r'\A([0-9]{4})([0-9]{3})\Z')


def _parse_week_date(iso_y, wk, wd):
    if iso_y < 1 or iso_y > 9999:
        raise ValueError("ISO year out of range")
    if wk < 1 or wk > iso_weeks_in_year(iso_y):
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target_ord = monday_w1 + (wk - 1) * 7 + (wd - 1)
    if target_ord < 1 or target_ord > _MAX_ORD:
        raise ValueError("date out of range")
    return from_ordinal(target_ord)


def _parse_ordinal_date(y, doy):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError("day of year out of range")
    ord_val = to_ordinal(y, 1, 1) + doy - 1
    return from_ordinal(ord_val)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    mt = _EXT_CAL_RE.fullmatch(s)
    if mt:
        y, m, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if m < 1 or m > 12:
            raise ValueError("month out of range")
        if d < 1 or d > days_in_month(y, m):
            raise ValueError("day out of range")
        return (y, m, d)

    mt = _EXT_WEEK_RE.fullmatch(s)
    if mt:
        return _parse_week_date(int(mt.group(1)), int(mt.group(2)), int(mt.group(3)))

    mt = _BASIC_WEEK_RE.fullmatch(s)
    if mt:
        return _parse_week_date(int(mt.group(1)), int(mt.group(2)), int(mt.group(3)))

    mt = _EXT_ORD_RE.fullmatch(s)
    if mt:
        return _parse_ordinal_date(int(mt.group(1)), int(mt.group(2)))

    mt = _BASIC_CAL_RE.fullmatch(s)
    if mt:
        y, m, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if m < 1 or m > 12:
            raise ValueError("month out of range")
        if d < 1 or d > days_in_month(y, m):
            raise ValueError("day out of range")
        return (y, m, d)

    mt = _BASIC_ORD_RE.fullmatch(s)
    if mt:
        return _parse_ordinal_date(int(mt.group(1)), int(mt.group(2)))

    raise ValueError("invalid date format")


def format_date(date, form):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    y, m, d = date
    _check_date_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid format")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_wk, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_wk:02d}-{iso_wd}"


def diff(a, b):
    if not _is_date(a):
        raise TypeError("a must be a tuple of 3 ints")
    if not _is_date(b):
        raise TypeError("b must be a tuple of 3 ints")
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if a < b:
        return _diff_ordered(a, b)
    elif a > b:
        ya, ma, da = _diff_ordered(b, a)
        return (-ya, -ma, -da)
    else:
        return (0, 0, 0)


def _diff_ordered(a, b):
    ay, am, ad = a
    by, bm, bd = b
    ta = (ay - 1) * 12 + (am - 1)
    tb = (by - 1) * 12 + (bm - 1)
    k_max = tb - ta

    if k_max <= 0:
        K = 0
    else:
        shifted = _add_months_raw(ay, am, ad, k_max)
        if shifted <= b:
            K = k_max
        else:
            K = k_max - 1

    years, months = divmod(K, 12)
    shifted_date = _add_months_raw(ay, am, ad, K)
    days = to_ordinal(b[0], b[1], b[2]) - to_ordinal(shifted_date[0], shifted_date[1], shifted_date[2])
    return (years, months, days)


def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    dim = _MONTH_DAYS[new_m]
    if new_m == 2 and new_y % 4 == 0 and (new_y % 100 != 0 or new_y % 400 == 0):
        dim = 29
    new_d = d if d <= dim else dim
    return (new_y, new_m, new_d)
