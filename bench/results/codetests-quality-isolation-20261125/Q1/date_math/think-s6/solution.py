import re


# ---------------------------------------------------------------------------
# Internal helpers (no public API)
# ---------------------------------------------------------------------------

_MDAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]

_MIN_ORD = 1
_MAX_ORD = 3652059  # to_ordinal(9999, 12, 31)


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _check_date(x, name):
    if type(x) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(v).__name__}")


def _dim(y, m):
    """Days in month m of year y (no validation)."""
    if m == 2:
        if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
            return 29
        return 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _validate_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim}")


def _days_before_month(y, m):
    """Number of days from Jan 1 to the first day of month m."""
    d = _MDAYS[m - 1]
    if m > 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        d += 1
    return d


def _to_ordinal_raw(y, m, d):
    """Ordinal of (y,m,d) without validation. (1,1,1) -> 1."""
    days = 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    days += _days_before_month(y, m)
    days += d
    return days


def _add_months_raw(date, n):
    """add_months without type/range checks."""
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _check_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)
    return _to_ordinal_raw(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if not (_MIN_ORD <= n <= _MAX_ORD):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")

    t = n - 1  # 0-based day count

    # Binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        days = 365 * (mid - 1) + (mid - 1) // 4 - (mid - 1) // 100 + (mid - 1) // 400
        if days <= t:
            lo = mid
        else:
            hi = mid - 1
    y = lo

    doy = t - (365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400) + 1

    # Find month and day (at most 12 steps)
    m = 1
    while m <= 12:
        md = _dim(y, m)
        if doy <= md:
            break
        doy -= md
        m += 1

    return (y, m, doy)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)
    return (_to_ordinal_raw(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    _validate_date(*date)
    ord_val = _to_ordinal_raw(*date) + n
    if not (_MIN_ORD <= ord_val <= _MAX_ORD):
        raise OverflowError(f"result ordinal {ord_val} out of range 1..{_MAX_ORD}")
    return from_ordinal(ord_val)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    _validate_date(*date)
    result = _add_months_raw(date, n)
    ny, nm, nd = result
    if not (1 <= ny <= 9999):
        raise OverflowError(f"result year {ny} out of range 1..9999")
    return result


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = (_to_ordinal_raw(iso_year, 1, 1) - 1) % 7  # 0=Mon
    if wd == 3:  # Thursday
        return 53
    if wd == 2 and (iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0)):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)

    ord_val = _to_ordinal_raw(y, m, d)
    wd = (ord_val - 1) % 7  # 0=Mon .. 6=Sun

    # Thursday of this week
    thu_ord = ord_val + (3 - wd)
    iso_y = from_ordinal(thu_ord)[0]

    # Monday of week 1 of iso_y
    jan4_ord = _to_ordinal_raw(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_week1 = jan4_ord - jan4_wd

    # Monday of current week
    mon_cur = ord_val - wd

    week = (mon_cur - mon_week1) // 7 + 1
    iso_wd = wd + 1  # 1=Mon .. 7=Sun

    return (iso_y, week, iso_wd)


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

    jan4_ord = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_week1 = jan4_ord - jan4_wd

    target_ord = mon_week1 + (week - 1) * 7 + (weekday - 1)

    if not (_MIN_ORD <= target_ord <= _MAX_ORD):
        raise OverflowError(f"result ordinal {target_ord} out of range 1..{_MAX_ORD}")
    return from_ordinal(target_ord)


# ---------------------------------------------------------------------------
# parse / format_date
# ---------------------------------------------------------------------------

_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BASIC_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BASIC_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WEEK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BASIC_WEEK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mm <= 12):
            raise ValueError(f"month {mm} out of range")
        dim = _dim(y, mm)
        if not (1 <= dd <= dim):
            raise ValueError(f"day {dd} out of range 1..{dim}")
        return (y, mm, dd)

    m = _RE_BASIC_CAL.fullmatch(s)
    if m:
        y, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mm <= 12):
            raise ValueError(f"month {mm} out of range")
        dim = _dim(y, mm)
        if not (1 <= dd <= dim):
            raise ValueError(f"day {dd} out of range 1..{dim}")
        return (y, mm, dd)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_to_ordinal_raw(y, 1, 1) + doy - 1)

    m = _RE_BASIC_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_to_ordinal_raw(y, 1, 1) + doy - 1)

    m = _RE_EXT_WEEK.fullmatch(s)
    if m:
        iy, wk, dw = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= iy <= 9999):
            raise ValueError(f"iso_year {iy} out of range")
        max_wk = iso_weeks_in_year(iy)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if not (1 <= dw <= 7):
            raise ValueError(f"weekday {dw} out of range 1..7")
        try:
            return from_iso_week(iy, wk, dw)
        except OverflowError:
            raise ValueError(f"week date out of supported range")

    m = _RE_BASIC_WEEK.fullmatch(s)
    if m:
        iy, wk, dw = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= iy <= 9999):
            raise ValueError(f"iso_year {iy} out of range")
        max_wk = iso_weeks_in_year(iy)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if not (1 <= dw <= 7):
            raise ValueError(f"weekday {dw} out of range 1..7")
        try:
            return from_iso_week(iy, wk, dw)
        except OverflowError:
            raise ValueError(f"week date out of supported range")

    raise ValueError(f"unrecognized date string: {s!r}")


def format_date(date, form):
    _check_date(date, 'date')
    _validate_date(*date)

    if not isinstance(form, str) or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")

    y, m, d = date

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal_raw(y, m, d) - _to_ordinal_raw(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    _validate_date(*a)
    _validate_date(*b)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    # Upper bound: max months from any valid date to (9999,12,31)
    hi = 119987  # (9999*12 - 1) - 0
    lo = 0

    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _add_months_raw(a, mid)
        if shifted <= b:
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_raw(a, K)
    days = _to_ordinal_raw(*b) - _to_ordinal_raw(*shifted)

    return (years, months, days)