import re

# ---------------------------------------------------------------------------
# Internal helpers (no public exposure)
# ---------------------------------------------------------------------------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    return (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[m - 1]

def _days_before_year(y):
    n = y - 1
    return n * 365 + n // 4 - n // 100 + n // 400

def _days_before_month(y, m):
    # cumulative days before month m in year y
    md = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    s = 0
    for i in range(m - 1):
        s += md[i]
    if m > 2 and _is_leap(y):
        s += 1
    return s

def _days_in_year(y):
    return 366 if _is_leap(y) else 365

# ---------------------------------------------------------------------------
# Type / range checking helpers
# ---------------------------------------------------------------------------

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")

def _check_date_tuple(date, name):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints, got {type(date).__name__}")
    if len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(date[i]).__name__}")

def _check_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _check_int(y, "y")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)

def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)

def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid_date(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d

def from_ordinal(n):
    _check_int(n, "n")
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    # Binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    rem = n - _days_before_year(y)  # 1-based day within year y
    # Find month
    md = (31, 28 + (1 if _is_leap(y) else 0), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    m = 1
    while rem > md[m - 1]:
        rem -= md[m - 1]
        m += 1
    d = rem
    return (y, m, d)

def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7

def add_days(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_valid_date(y, m, d)
    ord_n = to_ordinal(y, m, d) + n
    if ord_n < 1 or ord_n > 3652059:
        raise OverflowError(f"result out of range: ordinal {ord_n}")
    return from_ordinal(ord_n)

def add_months(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError(f"target year {ty} out of range 1..9999")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)

def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    w = (to_ordinal(iso_year, 1, 1) - 1) % 7  # weekday of Jan 1
    if w == 3 or (_is_leap(iso_year) and w == 2):
        return 53
    return 52

def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid_date(y, m, d)
    ord_date = to_ordinal(y, m, d)
    wd = (ord_date - 1) % 7  # Mon=0
    iso_wd = wd + 1  # Mon=1
    date_mon = ord_date - wd  # ordinal of Monday of this week
    # Monday of week 1 of ISO year y
    ord_jan4 = to_ordinal(y, 1, 4)
    wd_jan4 = (ord_jan4 - 1) % 7
    week1_mon = ord_jan4 - wd_jan4
    offset = date_mon - week1_mon
    week = offset // 7 + 1
    if week >= 1:
        w_y = iso_weeks_in_year(y)
        if week <= w_y:
            return (y, week, iso_wd)
        else:
            return (y + 1, 1, iso_wd)
    else:
        w_prev = iso_weeks_in_year(y - 1)
        return (y - 1, week + w_prev, iso_wd)

def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    # Compute ordinal of Monday of week 1
    ord_jan4 = to_ordinal(iso_year, 1, 4)
    wd_jan4 = (ord_jan4 - 1) % 7
    week1_mon = ord_jan4 - wd_jan4
    result = week1_mon + (week - 1) * 7 + (weekday - 1)
    if result < 1 or result > 3652059:
        raise OverflowError(f"result out of range: ordinal {result}")
    return from_ordinal(result)

# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_EXT_WK  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BAS_WK  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')
_RE_BAS_8   = re.compile(r'([0-9]{8})')

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    # Extended calendar: YYYY-MM-DD
    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError(f"day {d} out of range for {y}-{mo:02d}")
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD
    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= doy <= _days_in_year(y)):
            raise ValueError(f"day of year {doy} out of range")
        return from_ordinal(_days_before_year(y) + doy)

    # Extended week: YYYY-Www-D
    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date out of range: {s}")

    # Basic week: YYYYWwwD
    m = _RE_BAS_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date out of range: {s}")

    # Basic 8-digit: YYYYMMDD or YYYYDDD
    m = _RE_BAS_8.fullmatch(s)
    if m:
        s8 = m.group(1)
        y = int(s8[0:4])
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        # Try basic calendar first
        mo = int(s8[4:6])
        d = int(s8[6:8])
        if 1 <= mo <= 12 and 1 <= d <= _dim(y, mo):
            return (y, mo, d)
        # Try basic ordinal
        doy = int(s8[4:7])
        if 1 <= doy <= _days_in_year(y):
            return from_ordinal(_days_before_year(y) + doy)
        raise ValueError(f"invalid date: {s}")

    raise ValueError(f"unrecognized date format: {s!r}")

# ---------------------------------------------------------------------------
# format_date
# ---------------------------------------------------------------------------

def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _check_valid_date(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a str, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"
    else:
        raise ValueError(f"unknown form {form!r}")

# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def _add_months_internal(y, m, d, k):
    """Return (ty, tm, td) or None if target year out of range."""
    total = (y - 1) * 12 + (m - 1) + k
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        return None
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)

def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        r = diff(b, a)
        return (-r[0], -r[1], -r[2])

    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    # Upper bound for K: target year must be <= 9999
    max_k = 9999 * 12 - 1 - (ay - 1) * 12 - (am - 1)
    lo, hi = 0, max_k
    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _add_months_internal(ay, am, ad, mid)
        if shifted is not None and shifted <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_internal(ay, am, ad, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
