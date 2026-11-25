import re


def _days_in_month(y, m):
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30


def _days_before_year(y):
    return (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


def _days_before_month(y, m):
    t = 0
    for i in range(1, m):
        t += _days_in_month(y, i)
    return t


def _check_date_type(date):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a tuple of exactly 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError("date must be a tuple of exactly 3 ints")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError("day out of range for given month")


def is_leap(y):
    if type(y) is not int:
        raise TypeError("y must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if type(y) is not int:
        raise TypeError("y must be int")
    if type(m) is not int:
        raise TypeError("m must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be int")
    if type(m) is not int:
        raise TypeError("m must be int")
    if type(d) is not int:
        raise TypeError("d must be int")
    _check_date_range(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    if type(n) is not int:
        raise TypeError("n must be int")
    if n < 1 or n > 3652059:
        raise ValueError("ordinal out of range 1..3652059")
    y = 1 + (n - 1) * 4 // 1461
    while _days_before_year(y) > n - 1:
        y -= 1
    while _days_before_year(y + 1) <= n - 1:
        y += 1
    doy = n - _days_before_year(y)
    m = 1
    while doy > _days_in_month(y, m):
        doy -= _days_in_month(y, m)
        m += 1
    return (y, m, doy)


def weekday(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be int")
    if type(m) is not int:
        raise TypeError("m must be int")
    if type(d) is not int:
        raise TypeError("d must be int")
    _check_date_range(y, m, d)
    return (_days_before_year(y) + _days_before_month(y, m) + d - 1) % 7


def add_days(date, n):
    _check_date_type(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    _check_date_range(y, m, d)
    ordinal = _days_before_year(y) + _days_before_month(y, m) + d + n
    if ordinal < 1 or ordinal > 3652059:
        raise OverflowError("result out of supported range")
    return from_ordinal(ordinal)


def add_months(date, n):
    _check_date_type(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError("result out of supported range")
    new_d = min(d, _days_in_month(new_y, new_m))
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range 1..9999")
    wd = (_days_before_year(iso_year) + 1 - 1) % 7
    if wd == 3:
        return 53
    if (iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0)) and wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be int")
    if type(m) is not int:
        raise TypeError("m must be int")
    if type(d) is not int:
        raise TypeError("d must be int")
    _check_date_range(y, m, d)
    ord_d = _days_before_year(y) + _days_before_month(y, m) + d
    wd = (ord_d - 1) % 7
    ord_jan4 = _days_before_year(y) + 4
    wd_jan4 = (ord_jan4 - 1) % 7
    mon_w1 = ord_jan4 - wd_jan4
    iso_wk = (ord_d - mon_w1) // 7 + 1
    iso_wd = wd + 1
    if iso_wk < 1:
        iso_y = y - 1
        iso_wk = iso_weeks_in_year(iso_y) + iso_wk
    elif iso_wk > iso_weeks_in_year(y):
        iso_y = y + 1
        iso_wk = 1
    else:
        iso_y = y
    return (iso_y, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be int")
    if type(week) is not int:
        raise TypeError("week must be int")
    if type(weekday) is not int:
        raise TypeError("weekday must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range 1..9999")
    nw = iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range 1..7")
    ord_jan4 = _days_before_year(iso_year) + 4
    wd_jan4 = (ord_jan4 - 1) % 7
    mon_w1 = ord_jan4 - wd_jan4
    ord_target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if ord_target < 1 or ord_target > 3652059:
        raise OverflowError("result out of supported range")
    return from_ordinal(ord_target)


_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_WK_EXT = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9]{1})')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_BAS = re.compile(r'([0-9]{4})W([0-9]{2})([0-9]{1})')


def _parse_week_date(y, wk, wd):
    nw = iso_weeks_in_year(y)
    if wk < 1 or wk > nw:
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range 1..7")
    ord_jan4 = _days_before_year(y) + 4
    wd_jan4 = (ord_jan4 - 1) % 7
    mon_w1 = ord_jan4 - wd_jan4
    ord_target = mon_w1 + (wk - 1) * 7 + (wd - 1)
    if ord_target < 1 or ord_target > 3652059:
        raise ValueError("date out of range")
    return from_ordinal(ord_target)


def _parse_ordinal_date(y, doy):
    max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError("day of year out of range")
    return from_ordinal(_days_before_year(y) + doy)


def _parse_calendar_date(y, mo, d):
    if mo < 1 or mo > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _days_in_month(y, mo):
        raise ValueError("day out of range")
    return (y, mo, d)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    m = _RE_CAL_EXT.fullmatch(s)
    if m:
        y = int(m.group(1))
        if y < 1:
            raise ValueError("year 0000 not allowed")
        return _parse_calendar_date(y, int(m.group(2)), int(m.group(3)))

    m = _RE_ORD_EXT.fullmatch(s)
    if m:
        y = int(m.group(1))
        if y < 1:
            raise ValueError("year 0000 not allowed")
        return _parse_ordinal_date(y, int(m.group(2)))

    m = _RE_WK_EXT.fullmatch(s)
    if m:
        y = int(m.group(1))
        if y < 1:
            raise ValueError("year 0000 not allowed")
        return _parse_week_date(y, int(m.group(2)), int(m.group(3)))

    m = _RE_CAL_BAS.fullmatch(s)
    if m:
        y = int(m.group(1))
        if y < 1:
            raise ValueError("year 0000 not allowed")
        return _parse_calendar_date(y, int(m.group(2)), int(m.group(3)))

    m = _RE_ORD_BAS.fullmatch(s)
    if m:
        y = int(m.group(1))
        if y < 1:
            raise ValueError("year 0000 not allowed")
        return _parse_ordinal_date(y, int(m.group(2)))

    m = _RE_WK_BAS.fullmatch(s)
    if m:
        y = int(m.group(1))
        if y < 1:
            raise ValueError("year 0000 not allowed")
        return _parse_week_date(y, int(m.group(2)), int(m.group(3)))

    raise ValueError("unrecognized date format")


def format_date(date, form):
    _check_date_type(date)
    y, m, d = date
    _check_date_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_wk, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_wk:02d}-{iso_wd}"


def diff(a, b):
    _check_date_type(a)
    _check_date_type(b)
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if a > b:
        yr, mo, dy = diff(b, a)
        return (-yr, -mo, -dy)

    # a <= b: binary search for largest K >= 0 with add_months(a, K) <= b
    lo = 0
    hi = (by - ay) * 12 + (bm - am)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        total = (ay - 1) * 12 + (am - 1) + mid
        ny = total // 12 + 1
        nm = total % 12 + 1
        nd = min(ad, _days_in_month(ny, nm))
        if (ny, nm, nd) <= (by, bm, bd):
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    total = (ay - 1) * 12 + (am - 1) + K
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(ad, _days_in_month(ny, nm))
    shifted_ord = _days_before_year(ny) + _days_before_month(ny, nm) + nd
    b_ord = _days_before_year(by) + _days_before_month(by, bm) + bd
    days = b_ord - shifted_ord
    return (years, months, days)
