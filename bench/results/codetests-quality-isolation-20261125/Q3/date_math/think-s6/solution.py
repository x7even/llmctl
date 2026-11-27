import re

# ---------------------------------------------------------------------------
# Internal helpers (no type/range checking – callers must validate first)
# ---------------------------------------------------------------------------

def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _dim_raw(y, m):
    if m == 2:
        return 29 if _is_leap_raw(y) else 28
    return (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[m - 1]

def _F(y):
    """Total number of days in years 1..y (i.e. days before year y+1)."""
    return y * 365 + y // 4 - y // 100 + y // 400

def _to_ord_raw(y, m, d):
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    return _F(y - 1) + cum[m - 1] + (1 if _is_leap_raw(y) and m > 2 else 0) + d

def _from_ord_raw(n):
    a = n - 1
    y = a // 365 + 1
    while y > 1 and _F(y - 1) > a:
        y -= 1
    while _F(y) <= a:
        y += 1
    doy = a - _F(y - 1) + 1
    if _is_leap_raw(y):
        cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
    else:
        cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    m = 1
    while m < 12 and cum[m] < doy:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)

def _weekday_raw(y, m, d):
    return (_to_ord_raw(y, m, d) - 1) % 7

def _add_months_raw(date, n):
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim_raw(ny, nm) else _dim_raw(ny, nm)
    return (ny, nm, nd)

def _iso_weeks_in_year_raw(iso_year):
    jan1_wd = _F(iso_year - 1) % 7  # 0=Mon … 6=Sun
    if jan1_wd == 3:
        return 53
    if _is_leap_raw(iso_year) and jan1_wd == 2:
        return 53
    return 52

def _iso_week_raw(y, m, d):
    ord_val = _to_ord_raw(y, m, d)
    wd = (ord_val - 1) % 7
    iso_wd = wd + 1
    ord_jan4 = _to_ord_raw(y, 1, 4)
    wd_jan4 = (ord_jan4 - 1) % 7
    mon_week1 = ord_jan4 - wd_jan4
    days_from = ord_val - mon_week1
    iso_w = days_from // 7 + 1
    if iso_w < 1:
        iso_y = y - 1
        iso_w = _iso_weeks_in_year_raw(iso_y)
    elif iso_w > _iso_weeks_in_year_raw(y):
        iso_y = y + 1
        iso_w = 1
    else:
        iso_y = y
    return (iso_y, iso_w, iso_wd)

def _from_iso_week_raw(iso_year, week, weekday):
    ord_jan4 = _to_ord_raw(iso_year, 1, 4)
    wd_jan4 = (ord_jan4 - 1) % 7
    mon_week1 = ord_jan4 - wd_jan4
    target = mon_week1 + (week - 1) * 7 + (weekday - 1)
    return _from_ord_raw(target)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_MAX_ORD = 3652059  # ordinal of (9999, 12, 31)

def _check_int(val, name):
    if type(val) is not int:
        raise TypeError(f"{name} must be int, got {type(val).__name__}")

def _check_date_tuple(val, name):
    if type(val) is not tuple or len(val) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints, got {type(val).__name__}")
    for i, v in enumerate(val):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(v).__name__}")

def _check_year(y):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")

def _check_month(m):
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")

def _check_valid_date(y, m, d):
    _check_year(y)
    _check_month(m)
    dim = _dim_raw(y, m)
    if d < 1 or d > dim:
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m}")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _check_int(y, "y")
    _check_year(y)
    return _is_leap_raw(y)

def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_year(y)
    _check_month(m)
    return _dim_raw(y, m)

def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid_date(y, m, d)
    return _to_ord_raw(y, m, d)

def from_ordinal(n):
    _check_int(n, "n")
    if n < 1 or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ord_raw(n)

def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid_date(y, m, d)
    return _weekday_raw(y, m, d)

def add_days(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_valid_date(y, m, d)
    ord_val = _to_ord_raw(y, m, d) + n
    if ord_val < 1 or ord_val > _MAX_ORD:
        raise OverflowError(f"result ordinal {ord_val} out of range 1..{_MAX_ORD}")
    return _from_ord_raw(ord_val)

def add_months(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError(f"target year {ny} out of range 1..9999")
    nd = d if d <= _dim_raw(ny, nm) else _dim_raw(ny, nm)
    return (ny, nm, nd)

def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year_raw(iso_year)

def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid_date(y, m, d)
    return _iso_week_raw(y, m, d)

def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = _iso_weeks_in_year_raw(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw} for ISO year {iso_year}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    result = _from_iso_week_raw(iso_year, week, weekday)
    if result < (1, 1, 1) or result > (9999, 12, 31):
        raise OverflowError(f"result {result} out of range (1,1,1)..(9999,12,31)")
    return result

# ---------------------------------------------------------------------------
# parse / format_date
# ---------------------------------------------------------------------------

_RE_CAL_EXT = re.compile(r'\A([0-9]{4})-([0-9]{2})-([0-9]{2})\Z')
_RE_CAL_BAS = re.compile(r'\A([0-9]{4})([0-9]{2})([0-9]{2})\Z')
_RE_ORD_EXT = re.compile(r'\A([0-9]{4})-([0-9]{3})\Z')
_RE_ORD_BAS = re.compile(r'\A([0-9]{4})([0-9]{3})\Z')
_RE_WK_EXT  = re.compile(r'\A([0-9]{4})-W([0-9]{2})-([0-9])\Z')
_RE_WK_BAS  = re.compile(r'\A([0-9]{4})W([0-9]{2})([0-9])\Z')

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    # --- extended calendar: YYYY-MM-DD ---
    mt = _RE_CAL_EXT.match(s)
    if mt:
        y, mo, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _dim_raw(y, mo):
            raise ValueError(f"day {d} out of range for {y}-{mo:02d}")
        return (y, mo, d)

    # --- extended ordinal: YYYY-DDD ---
    mt = _RE_ORD_EXT.match(s)
    if mt:
        y, doy = int(mt.group(1)), int(mt.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day-of-year {doy} out of range 1..{max_doy}")
        return _from_ord_raw(_F(y - 1) + doy)

    # --- extended week: YYYY-Www-D ---
    mt = _RE_WK_EXT.match(s)
    if mt:
        y, wk, wd = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        nw = _iso_weeks_in_year_raw(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        result = _from_iso_week_raw(y, wk, wd)
        if result < (1, 1, 1) or result > (9999, 12, 31):
            raise ValueError(f"date {result} out of supported range")
        return result

    # --- basic calendar: YYYYMMDD ---
    mt = _RE_CAL_BAS.match(s)
    if mt:
        y, mo, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _dim_raw(y, mo):
            raise ValueError(f"day {d} out of range for {y}-{mo:02d}")
        return (y, mo, d)

    # --- basic ordinal: YYYYDDD ---
    mt = _RE_ORD_BAS.match(s)
    if mt:
        y, doy = int(mt.group(1)), int(mt.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day-of-year {doy} out of range 1..{max_doy}")
        return _from_ord_raw(_F(y - 1) + doy)

    # --- basic week: YYYYWwwD ---
    mt = _RE_WK_BAS.match(s)
    if mt:
        y, wk, wd = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        nw = _iso_weeks_in_year_raw(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        result = _from_iso_week_raw(y, wk, wd)
        if result < (1, 1, 1) or result > (9999, 12, 31):
            raise ValueError(f"date {result} out of supported range")
        return result

    raise ValueError(f"unrecognised date string: {s!r}")

def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _check_valid_date(y, m, d)

    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week', got {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ord_raw(y, m, d) - _F(y - 1)
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_d = _iso_week_raw(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_d}"

# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a < b:
        # Binary search for largest K >= 0 with _add_months_raw(a, K) <= b
        max_months = (by - 1) * 12 + (bm - 1) - ((ay - 1) * 12 + (am - 1))
        lo, hi = 0, max_months
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _add_months_raw(a, mid) <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _add_months_raw(a, K)
        days = _to_ord_raw(by, bm, bd) - _to_ord_raw(*shifted)
        return (years, months, days)
    else:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
