"""Proleptic-Gregorian calendar arithmetic for years 1 through 9999."""

_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORDINAL = 3652059


def _check_int(v, name='value'):
    if type(v) is not int:
        raise TypeError(f"{name} must be an int, got {type(v).__name__}")


def _check_date_tuple(d, name='date'):
    if type(d) is not tuple or len(d) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, x in enumerate(d):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(x).__name__}")


def _check_date_range(y, m, d):
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if not 1 <= m <= 12:
        raise ValueError(f"month {m} out of range 1..12")
    dim = _MDAYS[m - 1]
    if m == 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        dim = 29
    if not 1 <= d <= dim:
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


def _days_before_year(y):
    y -= 1
    return 365 * y + y // 4 - y // 100 + y // 400


def _days_before_month(y, m):
    total = _CUM[m - 1]
    if m > 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        total += 1
    return total


def _dim(y, m):
    d = _MDAYS[m - 1]
    if m == 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        d = 29
    return d


def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total > 9999 * 12 + 11:
        raise OverflowError("result out of range")
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(d, _dim(ny, nm))
    return (ny, nm, nd)


def is_leap(y):
    _check_int(y, 'y')
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if not 1 <= m <= 12:
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
    if not 1 <= n <= _MAX_ORDINAL:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    m = 1
    while m <= 12:
        dim = _MDAYS[m - 1] + (1 if m == 2 and leap else 0)
        if doy <= dim:
            return (y, m, doy)
        doy -= dim
        m += 1
    raise ValueError("internal error in from_ordinal")


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (_days_before_year(y) + _days_before_month(y, m) + d - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ordinal = _days_before_year(y) + _days_before_month(y, m) + d + n
    if ordinal < 1 or ordinal > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {ordinal} out of range 1..{_MAX_ORDINAL}")
    return from_ordinal(ordinal)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    return _add_months_raw(y, m, d, n)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not 1 <= iso_year <= 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = (_days_before_year(iso_year) + 0) % 7  # weekday of Jan 1
    if wd == 3:
        return 53
    if wd == 2 and iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ordinal = _days_before_year(y) + _days_before_month(y, m) + d
    wd = (ordinal - 1) % 7
    mon_ordinal = ordinal - wd
    thu_ordinal = mon_ordinal + 3
    # Find year of thu_ordinal
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < thu_ordinal:
            lo = mid
        else:
            hi = mid - 1
    iso_y = lo
    jan4 = _days_before_year(iso_y) + 3
    jan4_wd = (jan4 - 1) % 7
    first_mon = jan4 - jan4_wd
    week = (mon_ordinal - first_mon) // 7 + 1
    iso_wd = wd + 1
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday_val):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday_val, 'weekday')
    if not 1 <= iso_year <= 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not 1 <= week <= max_week:
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not 1 <= weekday_val <= 7:
        raise ValueError(f"weekday {weekday_val} out of range 1..7")
    jan4 = _days_before_year(iso_year) + 3
    jan4_wd = (jan4 - 1) % 7
    first_mon = jan4 - jan4_wd
    ordinal = first_mon + (week - 1) * 7 + (weekday_val - 1)
    if ordinal < 1 or ordinal > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {ordinal} out of range")
    return from_ordinal(ordinal)


def _parse_digits(s, start, end):
    for i in range(start, end):
        c = s[i]
        if c < '0' or c > '9':
            raise ValueError(f"invalid character {c!r} in date string")
    return int(s[start:end])


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")
    n = len(s)

    if n == 10:
        if s[4] != '-' or s[7] != '-':
            raise ValueError(f"invalid date string: {s!r}")
        year = _parse_digits(s, 0, 4)
        if s[5] == 'W':
            # YYYY-Www-D
            wk = _parse_digits(s, 6, 8)
            c9 = s[9]
            if c9 < '1' or c9 > '7':
                raise ValueError(f"invalid weekday in date string: {s!r}")
            wd = c9 - '0'
            if not 1 <= year <= 9999:
                raise ValueError(f"year {year} out of range")
            if not 1 <= wk <= 53:
                raise ValueError(f"week {wk} out of range")
            if wk > iso_weeks_in_year(year):
                raise ValueError(f"week {wk} invalid for ISO year {year}")
            try:
                return from_iso_week(year, wk, wd)
            except OverflowError:
                raise ValueError(f"date out of range: {s!r}")
        else:
            # YYYY-MM-DD
            month = _parse_digits(s, 5, 7)
            day = _parse_digits(s, 8, 10)
            if not 1 <= year <= 9999:
                raise ValueError(f"year {year} out of range")
            if not 1 <= month <= 12:
                raise ValueError(f"month {month} out of range")
            if not 1 <= day <= _dim(year, month):
                raise ValueError(f"day {day} out of range")
            return (year, month, day)

    elif n == 8:
        if s[4] == '-':
            # YYYY-DDD
            year = _parse_digits(s, 0, 4)
            doy = _parse_digits(s, 5, 8)
            if not 1 <= year <= 9999:
                raise ValueError(f"year {year} out of range")
            max_doy = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
            if not 1 <= doy <= max_doy:
                raise ValueError(f"day of year {doy} out of range")
            return from_ordinal(_days_before_year(year) + doy)
        elif s[4] == 'W':
            # YYYYWwwD
            year = _parse_digits(s, 0, 4)
            wk = _parse_digits(s, 5, 7)
            c7 = s[7]
            if c7 < '1' or c7 > '7':
                raise ValueError(f"invalid weekday in date string: {s!r}")
            wd = c7 - '0'
            if not 1 <= year <= 9999:
                raise ValueError(f"year {year} out of range")
            if not 1 <= wk <= 53:
                raise ValueError(f"week {wk} out of range")
            if wk > iso_weeks_in_year(year):
                raise ValueError(f"week {wk} invalid for ISO year {year}")
            try:
                return from_iso_week(year, wk, wd)
            except OverflowError:
                raise ValueError(f"date out of range: {s!r}")
        else:
            # YYYYMMDD
            year = _parse_digits(s, 0, 4)
            month = _parse_digits(s, 4, 6)
            day = _parse_digits(s, 6, 8)
            if not 1 <= year <= 9999:
                raise ValueError(f"year {year} out of range")
            if not 1 <= month <= 12:
                raise ValueError(f"month {month} out of range")
            if not 1 <= day <= _dim(year, month):
                raise ValueError(f"day {day} out of range")
            return (year, month, day)

    elif n == 7:
        # YYYYDDD
        year = _parse_digits(s, 0, 4)
        doy = _parse_digits(s, 4, 7)
        if not 1 <= year <= 9999:
            raise ValueError(f"year {year} out of range")
        max_doy = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
        if not 1 <= doy <= max_doy:
            raise ValueError(f"day of year {doy} out of range")
        return from_ordinal(_days_before_year(year) + doy)

    else:
        raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)

    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")

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

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    a_total = (ay - 1) * 12 + (am - 1)
    b_total = (by - 1) * 12 + (bm - 1)
    hi = b_total - a_total + 12
    max_total = 9999 * 12 + 11
    cap = max_total - a_total
    if hi > cap:
        hi = cap
    lo = 0

    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _add_months_raw(ay, am, ad, mid)
        if shifted <= b:
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_raw(ay, am, ad, K)
    days = (_days_before_year(by) + _days_before_month(by, bm) + bd) - \
           (_days_before_year(shifted[0]) + _days_before_month(shifted[0], shifted[1]) + shifted[2])
    return (years, months, days)