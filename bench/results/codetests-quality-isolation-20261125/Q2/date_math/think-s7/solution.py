import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
ERA_DAYS = 146097          # days in a 400-year Gregorian cycle
MIN_ORD = 1
MAX_ORD = 3652059          # to_ordinal(9999, 12, 31)

# ---------------------------------------------------------------------------
# Pre-compiled regexes (ASCII digits only)
# ---------------------------------------------------------------------------
_RE_EXT_CAL = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_BAS_CAL = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_EXT_ORD = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_BAS_ORD = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_EXT_WK  = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_BAS_WK  = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')

# ---------------------------------------------------------------------------
# Internal helpers (no public API)
# ---------------------------------------------------------------------------

def _is_int(v):
    return type(v) is int


def _check_int(v):
    if not _is_int(v):
        raise TypeError(f"expected int, got {type(v).__name__}")


def _check_date_tuple(date):
    if not (type(date) is tuple and len(date) == 3):
        raise TypeError("expected a tuple of exactly 3 ints")
    for x in date:
        if not _is_int(x):
            raise TypeError("expected a tuple of exactly 3 ints")


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    d = _MONTH_DAYS[m - 1]
    if m == 2 and _leap(y):
        d = 29
    return d


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    lim = _dim(y, m)
    if d < 1 or d > lim:
        raise ValueError(f"day {d} out of range 1..{lim}")


def _days_before_year(y):
    """Total days in years 1 .. y-1."""
    n = y - 1
    r = n % 400
    return (n // 400) * ERA_DAYS + r * 365 + r // 4 - r // 100


def _days_before_year_in_era(y):
    """Days in years 1..y-1 within a 400-year era (y in 1..400)."""
    n = y - 1
    return n * 365 + n // 4 - n // 100


def _shift(y, m, d, k):
    """add_months without any checking (caller guarantees validity)."""
    total = (y - 1) * 12 + (m - 1) + k
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _check_int(y)
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _leap(y)


def days_in_month(y, m):
    _check_int(y)
    _check_int(m)
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y)
    _check_int(m)
    _check_int(d)
    _check_date_range(y, m, d)
    # days before this year
    n = y - 1
    r = n % 400
    days = (n // 400) * ERA_DAYS + r * 365 + r // 4 - r // 100
    # days before this month in this year
    if _leap(y):
        days += _CUM_LEAP[m - 1]
    else:
        days += _CUM_NONLEAP[m - 1]
    days += d
    return days


def from_ordinal(n):
    _check_int(n)
    if n < MIN_ORD or n > MAX_ORD:
        raise ValueError(f"ordinal {n} out of range {MIN_ORD}..{MAX_ORD}")
    n0 = n - 1
    era = n0 // ERA_DAYS
    day_in_era = n0 % ERA_DAYS

    # locate year within the era (1..400)
    y_est = day_in_era // 365 + 1
    while _days_before_year_in_era(y_est + 1) <= day_in_era:
        y_est += 1
    while y_est > 1 and _days_before_year_in_era(y_est) > day_in_era:
        y_est -= 1
    y_in_era = y_est
    y = era * 400 + y_in_era

    day_in_year = day_in_era - _days_before_year_in_era(y_in_era)  # 0-indexed

    cum = _CUM_LEAP if _leap(y) else _CUM_NONLEAP
    m = 1
    for i in range(1, 12):
        if day_in_year >= cum[i]:
            m = i + 1
        else:
            break
    d = day_in_year - cum[m - 1] + 1
    return (y, m, d)


def weekday(y, m, d):
    _check_int(y)
    _check_int(m)
    _check_int(d)
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date)
    _check_int(n)
    y, m, d = date
    _check_date_range(y, m, d)
    ord_n = to_ordinal(y, m, d) + n
    if ord_n < MIN_ORD or ord_n > MAX_ORD:
        raise OverflowError("result out of range 1..9999")
    return from_ordinal(ord_n)


def add_months(date, n):
    _check_date_tuple(date)
    _check_int(n)
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("result out of range 1..9999")
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"year {iso_year} out of range 1..9999")
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7  # Mon=0
    if wd == 3:
        return 53
    if wd == 2 and _leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y)
    _check_int(m)
    _check_int(d)
    _check_date_range(y, m, d)
    wd = (to_ordinal(y, m, d) - 1) % 7  # Mon=0
    iso_weekday = wd + 1                 # Mon=1

    # Thursday of this week
    offset = 3 - wd
    thu_ord = to_ordinal(y, m, d) + offset
    iso_year = from_ordinal(thu_ord)[0]

    # Monday of ISO week 1 of iso_year
    jan4_wd = (to_ordinal(iso_year, 1, 4) - 1) % 7
    mon_w1 = to_ordinal(iso_year, 1, 4) - jan4_wd

    iso_wk = (to_ordinal(y, m, d) - mon_w1) // 7 + 1
    return (iso_year, iso_wk, iso_weekday)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year)
    _check_int(week)
    _check_int(weekday)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")

    jan4_wd = (to_ordinal(iso_year, 1, 4) - 1) % 7
    mon_w1 = to_ordinal(iso_year, 1, 4) - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)

    if target < MIN_ORD or target > MAX_ORD:
        raise OverflowError("result out of range 1..9999")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"expected str, got {type(s).__name__}")

    # Try the six forms (order doesn't matter; they're mutually exclusive)
    mch = _RE_EXT_CAL.match(s)
    if mch:
        y, mo, d = int(mch.group(1)), int(mch.group(2)), int(mch.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        _check_date_range(y, mo, d)
        return (y, mo, d)

    mch = _RE_EXT_WK.match(s)
    if mch:
        y, wk, wd = int(mch.group(1)), int(mch.group(2)), int(mch.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        nw = iso_weeks_in_year(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        # Compute the date; if out of range → ValueError (not OverflowError)
        jan4_wd = (to_ordinal(y, 1, 4) - 1) % 7
        mon_w1 = to_ordinal(y, 1, 4) - jan4_wd
        target = mon_w1 + (wk - 1) * 7 + (wd - 1)
        if target < MIN_ORD or target > MAX_ORD:
            raise ValueError("date out of range")
        return from_ordinal(target)

    mch = _RE_EXT_ORD.match(s)
    if mch:
        y, doy = int(mch.group(1)), int(mch.group(2))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        max_doy = 366 if _leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    mch = _RE_BAS_CAL.match(s)
    if mch:
        y, mo, d = int(mch.group(1)), int(mch.group(2)), int(mch.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        _check_date_range(y, mo, d)
        return (y, mo, d)

    mch = _RE_BAS_WK.match(s)
    if mch:
        y, wk, wd = int(mch.group(1)), int(mch.group(2)), int(mch.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        nw = iso_weeks_in_year(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_wd = (to_ordinal(y, 1, 4) - 1) % 7
        mon_w1 = to_ordinal(y, 1, 4) - jan4_wd
        target = mon_w1 + (wk - 1) * 7 + (wd - 1)
        if target < MIN_ORD or target > MAX_ORD:
            raise ValueError("date out of range")
        return from_ordinal(target)

    mch = _RE_BAS_ORD.match(s)
    if mch:
        y, doy = int(mch.group(1)), int(mch.group(2))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        max_doy = 366 if _leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date_tuple(date)
    y, m, d = date
    _check_date_range(y, m, d)

    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, iday = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iday}"


def diff(a, b):
    _check_date_tuple(a)
    _check_date_tuple(b)
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if (ay, am, ad) > (by, bm, bd):
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    hi = (by - ay) * 12 + 12
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift(ay, am, ad, mid) <= (by, bm, bd):
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    shifted = _shift(ay, am, ad, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(*shifted)
    return (years, months, days)
