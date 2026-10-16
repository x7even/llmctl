import re

__all__ = [
    'is_leap', 'days_in_month', 'to_ordinal', 'from_ordinal', 'weekday',
    'add_days', 'add_months', 'iso_weeks_in_year', 'iso_week', 'from_iso_week',
    'parse', 'format_date', 'diff',
]

# ─── internal constants ───────────────────────────────────────────────
_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MAX_ORD = 3652059  # ordinal of (9999, 12, 31)

# ─── regex patterns for parse ─────────────────────────────────────────
_RE_CAL_EXT = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_ORD_EXT = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_WK_EXT  = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_CAL_BAS = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_ORD_BAS = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_WK_BAS  = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')


# ─── internal helpers ─────────────────────────────────────────────────
def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MONTH_DAYS[m - 1]


def _days_before_year(y):
    """Days in years 1..y-1."""
    n = y - 1
    return 365 * n + n // 4 - n // 100 + n // 400


def _days_before_month(y, m):
    """Days in months 1..m-1 of year y."""
    r = _DAYS_BEFORE_MONTH[m - 1]
    if m > 2 and _is_leap(y):
        r += 1
    return r


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int")


def _check_date_tuple(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")


# ─── public API ───────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    # Estimate year
    y = (n * 400) // 146097 + 1
    while _days_before_year(y) >= n:
        y -= 1
    while _days_before_year(y + 1) < n:
        y += 1
    doy = n - _days_before_year(y)  # 1-based day of year
    leap = _is_leap(y)
    for m in range(1, 13):
        md = _MONTH_DAYS[m - 1]
        if m == 2 and leap:
            md = 29
        if doy <= md:
            return (y, m, doy)
        doy -= md
    raise ValueError("internal error in from_ordinal")


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
    ord_n = to_ordinal(y, m, d) + n
    if ord_n < 1 or ord_n > _MAX_ORD:
        raise OverflowError(f"result ordinal {ord_n} out of range")
    return from_ordinal(ord_n)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError(f"target year {ty} out of range 1..9999")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = _days_before_year(iso_year) % 7  # (jan1_ord - 1) % 7
    if jan1_wd == 3 or (_is_leap(iso_year) and jan1_wd == 2):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ordinal = to_ordinal(y, m, d)
    wd = (ordinal - 1) % 7  # Monday=0
    # Thursday of this week
    thursday_ord = ordinal - wd + 3
    iso_y = from_ordinal(thursday_ord)[0]
    # Monday of week 1 of iso_y
    jan1_ord = _days_before_year(iso_y) + 1
    jan1_wd = (jan1_ord - 1) % 7
    first_thu = jan1_ord + (3 - jan1_wd) % 7
    monday_w1 = first_thu - 3
    iso_wk = (ordinal - monday_w1) // 7 + 1
    iso_wd = wd + 1  # Monday=1
    return (iso_y, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_wk:
        raise ValueError(f"week {week} out of range 1..{max_wk}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan1_ord = _days_before_year(iso_year) + 1
    jan1_wd = (jan1_ord - 1) % 7
    first_thu = jan1_ord + (3 - jan1_wd) % 7
    monday_w1 = first_thu - 3
    target = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError(f"result ordinal {target} out of range")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    # Extended calendar: YYYY-MM-DD
    m = _RE_CAL_EXT.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        _check_date_range(y, mo, d)
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD
    m = _RE_ORD_EXT.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    # Extended week: YYYY-Www-D
    m = _RE_WK_EXT.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of supported range")

    # Basic calendar: YYYYMMDD
    m = _RE_CAL_BAS.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        _check_date_range(y, mo, d)
        return (y, mo, d)

    # Basic ordinal: YYYYDDD
    m = _RE_ORD_BAS.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    # Basic week: YYYYWwwD
    m = _RE_WK_BAS.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of supported range")

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str:
        raise ValueError("form must be a string")
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    a_ord = to_ordinal(ay, am, ad)
    b_ord = to_ordinal(by, bm, bd)

    if a_ord > b_ord:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    base = (ay - 1) * 12 + (am - 1)

    def _shift_le(K):
        total = base + K
        ty = total // 12 + 1
        tm = total % 12 + 1
        td = ad if ad <= _dim(ty, tm) else _dim(ty, tm)
        if ty != by:
            return ty < by
        if tm != bm:
            return tm < bm
        return td <= bd

    lo, hi = 0, 119988  # hi is always "False" (year > 9999)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift_le(mid):
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)

    total = base + K
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = ad if ad <= _dim(ty, tm) else _dim(ty, tm)
    days = b_ord - to_ordinal(ty, tm, td)
    return (years, months, days)