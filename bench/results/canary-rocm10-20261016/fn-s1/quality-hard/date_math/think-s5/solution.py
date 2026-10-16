"""Proleptic-Gregorian calendar arithmetic for years 1-9999.
Pure integer arithmetic; no datetime/calendar/time/dateutil/email.utils imports.
"""

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTH_CUM = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)

_MIN_ORD = 1
_MAX_ORD = 3652059  # ordinal of (9999, 12, 31)


def _is_int(x):
    return type(x) is int


def _is_date(d):
    return (type(d) is tuple and len(d) == 3
            and type(d[0]) is int and type(d[1]) is int and type(d[2]) is int)


def _validate_date(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")


def _days_before_year(y):
    z = y - 1
    return 365 * z + z // 4 - z // 100 + z // 400


def _days_before_month(y, m):
    r = _MONTH_CUM[m]
    if m > 2 and is_leap(y):
        r += 1
    return r


def is_leap(y):
    if not _is_int(y):
        raise TypeError("year must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("year and month must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if m == 2 and is_leap(y):
        return 29
    return _MONTH_DAYS[m]


def to_ordinal(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, day must be int")
    _validate_date(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be int")
    if n < _MIN_ORD or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    n0 = n - 1
    y = n0 * 400 // 146097 + 1
    if _days_before_year(y) > n0:
        y -= 1
    elif _days_before_year(y + 1) <= n0:
        y += 1
    day_in_year = n0 - _days_before_year(y) + 1
    for m in range(1, 13):
        dim = days_in_month(y, m)
        if day_in_year <= dim:
            return (y, m, day_in_year)
        day_in_year -= dim
    return (y, 12, day_in_year)


def weekday(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, day must be int")
    _validate_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    if not _is_date(date) or not _is_int(n):
        raise TypeError("date must be tuple of 3 ints, n must be int")
    y, m, d = date
    _validate_date(y, m, d)
    ord_ = to_ordinal(y, m, d) + n
    if ord_ < _MIN_ORD or ord_ > _MAX_ORD:
        raise OverflowError("result out of range")
    return from_ordinal(ord_)


def add_months(date, n):
    if not _is_date(date) or not _is_int(n):
        raise TypeError("date must be tuple of 3 ints, n must be int")
    y, m, d = date
    _validate_date(y, m, d)
    total_m = (m - 1) + n
    ty = y + total_m // 12
    tm = total_m % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("target year out of range")
    td = min(d, days_in_month(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    wd = weekday(iso_year, 1, 1)
    if wd == 3:
        return 53
    if wd == 2 and is_leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, day must be int")
    _validate_date(y, m, d)
    ord_ = to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7
    iso_wd = wd + 1
    thu_ord = ord_ + (3 - wd)
    iso_y = from_ordinal(thu_ord)[0]
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_mon = jan4_ord - jan4_wd
    iso_w = (ord_ - week1_mon) // 7 + 1
    return (iso_y, iso_w, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year) or not _is_int(week) or not _is_int(weekday):
        raise TypeError("iso_year, week, weekday must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    if week < 1 or week > iso_weeks_in_year(iso_year):
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_mon = jan4_ord - jan4_wd
    target_ord = week1_mon + (week - 1) * 7 + (weekday - 1)
    if target_ord < _MIN_ORD or target_ord > _MAX_ORD:
        raise OverflowError("result out of range")
    return from_ordinal(target_ord)


def _all_ascii_digits(s, start, end):
    for i in range(start, end):
        c = s[i]
        if c < '0' or c > '9':
            return False
    return True


def _parse_calendar(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")
    return (y, m, d)


def _parse_ordinal(y, doy):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    max_doy = 366 if is_leap(y) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError("day of year out of range")
    m = 1
    while doy > days_in_month(y, m):
        doy -= days_in_month(y, m)
        m += 1
    return (y, m, doy)


def _parse_week(y, w, wd):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if w < 1 or w > 53:
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    if w == 53 and iso_weeks_in_year(y) == 52:
        raise ValueError("week 53 in a 52-week year")
    jan4_ord = to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_mon = jan4_ord - jan4_wd
    target_ord = week1_mon + (w - 1) * 7 + (wd - 1)
    if target_ord < _MIN_ORD or target_ord > _MAX_ORD:
        raise ValueError("date out of range")
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    L = len(s)

    if L == 10:
        if s[4] == '-' and s[5] == 'W':
            # Extended week: YYYY-Www-D
            if not (_all_ascii_digits(s, 0, 4) and _all_ascii_digits(s, 6, 8)
                    and _all_ascii_digits(s, 9, 10)):
                raise ValueError("invalid week date")
            return _parse_week(int(s[0:4]), int(s[6:8]), int(s[9]))
        elif s[4] == '-':
            # Extended calendar: YYYY-MM-DD
            if not (_all_ascii_digits(s, 0, 4) and _all_ascii_digits(s, 5, 7)
                    and _all_ascii_digits(s, 8, 10)):
                raise ValueError("invalid calendar date")
            return _parse_calendar(int(s[0:4]), int(s[5:7]), int(s[8:10]))
        else:
            raise ValueError("invalid date format")

    elif L == 8:
        if s[4] == '-':
            # Extended ordinal: YYYY-DDD
            if not (_all_ascii_digits(s, 0, 4) and _all_ascii_digits(s, 5, 8)):
                raise ValueError("invalid ordinal date")
            return _parse_ordinal(int(s[0:4]), int(s[5:8]))
        elif s[4] == 'W':
            # Basic week: YYYYWwwD
            if not (_all_ascii_digits(s, 0, 4) and _all_ascii_digits(s, 5, 7)
                    and _all_ascii_digits(s, 7, 8)):
                raise ValueError("invalid week date")
            return _parse_week(int(s[0:4]), int(s[5:7]), int(s[7]))
        else:
            # Basic calendar: YYYYMMDD
            if not _all_ascii_digits(s, 0, 8):
                raise ValueError("invalid calendar date")
            return _parse_calendar(int(s[0:4]), int(s[4:6]), int(s[6:8]))

    elif L == 7:
        # Basic ordinal: YYYYDDD
        if not (_all_ascii_digits(s, 0, 4) and _all_ascii_digits(s, 4, 7)):
            raise ValueError("invalid ordinal date")
        return _parse_ordinal(int(s[0:4]), int(s[4:7]))

    else:
        raise ValueError("invalid date format")


def format_date(date, form):
    if not _is_date(date):
        raise TypeError("date must be tuple of 3 ints")
    y, m, d = date
    _validate_date(y, m, d)
    if type(form) is not str:
        raise ValueError("form must be a string")
    if form == 'calendar':
        return "%04d-%02d-%02d" % (y, m, d)
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return "%04d-%03d" % (y, doy)
    elif form == 'week':
        iy, iw, iwd = iso_week(y, m, d)
        return "%04d-W%02d-%d" % (iy, iw, iwd)
    else:
        raise ValueError("invalid form")


def diff(a, b):
    if not _is_date(a) or not _is_date(b):
        raise TypeError("dates must be tuples of 3 ints")
    _validate_date(a[0], a[1], a[2])
    _validate_date(b[0], b[1], b[2])
    if a == b:
        return (0, 0, 0)
    if a > b:
        yr, mo, dy = diff(b, a)
        return (-yr, -mo, -dy)
    # a < b
    lo = 0
    hi = (b[0] - a[0]) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            shifted = add_months(a, mid)
        except OverflowError:
            hi = mid - 1
            continue
        if shifted <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = to_ordinal(b[0], b[1], b[2]) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
