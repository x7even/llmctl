import re

# ---------------------------------------------------------------------------
# Internal helpers (no public API)
# ---------------------------------------------------------------------------

_CUM = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
_CUM_LEAP = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
_MAX_ORD = 3652059  # ordinal of (9999, 12, 31)
_MAX_MONTH_IDX = 9999 * 12 - 1  # 119987


def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_raw(y, m):
    if m == 2:
        return 29 if _is_leap_raw(y) else 28
    return 31 if m in (1, 3, 5, 7, 8, 10, 12) else 30


def _jan1_ord(y):
    return (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400 + 1


def _to_ord_raw(y, m, d):
    o = _jan1_ord(y) + _CUM[m - 1] + d - 1
    if m > 2 and _is_leap_raw(y):
        o += 1
    return o


def _year_from_ord(o):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if _jan1_ord(mid) <= o:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _from_ord_raw(n):
    y = _year_from_ord(n)
    doy = n - _jan1_ord(y) + 1
    cum = _CUM_LEAP if _is_leap_raw(y) else _CUM
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if cum[mid - 1] < doy:
            lo = mid
        else:
            hi = mid - 1
    m = lo
    d = doy - cum[m - 1]
    return (y, m, d)


def _wd_raw(y, m, d):
    return (_to_ord_raw(y, m, d) - 1) % 7


def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total > _MAX_MONTH_IDX:
        raise OverflowError("month index out of range")
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim_raw(ny, nm) else _dim_raw(ny, nm)
    return (ny, nm, nd)


# ---------------------------------------------------------------------------
# Type / range validators
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


def _chk_str(x, name):
    if type(x) is not str:
        raise TypeError(f"{name} must be a str, got {type(x).__name__}")


def _validate(y, m, d):
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if not 1 <= m <= 12:
        raise ValueError(f"month {m} out of range 1..12")
    if not 1 <= d <= _dim_raw(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim_raw(y, m)}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _chk_int(y, 'y')
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if not 1 <= m <= 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim_raw(y, m)


def to_ordinal(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _validate(y, m, d)
    return _to_ord_raw(y, m, d)


def from_ordinal(n):
    _chk_int(n, 'n')
    if not 1 <= n <= _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ord_raw(n)


def weekday(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _validate(y, m, d)
    return _wd_raw(y, m, d)


def add_days(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _validate(y, m, d)
    o = _to_ord_raw(y, m, d) + n
    if o < 1 or o > _MAX_ORD:
        raise OverflowError(f"result ordinal {o} out of range 1..{_MAX_ORD}")
    return _from_ord_raw(o)


def add_months(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _validate(y, m, d)
    return _add_months_raw(y, m, d, n)


def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, 'iso_year')
    if not 1 <= iso_year <= 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = _wd_raw(iso_year, 1, 1)
    if wd == 3:
        return 53
    if wd == 2 and _is_leap_raw(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _validate(y, m, d)
    o = _to_ord_raw(y, m, d)
    wd = (o - 1) % 7
    monday = o - wd
    thursday = monday + 3
    iso_y = _year_from_ord(thursday)
    jan4_o = _jan1_ord(iso_y) + 3
    jan4_wd = (jan4_o - 1) % 7
    monday_w1 = jan4_o - jan4_wd
    week = (monday - monday_w1) // 7 + 1
    return (iso_y, week, wd + 1)


def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, 'iso_year')
    _chk_int(week, 'week')
    _chk_int(weekday, 'weekday')
    if not 1 <= iso_year <= 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    mw = iso_weeks_in_year(iso_year)
    if not 1 <= week <= mw:
        raise ValueError(f"week {week} out of range 1..{mw}")
    if not 1 <= weekday <= 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_o = _jan1_ord(iso_year) + 3
    jan4_wd = (jan4_o - 1) % 7
    monday_w1 = jan4_o - jan4_wd
    target = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError(f"result ordinal {target} out of range 1..{_MAX_ORD}")
    return _from_ord_raw(target)


# ---------------------------------------------------------------------------
# parse / format_date
# ---------------------------------------------------------------------------

_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BAS  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def parse(s):
    _chk_str(s, 's')

    m = _RE_CAL_EXT.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y == 0:
            raise ValueError("year 0000 is not supported")
        _validate(y, mo, d)
        return (y, mo, d)

    m = _RE_CAL_BAS.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y == 0:
            raise ValueError("year 0000 is not supported")
        _validate(y, mo, d)
        return (y, mo, d)

    m = _RE_ORD_EXT.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y == 0:
            raise ValueError("year 0000 is not supported")
        max_doy = 366 if _is_leap_raw(y) else 365
        if not 1 <= doy <= max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ord_raw(_jan1_ord(y) + doy - 1)

    m = _RE_ORD_BAS.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y == 0:
            raise ValueError("year 0000 is not supported")
        max_doy = 366 if _is_leap_raw(y) else 365
        if not 1 <= doy <= max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ord_raw(_jan1_ord(y) + doy - 1)

    m = _RE_WK_EXT.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y == 0:
            raise ValueError("year 0000 is not supported")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("week date out of supported range")

    m = _RE_WK_BAS.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y == 0:
            raise ValueError("year 0000 is not supported")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("week date out of supported range")

    raise ValueError(f"unrecognized date string: {s!r}")


def format_date(date, form):
    _chk_date(date, 'date')
    y, m, d = date
    _validate(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a str, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = _to_ord_raw(y, m, d) - _jan1_ord(y) + 1
        return f"{y:04d}-{doy:03d}"
    if form == 'week':
        iy, wk, wd = iso_week(y, m, d)
        return f"{iy:04d}-W{wk:02d}-{wd}"
    raise ValueError(f"unknown form {form!r}")


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def diff(a, b):
    _chk_date(a, 'a')
    _chk_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _validate(ay, am, ad)
    _validate(by, bm, bd)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: binary search for largest K >= 0 with shift(a, K) <= b
    lo, hi = 0, (by - ay) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        try:
            shifted = _add_months_raw(ay, am, ad, mid)
        except OverflowError:
            hi = mid - 1
            continue
        if shifted <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_raw(ay, am, ad, K)
    days = _to_ord_raw(by, bm, bd) - _to_ord_raw(*shifted)
    return (years, months, days)