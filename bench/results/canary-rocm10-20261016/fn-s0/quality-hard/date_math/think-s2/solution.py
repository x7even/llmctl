import re

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
_MAX_ORDINAL = 3652059


def _is_int(x):
    return type(x) is int


def _check_date_type(t, name='date'):
    if type(t) is not tuple or len(t) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if not all(_is_int(x) for x in t):
        raise TypeError(f"{name} must be a tuple of 3 ints")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError("day out of range")


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MONTH_DAYS[m]


def _days_before_year(y):
    z = y - 1
    return 365 * z + z // 4 - z // 100 + z // 400


def _iso_weeks_in_year(iso_year):
    jan1_wd = (_to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if jan1_wd == 2 and _is_leap(iso_year):
        return 53
    return 52


def _to_ordinal(y, m, d):
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NONLEAP
    return _days_before_year(y) + cum[m - 1] + d


def _from_ordinal(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    day_in_year = n - _days_before_year(y) - 1
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NONLEAP
    lo2, hi2 = 0, 11
    while lo2 < hi2:
        mid2 = (lo2 + hi2 + 1) // 2
        if cum[mid2] <= day_in_year:
            lo2 = mid2
        else:
            hi2 = mid2 - 1
    m = lo2 + 1
    d = day_in_year - cum[lo2] + 1
    return (y, m, d)


def _shift(a, k):
    total = a[0] * 12 + (a[1] - 1) + k
    ny = total // 12
    nm = total % 12 + 1
    nd = min(a[2], _days_in_month(ny, nm))
    return (ny, nm, nd)


def _diff_ordered(a, b):
    K = (b[0] - a[0]) * 12 + (b[1] - a[1])
    if K < 0:
        K = 0
    while _shift(a, K) > b:
        K -= 1
    while _shift(a, K + 1) <= b:
        K += 1
    years, months = divmod(K, 12)
    shifted = _shift(a, K)
    days = _to_ordinal(b[0], b[1], b[2]) - _to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)


def _parse_week_date(iso_y, wk, wd):
    if iso_y < 1 or iso_y > 9999:
        raise ValueError("iso year out of range")
    max_wk = _iso_weeks_in_year(iso_y)
    if wk < 1 or wk > max_wk:
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    jan4_ord = _to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_thursday_ord = jan4_ord - jan4_wd + 3
    first_monday_ord = first_thursday_ord - 3
    target_ord = first_monday_ord + (wk - 1) * 7 + (wd - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise ValueError("date out of range")
    return _from_ordinal(target_ord)


# --- Public API ---

def is_leap(y):
    if not _is_int(y):
        raise TypeError("year must be an int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap(y)


def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("year and month must be ints")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, and day must be ints")
    _check_date_range(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be an int")
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError("ordinal out of range")
    return _from_ordinal(n)


def weekday(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, and day must be ints")
    _check_date_range(y, m, d)
    return (_to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_type(date, 'date')
    if not _is_int(n):
        raise TypeError("n must be an int")
    _check_date_range(date[0], date[1], date[2])
    ord_val = _to_ordinal(date[0], date[1], date[2]) + n
    if ord_val < 1 or ord_val > _MAX_ORDINAL:
        raise OverflowError("resulting date out of range")
    return _from_ordinal(ord_val)


def add_months(date, n):
    _check_date_type(date, 'date')
    if not _is_int(n):
        raise TypeError("n must be an int")
    _check_date_range(date[0], date[1], date[2])
    total = date[0] * 12 + (date[1] - 1) + n
    ny = total // 12
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("resulting year out of range")
    nd = min(date[2], _days_in_month(ny, nm))
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be an int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, and day must be ints")
    _check_date_range(y, m, d)
    ord_val = _to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    iso_wd = wd + 1
    thursday_ord = ord_val - wd + 3
    # find year containing thursday_ord
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < thursday_ord:
            lo = mid
        else:
            hi = mid - 1
    thursday_y = lo
    jan4_ord = _to_ordinal(thursday_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_thursday_ord = jan4_ord - jan4_wd + 3
    week = (thursday_ord - first_thursday_ord) // 7 + 1
    return (thursday_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year) or not _is_int(week) or not _is_int(weekday):
        raise TypeError("iso_year, week, and weekday must be ints")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    max_week = _iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_thursday_ord = jan4_ord - jan4_wd + 3
    first_monday_ord = first_thursday_ord - 3
    target_ord = first_monday_ord + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise OverflowError("resulting date out of range")
    return _from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    # Extended calendar: YYYY-MM-DD (10 chars)
    m = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    # Extended week: YYYY-Www-D (10 chars)
    m = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([1-7])', s)
    if m:
        return _parse_week_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # Basic week: YYYYWwwD (8 chars)
    m = re.fullmatch(r'([0-9]{4})W([0-9]{2})([1-7])', s)
    if m:
        return _parse_week_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # Extended ordinal: YYYY-DDD (8 chars)
    m = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return _from_ordinal(_to_ordinal(y, 1, 1) + doy - 1)

    # Basic ordinal: YYYYDDD (7 chars)
    m = re.fullmatch(r'([0-9]{7})', s)
    if m:
        y, doy = int(m.group(1)[:4]), int(m.group(1)[4:])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return _from_ordinal(_to_ordinal(y, 1, 1) + doy - 1)

    # Basic calendar: YYYYMMDD (8 chars)
    m = re.fullmatch(r'([0-9]{8})', s)
    if m:
        y, mo, d = int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    raise ValueError("invalid date string")


def format_date(date, form):
    _check_date_type(date, 'date')
    _check_date_range(date[0], date[1], date[2])
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("form must be 'calendar', 'ordinal', or 'week'")
    y, m, d = date
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, wk, wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{wk:02d}-{wd}"


def diff(a, b):
    _check_date_type(a, 'a')
    _check_date_type(b, 'b')
    _check_date_range(a[0], a[1], a[2])
    _check_date_range(b[0], b[1], b[2])
    if a > b:
        years, months, days = _diff_ordered(b, a)
        return (-years, -months, -days)
    else:
        return _diff_ordered(a, b)
