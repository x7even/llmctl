import re

# ─── constants ────────────────────────────────────────────────────────────────
_MD = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MIN_ORD = 1
_MAX_ORD = 3652059

# ─── internal helpers (no validation) ────────────────────────────────────────

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _dim(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MD[m - 1]

def _db_year(y):
    """Days in years 1..y-1."""
    y -= 1
    r = y % 400
    return (y // 400) * 146097 + r * 365 + r // 4 - r // 100

def _db_month(y, m):
    t = _CUM[m - 1]
    if m > 2 and _is_leap(y):
        t += 1
    return t

def _ord(y, m, d):
    return _db_year(y) + _db_month(y, m) + d

def _from_ord(n):
    """Assume 1 <= n <= _MAX_ORD."""
    full400 = (n - 1) // 146097
    rem = (n - 1) % 146097
    ybase = full400 * 400
    k = rem // 365
    while k > 0 and k * 365 + k // 4 - k // 100 > rem:
        k -= 1
    while k < 399 and (k + 1) * 365 + (k + 1) // 4 - (k + 1) // 100 <= rem:
        k += 1
    y = ybase + k + 1
    doy = rem - (k * 365 + k // 4 - k // 100) + 1
    m = 1
    while m <= 12:
        dm = _dim(y, m)
        if doy <= dm:
            return (y, m, doy)
        doy -= dm
        m += 1
    raise ValueError("internal error in _from_ord")

def _add_months(y, m, d, n):
    """Assume (y,m,d) valid. Raise OverflowError if target year out of range."""
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("add_months result out of range")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)

def _iso_weeks(y):
    """Assume 1 <= y <= 9999."""
    j1 = _db_year(y) % 7
    if j1 == 3:
        return 53
    if j1 == 2 and _is_leap(y):
        return 53
    return 52

def _find_max_K(a, b):
    """Largest K>=0 with _add_months(*a, K) <= b. Assume a<=b, both valid."""
    lo, hi = 0, 120000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            s = _add_months(*a, mid)
            if s <= b:
                lo = mid
            else:
                hi = mid - 1
        except OverflowError:
            hi = mid - 1
    return lo

# ─── type / range check helpers ──────────────────────────────────────────────

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")

def _chk_date(d, name):
    if not isinstance(d, tuple) or len(d) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, x in enumerate(d):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(x).__name__}")

def _chk_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dm = _dim(y, m)
    if not (1 <= d <= dm):
        raise ValueError(f"day {d} out of range 1..{dm}")

# ─── public API ──────────────────────────────────────────────────────────────

def is_leap(y):
    _chk_int(y, "y")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)

def days_in_month(y, m):
    _chk_int(y, "y")
    _chk_int(m, "m")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)

def to_ordinal(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_range(y, m, d)
    return _ord(y, m, d)

def from_ordinal(n):
    _chk_int(n, "n")
    if not (_MIN_ORD <= n <= _MAX_ORD):
        raise ValueError(f"ordinal {n} out of range {_MIN_ORD}..{_MAX_ORD}")
    return _from_ord(n)

def weekday(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_range(y, m, d)
    return (_ord(y, m, d) - 1) % 7

def add_days(date, n):
    _chk_date(date, "date")
    _chk_int(n, "n")
    y, m, d = date
    _chk_range(y, m, d)
    o = _ord(y, m, d) + n
    if o < _MIN_ORD or o > _MAX_ORD:
        raise OverflowError(f"result ordinal {o} out of range")
    return _from_ord(o)

def add_months(date, n):
    _chk_date(date, "date")
    _chk_int(n, "n")
    y, m, d = date
    _chk_range(y, m, d)
    return _add_months(y, m, d, n)

def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, "iso_year")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks(iso_year)

def iso_week(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_range(y, m, d)
    o = _ord(y, m, d)
    wd = (o - 1) % 7
    # Monday of week 1 of ISO year y
    j4 = _db_year(y) + 4
    j4w = (j4 - 1) % 7
    mon1 = j4 - j4w
    iw = (o - mon1) // 7 + 1
    iy = y
    if iw < 1:
        iy = y - 1
        j4 = _db_year(iy) + 4
        j4w = (j4 - 1) % 7
        mon1 = j4 - j4w
        iw = (o - mon1) // 7 + 1
    elif iw > _iso_weeks(y):
        iy = y + 1
        j4 = _db_year(iy) + 4
        j4w = (j4 - 1) % 7
        mon1 = j4 - j4w
        iw = (o - mon1) // 7 + 1
    return (iy, iw, wd + 1)

def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, "iso_year")
    _chk_int(week, "week")
    _chk_int(weekday, "weekday")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    max_wk = _iso_weeks(iso_year)
    if not (1 <= week <= max_wk):
        raise ValueError(f"week {week} out of range 1..{max_wk}")
    j4 = _db_year(iso_year) + 4
    j4w = (j4 - 1) % 7
    mon1 = j4 - j4w
    target = mon1 + (week - 1) * 7 + (weekday - 1)
    if target < _MIN_ORD or target > _MAX_ORD:
        raise OverflowError(f"result ordinal {target} out of range")
    return _from_ord(target)

# ─── parse / format ──────────────────────────────────────────────────────────

_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BAS  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')

def _from_doy(y, doy):
    m = 1
    while m <= 12:
        dm = _dim(y, m)
        if doy <= dm:
            return (y, m, doy)
        doy -= dm
        m += 1
    raise ValueError("internal error")

def _parse_week(iso_yr, wk, wd):
    if not (1 <= iso_yr <= 9999):
        raise ValueError(f"iso_year {iso_yr} out of range")
    if not (1 <= wd <= 7):
        raise ValueError(f"weekday {wd} out of range 1..7")
    max_wk = _iso_weeks(iso_yr)
    if not (1 <= wk <= max_wk):
        raise ValueError(f"week {wk} out of range 1..{max_wk}")
    j4 = _db_year(iso_yr) + 4
    j4w = (j4 - 1) % 7
    mon1 = j4 - j4w
    target = mon1 + (wk - 1) * 7 + (wd - 1)
    if target < _MIN_ORD or target > _MAX_ORD:
        raise ValueError("week date out of supported range")
    return _from_ord(target)

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    m = _RE_CAL_EXT.fullmatch(s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        _chk_range(y, mo, d)
        return (y, mo, d)

    m = _RE_CAL_BAS.fullmatch(s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        _chk_range(y, mo, d)
        return (y, mo, d)

    m = _RE_ORD_EXT.fullmatch(s)
    if m:
        y, doy = int(m[1]), int(m[2])
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_doy(y, doy)

    m = _RE_ORD_BAS.fullmatch(s)
    if m:
        y, doy = int(m[1]), int(m[2])
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_doy(y, doy)

    m = _RE_WK_EXT.fullmatch(s)
    if m:
        return _parse_week(int(m[1]), int(m[2]), int(m[3]))

    m = _RE_WK_BAS.fullmatch(s)
    if m:
        return _parse_week(int(m[1]), int(m[2]), int(m[3]))

    raise ValueError(f"invalid date string: {s!r}")

def format_date(date, form):
    _chk_date(date, "date")
    y, m, d = date
    _chk_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = _ord(y, m, d) - _db_year(y)
        return f"{y:04d}-{doy:03d}"
    # week
    iy, iw, wd = iso_week(y, m, d)
    return f"{iy:04d}-W{iw:02d}-{wd}"

# ─── diff ────────────────────────────────────────────────────────────────────

def diff(a, b):
    _chk_date(a, "a")
    _chk_date(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _chk_range(ay, am, ad)
    _chk_range(by, bm, bd)

    a_ord = _ord(ay, am, ad)
    b_ord = _ord(by, bm, bd)

    if a_ord <= b_ord:
        K = _find_max_K(a, b)
        years, months = divmod(K, 12)
        shifted = _add_months(ay, am, ad, K)
        days = b_ord - _ord(*shifted)
        return (years, months, days)
    else:
        K = _find_max_K(b, a)
        years, months = divmod(K, 12)
        shifted = _add_months(by, bm, bd, K)
        days = a_ord - _ord(*shifted)
        return (-years, -months, -days)