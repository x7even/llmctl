import re

_RE_EXT_CAL = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_BASIC_CAL = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_EXT_ORD = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_BASIC_ORD = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_EXT_WK = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_BASIC_WK = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')

_MD = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_int(x):
    return type(x) is int


def _check_date_tuple(date):
    if not isinstance(date, tuple) or len(date) != 3:
        raise TypeError("date must be a tuple of exactly 3 ints")
    for v in date:
        if type(v) is not int:
            raise TypeError("date elements must be int")


def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    dim = _MD[m - 1]
    if m == 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        dim = 29
    if not (1 <= d <= dim):
        raise ValueError("day out of range")


def is_leap(y):
    if type(y) is not int:
        raise TypeError("y must be int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if type(y) is not int:
        raise TypeError("y must be int")
    if type(m) is not int:
        raise TypeError("m must be int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    return _MD[m - 1]


def _leaps(n):
    return n // 4 - n // 100 + n // 400


def _days_before_year(y):
    return (y - 1) * 365 + _leaps(y - 1)


def to_ordinal(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be int")
    _check_date_range(y, m, d)
    result = _days_before_year(y)
    for i in range(m - 1):
        result += _MD[i]
    if m > 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        result += 1
    result += d
    return result


def from_ordinal(n):
    if type(n) is not int:
        raise TypeError("n must be int")
    if not (1 <= n <= 3652059):
        raise ValueError("ordinal out of range 1..3652059")
    np = n - 1
    y = 1 + (np * 400) // 146097
    while _days_before_year(y) > np:
        y -= 1
    while _days_before_year(y + 1) <= np:
        y += 1
    doy = np - _days_before_year(y) + 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    m = 1
    for i in range(12):
        md = _MD[i] + (1 if i == 1 and leap else 0)
        if doy <= md:
            m = i + 1
            d = doy
            break
        doy -= md
    return (y, m, d)


def weekday(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be int")
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    _check_date_range(y, m, d)
    o = to_ordinal(y, m, d) + n
    if o < 1 or o > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(o)


def add_months(date, n):
    _check_date_tuple(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of range")
    td = min(d, days_in_month(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if wd == 3:
        return 53
    if iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0) and wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be int")
    _check_date_range(y, m, d)
    iso_wd = (to_ordinal(y, m, d) - 1) % 7 + 1
    mon_w1 = to_ordinal(y, 1, 4) - (to_ordinal(y, 1, 4) - 1) % 7
    o = to_ordinal(y, m, d)
    week = (o - mon_w1) // 7 + 1
    if week < 1:
        iso_y = y - 1
        week += iso_weeks_in_year(iso_y)
    elif week > iso_weeks_in_year(y):
        iso_y = y + 1
        week = 1
    else:
        iso_y = y
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday_val):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be int")
    if type(week) is not int:
        raise TypeError("week must be int")
    if type(weekday_val) is not int:
        raise TypeError("weekday must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_wk):
        raise ValueError("week out of range")
    if not (1 <= weekday_val <= 7):
        raise ValueError("weekday out of range 1..7")
    mon_w1 = to_ordinal(iso_year, 1, 4) - (to_ordinal(iso_year, 1, 4) - 1) % 7
    target = mon_w1 + (week - 1) * 7 + (weekday_val - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    m = _RE_EXT_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid year")
        if not (1 <= mo <= 12):
            raise ValueError("invalid month")
        if not (1 <= d <= days_in_month(y, mo)):
            raise ValueError("invalid day")
        return (y, mo, d)

    m = _RE_EXT_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("invalid year")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("invalid day of year")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_EXT_WK.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid year")
        if not (1 <= wd <= 7):
            raise ValueError("invalid weekday")
        if not (1 <= wk <= iso_weeks_in_year(y)):
            raise ValueError("invalid week")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    m = _RE_BASIC_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid year")
        if not (1 <= mo <= 12):
            raise ValueError("invalid month")
        if not (1 <= d <= days_in_month(y, mo)):
            raise ValueError("invalid day")
        return (y, mo, d)

    m = _RE_BASIC_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("invalid year")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("invalid day of year")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_BASIC_WK.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid year")
        if not (1 <= wd <= 7):
            raise ValueError("invalid weekday")
        if not (1 <= wk <= iso_weeks_in_year(y)):
            raise ValueError("invalid week")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    raise ValueError("unrecognized date format")


def format_date(date, form):
    _check_date_tuple(date)
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str:
        raise ValueError("form must be a string")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iso_y, iso_w, iso_d = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_d}"
    else:
        raise ValueError("unknown form")


def diff(a, b):
    _check_date_tuple(a)
    _check_date_tuple(b)
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    ord_a = to_ordinal(ay, am, ad)
    ord_b = to_ordinal(by, bm, bd)

    if ord_a <= ord_b:
        lo, hi = 0, (by - ay) * 12 + 12
        while lo < hi:
            mid = (lo + hi + 1) // 2
            total = (am - 1) + mid
            ty = ay + total // 12
            tm = total % 12 + 1
            if ty > 9999:
                hi = mid - 1
            else:
                td = min(ad, days_in_month(ty, tm))
                if (ty, tm, td) <= (by, bm, bd):
                    lo = mid
                else:
                    hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        total = (am - 1) + K
        ty = ay + total // 12
        tm = total % 12 + 1
        td = min(ad, days_in_month(ty, tm))
        days = ord_b - to_ordinal(ty, tm, td)
        return (years, months, days)
    else:
        years, months, days = diff(b, a)
        return (-years, -months, -days)