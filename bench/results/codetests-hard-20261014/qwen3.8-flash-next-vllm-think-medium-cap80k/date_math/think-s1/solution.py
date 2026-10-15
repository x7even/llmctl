"""Proleptic-Gregorian calendar arithmetic for years 1–9999.
No datetime/calendar/time/dateutil/email.utils imports."""

__all__ = [
    'is_leap', 'days_in_month', 'to_ordinal', 'from_ordinal',
    'weekday', 'add_days', 'add_months', 'iso_weeks_in_year',
    'iso_week', 'from_iso_week', 'parse', 'format_date', 'diff',
]

_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
_MLEN = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MAX_ORD = 3652059


def _ck_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _ck_date(d, name):
    if type(d) is not tuple or len(d) != 3 or not all(type(x) is int for x in d):
        raise TypeError(f"{name} must be a tuple of 3 ints")


def _vr(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")


def _dim(y, m):
    if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        return 29
    return _MLEN[m - 1]


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def is_leap(y):
    _ck_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _leap(y)


def days_in_month(y, m):
    _ck_int(y, 'y')
    _ck_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _ck_int(y, 'y')
    _ck_int(m, 'm')
    _ck_int(d, 'd')
    _vr(y, m, d)
    y0 = y - 1
    by = 365 * y0 + y0 // 4 - y0 // 100 + y0 // 400
    if _leap(y) and m > 2:
        return by + _CUM_LEAP[m - 1] + d
    return by + _CUM[m - 1] + d


def from_ordinal(n):
    _ck_int(n, 'n')
    if n < 1 or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    z = n - 1
    n400 = z // 146097
    z %= 146097
    n100 = z // 36524
    z %= 36524
    n4 = z // 1461
    z %= 1461
    n1 = z // 365
    z %= 365
    y = n400 * 400 + n100 * 100 + n4 * 4 + n1 + 1
    if n100 == 4 or n1 == 4:
        y -= 1
    y0 = y - 1
    by = 365 * y0 + y0 // 4 - y0 // 100 + y0 // 400
    doy = n - by - 1
    if _leap(y):
        lo, hi = 0, 11
        while lo < hi:
            mid = (lo + hi + 1) >> 1
            if _CUM_LEAP[mid] <= doy:
                lo = mid
            else:
                hi = mid - 1
        return (y, lo + 1, doy - _CUM_LEAP[lo] + 1)
    else:
        lo, hi = 0, 11
        while lo < hi:
            mid = (lo + hi + 1) >> 1
            if _CUM[mid] <= doy:
                lo = mid
            else:
                hi = mid - 1
        return (y, lo + 1, doy - _CUM[lo] + 1)


def weekday(y, m, d):
    _ck_int(y, 'y')
    _ck_int(m, 'm')
    _ck_int(d, 'd')
    _vr(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _ck_date(date, 'date')
    _ck_int(n, 'n')
    y, m, d = date
    _vr(y, m, d)
    no = to_ordinal(y, m, d) + n
    if no < 1 or no > _MAX_ORD:
        raise OverflowError("result date out of range")
    return from_ordinal(no)


def add_months(date, n):
    _ck_date(date, 'date')
    _ck_int(n, 'n')
    y, m, d = date
    _vr(y, m, d)
    tm = (y - 1) * 12 + (m - 1) + n
    ny = tm // 12 + 1
    nm = tm % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("target year out of range")
    md = _dim(ny, nm)
    return (ny, nm, d if d <= md else md)


def iso_weeks_in_year(iso_year):
    _ck_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    y0 = iso_year - 1
    by = 365 * y0 + y0 // 4 - y0 // 100 + y0 // 400
    wd = by % 7  # weekday of Jan 1: 0=Mon..6=Sun
    if wd == 3 or (_leap(iso_year) and wd == 2):
        return 53
    return 52


def iso_week(y, m, d):
    _ck_int(y, 'y')
    _ck_int(m, 'm')
    _ck_int(d, 'd')
    _vr(y, m, d)
    ov = to_ordinal(y, m, d)
    wd = (ov - 1) % 7
    thu = ov + (3 - wd)
    # year of that Thursday
    z = thu - 1
    n400 = z // 146097; z %= 146097
    n100 = z // 36524; z %= 36524
    n4 = z // 1461; z %= 1461
    n1 = z // 365
    iy = n400 * 400 + n100 * 100 + n4 * 4 + n1 + 1
    if n100 == 4 or n1 == 4:
        iy -= 1
    # Monday of ISO week 1 of iy
    iy0 = iy - 1
    jan4 = 365 * iy0 + iy0 // 4 - iy0 // 100 + iy0 // 400 + 4
    j4wd = (jan4 - 1) % 7
    mon1 = jan4 + (3 - j4wd) - 3
    mon_this = ov - wd
    iw = (mon_this - mon1) // 7 + 1
    return (iy, iw, wd + 1)


def from_iso_week(iso_year, week, weekday):
    _ck_int(iso_year, 'iso_year')
    _ck_int(week, 'week')
    _ck_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    mw = iso_weeks_in_year(iso_year)
    if week < 1 or week > mw:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    iy0 = iso_year - 1
    jan4 = 365 * iy0 + iy0 // 4 - iy0 // 100 + iy0 // 400 + 4
    j4wd = (jan4 - 1) % 7
    mon1 = jan4 + (3 - j4wd) - 3
    tgt = mon1 + (week - 1) * 7 + (weekday - 1)
    if tgt < 1 or tgt > _MAX_ORD:
        raise OverflowError("result date out of range")
    return from_ordinal(tgt)


def _adig(c):
    return '0' <= c <= '9'


def _pd(s):
    v = 0
    for c in s:
        v = v * 10 + (ord(c) - 48)
    return v


def _vc(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")
    return (y, m, d)


def _vo(y, doy):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    mx = 366 if _leap(y) else 365
    if doy < 1 or doy > mx:
        raise ValueError("ordinal day out of range")
    y0 = y - 1
    by = 365 * y0 + y0 // 4 - y0 // 100 + y0 // 400
    return from_ordinal(by + doy)


def _vw(iy, wk, wd):
    if iy < 1 or iy > 9999:
        raise ValueError("ISO year out of range")
    if wk < 1 or wk > 53:
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    mw = iso_weeks_in_year(iy)
    if wk > mw:
        raise ValueError("week out of range for ISO year")
    iy0 = iy - 1
    jan4 = 365 * iy0 + iy0 // 4 - iy0 // 100 + iy0 // 400 + 4
    j4wd = (jan4 - 1) % 7
    mon1 = jan4 + (3 - j4wd) - 3
    tgt = mon1 + (wk - 1) * 7 + (wd - 1)
    if tgt < 1 or tgt > _MAX_ORD:
        raise ValueError("result date out of range")
    return from_ordinal(tgt)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    ln = len(s)
    if ln == 10:
        if not all(_adig(c) for c in s[:4]):
            raise ValueError("invalid year")
        if s[4] != '-':
            raise ValueError("invalid format")
        if s[5] == 'W':
            if not all(_adig(c) for c in s[6:8]):
                raise ValueError("invalid week")
            if s[8] != '-':
                raise ValueError("invalid format")
            if not _adig(s[9]):
                raise ValueError("invalid weekday")
            return _vw(_pd(s[:4]), _pd(s[6:8]), _pd(s[9]))
        elif _adig(s[5]):
            if not all(_adig(c) for c in s[5:7]):
                raise ValueError("invalid month")
            if s[7] != '-':
                raise ValueError("invalid format")
            if not all(_adig(c) for c in s[8:10]):
                raise ValueError("invalid day")
            return _vc(_pd(s[:4]), _pd(s[5:7]), _pd(s[8:10]))
        else:
            raise ValueError("invalid format")
    elif ln == 8:
        if not all(_adig(c) for c in s[:4]):
            raise ValueError("invalid year")
        if s[4] == '-':
            if not all(_adig(c) for c in s[5:8]):
                raise ValueError("invalid ordinal day")
            return _vo(_pd(s[:4]), _pd(s[5:8]))
        elif s[4] == 'W':
            if not all(_adig(c) for c in s[5:7]):
                raise ValueError("invalid week")
            if not _adig(s[7]):
                raise ValueError("invalid weekday")
            return _vw(_pd(s[:4]), _pd(s[5:7]), _pd(s[7]))
        elif _adig(s[4]):
            if not all(_adig(c) for c in s[4:8]):
                raise ValueError("invalid date")
            return _vc(_pd(s[:4]), _pd(s[4:6]), _pd(s[6:8]))
        else:
            raise ValueError("invalid format")
    elif ln == 7:
        if not all(_adig(c) for c in s):
            raise ValueError("invalid format")
        return _vo(_pd(s[:4]), _pd(s[4:7]))
    else:
        raise ValueError("invalid format")


def format_date(date, form):
    _ck_date(date, 'date')
    y, m, d = date
    _vr(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        if _leap(y) and m > 2:
            doy = _CUM_LEAP[m - 1] + d
        else:
            doy = _CUM[m - 1] + d
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _ck_date(a, 'a')
    _ck_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _vr(ay, am, ad)
    _vr(by, bm, bd)
    if a == b:
        return (0, 0, 0)
    if a > b:
        yr, mo, dy = diff(b, a)
        return (-yr, -mo, -dy)
    # a < b
    b_ord = to_ordinal(by, bm, bd)
    lo = 0
    hi = (by - ay + 2) * 12
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        tm = (ay - 1) * 12 + (am - 1) + mid
        ny = tm // 12 + 1
        nm = tm % 12 + 1
        if ny < 1 or ny > 9999:
            hi = mid - 1
            continue
        md = _dim(ny, nm)
        nd = ad if ad <= md else md
        y0 = ny - 1
        s_ord = 365 * y0 + y0 // 4 - y0 // 100 + y0 // 400
        if _leap(ny) and nm > 2:
            s_ord += _CUM_LEAP[nm - 1] + nd
        else:
            s_ord += _CUM[nm - 1] + nd
        if s_ord <= b_ord:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    tm = (ay - 1) * 12 + (am - 1) + K
    ny = tm // 12 + 1
    nm = tm % 12 + 1
    md = _dim(ny, nm)
    nd = ad if ad <= md else md
    y0 = ny - 1
    s_ord = 365 * y0 + y0 // 4 - y0 // 100 + y0 // 400
    if _leap(ny) and nm > 2:
        s_ord += _CUM_LEAP[nm - 1] + nd
    else:
        s_ord += _CUM[nm - 1] + nd
    days = b_ord - s_ord
    return (years, months, days)
