import re

# Pre-compiled regexes for parse (ASCII digits only)
_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BAS  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')

# Cumulative days before each month (index 0 = before Jan, index 11 = before Dec)
_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP    = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)

_MAX_ORD = 3652059  # to_ordinal(9999, 12, 31)


def _is_leap_unchecked(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_unchecked(y, m):
    if m == 2:
        return 29 if _is_leap_unchecked(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for v in x:
        if type(v) is not int:
            raise TypeError(f"{name} must be a tuple of exactly 3 ints")


def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim_unchecked(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim}")


def _days_before_year(y):
    """Total days from year 1 through year y-1 (i.e. before Jan 1 of year y)."""
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


def _total_days_through_year(y):
    """Total days from year 1 through end of year y."""
    return 365 * y + y // 4 - y // 100 + y // 400


def is_leap(y):
    _check_int(y, "y")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_unchecked(y)


def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim_unchecked(y, m)


def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    days = _days_before_year(y)
    cum = _CUM_LEAP if _is_leap_unchecked(y) else _CUM_NONLEAP
    days += cum[m - 1]
    days += d
    return days


def from_ordinal(n):
    _check_int(n, "n")
    if not (1 <= n <= _MAX_ORD):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    # Binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        if _total_days_through_year(mid) < n:
            lo = mid + 1
        else:
            hi = mid
    y = lo
    doy = n - _days_before_year(y)  # 1-based day of year
    cum = _CUM_LEAP if _is_leap_unchecked(y) else _CUM_NONLEAP
    # Find month: smallest m in 1..12 with cum[m] >= doy
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < doy:
            lo = mid + 1
        else:
            hi = mid
    m = lo
    d = doy - cum[m - 1]
    return (y, m, d)


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    ord_ = to_ordinal(y, m, d) + n
    if ord_ < 1 or ord_ > _MAX_ORD:
        raise OverflowError("result out of supported range")
    return from_ordinal(ord_)


def add_months(date, n):
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if not (1 <= ny <= 9999):
        raise OverflowError("result out of supported range")
    nd = d if d <= _dim_unchecked(ny, nm) else _dim_unchecked(ny, nm)
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    # Weekday of Jan 1 (Mon=0)
    wd = (_days_before_year(iso_year) + 1 - 1) % 7
    if wd == 3 or (wd == 2 and _is_leap_unchecked(iso_year)):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    ord_ = to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7  # Mon=0
    iso_wd = wd + 1      # Mon=1
    # Thursday of this week
    thursday_ord = ord_ - wd + 3
    iso_y, _, _ = from_ordinal(thursday_ord)
    # Monday of week 1 of iso_y
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    week = (ord_ - monday_w1) // 7 + 1
    return (iso_y, week, iso_wd)


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
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError("result out of supported range")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    # Try each form
    m = _RE_CAL_EXT.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _dim_unchecked(y, mo)):
            raise ValueError(f"day {d} out of range for {y}-{mo:02d}")
        return (y, mo, d)

    m = _RE_WK_EXT.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("week date out of supported range")

    m = _RE_CAL_BAS.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _dim_unchecked(y, mo)):
            raise ValueError(f"day {d} out of range for {y}-{mo:02d}")
        return (y, mo, d)

    m = _RE_ORD_EXT.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap_unchecked(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_WK_BAS.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("week date out of supported range")

    m = _RE_ORD_BAS.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap_unchecked(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    raise ValueError(f"cannot parse {s!r}")


def format_date(date, form):
    _check_date(date, "date")
    y, m, d = date
    _check_date_range(y, m, d)

    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, wk, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{wk:02d}-{iso_wd}"


def diff(a, b):
    _check_date(a, "a")
    _check_date(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    def shift(k):
        total = (ay - 1) * 12 + (am - 1) + k
        ny = total // 12 + 1
        nm = total % 12 + 1
        nd = ad if ad <= _dim_unchecked(ny, nm) else _dim_unchecked(ny, nm)
        return (ny, nm, nd)

    # Upper bound: shifting by this many months guarantees year > by
    hi = (by - ay) * 12 + 12
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if shift(mid) <= b:
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    days = to_ordinal(by, bm, bd) - to_ordinal(*shift(K))
    return (years, months, days)