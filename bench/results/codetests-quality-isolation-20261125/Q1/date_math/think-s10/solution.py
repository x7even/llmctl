import re

_DIM = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORD = 3652059

_RE_EXT_CAL = re.compile(r'\A([0-9]{4})-([0-9]{2})-([0-9]{2})\Z')
_RE_BAS_CAL = re.compile(r'\A([0-9]{4})([0-9]{2})([0-9]{2})\Z')
_RE_EXT_ORD = re.compile(r'\A([0-9]{4})-([0-9]{3})\Z')
_RE_BAS_ORD = re.compile(r'\A([0-9]{4})([0-9]{3})\Z')
_RE_EXT_WK  = re.compile(r'\A([0-9]{4})-W([0-9]{2})-([0-9])\Z')
_RE_BAS_WK  = re.compile(r'\A([0-9]{4})W([0-9]{2})([0-9])\Z')


# ─── internal helpers (no public type-checking) ───────────────────────────

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _dim(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _DIM[m - 1]

def _dbm(y, m):
    t = _CUM[m - 1]
    if m > 2 and _is_leap(y):
        t += 1
    return t

def _dby(y):
    y1 = y - 1
    return 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400

def _diy(y):
    return 366 if _is_leap(y) else 365

def _ord(y, m, d):
    return _dby(y) + _dbm(y, m) + d

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")

def _check_date(x, name):
    if type(x) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i in range(3):
        if type(x[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int")

def _validate(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)} for {y:04d}-{m:02d}")

def _from_ord(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        if _dby(mid + 1) < n:
            lo = mid + 1
        else:
            hi = mid
    y = lo
    doy = n - _dby(y)
    md = list(_DIM)
    if _is_leap(y):
        md[1] = 29
    m = 1
    while doy > md[m - 1]:
        doy -= md[m - 1]
        m += 1
    return (y, m, doy)

def _add_months(y, m, d, n):
    tm = (y - 1) * 12 + (m - 1) + n
    ny = tm // 12 + 1
    nm = tm % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError(f"target year {ny} out of range 1..9999")
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)

def _iso_week(y, m, d):
    o = _ord(y, m, d)
    wd = (o - 1) % 7
    mon = o - wd
    thu = mon + 3
    iso_y = _from_ord(thu)[0]
    jan4 = _ord(iso_y, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4_wd
    week = (mon - mon_w1) // 7 + 1
    return (iso_y, week, wd + 1)

def _iso_weeks_in_year(iy):
    wd = (_ord(iy, 1, 1) - 1) % 7
    if wd == 3:
        return 53
    if wd == 2 and _is_leap(iy):
        return 53
    return 52


# ─── public API ────────────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y, "y")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)

def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)

def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate(y, m, d)
    return _ord(y, m, d)

def from_ordinal(n):
    _check_int(n, "n")
    if n < 1 or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ord(n)

def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate(y, m, d)
    return (_ord(y, m, d) - 1) % 7

def add_days(date, n):
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _validate(y, m, d)
    o = _ord(y, m, d) + n
    if o < 1 or o > _MAX_ORD:
        raise OverflowError(f"result ordinal {o} out of range 1..{_MAX_ORD}")
    return _from_ord(o)

def add_months(date, n):
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _validate(y, m, d)
    return _add_months(y, m, d, n)

def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)

def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate(y, m, d)
    return _iso_week(y, m, d)

def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = _iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4 = _ord(iso_year, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError(f"result ordinal {target} out of range 1..{_MAX_ORD}")
    return _from_ord(target)

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    m = _RE_EXT_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _validate(y, mo, d)
        return (y, mo, d)

    m = _RE_BAS_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _validate(y, mo, d)
        return (y, mo, d)

    m = _RE_EXT_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        if doy < 1 or doy > _diy(y):
            raise ValueError(f"day of year {doy} out of range 1..{_diy(y)}")
        return _from_ord(_dby(y) + doy)

    m = _RE_BAS_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        if doy < 1 or doy > _diy(y):
            raise ValueError(f"day of year {doy} out of range 1..{_diy(y)}")
        return _from_ord(_dby(y) + doy)

    m = _RE_EXT_WK.match(s)
    if m:
        iy, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if iy < 1 or iy > 9999:
            raise ValueError(f"iso_year {iy} out of range 1..9999")
        nw = _iso_weeks_in_year(iy)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4 = _ord(iy, 1, 4)
        jan4_wd = (jan4 - 1) % 7
        mon_w1 = jan4 - jan4_wd
        target = mon_w1 + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > _MAX_ORD:
            raise ValueError(f"week date out of range")
        return _from_ord(target)

    m = _RE_BAS_WK.match(s)
    if m:
        iy, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if iy < 1 or iy > 9999:
            raise ValueError(f"iso_year {iy} out of range 1..9999")
        nw = _iso_weeks_in_year(iy)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4 = _ord(iy, 1, 4)
        jan4_wd = (jan4 - 1) % 7
        mon_w1 = jan4 - jan4_wd
        target = mon_w1 + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > _MAX_ORD:
            raise ValueError(f"week date out of range")
        return _from_ord(target)

    raise ValueError(f"invalid date string: {s!r}")

def format_date(date, form):
    _check_date(date, "date")
    y, m, d = date
    _validate(y, m, d)

    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _dbm(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, id_ = _iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"

def diff(a, b):
    _check_date(a, "a")
    _check_date(b, "b")
    _validate(a[0], a[1], a[2])
    _validate(b[0], b[1], b[2])

    if a <= b:
        lo, hi = 0, 119987
        while lo < hi:
            mid = (lo + hi + 1) // 2
            try:
                shifted = _add_months(a[0], a[1], a[2], mid)
            except OverflowError:
                shifted = None
            if shifted is not None and shifted <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _add_months(a[0], a[1], a[2], K)
        days = _ord(b[0], b[1], b[2]) - _ord(shifted[0], shifted[1], shifted[2])
        return (years, months, days)
    else:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
