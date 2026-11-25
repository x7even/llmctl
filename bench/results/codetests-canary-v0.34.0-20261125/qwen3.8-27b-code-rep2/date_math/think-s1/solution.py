import re

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")

def _check_date_tuple(x, name):
    if type(x) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints, got {type(x).__name__}")
    if len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints, got length {len(x)}")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(v).__name__}")

def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    dim = days_in_month(y, m)
    if d < 1 or d > dim:
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m:02d}")

def _days_before_year(y):
    """Number of days in years 1 through y-1."""
    n = y - 1
    return n * 365 + n // 4 - n // 100 + n // 400

_MDAYS_COMMON = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MDAYS_LEAP   = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_BEFORE   = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)

def _month_day_from_doy(y, doy):
    """Convert 1-based day-of-year to (month, day)."""
    mdays = _MDAYS_LEAP if is_leap(y) else _MDAYS_COMMON
    for m in range(1, 13):
        if doy <= mdays[m - 1]:
            return (m, doy)
        doy -= mdays[m - 1]
    raise ValueError("internal error: invalid day of year")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    return _MDAYS_COMMON[m - 1]

def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    result = _days_before_year(y) + _CUM_BEFORE[m - 1]
    if m > 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        result += 1
    result += d
    return result

def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    m = n - 1  # 0-based
    # Estimate year
    y = m // 365 + 1
    while _days_before_year(y) > m:
        y -= 1
    while _days_before_year(y + 1) <= m:
        y += 1
    doy = m - _days_before_year(y) + 1
    month, day = _month_day_from_doy(y, doy)
    return (y, month, day)

def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7

def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError(f"result ordinal {ord_val} out of range 1..3652059")
    return from_ordinal(ord_val)

def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0:
        raise OverflowError("result before year 1")
    if total >= 9999 * 12:
        raise OverflowError("result after year 9999")
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = min(d, days_in_month(ty, tm))
    return (ty, tm, td)

def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if wd == 3:
        return 53
    if wd == 2 and (iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0)):
        return 53
    return 52

def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    iso_wd = wd + 1
    jan4_ord = to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    week_num = (ord_val - week1_monday) // 7 + 1
    if week_num < 1:
        iso_y = y - 1
        return (iso_y, iso_weeks_in_year(iso_y), iso_wd)
    elif week_num > iso_weeks_in_year(y):
        return (y + 1, 1, iso_wd)
    else:
        return (y, week_num, iso_wd)

def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    n_weeks = iso_weeks_in_year(iso_year)
    if week < 1 or week > n_weeks:
        raise ValueError(f"week {week} out of range 1..{n_weeks} for ISO year {iso_year}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target = week1_monday + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError(f"result ordinal {target} out of range 1..3652059")
    return from_ordinal(target)

# ---------------------------------------------------------------------------
# parse / format_date
# ---------------------------------------------------------------------------

_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_WK_EXT  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_BAS  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    # Calendar extended: YYYY-MM-DD
    m = _RE_CAL_EXT.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range 1..9999")
        _check_date_range(y, mo, d)
        return (y, mo, d)

    # Ordinal extended: YYYY-DDD
    m = _RE_ORD_EXT.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        month, day = _month_day_from_doy(y, doy)
        return (y, month, day)

    # Week extended: YYYY-Www-D
    m = _RE_WK_EXT.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"ISO year {y} out of range 1..9999")
        n_weeks = iso_weeks_in_year(y)
        if wk < 1 or wk > n_weeks:
            raise ValueError(f"week {wk} out of range 1..{n_weeks}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date out of range 0001-01-01..9999-12-31")

    # Calendar basic: YYYYMMDD
    m = _RE_CAL_BAS.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range 1..9999")
        _check_date_range(y, mo, d)
        return (y, mo, d)

    # Ordinal basic: YYYYDDD
    m = _RE_ORD_BAS.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        month, day = _month_day_from_doy(y, doy)
        return (y, month, day)

    # Week basic: YYYYWwwD
    m = _RE_WK_BAS.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"ISO year {y} out of range 1..9999")
        n_weeks = iso_weeks_in_year(y)
        if wk < 1 or wk > n_weeks:
            raise ValueError(f"week {wk} out of range 1..{n_weeks}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date out of range 0001-01-01..9999-12-31")

    raise ValueError(f"unrecognized date format: {s!r}")

def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)

    if type(form) is not str:
        raise ValueError(f"form must be a string, got {type(form).__name__}")
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week', got {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_d = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_d}"

# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ya, ma, da = a
    yb, mb, db = b
    _check_date_range(ya, ma, da)
    _check_date_range(yb, mb, db)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    def _shift_le(K):
        total = (ya - 1) * 12 + (ma - 1) + K
        if total < 0:
            return True
        ty = total // 12 + 1
        if ty > 9999:
            return False
        tm = total % 12 + 1
        td = min(da, days_in_month(ty, tm))
        return (ty, tm, td) <= b

    K = (yb - ya) * 12 + (mb - ma)
    while K > 0 and not _shift_le(K):
        K -= 1
    while _shift_le(K + 1):
        K += 1

    years, months = divmod(K, 12)
    total = (ya - 1) * 12 + (ma - 1) + K
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = min(da, days_in_month(ty, tm))
    days = to_ordinal(yb, mb, db) - to_ordinal(ty, tm, td)
    return (years, months, days)
