import re

_CUM_COMMON = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
_MAX_ORD = 3652059

_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BAS_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30


def _days_before_year(y):
    n = y - 1
    return 365 * n + n // 4 - n // 100 + n // 400


def _days_before_month(y, m):
    r = _CUM_COMMON[m - 1]
    if m > 2 and _is_leap(y):
        r += 1
    return r


def _to_ord(y, m, d):
    return _days_before_year(y) + _days_before_month(y, m) + d


def _from_ord(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        if _days_before_year(mid) < n:
            lo = mid + 1
        else:
            hi = mid
    y = lo
    doy = n - _days_before_year(y)
    cum = _CUM_LEAP if _is_leap(y) else _CUM_COMMON
    m = 1
    while m < 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def _add_months_int(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if not (1 <= ny <= 9999):
        raise OverflowError("result out of range")
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


def _iso_weeks(iy):
    wd = (_to_ord(iy, 1, 1) - 1) % 7
    if wd == 3:
        return 53
    if _is_leap(iy) and wd == 2:
        return 53
    return 52


def _iso_week(y, m, d):
    o = _to_ord(y, m, d)
    wd = (o - 1) % 7
    mon = o - wd
    thu = mon + 3
    iy = _from_ord(thu)[0]
    j4 = _to_ord(iy, 1, 4)
    j4w = (j4 - 1) % 7
    mon_w1 = j4 - j4w
    week = (mon - mon_w1) // 7 + 1
    return (iy, week, wd + 1)


def _from_iso(iy, wk, wd):
    j4 = _to_ord(iy, 1, 4)
    j4w = (j4 - 1) % 7
    mon_w1 = j4 - j4w
    t = mon_w1 + (wk - 1) * 7 + (wd - 1)
    if t < 1 or t > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(t)


def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _chk_date(dt, name):
    if type(dt) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(dt) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(dt):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _chk_valid(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError(f"day {d} invalid for {y:04d}-{m:02d}")


def is_leap(y):
    _chk_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_valid(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    _chk_int(n, 'n')
    if not (1 <= n <= _MAX_ORD):
        raise ValueError("ordinal out of range 1..3652059")
    return _from_ord(n)


def weekday(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_valid(y, m, d)
    return (_to_ord(y, m, d) - 1) % 7


def add_days(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _chk_valid(y, m, d)
    o = _to_ord(y, m, d) + n
    if o < 1 or o > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(o)


def add_months(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _chk_valid(y, m, d)
    return _add_months_int(y, m, d, n)


def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    return _iso_weeks(iso_year)


def iso_week(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_valid(y, m, d)
    return _iso_week(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, 'iso_year')
    _chk_int(week, 'week')
    _chk_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    mw = _iso_weeks(iso_year)
    if not (1 <= week <= mw):
        raise ValueError(f"week {week} out of range 1..{mw}")
    if not (1 <= weekday <= 7):
        raise ValueError("weekday out of range 1..7")
    return _from_iso(iso_year, week, weekday)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    mo = _RE_EXT_CAL.fullmatch(s)
    if mo:
        y, m, d = int(mo[1]), int(mo[2]), int(mo[3])
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= m <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _dim(y, m)):
            raise ValueError("day out of range")
        return (y, m, d)

    mo = _RE_BAS_CAL.fullmatch(s)
    if mo:
        y, m, d = int(mo[1]), int(mo[2]), int(mo[3])
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= m <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _dim(y, m)):
            raise ValueError("day out of range")
        return (y, m, d)

    mo = _RE_EXT_ORD.fullmatch(s)
    if mo:
        y, doy = int(mo[1]), int(mo[2])
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        mx = 366 if _is_leap(y) else 365
        if not (1 <= doy <= mx):
            raise ValueError("day of year out of range")
        return _from_ord(_days_before_year(y) + doy)

    mo = _RE_BAS_ORD.fullmatch(s)
    if mo:
        y, doy = int(mo[1]), int(mo[2])
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        mx = 366 if _is_leap(y) else 365
        if not (1 <= doy <= mx):
            raise ValueError("day of year out of range")
        return _from_ord(_days_before_year(y) + doy)

    mo = _RE_EXT_WK.fullmatch(s)
    if mo:
        y, wk, wd = int(mo[1]), int(mo[2]), int(mo[3])
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        mw = _iso_weeks(y)
        if not (1 <= wk <= mw):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        try:
            return _from_iso(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    mo = _RE_BAS_WK.fullmatch(s)
    if mo:
        y, wk, wd = int(mo[1]), int(mo[2]), int(mo[3])
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        mw = _iso_weeks(y)
        if not (1 <= wk <= mw):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        try:
            return _from_iso(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    raise ValueError("invalid date format")


def format_date(date, form):
    _chk_date(date, 'date')
    y, m, d = date
    _chk_valid(y, m, d)
    if type(form) is not str:
        raise ValueError("form must be a string")
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    iy, wk, wd = _iso_week(y, m, d)
    return f"{iy:04d}-W{wk:02d}-{wd}"


def diff(a, b):
    _chk_date(a, 'a')
    _chk_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _chk_valid(ay, am, ad)
    _chk_valid(by, bm, bd)

    if a <= b:
        lo, hi = 0, (by - ay) * 12 + (bm - am)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _add_months_int(ay, am, ad, mid) <= (by, bm, bd):
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _add_months_int(ay, am, ad, K)
        days = _to_ord(by, bm, bd) - _to_ord(*shifted)
        return (years, months, days)
    else:
        dy, dm, dd = diff(b, a)
        return (-dy, -dm, -dd)
