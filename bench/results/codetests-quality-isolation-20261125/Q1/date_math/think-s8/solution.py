import re

_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
_MAX_ORDINAL = 3652059

_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BAS_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def _is_int(x):
    return type(x) is int


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _check_date_tuple(date):
    if not isinstance(date, tuple) or len(date) != 3:
        raise TypeError("date must be a tuple of exactly 3 ints")
    for v in date:
        if not _is_int(v):
            raise TypeError("date elements must be ints")
    y, m, d = date
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    dim = _days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError("day out of range 1..%d" % dim)


def _days_before_year(y):
    return (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


def _shift(date, k):
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + k
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = d if d <= _days_in_month(ty, tm) else _days_in_month(ty, tm)
    return (ty, tm, td)


def is_leap(y):
    if not _is_int(y):
        raise TypeError("y must be int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("y and m must be ints")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    if not (_is_int(y) and _is_int(m) and _is_int(d)):
        raise TypeError("y, m, d must be ints")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    dim = _days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError("day out of range 1..%d" % dim)
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NONLEAP
    return _days_before_year(y) + cum[m - 1] + d


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be int")
    if not (1 <= n <= _MAX_ORDINAL):
        raise ValueError("ordinal out of range 1..3652059")
    a = n - 1
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) <= a:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    day_in_year = a - _days_before_year(y) + 1
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NONLEAP
    for m in range(1, 13):
        if day_in_year <= cum[m]:
            return (y, m, day_in_year - cum[m - 1])


def weekday(y, m, d):
    if not (_is_int(y) and _is_int(m) and _is_int(d)):
        raise TypeError("y, m, d must be ints")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    dim = _days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError("day out of range 1..%d" % dim)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    if not isinstance(date, tuple) or len(date) != 3:
        raise TypeError("date must be a tuple of exactly 3 ints")
    for v in date:
        if not _is_int(v):
            raise TypeError("date elements must be ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    _check_date_tuple(date)
    ord_n = to_ordinal(*date) + n
    if ord_n < 1 or ord_n > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(ord_n)


def add_months(date, n):
    if not isinstance(date, tuple) or len(date) != 3:
        raise TypeError("date must be a tuple of exactly 3 ints")
    for v in date:
        if not _is_int(v):
            raise TypeError("date elements must be ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    _check_date_tuple(date)
    result = _shift(date, n)
    ty = result[0]
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of range")
    return result


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if wd == 3:
        return 53
    if _is_leap(iso_year) and wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    if not (_is_int(y) and _is_int(m) and _is_int(d)):
        raise TypeError("y, m, d must be ints")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    dim = _days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError("day out of range 1..%d" % dim)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    iso_wd = wd + 1
    ord_monday = ord_val - wd
    ord_jan4 = to_ordinal(y, 1, 4)
    wd_jan4 = (ord_jan4 - 1) % 7
    ord_monday_w1 = ord_jan4 - wd_jan4
    weeks_diff = (ord_monday - ord_monday_w1) // 7
    iso_wk = weeks_diff + 1
    if iso_wk < 1:
        iso_yr = y - 1
        iso_wk = iso_weeks_in_year(iso_yr) + iso_wk
    else:
        nw = iso_weeks_in_year(y)
        if iso_wk > nw:
            iso_yr = y + 1
            iso_wk = 1
        else:
            iso_yr = y
    return (iso_yr, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not (_is_int(iso_year) and _is_int(week) and _is_int(weekday)):
        raise TypeError("iso_year, week, weekday must be ints")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    nw = iso_weeks_in_year(iso_year)
    if not (1 <= week <= nw):
        raise ValueError("week out of range 1..%d" % nw)
    if not (1 <= weekday <= 7):
        raise ValueError("weekday out of range 1..7")
    ord_jan4 = to_ordinal(iso_year, 1, 4)
    wd_jan4 = (ord_jan4 - 1) % 7
    ord_monday_w1 = ord_jan4 - wd_jan4
    ord_target = ord_monday_w1 + (week - 1) * 7 + (weekday - 1)
    if ord_target < 1 or ord_target > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(ord_target)


def parse(s):
    if not isinstance(s, str):
        raise TypeError("s must be str")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _days_in_month(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_BAS_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _days_in_month(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_BAS_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        nw = iso_weeks_in_year(y)
        if not (1 <= wk <= nw):
            raise ValueError("week out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("week date out of range")

    m = _RE_BAS_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        nw = iso_weeks_in_year(y)
        if not (1 <= wk <= nw):
            raise ValueError("week out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("week date out of range")

    raise ValueError("unrecognized date format")


def format_date(date, form):
    if not isinstance(date, tuple) or len(date) != 3:
        raise TypeError("date must be a tuple of exactly 3 ints")
    for v in date:
        if not _is_int(v):
            raise TypeError("date elements must be ints")
    _check_date_tuple(date)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("form must be 'calendar', 'ordinal', or 'week'")
    y, m, d = date
    if form == 'calendar':
        return "%04d-%02d-%02d" % (y, m, d)
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return "%04d-%03d" % (y, doy)
    else:
        iy, iw, id_ = iso_week(y, m, d)
        return "%04d-W%02d-%d" % (iy, iw, id_)


def diff(a, b):
    if not isinstance(a, tuple) or len(a) != 3:
        raise TypeError("a must be a tuple of exactly 3 ints")
    for v in a:
        if not _is_int(v):
            raise TypeError("a elements must be ints")
    if not isinstance(b, tuple) or len(b) != 3:
        raise TypeError("b must be a tuple of exactly 3 ints")
    for v in b:
        if not _is_int(v):
            raise TypeError("b elements must be ints")
    _check_date_tuple(a)
    _check_date_tuple(b)

    if a == b:
        return (0, 0, 0)

    if a > b:
        yr, mo, dy = diff(b, a)
        return (-yr, -mo, -dy)

    # a < b: find largest K >= 0 with shift(a, K) <= b
    lo, hi = 0, (b[0] - a[0]) * 12 + (b[1] - a[1]) + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift(a, mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _shift(a, K)
    days = to_ordinal(*b) - to_ordinal(*shifted)
    return (years, months, days)