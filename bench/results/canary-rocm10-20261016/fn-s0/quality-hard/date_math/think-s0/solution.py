"""Proleptic Gregorian calendar arithmetic for years 1 through 9999.

No imports of datetime, calendar, time, dateutil, or email.utils.
All computation is plain integer arithmetic.
"""

__all__ = [
    'is_leap', 'days_in_month', 'to_ordinal', 'from_ordinal', 'weekday',
    'add_days', 'add_months', 'iso_weeks_in_year', 'iso_week', 'from_iso_week',
    'parse', 'format_date', 'diff',
]

_MIN_ORD = 1
_MAX_ORD = 3652059

# Cumulative days before month m (index 0 unused, indices 1-12)
_DB = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_DB_L = (0, 0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
_MD = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


# --------------- internal helpers (no argument checking) ---------------

def _leap(y):
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def _dim(y, m):
    if m == 2 and _leap(y):
        return 29
    return _MD[m]


def _ord(y, m, d):
    dbm = _DB_L[m] if _leap(y) else _DB[m]
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400 + dbm + d


def _from_ord(n):
    z = n - 1
    n400, z = divmod(z, 146097)
    n100, z = divmod(z, 36524)
    n4, z = divmod(z, 1461)
    n1, z = divmod(z, 365)
    if n100 == 4:
        n100 = 3
        z += 36524
    if n1 == 4:
        n1 = 3
        z += 365
    year = 1 + 400 * n400 + 100 * n100 + 4 * n4 + n1
    doy = z
    leap = _leap(year)
    table = _DB_L if leap else _DB
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if table[mid] <= doy:
            lo = mid
        else:
            hi = mid - 1
    return (year, lo, doy - table[lo] + 1)


def _wd(ord_val):
    return (ord_val - 1) % 7


def _add_months_raw(y, m, d, n):
    total = (m - 1) + n
    ya = total // 12
    nm = total % 12 + 1
    ny = y + ya
    dim = _dim(ny, nm)
    nd = d if d <= dim else dim
    return (ny, nm, nd)


# --------------- type / range checking helpers ---------------

def _ci(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _cd(t, name="date"):
    if type(t) is not tuple:
        raise TypeError(f"{name} must be a tuple")
    if len(t) != 3:
        raise TypeError(f"{name} must have exactly 3 elements")
    for i, x in enumerate(t):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(x).__name__}")


def _cr(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m}")


# --------------- public API ---------------

def is_leap(y):
    _ci(y, "y")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _leap(y)


def days_in_month(y, m):
    _ci(y, "y")
    _ci(m, "m")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _ci(y, "y")
    _ci(m, "m")
    _ci(d, "d")
    _cr(y, m, d)
    return _ord(y, m, d)


def from_ordinal(n):
    _ci(n, "n")
    if n < _MIN_ORD or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range")
    return _from_ord(n)


def weekday(y, m, d):
    _ci(y, "y")
    _ci(m, "m")
    _ci(d, "d")
    _cr(y, m, d)
    return _wd(_ord(y, m, d))


def add_days(date, n):
    _cd(date)
    _ci(n, "n")
    y, m, d = date
    _cr(y, m, d)
    o = _ord(y, m, d) + n
    if o < _MIN_ORD or o > _MAX_ORD:
        raise OverflowError("resulting date out of range")
    return _from_ord(o)


def add_months(date, n):
    _cd(date)
    _ci(n, "n")
    y, m, d = date
    _cr(y, m, d)
    ny, nm, nd = _add_months_raw(y, m, d, n)
    if ny < 1 or ny > 9999:
        raise OverflowError("resulting year out of range")
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _ci(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    j1w = _wd(_ord(iso_year, 1, 1))
    if j1w == 3:
        return 53
    if j1w == 2 and _leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _ci(y, "y")
    _ci(m, "m")
    _ci(d, "d")
    _cr(y, m, d)
    o = _ord(y, m, d)
    wd = _wd(o)
    thu_o = o + (3 - wd)
    thu_date = _from_ord(thu_o)
    iso_yr = thu_date[0]
    j4o = _ord(iso_yr, 1, 4)
    j4w = _wd(j4o)
    mon_w1 = j4o - j4w
    wk = (thu_o - mon_w1) // 7 + 1
    return (iso_yr, wk, wd + 1)


def from_iso_week(iso_year, week, weekday):
    _ci(iso_year, "iso_year")
    _ci(week, "week")
    _ci(weekday, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_wk:
        raise ValueError(f"week {week} out of range for iso_year {iso_year}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    j4o = _ord(iso_year, 1, 4)
    j4w = _wd(j4o)
    mon_w1 = j4o - j4w
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < _MIN_ORD or target > _MAX_ORD:
        raise OverflowError("resulting date out of range")
    return _from_ord(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    n = len(s)

    def _dig(c):
        return '0' <= c <= '9'

    def _chk(s2):
        for c in s2:
            if not _dig(c):
                raise ValueError("invalid character in date string")

    if n == 10:
        if s[4] == '-' and s[5] == 'W' and s[8] == '-':
            _chk(s[0:4]); _chk(s[6:8]); _chk(s[9])
            yr = int(s[0:4]); wk = int(s[6:8]); wd = int(s[9])
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            if wk < 1 or wk > 53:
                raise ValueError("week out of range")
            if wk > iso_weeks_in_year(yr):
                raise ValueError("week 53 not valid for this ISO year")
            try:
                return from_iso_week(yr, wk, wd)
            except OverflowError:
                raise ValueError("date out of range")
        elif s[4] == '-' and s[7] == '-':
            _chk(s[0:4]); _chk(s[5:7]); _chk(s[8:10])
            yr = int(s[0:4]); mo = int(s[5:7]); dy = int(s[8:10])
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if mo < 1 or mo > 12:
                raise ValueError("month out of range")
            if dy < 1 or dy > _dim(yr, mo):
                raise ValueError("day out of range")
            return (yr, mo, dy)
        else:
            raise ValueError("invalid date format")

    elif n == 8:
        if s[4] == '-':
            _chk(s[0:4]); _chk(s[5:8])
            yr = int(s[0:4]); doy = int(s[5:8])
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            mx = 366 if _leap(yr) else 365
            if doy < 1 or doy > mx:
                raise ValueError("day-of-year out of range")
            return _from_ord(_ord(yr, 1, 1) + doy - 1)
        elif s[4] == 'W':
            _chk(s[0:4]); _chk(s[5:7]); _chk(s[7])
            yr = int(s[0:4]); wk = int(s[5:7]); wd = int(s[7])
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            if wk < 1 or wk > 53:
                raise ValueError("week out of range")
            if wk > iso_weeks_in_year(yr):
                raise ValueError("week 53 not valid for this ISO year")
            try:
                return from_iso_week(yr, wk, wd)
            except OverflowError:
                raise ValueError("date out of range")
        else:
            _chk(s[0:8])
            yr = int(s[0:4]); mo = int(s[4:6]); dy = int(s[6:8])
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if mo < 1 or mo > 12:
                raise ValueError("month out of range")
            if dy < 1 or dy > _dim(yr, mo):
                raise ValueError("day out of range")
            return (yr, mo, dy)

    elif n == 7:
        _chk(s[0:7])
        yr = int(s[0:4]); doy = int(s[4:7])
        if yr < 1 or yr > 9999:
            raise ValueError("year out of range")
        mx = 366 if _leap(yr) else 365
        if doy < 1 or doy > mx:
            raise ValueError("day-of-year out of range")
        return _from_ord(_ord(yr, 1, 1) + doy - 1)

    else:
        raise ValueError("invalid date format")


def format_date(date, form):
    _cd(date)
    y, m, d = date
    _cr(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _ord(y, m, d) - _ord(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _cd(a, "a")
    _cd(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _cr(ay, am, ad)
    _cr(by, bm, bd)

    oa = _ord(ay, am, ad)
    ob = _ord(by, bm, bd)

    if oa == ob:
        return (0, 0, 0)

    if oa > ob:
        yr, mo, dy = diff(b, a)
        return (-yr, -mo, -dy)

    # a < b
    K0 = (by - ay) * 12 + (bm - am)
    sy, sm, sd = _add_months_raw(ay, am, ad, K0)
    so = _ord(sy, sm, sd)

    if so <= ob:
        K = K0
    else:
        K = K0 - 1
        sy, sm, sd = _add_months_raw(ay, am, ad, K)
        so = _ord(sy, sm, sd)

    years, months = divmod(K, 12)
    days = ob - so
    return (years, months, days)
