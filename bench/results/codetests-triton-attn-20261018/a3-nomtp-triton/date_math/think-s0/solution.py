import re

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MONTH_DAYS = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_CUM_MONTH = [0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
_CUM_MONTH_LEAP = [0, 0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]

_MAX_ORDINAL = 3652059  # to_ordinal(9999, 12, 31)


def _is_int(x):
    return type(x) is int


def _check_date_arg(date, name="date"):
    if not isinstance(date, tuple) or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError(f"{name} elements must be ints")


def _days_before_year(y):
    """Total days in years 1 through y-1."""
    n = y - 1
    return 365 * n + n // 4 - n // 100 + n // 400


def _days_before_month(y, m):
    """Total days in months 1 through m-1 of year y."""
    total = _CUM_MONTH[m]
    if m > 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        total += 1
    return total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    if type(y) is not int:
        raise TypeError("y must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if type(y) is not int or type(m) is not int:
        raise TypeError("y and m must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    if m == 2:
        return 29 if is_leap(y) else 28
    return _MONTH_DAYS[m]


def to_ordinal(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    if type(n) is not int:
        raise TypeError("n must be int")
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError("ordinal out of range 1..3652059")
    n0 = n - 1  # 0-indexed
    # Approximate year
    y = n0 // 365 + 1
    # Adjust (at most 2 iterations)
    while _days_before_year(y) > n0:
        y -= 1
    while y < 9999 and _days_before_year(y + 1) <= n0:
        y += 1
    doy = n0 - _days_before_year(y) + 1  # 1-indexed day of year
    # Find month
    leap = is_leap(y)
    cum = _CUM_MONTH_LEAP if leap else _CUM_MONTH
    m = 1
    while cum[m + 1] < doy:
        m += 1
    d = doy - cum[m]
    return (y, m, d)


def weekday(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_arg(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")
    ordinal = to_ordinal(y, m, d) + n
    if ordinal < 1 or ordinal > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(ordinal)


def add_months(date, n):
    _check_date_arg(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("result out of range")
    nm = total % 12 + 1
    nd = min(d, days_in_month(ny, nm))
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range 1..9999")
    w1 = weekday(iso_year, 1, 1)  # Mon=0..Sun=6
    if w1 == 3:  # Thursday
        return 53
    if w1 == 2 and is_leap(iso_year):  # Wednesday in leap year
        return 53
    return 52


def iso_week(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")
    ordinal = to_ordinal(y, m, d)
    wd = (ordinal - 1) % 7  # Mon=0..Sun=6
    iso_wd = wd + 1  # Mon=1..Sun=7
    # Monday of the week containing this date
    monday_ordinal = ordinal - wd
    # Monday of week 1 of year y (the week containing Jan 4)
    jan4_ord = to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    week = (monday_ordinal - week1_monday) // 7 + 1
    if week < 1:
        iso_y = y - 1
        week += iso_weeks_in_year(iso_y)
    elif week > iso_weeks_in_year(y):
        iso_y = y + 1
        week -= iso_weeks_in_year(y)
    else:
        iso_y = y
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if type(iso_year) is not int or type(week) is not int or type(weekday) is not int:
        raise TypeError("iso_year, week, weekday must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError(f"week out of range 1..{max_week}")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range 1..7")
    # Monday of week 1
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    ordinal = week1_monday + (week - 1) * 7 + (weekday - 1)
    if ordinal < 1 or ordinal > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(ordinal)


# ---------------------------------------------------------------------------
# parse / format_date
# ---------------------------------------------------------------------------

_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BAS = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def _week1_monday_ordinal(iso_year):
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    return jan4_ord - jan4_wd


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    L = len(s)

    if L == 10:
        m = _RE_CAL_EXT.fullmatch(s)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1:
                raise ValueError("year out of range")
            if mo < 1 or mo > 12:
                raise ValueError("month out of range")
            if d < 1 or d > days_in_month(y, mo):
                raise ValueError("day out of range")
            return (y, mo, d)
        m = _RE_WK_EXT.fullmatch(s)
        if m:
            y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1:
                raise ValueError("year out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            max_wk = iso_weeks_in_year(y)
            if wk < 1 or wk > max_wk:
                raise ValueError("week out of range")
            ordinal = _week1_monday_ordinal(y) + (wk - 1) * 7 + (wd - 1)
            if ordinal < 1 or ordinal > _MAX_ORDINAL:
                raise ValueError("date out of range")
            return from_ordinal(ordinal)
        raise ValueError("invalid date string")

    if L == 8:
        if s[4] == '-':
            m = _RE_ORD_EXT.fullmatch(s)
            if m:
                y, doy = int(m.group(1)), int(m.group(2))
                if y < 1:
                    raise ValueError("year out of range")
                max_doy = 366 if is_leap(y) else 365
                if doy < 1 or doy > max_doy:
                    raise ValueError("day of year out of range")
                return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)
            raise ValueError("invalid date string")
        elif s[4] == 'W':
            m = _RE_WK_BAS.fullmatch(s)
            if m:
                y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 1:
                    raise ValueError("year out of range")
                if wd < 1 or wd > 7:
                    raise ValueError("weekday out of range")
                max_wk = iso_weeks_in_year(y)
                if wk < 1 or wk > max_wk:
                    raise ValueError("week out of range")
                ordinal = _week1_monday_ordinal(y) + (wk - 1) * 7 + (wd - 1)
                if ordinal < 1 or ordinal > _MAX_ORDINAL:
                    raise ValueError("date out of range")
                return from_ordinal(ordinal)
            raise ValueError("invalid date string")
        else:
            m = _RE_CAL_BAS.fullmatch(s)
            if m:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 1:
                    raise ValueError("year out of range")
                if mo < 1 or mo > 12:
                    raise ValueError("month out of range")
                if d < 1 or d > days_in_month(y, mo):
                    raise ValueError("day out of range")
                return (y, mo, d)
            raise ValueError("invalid date string")

    if L == 7:
        m = _RE_ORD_BAS.fullmatch(s)
        if m:
            y, doy = int(m.group(1)), int(m.group(2))
            if y < 1:
                raise ValueError("year out of range")
            max_doy = 366 if is_leap(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError("day of year out of range")
            return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)
        raise ValueError("invalid date string")

    raise ValueError("invalid date string")


def format_date(date, form):
    _check_date_arg(date)
    y, m, d = date
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")
    if not isinstance(form, str) or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def _shift_for_diff(a, k):
    """add_months(a, k) but returns a sentinel (10000,1,1) if year > 9999."""
    y, m, d = a
    total = (y - 1) * 12 + (m - 1) + k
    ny = total // 12 + 1
    if ny > 9999:
        return (10000, 1, 1)
    nm = total % 12 + 1
    nd = min(d, days_in_month(ny, nm))
    return (ny, nm, nd)


def diff(a, b):
    _check_date_arg(a, "a")
    _check_date_arg(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    for (yy, mm, dd) in (a, b):
        if yy < 1 or yy > 9999:
            raise ValueError("year out of range 1..9999")
        if mm < 1 or mm > 12:
            raise ValueError("month out of range 1..12")
        if dd < 1 or dd > days_in_month(yy, mm):
            raise ValueError("day out of range")

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    lo, hi = 0, 120000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift_for_diff(a, mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _shift_for_diff(a, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(*shifted)
    return (years, months, days)