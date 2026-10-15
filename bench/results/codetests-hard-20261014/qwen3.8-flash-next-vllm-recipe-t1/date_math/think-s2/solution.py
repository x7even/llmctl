import re

# ---------------------------------------------------------------------------
# Internal constants and helpers
# ---------------------------------------------------------------------------

_MONTH_PREFIX = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
# _MONTH_PREFIX[m] = number of days in months 1 .. m-1 (non-leap)

_CAL_EXT = re.compile(r'\A([0-9]{4})-([0-9]{2})-([0-9]{2})\Z')
_CAL_BAS = re.compile(r'\A([0-9]{8})\Z')
_ORD_EXT = re.compile(r'\A([0-9]{4})-([0-9]{3})\Z')
_ORD_BAS = re.compile(r'\A([0-9]{7})\Z')
_WK_EXT  = re.compile(r'\A([0-9]{4})-W([0-9]{2})-([0-9])\Z')
_WK_BAS  = re.compile(r'\A([0-9]{4})W([0-9]{2})([0-9])\Z')


def _is_int(x):
    return type(x) is int


def _check_date_arg(d, name):
    if type(d) is not tuple:
        raise TypeError(f'{name} must be a tuple')
    if len(d) != 3:
        raise TypeError(f'{name} must have exactly 3 elements')
    for i in range(3):
        if type(d[i]) is not int:
            raise TypeError(f'{name}[{i}] must be int, got {type(d[i]).__name__}')


def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_raw(y, m):
    """days_in_month without range checking."""
    if m == 2:
        return 29 if _is_leap_raw(y) else 28
    return _MONTH_PREFIX[m + 1] - _MONTH_PREFIX[m]


def _dbY(y):
    """Days before year y (= ordinal of Jan-1 of year y minus 1)."""
    yy = y - 1
    return 365 * yy + yy // 4 - yy // 100 + yy // 400


def _dbM(y, m):
    """Days before month m in year y (leap-adjusted)."""
    r = _MONTH_PREFIX[m]
    if m > 2 and _is_leap_raw(y):
        r += 1
    return r


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError('year out of range')
    if m < 1 or m > 12:
        raise ValueError('month out of range')
    if d < 1 or d > _dim_raw(y, m):
        raise ValueError('day out of range')


def _valid_date_full(date):
    _check_date_arg(date, 'date')
    _check_date_range(date[0], date[1], date[2])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    if not _is_int(y):
        raise TypeError('y must be an int')
    if y < 1 or y > 9999:
        raise ValueError('year out of range')
    return _is_leap_raw(y)


def days_in_month(y, m):
    if not _is_int(y):
        raise TypeError('y must be an int')
    if not _is_int(m):
        raise TypeError('m must be an int')
    if y < 1 or y > 9999:
        raise ValueError('year out of range')
    if m < 1 or m > 12:
        raise ValueError('month out of range')
    return _dim_raw(y, m)


def to_ordinal(y, m, d):
    if not _is_int(y):
        raise TypeError('y must be an int')
    if not _is_int(m):
        raise TypeError('m must be an int')
    if not _is_int(d):
        raise TypeError('d must be an int')
    _check_date_range(y, m, d)
    return _dbY(y) + _dbM(y, m) + d


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError('n must be an int')
    if n < 1 or n > 3652059:
        raise ValueError('ordinal out of range')
    # Binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if _dbY(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _dbY(y)  # 1-based day-of-year
    # Binary search for month
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if _dbM(y, mid) < doy:
            lo = mid
        else:
            hi = mid - 1
    m = lo
    d = doy - _dbM(y, m)
    return (y, m, d)


def weekday(y, m, d):
    if not _is_int(y):
        raise TypeError('y must be an int')
    if not _is_int(m):
        raise TypeError('m must be an int')
    if not _is_int(d):
        raise TypeError('d must be an int')
    _check_date_range(y, m, d)
    return (_dbY(y) + _dbM(y, m) + d - 1) % 7


def add_days(date, n):
    _check_date_arg(date, 'date')
    if not _is_int(n):
        raise TypeError('n must be an int')
    _check_date_range(date[0], date[1], date[2])
    ord_val = _dbY(date[0]) + _dbM(date[0], date[1]) + date[2] + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError('resulting date out of range')
    return from_ordinal(ord_val)


def _add_months_raw(date, n):
    """Compute add_months target without range check. Returns (y,m,d) or sentinel."""
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    if ty < 1:
        return (0, 1, 1)
    if ty > 9999:
        return (10000, 1, 1)
    tm = total % 12 + 1
    dim = _dim_raw(ty, tm)
    td = d if d <= dim else dim
    return (ty, tm, td)


def add_months(date, n):
    _check_date_arg(date, 'date')
    if not _is_int(n):
        raise TypeError('n must be an int')
    _check_date_range(date[0], date[1], date[2])
    result = _add_months_raw(date, n)
    if result[0] < 1 or result[0] > 9999:
        raise OverflowError('resulting year out of range')
    return result


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError('iso_year must be an int')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError('iso_year out of range')
    w = (_dbY(iso_year) + 1 - 1) % 7  # weekday of Jan 1: 0=Mon .. 6=Sun
    if w == 3:  # Thursday
        return 53
    if w == 2 and _is_leap_raw(iso_year):  # Wednesday + leap
        return 53
    return 52


def iso_week(y, m, d):
    if not _is_int(y):
        raise TypeError('y must be an int')
    if not _is_int(m):
        raise TypeError('m must be an int')
    if not _is_int(d):
        raise TypeError('d must be an int')
    _check_date_range(y, m, d)
    ord_val = _dbY(y) + _dbM(y, m) + d
    wd = (ord_val - 1) % 7          # 0=Mon .. 6=Sun
    iso_wd = wd + 1                  # 1=Mon .. 7=Sun
    # Thursday of the current week
    thu_ord = ord_val - wd + 3
    # ISO year = year containing that Thursday
    iso_y = from_ordinal(thu_ord)[0]
    # Monday of ISO week 1 (the week containing Jan 4)
    jan4_ord = _dbY(iso_y) + 4
    jan4_wd = (jan4_ord - 1) % 7
    mon1_ord = jan4_ord - jan4_wd
    # Monday of the current week
    mon_ord = ord_val - wd
    week = (mon_ord - mon1_ord) // 7 + 1
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year):
        raise TypeError('iso_year must be an int')
    if not _is_int(week):
        raise TypeError('week must be an int')
    if not _is_int(weekday):
        raise TypeError('weekday must be an int')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError('iso_year out of range')
    if week < 1 or week > iso_weeks_in_year(iso_year):
        raise ValueError('week out of range')
    if weekday < 1 or weekday > 7:
        raise ValueError('weekday out of range')
    jan4_ord = _dbY(iso_year) + 4
    jan4_wd = (jan4_ord - 1) % 7
    mon1_ord = jan4_ord - jan4_wd
    target_ord = mon1_ord + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError('date out of range')
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError('s must be a str')

    # Calendar extended: YYYY-MM-DD
    m = _CAL_EXT.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date_range(y, mo, d)
        return (y, mo, d)

    # Week extended: YYYY-Www-D
    m = _WK_EXT.match(s)
    if m:
        y, w, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError('year out of range')
        if w < 1 or w > iso_weeks_in_year(y):
            raise ValueError('week out of range')
        if d < 1 or d > 7:
            raise ValueError('weekday out of range')
        jan4_ord = _dbY(y) + 4
        jan4_wd = (jan4_ord - 1) % 7
        mon1_ord = jan4_ord - jan4_wd
        target_ord = mon1_ord + (w - 1) * 7 + (d - 1)
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError('date out of range')
        return from_ordinal(target_ord)

    # Calendar basic: YYYYMMDD (8 digits)
    m = _CAL_BAS.match(s)
    if m:
        y, mo, d = int(s[0:4]), int(s[4:6]), int(s[6:8])
        _check_date_range(y, mo, d)
        return (y, mo, d)

    # Ordinal extended: YYYY-DDD (8 chars with hyphen)
    m = _ORD_EXT.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        _check_ordinal_date(y, doy)
        return (y, 1, 1 + doy - 1) if doy <= 31 else _ordinal_to_ymd(y, doy)

    # Week basic: YYYYWwwD (8 chars)
    m = _WK_BAS.match(s)
    if m:
        y, w, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError('year out of range')
        if w < 1 or w > iso_weeks_in_year(y):
            raise ValueError('week out of range')
        if d < 1 or d > 7:
            raise ValueError('weekday out of range')
        jan4_ord = _dbY(y) + 4
        jan4_wd = (jan4_ord - 1) % 7
        mon1_ord = jan4_ord - jan4_wd
        target_ord = mon1_ord + (w - 1) * 7 + (d - 1)
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError('date out of range')
        return from_ordinal(target_ord)

    # Ordinal basic: YYYYDDD (7 digits)
    m = _ORD_BAS.match(s)
    if m:
        y, doy = int(s[0:4]), int(s[4:7])
        _check_ordinal_date(y, doy)
        return _ordinal_to_ymd(y, doy)

    raise ValueError('unrecognized date format')


def _check_ordinal_date(y, doy):
    if y < 1 or y > 9999:
        raise ValueError('year out of range')
    max_doy = 366 if _is_leap_raw(y) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError('day out of range')


def _ordinal_to_ymd(y, doy):
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if _dbM(y, mid) < doy:
            lo = mid
        else:
            hi = mid - 1
    m = lo
    d = doy - _dbM(y, m)
    return (y, m, d)


def format_date(date, form):
    _check_date_arg(date, 'date')
    _check_date_range(date[0], date[1], date[2])
    if form == 'calendar':
        y, m, d = date
        return '%04d-%02d-%02d' % (y, m, d)
    elif form == 'ordinal':
        y, m, d = date
        doy = _dbY(y) + _dbM(y, m) + d - _dbY(y)
        # simpler: doy = _dbM(y, m) + d
        doy = _dbM(y, m) + d
        return '%04d-%03d' % (y,