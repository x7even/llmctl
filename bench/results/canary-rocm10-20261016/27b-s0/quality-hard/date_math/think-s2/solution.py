import re

_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MPREFIX = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_MAX_ORD = 3652059


def _is_int(x):
    return type(x) is int


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    return _MDAYS[m - 1]


def _days_before_year(y):
    yy = y - 1
    return 365 * yy + yy // 4 - yy // 100 + yy // 400


def _days_before_month(y, m):
    s = _MPREFIX[m - 1]
    if m > 2 and _is_leap(y):
        s += 1
    return s


def _to_ord(y, m, d):
    return _days_before_year(y) + _days_before_month(y, m) + d


def _from_ord(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    m = 1
    while m <= 12 and doy > _dim(y, m):
        doy -= _dim(y, m)
        m += 1
    return (y, m, doy)


def _wd(y, m, d):
    return (_to_ord(y, m, d) - 1) % 7


def _add_months(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("result out of range")
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


def _check_date_tuple(date, name="date"):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for v in date:
        if not _is_int(v):
            raise TypeError(f"{name} elements must be int")
    y, m, d = date
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")


def _check_ymd(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("y, m, d must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")


def _iso_weeks(y):
    w = _wd(y, 1, 1)
    return 53 if (w == 3 or (_is_leap(y) and w == 2)) else 52


def _doy_to_md(y, doy):
    m = 1
    while m <= 12 and doy > _dim(y, m):
        doy -= _dim(y, m)
        m += 1
    return (m, doy)


# ─── Public API ───────────────────────────────────────────────────────────

def is_leap(y):
    if not _is_int(y):
        raise TypeError("y must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap(y)


def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("y and m must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_ymd(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be int")
    if n < 1 or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    return _from_ord(n)


def weekday(y, m, d):
    _check_ymd(y, m, d)
    return _wd(y, m, d)


def add_days(date, n):
    _check_date_tuple(date, "date")
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    o = _to_ord(y, m, d) + n
    if o < 1 or o > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(o)


def add_months(date, n):
    _check_date_tuple(date, "date")
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    return _add_months(y, m, d, n)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("year out of range")
    return _iso_weeks(iso_year)


def iso_week(y, m, d):
    _check_ymd(y, m, d)
    o = _to_ord(y, m, d)
    w = (o - 1) % 7
    thu = o - w + 3
    iso_y = _from_ord(thu)[0]
    jan4 = _to_ord(iso_y, 1, 4)
    jan4_w = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4_w
    mon_this = o - w
    week = (mon_this - mon_w1) // 7 + 1
    return (iso_y, week, w + 1)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year) or not _is_int(week) or not _is_int(weekday):
        raise TypeError("iso_year, week, weekday must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    mw = _iso_weeks(iso_year)
    if week < 1 or week > mw:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4 = _to_ord(iso_year, 1, 4)
    jan4_w = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4_w
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(target)


_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_WK_EXT  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BAS  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')
_RE_8DIG    = re.compile(r'([0-9]{4})([0-9]{4})')


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    if len(s) == 10:
        m = _RE_CAL_EXT.fullmatch(s)
        if m:
            y, mo, d = int(m[1]), int(m[2]), int(m[3])
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if mo < 1 or mo > 12:
                raise ValueError("month out of range")
            if d < 1 or d > _dim(y, mo):
                raise ValueError("day out of range")
            return (y, mo, d)

        m = _RE_WK_EXT.fullmatch(s)
        if m:
            y, w, wd = int(m[1]), int(m[2]), int(m[3])
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if w < 1 or w > _iso_weeks(y):
                raise ValueError("week out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            jan4 = _to_ord(y, 1, 4)
            mon_w1 = jan4 - (jan4 - 1) % 7
            target = mon_w1 + (w - 1) * 7 + (wd - 1)
            if target < 1 or target > _MAX_ORD:
                raise ValueError("date out of range")
            return _from_ord(target)

    if len(s) == 8:
        m = _RE_ORD_EXT.fullmatch(s)
        if m:
            y, doy = int(m[1]), int(m[2])
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            max_doy = 366 if _is_leap(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError("day of year out of range")
            mm, dd = _doy_to_md(y, doy)
            return (y, mm, dd)

        m = _RE_WK_BAS.fullmatch(s)
        if m:
            y, w, wd = int(m[1]), int(m[2]), int(m[3])
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if w < 1 or w > _iso_weeks(y):
                raise ValueError("week out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            jan4 = _to_ord(y, 1, 4)
            mon_w1 = jan4 - (jan4 - 1) % 7
            target = mon_w1 + (w - 1) * 7 + (wd - 1)
            if target < 1 or target > _MAX_ORD:
                raise ValueError("date out of range")
            return _from_ord(target)

        m = _RE_8DIG.fullmatch(s)
        if m:
            y = int(m[1])
            rest = m[2]
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            mo = int(rest[0:2])
            d = int(rest[2:4])
            if 1 <= mo <= 12 and 1 <= d <= _dim(y, mo):
                return (y, mo, d)
            doy = int(rest)
            max_doy = 366 if _is_leap(y) else 365
            if 1 <= doy <= max_doy:
                mm, dd = _doy_to_md(y, doy)
                return (y, mm, dd)
            raise ValueError("invalid date")

    raise ValueError("invalid format")


def format_date(date, form):
    _check_date_tuple(date, "date")
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    y, m, d = date
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = _to_ord(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    # week
    iso_y, iso_w, iso_wd = iso_week(y, m, d)
    return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
    ay, am, ad = a
    by, bm, bd = b
    lo = 0
    hi = (by - ay) * 12 + (bm - am)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _add_months(ay, am, ad, mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months(ay, am, ad, K)
    days = _to_ord(by, bm, bd) - _to_ord(shifted[0], shifted[1], shifted[2])
    return (years, months, days)