import re

# ---------------------------------------------------------------------------
# Internal helpers (no type/range checking; assume valid inputs)
# ---------------------------------------------------------------------------

def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _days_in_month_raw(y, m):
    if m == 2:
        return 29 if _is_leap_raw(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31

def _days_before_month(y, m):
    """Number of days in months 1..m-1 of year y."""
    if m <= 2:
        return 31 * (m - 1)
    feb_adj = 2 if _is_leap_raw(y) else 3
    thirty = (1 if m > 4 else 0) + (1 if m > 6 else 0) + (1 if m > 9 else 0) + (1 if m > 11 else 0)
    return 31 * (m - 1) - feb_adj - thirty

def _to_ordinal_raw(y, m, d):
    yp1 = y - 1
    return 365 * yp1 + yp1 // 4 - yp1 // 100 + yp1 // 400 + _days_before_month(y, m) + d

def _from_ordinal_raw(n):
    """Invert ordinal (1-based) to (y, m, d). Assumes 1 <= n <= 3652059."""
    # Binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        yp1 = mid - 1
        if 365 * yp1 + yp1 // 4 - yp1 // 100 + yp1 // 400 + 1 <= n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    yp1 = y - 1
    start = 365 * yp1 + yp1 // 4 - yp1 // 100 + yp1 // 400 + 1
    doy = n - start + 1  # 1-based day-of-year
    leap = _is_leap_raw(y)
    md = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    m = 1
    while m <= 12 and doy > md[m - 1]:
        doy -= md[m - 1]
        m += 1
    return (y, m, doy)

# ---------------------------------------------------------------------------
# Type / range checking helpers
# ---------------------------------------------------------------------------

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")

def _check_date_tuple(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(date[i]).__name__}")

def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _days_in_month_raw(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m:02d}")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _check_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)

def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _days_in_month_raw(y, m)

def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _to_ordinal_raw(y, m, d)

def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ordinal_raw(n)

def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (_to_ordinal_raw(y, m, d) - 1) % 7

def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    new_ord = _to_ordinal_raw(y, m, d) + n
    if new_ord < 1 or new_ord > 3652059:
        raise OverflowError("result out of supported range")
    return _from_ordinal_raw(new_ord)

def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if not (1 <= new_y <= 9999):
        raise OverflowError("result out of supported range")
    new_d = min(d, _days_in_month_raw(new_y, new_m))
    return (new_y, new_m, new_d)

def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = (_to_ordinal_raw(iso_year, 1, 1) - 1) % 7  # 0=Mon
    if wd == 3 or (_is_leap_raw(iso_year) and wd == 2):
        return 53
    return 52

def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ordinal = _to_ordinal_raw(y, m, d)
    weekday_0 = (ordinal - 1) % 7
    iso_weekday = weekday_0 + 1
    monday_of_week = ordinal - weekday_0
    thursday_of_week = monday_of_week + 3
    iso_year = _from_ordinal_raw(thursday_of_week)[0]
    ord_jan4 = _to_ordinal_raw(iso_year, 1, 4)
    wd_jan4 = (ord_jan4 - 1) % 7
    monday_of_week1 = ord_jan4 - wd_jan4
    iso_week_num = (monday_of_week - monday_of_week1) // 7 + 1
    return (iso_year, iso_week_num, iso_weekday)

def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    ord_jan4 = _to_ordinal_raw(iso_year, 1, 4)
    wd_jan4 = (ord_jan4 - 1) % 7
    monday_of_week1 = ord_jan4 - wd_jan4
    target = monday_of_week1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of supported range")
    return _from_ordinal_raw(target)

# ---------------------------------------------------------------------------
# parse / format_date
# ---------------------------------------------------------------------------

_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WK  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BAS_WK  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    # Extended calendar: YYYY-MM-DD (10 chars)
    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not allowed")
        _check_date_range(y, mo, d)
        return (y, mo, d)

    # Basic calendar: YYYYMMDD (8 digits)
    m = _RE_BAS_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not allowed")
        _check_date_range(y, mo, d)
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD (8 chars)
    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year 0000 is not allowed")
        if doy < 1:
            raise ValueError("day of year 000 is not allowed")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ordinal_raw(_to_ordinal_raw(y, 1, 1) + doy - 1)

    # Basic ordinal: YYYYDDD (7 digits)
    m = _RE_BAS_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year 0000 is not allowed")
        if doy < 1:
            raise ValueError("day of year 000 is not allowed")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ordinal_raw(_to_ordinal_raw(y, 1, 1) + doy - 1)

    # Extended week: YYYY-Www-D (11 chars)
    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not allowed")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("week date out of supported range")

    # Basic week: YYYYWwwD (8 chars)
    m = _RE_BAS_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not allowed")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("week date out of supported range")

    raise ValueError(f"invalid date string: {s!r}")

def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a string, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal_raw(y, m, d) - _to_ordinal_raw(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"
    else:
        raise ValueError(f"invalid form: {form!r}")

# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    y1, m1, d1 = a
    y2, m2, d2 = b
    _check_date_range(y1, m1, d1)
    _check_date_range(y2, m2, d2)

    if a > b:
        r = diff(b, a)
        return (-r[0], -r[1], -r[2])

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    a_mi = (y1 - 1) * 12 + (m1 - 1)
    b_mi = (y2 - 1) * 12 + (m2 - 1)
    hi = b_mi - a_month_idx if False else b_mi - a_mi  # b_mi - a_mi
    if hi < 0:
        hi = 0

    def _shift(k):
        total = a_mi + k
        ny = total // 12 + 1
        nm = total % 12 + 1
        nd = min(d1, _days_in_month_raw(ny, nm))
        return (ny, nm, nd)

    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift(mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _shift(K)
    days = _to_ordinal_raw(y2, m2, d2) - _to_ordinal_raw(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
