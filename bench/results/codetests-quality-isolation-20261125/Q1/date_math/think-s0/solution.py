import re

_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9]{1})')
_RE_WK_BAS = re.compile(r'([0-9]{4})W([0-9]{2})([0-9]{1})')

_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    return _MDAYS[m - 1]


def _days_before_year(y):
    y -= 1
    return y * 365 + y // 4 - y // 100 + y // 400


def _check_int(v, name):
    if type(v) is not int:
        raise TypeError(f"{name} must be int")


def _check_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for v in x:
        if type(v) is not int:
            raise TypeError(f"{name} must be a tuple of 3 ints")


def _check_valid(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("date out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")


def is_leap(y):
    _check_int(y, "y")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid(y, m, d)
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NONLEAP
    return _days_before_year(y) + cum[m - 1] + d


def from_ordinal(n):
    _check_int(n, "n")
    if n < 1 or n > 3652059:
        raise ValueError("ordinal out of range")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NONLEAP
    m = 1
    while m <= 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_valid(y, m, d)
    o = to_ordinal(y, m, d) + n
    if o < 1 or o > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(o)


def add_months(date, n):
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_valid(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("result out of range")
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    w = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if w == 3:
        return 53
    if _is_leap(iso_year) and w == 2:
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid(y, m, d)
    w = (to_ordinal(y, m, d) - 1) % 7
    iso_wd = w + 1
    ord_ = to_ordinal(y, m, d)
    thur_ord = ord_ - w + 3
    iso_y = from_ordinal(thur_ord)[0]
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_w = (jan4_ord - 1) % 7
    week1_mon = jan4_ord - jan4_w
    mon_ord = ord_ - w
    week = (mon_ord - week1_mon) // 7 + 1
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday_val):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday_val, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    mw = iso_weeks_in_year(iso_year)
    if week < 1 or week > mw:
        raise ValueError("week out of range")
    if weekday_val < 1 or weekday_val > 7:
        raise ValueError("weekday out of range")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_w = (jan4_ord - 1) % 7
    week1_mon = jan4_ord - jan4_w
    target = week1_mon + (week - 1) * 7 + (weekday_val - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    m = _RE_CAL_EXT.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid date")
        _check_valid(y, mo, d)
        return (y, mo, d)

    m = _RE_WK_EXT.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid date")
        if wk < 1 or wk > iso_weeks_in_year(y):
            raise ValueError("invalid date")
        if wd < 1 or wd > 7:
            raise ValueError("invalid date")
        jan4_ord = to_ordinal(y, 1, 4)
        jan4_w = (jan4_ord - 1) % 7
        target = jan4_ord - jan4_w + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > 3652059:
            raise ValueError("invalid date")
        return from_ordinal(target)

    m = _RE_ORD_EXT.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("invalid date")
        max_d = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_d:
            raise ValueError("invalid date")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_CAL_BAS.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid date")
        _check_valid(y, mo, d)
        return (y, mo, d)

    m = _RE_WK_BAS.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid date")
        if wk < 1 or wk > iso_weeks_in_year(y):
            raise ValueError("invalid date")
        if wd < 1 or wd > 7:
            raise ValueError("invalid date")
        jan4_ord = to_ordinal(y, 1, 4)
        jan4_w = (jan4_ord - 1) % 7
        target = jan4_ord - jan4_w + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > 3652059:
            raise ValueError("invalid date")
        return from_ordinal(target)

    m = _RE_ORD_BAS.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("invalid date")
        max_d = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_d:
            raise ValueError("invalid date")
        return from_ordinal(_days_before_year(y) + doy)

    raise ValueError("invalid date string")


def format_date(date, form):
    _check_date(date, "date")
    y, m, d = date
    _check_valid(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    iy, iw, id_ = iso_week(y, m, d)
    return f"{iy:04d}-W{iw:02d}-{id_}"


def diff(a, b):
    _check_date(a, "a")
    _check_date(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_valid(ay, am, ad)
    _check_valid(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        r = diff(b, a)
        return (-r[0], -r[1], -r[2])

    # a < b: find largest K >= 0 with add_months(a, K) <= b
    def _shift_leq(K):
        total = (ay - 1) * 12 + (am - 1) + K
        ny = total // 12 + 1
        nm = total % 12 + 1
        if ny < 1 or ny > 9999:
            return False
        nd = ad if ad <= _dim(ny, nm) else _dim(ny, nm)
        return (ny, nm, nd) <= b

    lo, hi = 0, (by - ay) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift_leq(mid):
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    total = (ay - 1) * 12 + (am - 1) + K
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = ad if ad <= _dim(ny, nm) else _dim(ny, nm)
    days = to_ordinal(by, bm, bd) - to_ordinal(ny, nm, nd)
    return (years, months, days)
