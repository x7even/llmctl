import re

# ---------------------------------------------------------------------------
# Internal helpers (no type/range checking; callers guarantee validity)
# ---------------------------------------------------------------------------

_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MAX_ORD = 3652059  # ordinal of (9999,12,31)


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    return _MDAYS[m - 1]


def _to_ordinal(y, m, d):
    yy = y - 1
    leaps = yy // 4 - yy // 100 + yy // 400
    days = yy * 365 + leaps
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NONLEAP
    return days + cum[m - 1] + d


def _from_ordinal(n):
    y = 1 + (n - 1) * 400 // 146097
    while y > 1 and _to_ordinal(y, 1, 1) > n:
        y -= 1
    while y < 9999 and _to_ordinal(y + 1, 1, 1) <= n:
        y += 1
    doy = n - _to_ordinal(y, 1, 1) + 1
    md = list(_MDAYS)
    if _is_leap(y):
        md[1] = 29
    m = 1
    while m <= 12 and doy > md[m - 1]:
        doy -= md[m - 1]
        m += 1
    return (y, m, doy)


def _weekday(y, m, d):
    return (_to_ordinal(y, m, d) - 1) % 7


def _iso_weeks_in_year(y):
    wd = _weekday(y, 1, 1)
    if wd == 3:
        return 53
    if _is_leap(y) and wd == 2:
        return 53
    return 52


def _iso_week(y, m, d):
    ord_ = _to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7  # Mon=0
    mon_ord = ord_ - wd
    thu_ord = mon_ord + 3
    iso_y = _from_ordinal(thu_ord)[0]
    jan4_ord = _to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    week = (mon_ord - mon_w1) // 7 + 1
    return (iso_y, week, wd + 1)


def _from_iso_week(iso_y, week, wd):
    jan4_ord = _to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (wd - 1)
    return _from_ordinal(target)


def _add_months_raw(y, m, d, n):
    """Return (ty, tm, td) or None if out of year range."""
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        return None
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)


def _shift_le(a, K, b_ord):
    r = _add_months_raw(a[0], a[1], a[2], K)
    if r is None:
        return False
    return _to_ordinal(r[0], r[1], r[2]) <= b_ord


# ---------------------------------------------------------------------------
# Type / range validation helpers
# ---------------------------------------------------------------------------

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _chk_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i in range(3):
        if type(x[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(x[i]).__name__}")


def _chk_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError(f"day {d} out of range for {y:04d}-{m:02d}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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
    _chk_valid_date(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    _chk_int(n, "n")
    if not (1 <= n <= _MAX_ORD):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ordinal(n)


def weekday(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_valid_date(y, m, d)
    return _weekday(y, m, d)


def add_days(date, n):
    _chk_date(date, "date")
    _chk_int(n, "n")
    y, m, d = date
    _chk_valid_date(y, m, d)
    target = _to_ordinal(y, m, d) + n
    if target < 1 or target > _MAX_ORD:
        raise OverflowError(f"result ordinal {target} out of range 1..{_MAX_ORD}")
    return _from_ordinal(target)


def add_months(date, n):
    _chk_date(date, "date")
    _chk_int(n, "n")
    y, m, d = date
    _chk_valid_date(y, m, d)
    r = _add_months_raw(y, m, d, n)
    if r is None:
        raise OverflowError("result year out of range 1..9999")
    return r


def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, "iso_year")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"ISO year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_valid_date(y, m, d)
    return _iso_week(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, "iso_year")
    _chk_int(week, "week")
    _chk_int(weekday, "weekday")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"ISO year {iso_year} out of range 1..9999")
    max_w = _iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_w):
        raise ValueError(f"week {week} out of range 1..{max_w}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    result = _from_iso_week(iso_year, week, weekday)
    ry, rm, rd = result
    if ry < 1 or ry > 9999:
        raise OverflowError("result date out of range")
    return result


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    # Extended calendar: YYYY-MM-DD
    m = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        _chk_valid_date(y, mo, d)
        return (y, mo, d)

    # Extended week: YYYY-Www-D
    m = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
    if m:
        y, w, wd = int(m[1]), int(m[2]), int(m[3])
        return _parse_week(y, w, wd)

    # Basic calendar: YYYYMMDD
    m = re.fullmatch(r'([0-9]{4})([0-9]{2})([0-9]{2})', s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        _chk_valid_date(y, mo, d)
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD
    m = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
    if m:
        y, doy = int(m[1]), int(m[2])
        return _parse_ordinal(y, doy)

    # Basic week: YYYYWwwD
    m = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
    if m:
        y, w, wd = int(m[1]), int(m[2]), int(m[3])
        return _parse_week(y, w, wd)

    # Basic ordinal: YYYYDDD
    m = re.fullmatch(r'([0-9]{4})([0-9]{3})', s)
    if m:
        y, doy = int(m[1]), int(m[2])
        return _parse_ordinal(y, doy)

    raise ValueError(f"invalid date string: {s!r}")


def _parse_week(y, w, wd):
    if not (1 <= y <= 9999):
        raise ValueError(f"ISO year {y} out of range 1..9999")
    max_w = _iso_weeks_in_year(y)
    if not (1 <= w <= max_w):
        raise ValueError(f"week {w} out of range 1..{max_w}")
    if not (1 <= wd <= 7):
        raise ValueError(f"weekday {wd} out of range 1..7")
    result = _from_iso_week(y, w, wd)
    if result[0] < 1 or result[0] > 9999:
        raise ValueError("date out of supported range")
    return result


def _parse_ordinal(y, doy):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    max_doy = 366 if _is_leap(y) else 365
    if not (1 <= doy <= max_doy):
        raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
    year_start = _to_ordinal(y, 1, 1)
    return _from_ordinal(year_start + doy - 1)


def format_date(date, form):
    _chk_date(date, "date")
    y, m, d = date
    _chk_valid_date(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, iday = _iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iday:01d}"


def diff(a, b):
    _chk_date(a, "a")
    _chk_date(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _chk_valid_date(ay, am, ad)
    _chk_valid_date(by, bm, bd)

    a_ord = _to_ordinal(ay, am, ad)
    b_ord = _to_ordinal(by, bm, bd)

    if a_ord <= b_ord:
        # Binary search for largest K >= 0 with add_months(a, K) <= b
        lo, hi = 0, 120000
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _shift_le(a, mid, b_ord):
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _add_months_raw(ay, am, ad, K)
        days = b_ord - _to_ordinal(shifted[0], shifted[1], shifted[2])
        return (years, months, days)
    else:
        y, m, d = diff(b, a)
        return (-y, -m, -d)