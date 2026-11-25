import re

# ---------------------------------------------------------------------------
# Internal helpers (assume valid inputs; no checking)
# ---------------------------------------------------------------------------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31

_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP    = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)

def _to_ord(y, m, d):
    t = y - 1
    dby = 365 * t + t // 4 - t // 100 + t // 400
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NONLEAP
    return dby + cum[m - 1] + d

def _from_ord(n):
    n0 = n - 1
    t = n0 * 400 // 146097
    while 365 * t + t // 4 - t // 100 + t // 400 > n0:
        t -= 1
    while 365 * (t + 1) + (t + 1) // 4 - (t + 1) // 100 + (t + 1) // 400 <= n0:
        t += 1
    y = t + 1
    doy = n0 - (365 * t + t // 4 - t // 100 + t // 400)
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NONLEAP
    m = 1
    while m <= 12 and doy >= cum[m]:
        m += 1
    d = doy - cum[m - 1] + 1
    return (y, m, d)

def _weekday(y, m, d):
    return (_to_ord(y, m, d) - 1) % 7

def _iso_weeks(y):
    w = _weekday(y, 1, 1)
    if w == 3:
        return 53
    if _is_leap(y) and w == 2:
        return 53
    return 52

def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)

def _iso_week(y, m, d):
    ov = _to_ord(y, m, d)
    wd = (ov - 1) % 7
    iso_wd = wd + 1
    j4 = _to_ord(y, 1, 4)
    j4w = (j4 - 1) % 7
    mon_w1 = j4 - j4w
    mon_cur = ov - wd
    wk = (mon_cur - mon_w1) // 7 + 1
    if wk <= 0:
        iy = y - 1
        iw = _iso_weeks(iy) + wk
    elif wk > _iso_weeks(y):
        iy = y + 1
        iw = 1
    else:
        iy = y
        iw = wk
    return (iy, iw, iso_wd)

def _from_iso_week_raw(iy, wk, wd):
    j4 = _to_ord(iy, 1, 4)
    j4w = (j4 - 1) % 7
    mon_w1 = j4 - j4w
    target = mon_w1 + (wk - 1) * 7 + (wd - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return _from_ord(target)

# ---------------------------------------------------------------------------
# Type / range checking helpers
# ---------------------------------------------------------------------------

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")

def _chk_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(v).__name__}")

def _chk_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim}")

# ---------------------------------------------------------------------------
# Regexes for parse (compiled once)
# ---------------------------------------------------------------------------

_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT  = re.compile(r'([0-9]{4})-W([0-9]{2})([0-9])')
_RE_WK_BAS  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _chk_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)

def days_in_month(y, m):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)

def to_ordinal(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_valid_date(y, m, d)
    return _to_ord(y, m, d)

def from_ordinal(n):
    _chk_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ord(n)

def weekday(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_valid_date(y, m, d)
    return _weekday(y, m, d)

def add_days(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _chk_valid_date(y, m, d)
    ov = _to_ord(y, m, d) + n
    if ov < 1 or ov > 3652059:
        raise OverflowError("result out of range")
    return _from_ord(ov)

def add_months(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _chk_valid_date(y, m, d)
    ty, tm, td = _add_months_raw(y, m, d, n)
    if not (1 <= ty <= 9999):
        raise OverflowError(f"target year {ty} out of range")
    return (ty, tm, td)

def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks(iso_year)

def iso_week(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_valid_date(y, m, d)
    return _iso_week(y, m, d)

def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, 'iso_year')
    _chk_int(week, 'week')
    _chk_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = _iso_weeks(iso_year)
    if not (1 <= week <= nw):
        raise ValueError(f"week {week} out of range 1..{nw}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    return _from_iso_week_raw(iso_year, week, weekday)

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    # Extended calendar: YYYY-MM-DD
    mo = _RE_CAL_EXT.fullmatch(s)
    if mo is not None:
        y, m, d = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= m <= 12):
            raise ValueError(f"month {m} out of range")
        if not (1 <= d <= _dim(y, m)):
            raise ValueError(f"day {d} out of range")
        return (y, m, d)

    # Basic calendar: YYYYMMDD
    mo = _RE_CAL_BAS.fullmatch(s)
    if mo is not None:
        y, m, d = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= m <= 12):
            raise ValueError(f"month {m} out of range")
        if not (1 <= d <= _dim(y, m)):
            raise ValueError(f"day {d} out of range")
        return (y, m, d)

    # Extended ordinal: YYYY-DDD
    mo = _RE_ORD_EXT.fullmatch(s)
    if mo is not None:
        y, doy = int(mo.group(1)), int(mo.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range")
        return _from_ord(_to_ord(y, 1, 1) + doy - 1)

    # Basic ordinal: YYYYDDD
    mo = _RE_ORD_BAS.fullmatch(s)
    if mo is not None:
        y, doy = int(mo.group(1)), int(mo.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range")
        return _from_ord(_to_ord(y, 1, 1) + doy - 1)

    # Extended week: YYYY-Www-D
    mo = _RE_WK_EXT.fullmatch(s)
    if mo is not None:
        iy, wk, wd = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
        if not (1 <= iy <= 9999):
            raise ValueError(f"iso_year {iy} out of range")
        nw = _iso_weeks(iy)
        if not (1 <= wk <= nw):
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return _from_iso_week_raw(iy, wk, wd)
        except OverflowError:
            raise ValueError("week date out of supported range")

    # Basic week: YYYYWwwD
    mo = _RE_WK_BAS.fullmatch(s)
    if mo is not None:
        iy, wk, wd = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
        if not (1 <= iy <= 9999):
            raise ValueError(f"iso_year {iy} out of range")
        nw = _iso_weeks(iy)
        if not (1 <= wk <= nw):
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return _from_iso_week_raw(iy, wk, wd)
        except OverflowError:
            raise ValueError("week date out of supported range")

    raise ValueError(f"unrecognized date format: {s!r}")

def format_date(date, form):
    _chk_date(date, 'date')
    y, m, d = date
    _chk_valid_date(y, m, d)

    if form != 'calendar' and form != 'ordinal' and form != 'week':
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week', got {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ord(y, m, d) - _to_ord(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iy, wk, wd = _iso_week(y, m, d)
        return f"{iy:04d}-W{wk:02d}-{wd}"

def diff(a, b):
    _chk_date(a, 'a')
    _chk_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _chk_valid_date(ay, am, ad)
    _chk_valid_date(by, bm, bd)

    if _to_ord(ay, am, ad) > _to_ord(by, bm, bd):
        years, months, days = diff(b, a)
        return (-years, -months, -days)

    # a <= b
    a_mi = (ay - 1) * 12 + (am - 1)
    b_mi = (by - 1) * 12 + (bm - 1)
    K0 = b_mi - a_mi  # >= 0

    ty, tm, td = _add_months_raw(ay, am, ad, K0)
    if (ty, tm, td) <= (by, bm, bd):
        K = K0
    else:
        K = K0 - 1

    years, months = divmod(K, 12)
    shifted = _add_months_raw(ay, am, ad, K)
    days = _to_ord(by, bm, bd) - _to_ord(shifted[0], shifted[1], shifted[2])

    return (years, months, days)