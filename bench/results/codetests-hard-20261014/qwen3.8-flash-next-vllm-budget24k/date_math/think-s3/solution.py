"""Proleptic Gregorian calendar arithmetic for years 1–9999 (no datetime/calendar/time imports)."""

# Cumulative days before each month (index 0 = before Jan, index 12 = end of year)
_CUM = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]
_CUM_L = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366]

_MIN_ORD = 1
_MAX_ORD = 3652059


def _is_int(x):
    return type(x) is int


def _check_date_tuple(date, name):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError(f"{name} must be a tuple of 3 ints")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")


def is_leap(y):
    if not _is_int(y):
        raise TypeError("year must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("year and month must be int")
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
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, day must be int")
    _check_date_range(y, m, d)
    y1 = y - 1
    days = 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
    if is_leap(y):
        days += _CUM_L[m - 1]
    else:
        days += _CUM[m - 1]
    days += d
    return days


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be int")
    if n < _MIN_ORD or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    y = (n - 1) * 400 // 146097 + 1
    while to_ordinal(y, 1, 1) > n:
        y -= 1
    while to_ordinal(y + 1, 1, 1) <= n:
        y += 1
    doy = n - to_ordinal(y, 1, 1)
    cum = _CUM_L if is_leap(y) else _CUM
    for m in range(1, 13):
        if doy < cum[m]:
            break
    d = doy - cum[m - 1] + 1
    return (y, m, d)


def weekday(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, day must be int")
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, 'date')
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    _check_date_range(y, m, d)
    o = to_ordinal(y, m, d) + n
    if o < _MIN_ORD or o > _MAX_ORD:
        raise OverflowError("resulting date out of range")
    return from_ordinal(o)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError("resulting date out of range")
    max_d = days_in_month(new_y, new_m)
    new_d = d if d <= max_d else max_d
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if jan1_wd == 2 and is_leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("year, month, day must be int")
    _check_date_range(y, m, d)
    o = to_ordinal(y, m, d)
    wd = (o - 1) % 7
    iso_wd = wd + 1
    thu = o + (3 - wd)
    thu_date = from_ordinal(thu)
    iso_yr = thu_date[0]
    jan4 = to_ordinal(iso_yr, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    week1_mon = jan4 - jan4_wd
    cur_mon = o - wd
    iso_wk = (cur_mon - week1_mon) // 7 + 1
    return (iso_yr, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year) or not _is_int(week) or not _is_int(weekday):
        raise TypeError("iso_year, week, weekday must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    if week < 1 or week > iso_weeks_in_year(iso_year):
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4 = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    week1_mon = jan4 - jan4_wd
    target = week1_mon + (week - 1) * 7 + (weekday - 1)
    if target < _MIN_ORD or target > _MAX_ORD:
        raise OverflowError("resulting date out of range")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    def _all_digits(s, start, length):
        for i in range(start, start + length):
            if s[i] < '0' or s[i] > '9':
                return False
        return True

    def _pint(s, start, length):
        return int(s[start:start + length])

    n = len(s)

    if n == 10:
        if s[4] != '-':
            raise ValueError("invalid format")
        if s[5] == 'W':
            # YYYY-Www-D
            if s[8] != '-':
                raise ValueError("invalid format")
            if not _all_digits(s, 0, 4) or not _all_digits(s, 6, 2) or not _all_digits(s, 9, 1):
                raise ValueError("invalid format")
            yr = _pint(s, 0, 4)
            wk = _pint(s, 6, 2)
            wd = _pint(s, 9, 1)
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if wk < 1 or wk > iso_weeks_in_year(yr):
                raise ValueError("week out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            try:
                result = from_iso_week(yr, wk, wd)
            except OverflowError:
                raise ValueError("date out of range")
            return result
        else:
            # YYYY-MM-DD
            if s[7] != '-':
                raise ValueError("invalid format")
            if not _all_digits(s, 0, 4) or not _all_digits(s, 5, 2) or not _all_digits(s, 8, 2):
                raise ValueError("invalid format")
            yr = _pint(s, 0, 4)
            mo = _pint(s, 5, 2)
            dy = _pint(s, 8, 2)
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if mo < 1 or mo > 12:
                raise ValueError("month out of range")
            if dy < 1 or dy > days_in_month(yr, mo):
                raise ValueError("day out of range")
            return (yr, mo, dy)

    elif n == 8:
        if s[4] == '-':
            # YYYY-DDD
            if not _all_digits(s, 0, 4) or not _all_digits(s, 5, 3):
                raise ValueError("invalid format")
            yr = _pint(s, 0, 4)
            doy = _pint(s, 5, 3)
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            max_doy = 366 if is_leap(yr) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError("day of year out of range")
            return from_ordinal(to_ordinal(yr, 1, 1) + doy - 1)
        elif s[4] == 'W':
            # YYYYWwwD
            if not _all_digits(s, 0, 4) or not _all_digits(s, 5, 2) or not _all_digits(s, 7, 1):
                raise ValueError("invalid format")
            yr = _pint(s, 0, 4)
            wk = _pint(s, 5, 2)
            wd = _pint(s, 7, 1)
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if wk < 1 or wk > iso_weeks_in_year(yr):
                raise ValueError("week out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            try:
                result = from_iso_week(yr, wk, wd)
            except OverflowError:
                raise ValueError("date out of range")
            return result
        else:
            # YYYYMMDD
            if not _all_digits(s, 0, 8):
                raise ValueError("invalid format")
            yr = _pint(s, 0, 4)
            mo = _pint(s, 4, 2)
            dy = _pint(s, 6, 2)
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if mo < 1 or mo > 12:
                raise ValueError("month out of range")
            if dy < 1 or dy > days_in_month(yr, mo):
                raise ValueError("day out of range")
            return (yr, mo, dy)

    elif n == 7:
        # YYYYDDD
        if not _all_digits(s, 0, 7):
            raise ValueError("invalid format")
        yr = _pint(s, 0, 4)
        doy = _pint(s, 4, 3)
        if yr < 1 or yr > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if is_leap(yr) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return from_ordinal(to_ordinal(yr, 1, 1) + doy - 1)

    else:
        raise ValueError("invalid format")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid format")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iso_yr, iso_wk, iso_wd = iso_week(y, m, d)
        return f"{iso_yr:04d}-W{iso_wk:02d}-{iso_wd}"


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ya, ma, da = a
    yb, mb, db = b
    _check_date_range(ya, ma, da)
    _check_date_range(yb, mb, db)
    oa = to_ordinal(ya, ma, da)
    ob = to_ordinal(yb, mb, db)
    if oa == ob:
        return (0, 0, 0)
    if oa > ob:
        neg = diff(b, a)
        return (-neg[0], -neg[1], -neg[2])
    # a < b: find largest K >= 0 with add_months(a, K) <= b
    lo, hi = 0, (yb - ya) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            shifted = add_months(a, mid)
        except OverflowError:
            hi = mid - 1
            continue
        if to_ordinal(*shifted) <= ob:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = ob - to_ordinal(*shifted)
    return (years, months, days)
