"""Proleptic-Gregorian calendar arithmetic for years 1-9999 (no datetime/calendar/time/dateutil/email.utils)."""

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTH_DAYS_LEAP = (0, 31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
_MIN_ORD = 1
_MAX_ORD = 3652059


# --------------- internal helpers (no argument checking) ---------------

def _is_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def _dim(y, m):
    return _MONTH_DAYS_LEAP[m] if _is_leap(y) else _MONTH_DAYS[m]


def _to_ord(y, m, d):
    x = y - 1
    n = 365 * x + x // 4 - x // 100 + x // 400
    n += (_CUM_LEAP if _is_leap(y) else _CUM)[m - 1]
    return n + d


def _from_ord(n):
    x = (n - 1) * 400 // 146097
    if 365 * (x + 1) + (x + 1) // 4 - (x + 1) // 100 + (x + 1) // 400 <= n - 1:
        x += 1
    y = x + 1
    doy = n - (365 * x + x // 4 - x // 100 + x // 400)
    cum = _CUM_LEAP if _is_leap(y) else _CUM
    m = 1
    while m < 12 and doy > cum[m]:
        m += 1
    return (y, m, doy - cum[m - 1])


def _add_months_raw(date, n):
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d
    mx = _dim(ny, nm)
    if nd > mx:
        nd = mx
    return (ny, nm, nd)


def _iso_weeks_raw(y):
    wd = (_to_ord(y, 1, 1) - 1) % 7
    if wd == 3:
        return 53
    if wd == 2 and _is_leap(y):
        return 53
    return 52


def _iso_week_raw(y, m, d):
    n = _to_ord(y, m, d)
    wd0 = (n - 1) % 7
    thu = n - wd0 + 3
    x = (thu - 1) * 400 // 146097
    if 365 * (x + 1) + (x + 1) // 4 - (x + 1) // 100 + (x + 1) // 400 <= thu - 1:
        x += 1
    iy = x + 1
    jan4 = _to_ord(iy, 1, 4)
    mon1 = jan4 - (jan4 - 1) % 7
    iw = (thu - mon1) // 7 + 1
    return (iy, iw, wd0 + 1)


# --------------- type / range checking helpers ---------------

def _ci(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int")


def _cd(d, name):
    if type(d) is not tuple or len(d) != 3:
        raise TypeError(f"{name} must be a 3-tuple of ints")
    for v in d:
        if type(v) is not int:
            raise TypeError(f"{name} elements must be int")


def _cr(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")


# --------------- public API ---------------

def is_leap(y):
    _ci(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap(y)


def days_in_month(y, m):
    _ci(y, 'y')
    _ci(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cr(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    _ci(n, 'n')
    if n < _MIN_ORD or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    return _from_ord(n)


def weekday(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cr(y, m, d)
    return (_to_ord(y, m, d) - 1) % 7


def add_days(date, n):
    _cd(date, 'date')
    _ci(n, 'n')
    _cr(date[0], date[1], date[2])
    o = _to_ord(date[0], date[1], date[2]) + n
    if o < _MIN_ORD or o > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(o)


def add_months(date, n):
    _cd(date, 'date')
    _ci(n, 'n')
    _cr(date[0], date[1], date[2])
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("target year out of range")
    nd = d
    mx = _dim(ny, nm)
    if nd > mx:
        nd = mx
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _ci(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("year out of range")
    return _iso_weeks_raw(iso_year)


def iso_week(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cr(y, m, d)
    return _iso_week_raw(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _ci(iso_year, 'iso_year')
    _ci(week, 'week')
    _ci(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    if week < 1 or week > _iso_weeks_raw(iso_year):
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4 = _to_ord(iso_year, 1, 4)
    mon1 = jan4 - (jan4 - 1) % 7
    o = mon1 + (week - 1) * 7 + (weekday - 1)
    if o < _MIN_ORD or o > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(o)


# --------------- parse / format ---------------

def _ad(s, i, j):
    """all ASCII digits in s[i:j]"""
    for k in range(i, j):
        if s[k] < '0' or s[k] > '9':
            return False
    return True


def _cal_chk(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")
    return (y, m, d)


def _ord_chk(y, doy):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    mx = 366 if _is_leap(y) else 365
    if doy < 1 or doy > mx:
        raise ValueError("day-of-year out of range")
    cum = _CUM_LEAP if _is_leap(y) else _CUM
    m = 1
    while m < 12 and doy > cum[m]:
        m += 1
    return (y, m, doy - cum[m - 1])


def _wk_chk(iy, wk, wd):
    if iy < 1 or iy > 9999:
        raise ValueError("iso_year out of range")
    if wk < 1 or wk > _iso_weeks_raw(iy):
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    jan4 = _to_ord(iy, 1, 4)
    mon1 = jan4 - (jan4 - 1) % 7
    o = mon1 + (wk - 1) * 7 + (wd - 1)
    if o < _MIN_ORD or o > _MAX_ORD:
        raise ValueError("date out of range")
    return _from_ord(o)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    ln = len(s)
    if ln == 10:
        if not _ad(s, 0, 4):
            raise ValueError("invalid")
        if s[4] == 'W':
            if s[5] != '-' or not _ad(s, 6, 8) or s[8] != '-' or not _ad(s, 9, 10):
                raise ValueError("invalid")
            return _wk_chk(int(s[0:4]), int(s[6:8]), int(s[9]))
        elif s[4] == '-':
            if not _ad(s, 5, 7) or s[7] != '-' or not _ad(s, 8, 10):
                raise ValueError("invalid")
            return _cal_chk(int(s[0:4]), int(s[5:7]), int(s[8:10]))
        else:
            raise ValueError("invalid")
    elif ln == 8:
        if not _ad(s, 0, 4):
            raise ValueError("invalid")
        if s[4] == '-':
            if not _ad(s, 5, 8):
                raise ValueError("invalid")
            return _ord_chk(int(s[0:4]), int(s[5:8]))
        elif s[4] == 'W':
            if not _ad(s, 5, 7) or not _ad(s, 7, 8):
                raise ValueError("invalid")
            return _wk_chk(int(s[0:4]), int(s[5:7]), int(s[7]))
        elif '0' <= s[4] <= '9':
            if not _ad(s, 4, 8):
                raise ValueError("invalid")
            return _cal_chk(int(s[0:4]), int(s[4:6]), int(s[6:8]))
        else:
            raise ValueError("invalid")
    elif ln == 7:
        if not _ad(s, 0, 7):
            raise ValueError("invalid")
        return _ord_chk(int(s[0:4]), int(s[4:7]))
    else:
        raise ValueError("invalid")


def format_date(date, form):
    _cd(date, 'date')
    _cr(date[0], date[1], date[2])
    if form == 'calendar':
        return "%04d-%02d-%02d" % (date[0], date[1], date[2])
    elif form == 'ordinal':
        doy = _to_ord(date[0], date[1], date[2]) - _to_ord(date[0], 1, 1) + 1
        return "%04d-%03d" % (date[0], doy)
    elif form == 'week':
        iy, iw, id_ = _iso_week_raw(date[0], date[1], date[2])
        return "%04d-W%02d-%d" % (iy, iw, id_)
    else:
        raise ValueError("invalid form")


def diff(a, b):
    _cd(a, 'a')
    _cd(b, 'b')
    _cr(a[0], a[1], a[2])
    _cr(b[0], b[1], b[2])
    oa = _to_ord(a[0], a[1], a[2])
    ob = _to_ord(b[0], b[1], b[2])
    if oa > ob:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
    K = (b[0] - a[0]) * 12 + (b[1] - a[1])
    sh = _add_months_raw(a, K)
    if _to_ord(sh[0], sh[1], sh[2]) > ob:
        K -= 1
        sh = _add_months_raw(a, K)
    years, months = divmod(K, 12)
    days = ob - _to_ord(sh[0], sh[1], sh[2])
    return (years, months, days)
