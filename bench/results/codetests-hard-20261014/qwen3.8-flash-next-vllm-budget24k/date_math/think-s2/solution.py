"""Proleptic-Gregorian calendar arithmetic for years 1-9999.

No datetime/calendar/time/dateutil imports. Pure integer arithmetic.
"""

# Cumulative days before each month (index 0 = before Jan, index 12 = end of year)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)

_MAX_ORDINAL = 3652059  # (9999, 12, 31)


def _is_int(x):
    return type(x) is int


def _check_date_arg(d):
    if type(d) is not tuple or len(d) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    if type(d[0]) is not int or type(d[1]) is not int or type(d[2]) is not int:
        raise TypeError("date must be a tuple of 3 ints")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")


def is_leap(y):
    if not _is_int(y):
        raise TypeError("year must be an int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def days_in_month(y, m):
    if not _is_int(y):
        raise TypeError("year must be an int")
    if not _is_int(m):
        raise TypeError("month must be an int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if m == 2:
        return 29 if is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def to_ordinal(y, m, d):
    if not _is_int(y):
        raise TypeError("year must be an int")
    if not _is_int(m):
        raise TypeError("month must be an int")
    if not _is_int(d):
        raise TypeError("day must be an int")
    _check_date_range(y, m, d)
    y1 = y - 1
    days = 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
    if is_leap(y):
        days += _CUM_LEAP[m - 1]
    else:
        days += _CUM[m - 1]
    days += d
    return days


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("ordinal must be an int")
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError("ordinal out of range")
    n -= 1  # 0-based
    n400, n = divmod(n, 146097)
    n100, n = divmod(n, 36524)
    if n100 == 4:
        n100 = 3
        n = 36524
    n4, n = divmod(n, 1461)
    n1, n = divmod(n, 365)
    if n1 == 4:
        n1 = 3
        n = 365
    year = n400 * 400 + n100 * 100 + n4 * 4 + n1 + 1
    # n is 0-based day-of-year
    if is_leap(year):
        cum = _CUM_LEAP
    else:
        cum = _CUM
    lo, hi = 0, 11
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if cum[mid] <= n:
            lo = mid
        else:
            hi = mid - 1
    month = lo + 1
    day = n - cum[lo] + 1
    return (year, month, day)


def weekday(y, m, d):
    if not _is_int(y):
        raise TypeError("year must be an int")
    if not _is_int(m):
        raise TypeError("month must be an int")
    if not _is_int(d):
        raise TypeError("day must be an int")
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_arg(date)
    if not _is_int(n):
        raise TypeError("n must be an int")
    y, m, d = date
    _check_date_range(y, m, d)
    ordinal = to_ordinal(y, m, d) + n
    if ordinal < 1 or ordinal > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(ordinal)


def add_months(date, n):
    _check_date_arg(date)
    if not _is_int(n):
        raise TypeError("n must be an int")
    y, m, d = date
    _check_date_range(y, m, d)
    total_months = (y - 1) * 12 + (m - 1) + n
    new_year = total_months // 12 + 1
    new_month = total_months % 12 + 1
    if new_year < 1 or new_year > 9999:
        raise OverflowError("target year out of range")
    max_day = days_in_month(new_year, new_month)
    new_day = d if d <= max_day else max_day
    return (new_year, new_month, new_day)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be an int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    # weekday of Jan 1: Mon=0..Sun=6
    w = (to_ordinal(iso_year, 1, 1) - 1) % 7
    # 53 weeks iff Jan 1 is Thursday (3), or leap year and Jan 1 is Wednesday (2)
    if w == 3:
        return 53
    if w == 2 and is_leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    if not _is_int(y):
        raise TypeError("year must be an int")
    if not _is_int(m):
        raise TypeError("month must be an int")
    if not _is_int(d):
        raise TypeError("day must be an int")
    _check_date_range(y, m, d)
    ordinal = to_ordinal(y, m, d)
    wd = (ordinal - 1) % 7  # Mon=0..Sun=6
    iso_wd = wd + 1  # Mon=1..Sun=7
    # Jan 4 is always in ISO week 1
    o4 = to_ordinal(y, 1, 4)
    w4 = (o4 - 1) % 7  # weekday of Jan 4
    mon_w1 = o4 - w4  # Monday of ISO week 1
    mon_cur = ordinal - wd  # Monday of current week
    week_num = (mon_cur - mon_w1) // 7 + 1
    if week_num < 1:
        prev_y = y - 1
        return (prev_y, iso_weeks_in_year(prev_y), iso_wd)
    if week_num > iso_weeks_in_year(y):
        return (y + 1, 1, iso_wd)
    return (y, week_num, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be an int")
    if not _is_int(week):
        raise TypeError("week must be an int")
    if not _is_int(weekday):
        raise TypeError("weekday must be an int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    if week < 1 or week > iso_weeks_in_year(iso_year):
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    o4 = to_ordinal(iso_year, 1, 4)
    w4 = (o4 - 1) % 7
    mon_w1 = o4 - w4
    target_ordinal = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target_ordinal < 1 or target_ordinal > _MAX_ORDINAL:
        raise OverflowError("result date out of range")
    return from_ordinal(target_ordinal)


def _parse_digits(s, start, end):
    """Parse ASCII digits in s[start:end], return int. ValueError on non-digit."""
    result = 0
    for i in range(start, end):
        c = s[i]
        if c < '0' or c > '9':
            raise ValueError("invalid character in date string")
        result = result * 10 + (ord(c) - 48)
    return result


def _all_digits(s, start, end):
    for i in range(start, end):
        c = s[i]
        if c < '0' or c > '9':
            return False
    return True


def parse(s):
    if not isinstance(s, str):
        raise TypeError("s must be a str")
    length = len(s)
    if length == 10:
        # Extended calendar YYYY-MM-DD or extended week YYYY-Www-D
        if s[4] != '-':
            raise ValueError("invalid date string")
        if s[5] == 'W':
            # Extended week: YYYY-Www-D
            if s[8] != '-':
                raise ValueError("invalid date string")
            if not _all_digits(s, 0, 4) or not _all_digits(s, 6, 8) or not _all_digits(s, 9, 10):
                raise ValueError("invalid date string")
            iso_y = int(s[0:4])
            wk = int(s[6:8])
            wd = int(s[9])
            return _parse_week_date(iso_y, wk, wd)
        elif s[7] == '-':
            # Extended calendar: YYYY-MM-DD
            if not _all_digits(s, 0, 4) or not _all_digits(s, 5, 7) or not _all_digits(s, 8, 10):
                raise ValueError("invalid date string")
            y = int(s[0:4])
            m = int(s[5:7])
            d = int(s[8:10])
            return _parse_cal_date(y, m, d)
        else:
            raise ValueError("invalid date string")
    elif length == 8:
        if s[4] == '-':
            # Extended ordinal: YYYY-DDD
            if not _all_digits(s, 0, 4) or not _all_digits(s, 5, 8):
                raise ValueError("invalid date string")
            y = int(s[0:4])
            doy = int(s[5:8])
            return _parse_ord_date(y, doy)
        elif s[4] == 'W':
            # Basic week: YYYYWwwD
            if not _all_digits(s, 0, 4) or not _all_digits(s, 5, 7) or not _all_digits(s, 7, 8):
                raise ValueError("invalid date string")
            iso_y = int(s[0:4])
            wk = int(s[5:7])
            wd = int(s[7])
            return _parse_week_date(iso_y, wk, wd)
        else:
            # Basic calendar: YYYYMMDD
            if not _all_digits(s, 0, 8):
                raise ValueError("invalid date string")
            y = int(s[0:4])
            m = int(s[4:6])
            d = int(s[6:8])
            return _parse_cal_date(y, m, d)
    elif length == 7:
        # Basic ordinal: YYYYDDD
        if not _all_digits(s, 0, 7):
            raise ValueError("invalid date string")
        y = int(s[0:4])
        doy = int(s[4:7])
        return _parse_ord_date(y, doy)
    else:
        raise ValueError("invalid date string")


def _parse_cal_date(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")
    return (y, m, d)


def _parse_ord_date(y, doy):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    max_doy = 366 if is_leap(y) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError("day of year out of range")
    # Convert ordinal day to calendar date
    if is_leap(y):
        cum = _CUM_LEAP
    else:
        cum = _CUM
    lo, hi = 0, 11
    n = doy - 1  # 0-based
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if cum[mid] <= n:
            lo = mid
        else:
            hi = mid - 1
    month = lo + 1
    day = n - cum[lo] + 1
    return (y, month, day)


def _parse_week_date(iso_y, wk, wd):
    if iso_y < 1 or iso_y > 9999:
        raise ValueError("iso year out of range")
    if wk < 1 or wk > iso_weeks_in_year(iso_y):
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    o4 = to_ordinal(iso_y, 1, 4)
    w4 = (o4 - 1) % 7
    mon_w1 = o4 - w4
    target_ordinal = mon_w1 + (wk - 1) * 7 + (wd - 1)
    if target_ordinal < 1 or target_ordinal > _MAX_ORDINAL:
        raise ValueError("result date out of range")
    return from_ordinal(target_ordinal)


def format_date(date, form):
    _check_date_arg(date)
    y, m, d = date
    _check_date_range(y, m, d)
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"
    else:
        raise ValueError("form must be 'calendar', 'ordinal', or 'week'")


def diff(a, b):
    _check_date_arg(a)
    _check_date_arg(b)
    ay, am, ad = a
    _check_date_range(ay, am, ad)
    by, bm, bd = b
    _check_date_range(by, bm, bd)
    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    # Binary search
    lo = 0
    hi = (by - ay) * 12 + (bm - am)
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        shifted = add_months(a, mid)
        if shifted <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
