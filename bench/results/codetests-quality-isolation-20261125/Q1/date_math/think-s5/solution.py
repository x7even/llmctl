import re


def _is_int(x):
    return type(x) is int


def _is_date(x):
    return (type(x) is tuple and len(x) == 3 and
            all(type(v) is int for v in x))


def _valid_date(y, m, d):
    if y < 1 or y > 9999:
        return False
    if m < 1 or m > 12:
        return False
    if m == 2:
        max_d = 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    elif m in (4, 6, 9, 11):
        max_d = 30
    else:
        max_d = 31
    return 1 <= d <= max_d


def _days_before_year(y):
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


def _days_in_year(y):
    return 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365


_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)


def is_leap(y):
    if not _is_int(y):
        raise TypeError("y must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("y and m must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def to_ordinal(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("y, m, d must be int")
    if not _valid_date(y, m, d):
        raise ValueError("invalid date")
    cum = _CUM_LEAP if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else _CUM_NONLEAP
    return _days_before_year(y) + cum[m - 1] + d


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be int")
    if n < 1 or n > 3652059:
        raise ValueError("ordinal out of range")
    t = n - 1
    y = 1 + t // 365
    while _days_before_year(y) > t:
        y -= 1
    while _days_before_year(y) + _days_in_year(y) <= t:
        y += 1
    day_of_year = t - _days_before_year(y)
    cum = _CUM_LEAP if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else _CUM_NONLEAP
    m = 1
    for i in range(1, 12):
        if day_of_year >= cum[i]:
            m = i + 1
        else:
            break
    d = day_of_year - cum[m - 1] + 1
    return (y, m, d)


def weekday(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("y, m, d must be int")
    if not _valid_date(y, m, d):
        raise ValueError("invalid date")
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    if not _valid_date(y, m, d):
        raise ValueError("invalid date")
    new_ord = to_ordinal(y, m, d) + n
    if new_ord < 1 or new_ord > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(new_ord)


def add_months(date, n):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    if not _valid_date(y, m, d):
        raise ValueError("invalid date")
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError("result out of range")
    new_d = d
    dim = days_in_month(new_y, new_m)
    if new_d > dim:
        new_d = dim
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("year out of range")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if jan1_wd == 2 and (iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0)):
        return 53
    return 52


def iso_week(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("y, m, d must be int")
    if not _valid_date(y, m, d):
        raise ValueError("invalid date")
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    thursday_ord = ord_val + (3 - wd)
    if thursday_ord < to_ordinal(y, 1, 1):
        iso_y = y - 1
    elif thursday_ord > to_ordinal(y, 12, 31):
        iso_y = y + 1
    else:
        iso_y = y
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    mon_ord = ord_val - wd
    week = (mon_ord - mon_w1) // 7 + 1
    iso_wd = wd + 1
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year) or not _is_int(week) or not _is_int(weekday):
        raise TypeError("iso_year, week, weekday must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    max_week = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target_ord = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target_ord)


_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BASIC = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BASIC = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BASIC = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def parse(s):
    if not type(s) is str:
        raise TypeError("s must be str")

    m = _RE_CAL_EXT.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not _valid_date(y, mo, d):
            raise ValueError("invalid date")
        return (y, mo, d)

    m = _RE_CAL_BASIC.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not _valid_date(y, mo, d):
            raise ValueError("invalid date")
        return (y, mo, d)

    m = _RE_ORD_EXT.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_ORD_BASIC.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_WK_EXT.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    m = _RE_WK_BASIC.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    raise ValueError("unrecognized date format")


def format_date(date, form):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    y, m, d = date
    if not _valid_date(y, m, d):
        raise ValueError("invalid date")
    if not type(form) is str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    if not _is_date(a) or not _is_date(b):
        raise TypeError("a and b must be tuples of 3 ints")
    if not _valid_date(a[0], a[1], a[2]) or not _valid_date(b[0], b[1], b[2]):
        raise ValueError("invalid date")

    if a == b:
        return (0, 0, 0)

    if a <= b:
        lo = 0
        hi = (b[0] - a[0]) * 12 + 24
        while lo < hi:
            mid = (lo + hi + 1) // 2
            try:
                shifted = add_months(a, mid)
            except OverflowError:
                hi = mid - 1
                continue
            if shifted <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = add_months(a, K)
        days = to_ordinal(b[0], b[1], b[2]) - to_ordinal(shifted[0], shifted[1], shifted[2])
        return (years, months, days)
    else:
        r = diff(b, a)
        return (-r[0], -r[1], -r[2])