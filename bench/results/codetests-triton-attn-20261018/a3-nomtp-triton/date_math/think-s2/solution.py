import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORD = 3652059  # ordinal of (9999,12,31)

# Pre-compiled regexes for parse (ASCII digits only)
_RE_EXT_CAL   = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BASIC_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD   = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BASIC_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WK    = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BASIC_WK  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')

# ---------------------------------------------------------------------------
# Internal helpers (no validation)
# ---------------------------------------------------------------------------

def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_raw(y, m):
    """Days in month, no validation."""
    if m == 2 and _is_leap_raw(y):
        return 29
    return _MONTH_DAYS[m - 1]


def _to_ord_raw(y, m, d):
    """Ordinal (1-based) with no validation."""
    t = y - 1
    days = 365 * t + t // 4 - t // 100 + t // 400
    days += _CUM[m - 1]
    if m > 2 and _is_leap_raw(y):
        days += 1
    return days + d


def _shift_raw(y, m, d, k):
    """add_months without validation; returns None if year out of 1..9999."""
    total = (y - 1) * 12 + (m - 1) + k
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        return None
    td = d if d <= _dim_raw(ty, tm) else _dim_raw(ty, tm)
    return (ty, tm, td)


# ---------------------------------------------------------------------------
# Type / range check helpers
# ---------------------------------------------------------------------------

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int")


def _check_date_tuple(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for v in x:
        if type(v) is not int:
            raise TypeError(f"{name} must be a tuple of 3 ints")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim_raw(y, m):
        raise ValueError("day out of range")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _check_int(y, "y")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _dim_raw(y, m)


def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return _to_ord_raw(y, m, d)


def from_ordinal(n):
    _check_int(n, "n")
    if n < 1 or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    n0 = n - 1
    # Estimate year offset t (0-based)
    t = n0 // 365
    # Adjust downward
    while 365 * t + t // 4 - t // 100 + t // 400 > n0:
        t -= 1
    # Adjust upward
    while 365 * (t + 1) + (t + 1) // 4 - (t + 1) // 100 + (t + 1) // 400 <= n0:
        t += 1
    y = t + 1
    doy = n0 - (365 * t + t // 4 - t // 100 + t // 400)  # 0-based day in year
    # Find month (at most 11 iterations)
    if _is_leap_raw(y):
        cum = (31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
    else:
        cum = (31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    mi = 0
    while mi < 11 and doy >= cum[mi]:
        mi += 1
    d = doy - (cum[mi - 1] if mi > 0 else 0) + 1
    return (y, mi + 1, d)


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return (_to_ord_raw(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    ord_val = _to_ord_raw(y, m, d) + n
    if ord_val < 1 or ord_val > _MAX_ORD:
        raise OverflowError("result out of range")
    return from_ordinal(ord_val)


def add_months(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of range")
    td = d if d <= _dim_raw(ty, tm) else _dim_raw(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("year out of range")
    t = iso_year - 1
    jan1_wd = (365 * t + t // 4 - t // 100 + t // 400) % 7
    if jan1_wd == 3 or (_is_leap_raw(iso_year) and jan1_wd == 2):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    ord_val = _to_ord_raw(y, m, d)
    wd = (ord_val - 1) % 7          # 0=Mon
    iso_wd = wd + 1                 # 1=Mon
    mon_ord = ord_val - wd
    thu_ord = mon_ord + 3
    thu_date = from_ordinal(thu_ord)
    iso_year = thu_date[0]
    # Monday of ISO week 1 of iso_year
    jan4_ord = _to_ord_raw(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1_ord = jan4_ord - jan4_wd
    iso_wk = (mon_ord - mon_w1_ord) // 7 + 1
    return (iso_year, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    max_wk = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_wk:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4_ord = _to_ord_raw(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1_ord = jan4_ord - jan4_wd
    target_ord = mon_w1_ord + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORD:
        raise OverflowError("result out of range")
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    if len(s) == 10:
        m = _RE_EXT_CAL.fullmatch(s)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1 or y > 9999:
                raise ValueError("invalid date")
            if mo < 1 or mo > 12:
                raise ValueError("invalid date")
            if d < 1 or d > _dim_raw(y, mo):
                raise ValueError("invalid date")
            return (y, mo, d)
        m = _RE_EXT_WK.fullmatch(s)
        if m:
            y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1 or y > 9999:
                raise ValueError("invalid date")
            if wk < 1 or wk > iso_weeks_in_year(y):
                raise ValueError("invalid date")
            if wd < 1 or wd > 7:
                raise ValueError("invalid date")
            jan4_ord = _to_ord_raw(y, 1, 4)
            jan4_wd = (jan4_ord - 1) % 7
            mon_w1 = jan4_ord - jan4_wd
            target = mon_w1 + (wk - 1) * 7 + (wd - 1)
            if target < 1 or target > _MAX_ORD:
                raise ValueError("date out of range")
            return from_ordinal(target)
        raise ValueError("invalid date string")

    elif len(s) == 8:
        m = _RE_EXT_ORD.fullmatch(s)
        if m:
            y, doy = int(m.group(1)), int(m.group(2))
            if y < 1 or y > 9999:
                raise ValueError("invalid date")
            max_doy = 366 if _is_leap_raw(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError("invalid date")
            return from_ordinal(_to_ord_raw(y, 1, 1) + doy - 1)
        m = _RE_BASIC_WK.fullmatch(s)
        if m:
            y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1 or y > 9999:
                raise ValueError("invalid date")
            if wk < 1 or wk > iso_weeks_in_year(y):
                raise ValueError("invalid date")
            if wd < 1 or wd > 7:
                raise ValueError("invalid date")
            jan4_ord = _to_ord_raw(y, 1, 4)
            jan4_wd = (jan4_ord - 1) % 7
            mon_w1 = jan4_ord - jan4_wd
            target = mon_w1 + (wk - 1) * 7 + (wd - 1)
            if target < 1 or target > _MAX_ORD:
                raise ValueError("date out of range")
            return from_ordinal(target)
        m = _RE_BASIC_CAL.fullmatch(s)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1 or y > 9999:
                raise ValueError("invalid date")
            if mo < 1 or mo > 12:
                raise ValueError("invalid date")
            if d < 1 or d > _dim_raw(y, mo):
                raise ValueError("invalid date")
            return (y, mo, d)
        raise ValueError("invalid date string")

    elif len(s) == 7:
        m = _RE_BASIC_ORD.fullmatch(s)
        if m:
            y, doy = int(m.group(1)), int(m.group(2))
            if y < 1 or y > 9999:
                raise ValueError("invalid date")
            max_doy = 366 if _is_leap_raw(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError("invalid date")
            return from_ordinal(_to_ord_raw(y, 1, 1) + doy - 1)
        raise ValueError("invalid date string")

    else:
        raise ValueError("invalid date string")


def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _check_date_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ord_raw(y, m, d) - _to_ord_raw(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    _check_date_range(a[0], a[1], a[2])
    _check_date_range(b[0], b[1], b[2])

    if a == b:
        return (0, 0, 0)

    ord_a = _to_ord_raw(a[0], a[1], a[2])
    ord_b = _to_ord_raw(b[0], b[1], b[2])

    if ord_a > ord_b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    y1, m1, d1 = a
    y2, m2, d2 = b

    # Binary search: largest K >= 0 with _shift_raw(y1,m1,d1,K) <= b
    lo = 0
    hi = (y2 - y1) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _shift_raw(y1, m1, d1, mid)
        if shifted is not None and _to_ord_raw(shifted[0], shifted[1], shifted[2]) <= ord_b:
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    shifted = _shift_raw(y1, m1, d1, K)
    days = ord_b - _to_ord_raw(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
