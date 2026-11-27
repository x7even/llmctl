import re

# ---------------------------------------------------------------------------
# Internal helpers (no public API)
# ---------------------------------------------------------------------------

_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_NL = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORD = 3652059  # ordinal of (9999,12,31)


def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_raw(y, m):
    if m == 2:
        return 29 if _is_leap_raw(y) else 28
    return _MDAYS[m - 1]


def _days_before_month(y, m):
    s = _CUM_NL[m - 1]
    if m > 2 and _is_leap_raw(y):
        s += 1
    return s


def _to_ord(y, m, d):
    """Internal: assumes valid date. Returns 1-based ordinal."""
    n = y - 1
    days = n * 365 + n // 4 - n // 100 + n // 400
    days += _days_before_month(y, m) + d
    return days


def _from_ord(n):
    """Internal: assumes 1 <= n <= _MAX_ORD. Returns (y, m, d)."""
    # Estimate year
    y = (n * 400) // 146097 + 1
    # Adjust (at most a couple of steps)
    while y > 1:
        prev = (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
        if prev >= n:
            y -= 1
        else:
            break
    while y < 9999:
        cur = y * 365 + y // 4 - y // 100 + y // 400
        if cur < n:
            y += 1
        else:
            break

    prev = (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    doy = n - prev  # 1-based day of year

    if _is_leap_raw(y):
        cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
    else:
        cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)

    m = 1
    while m < 12 and cum[m] < doy:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"expected int for {name}, got {type(x).__name__}")


def _check_date_tuple(date, name):
    if type(date) is not tuple:
        raise TypeError(f"expected tuple for {name}, got {type(date).__name__}")
    if len(date) != 3:
        raise TypeError(f"expected 3-tuple for {name}, got {len(date)}-tuple")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"expected int for {name}[{i}], got {type(v).__name__}")


def _check_valid_date(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim_raw(y, m)
    if d < 1 or d > dim:
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m:02d}")


def _shift(a, k):
    """add_months(a, k) without any validation (internal)."""
    y, m, d = a
    total = (y - 1) * 12 + (m - 1) + k
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim_raw(ny, nm) else _dim_raw(ny, nm)
    return (ny, nm, nd)


# Regex patterns for parse (fullmatch, ASCII digits only)
_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BAS = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim_raw(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ord(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    return (_to_ord(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    ord_ = _to_ord(y, m, d) + n
    if ord_ < 1 or ord_ > _MAX_ORD:
        raise OverflowError(f"result ordinal {ord_} out of range")
    return _from_ord(ord_)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
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
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    # Jan 1 weekday: Mon=0
    jan1_wd = (_to_ord(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:  # Thursday
        return 53
    if jan1_wd == 2 and _is_leap_raw(iso_year):  # Wednesday in leap year
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    ord_ = _to_ord(y, m, d)
    wd = (ord_ - 1) % 7  # Mon=0
    # Thursday of this week
    thu_ord = ord_ + (3 - wd)
    iso_y, _, _ = _from_ord(thu_ord)
    # Monday of week 1 of iso_y
    jan4_ord = _to_ord(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_mon = jan4_ord - jan4_wd
    week = (ord_ - first_mon) // 7 + 1
    iso_wd = wd + 1  # Mon=1
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw} for ISO year {iso_year}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    # Monday of week 1
    jan4_ord = _to_ord(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_mon = jan4_ord - jan4_wd
    target_ord = first_mon + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORD:
        raise OverflowError(f"result ordinal {target_ord} out of range")
    return _from_ord(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"expected str, got {type(s).__name__}")

    # Try each pattern via fullmatch
    m = _RE_CAL_EXT.fullmatch(s)
    if m:
        y = int(m.group(1))
        mo = int(m.group(2))
        d = int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _dim_raw(y, mo):
            raise ValueError(f"day {d} out of range for {y}-{mo:02d}")
        return (y, mo, d)

    m = _RE_CAL_BAS.fullmatch(s)
    if m:
        y = int(m.group(1))
        mo = int(m.group(2))
        d = int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _dim_raw(y, mo):
            raise ValueError(f"day {d} out of range for {y}-{mo:02d}")
        return (y, mo, d)

    m = _RE_ORD_EXT.fullmatch(s)
    if m:
        y = int(m.group(1))
        doy = int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ord(_to_ord(y, 1, 1) + doy - 1)

    m = _RE_ORD_BAS.fullmatch(s)
    if m:
        y = int(m.group(1))
        doy = int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ord(_to_ord(y, 1, 1) + doy - 1)

    m = _RE_WK_EXT.fullmatch(s)
    if m:
        y = int(m.group(1))
        wk = int(m.group(2))
        wd = int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        nw = iso_weeks_in_year(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        # Compute date
        jan4_ord = _to_ord(y, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        first_mon = jan4_ord - jan4_wd
        target_ord = first_mon + (wk - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > _MAX_ORD:
            raise ValueError("date out of supported range")
        return _from_ord(target_ord)

    m = _RE_WK_BAS.fullmatch(s)
    if m:
        y = int(m.group(1))
        wk = int(m.group(2))
        wd = int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        nw = iso_weeks_in_year(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_ord = _to_ord(y, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        first_mon = jan4_ord - jan4_wd
        target_ord = first_mon + (wk - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > _MAX_ORD:
            raise ValueError("date out of supported range")
        return _from_ord(target_ord)

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_valid_date(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"unknown form {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        ord_ = _to_ord(y, m, d)
        jan1 = _to_ord(y, 1, 1)
        doy = ord_ - jan1 + 1
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    if a <= b:
        # Binary search for largest K >= 0 with shift(a, K) <= b
        lo = 0
        hi = (by - ay + 1) * 12
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _shift(a, mid) <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _shift(a, K)
        days = _to_ord(by, bm, bd) - _to_ord(*shifted)
        return (years, months, days)
    else:
        years, months, days = diff(b, a)
        return (-years, -months, -days)
