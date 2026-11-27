import re


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, x in enumerate(date):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _check_valid_date(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m}")


def _dim(y, m):
    """days_in_month without validation (assumes y in 1..9999, m in 1..12)."""
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


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
    _check_valid_date(y, m, d)
    yy = y - 1
    days_before_year = yy * 365 + yy // 4 - yy // 100 + yy // 400
    # cumulative days before month m
    if m <= 2:
        days_before_month = 0
    elif m <= 3:
        days_before_month = 31
    elif m <= 4:
        days_before_month = 31 + (29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28)
    elif m <= 5:
        days_before_month = 31 + _dim(y, 2) + 31
    elif m <= 6:
        days_before_month = 31 + _dim(y, 2) + 31 + 30
    elif m <= 7:
        days_before_month = 31 + _dim(y, 2) + 31 + 30 + 31
    elif m <= 8:
        days_before_month = 31 + _dim(y, 2) + 31 + 30 + 31 + 30
    elif m <= 9:
        days_before_month = 31 + _dim(y, 2) + 31 + 30 + 31 + 30 + 31
    elif m <= 10:
        days_before_month = 31 + _dim(y, 2) + 31 + 30 + 31 + 30 + 31 + 31
    elif m <= 11:
        days_before_month = 31 + _dim(y, 2) + 31 + 30 + 31 + 30 + 31 + 31 + 30
    else:
        days_before_month = 31 + _dim(y, 2) + 31 + 30 + 31 + 30 + 31 + 31 + 30 + 31
    return days_before_year + days_before_month + d


def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    # Binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        yy = mid - 1
        start = yy * 365 + yy // 4 - yy // 100 + yy // 400 + 1
        if start <= n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    yy = y - 1
    start_of_year = yy * 365 + yy // 4 - yy // 100 + yy // 400 + 1
    doy = n - start_of_year + 1
    # Find month and day
    md = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        md[1] = 29
    m = 1
    while doy > md[m - 1]:
        doy -= md[m - 1]
        m += 1
    return (y, m, doy)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    new_ord = to_ordinal(y, m, d) + n
    if new_ord < 1 or new_ord > 3652059:
        raise OverflowError("result out of supported range")
    return from_ordinal(new_ord)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    target_year = total // 12 + 1
    target_month = total % 12 + 1
    if target_year < 1 or target_year > 9999:
        raise OverflowError("result out of supported range")
    target_day = d if d <= _dim(target_year, target_month) else _dim(target_year, target_month)
    return (target_year, target_month, target_day)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0) and jan1_wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    ord_val = to_ordinal(y, m, d)
    iso_wd = (ord_val - 1) % 7 + 1  # 1=Mon..7=Sun
    thursday_ord = ord_val + (4 - iso_wd)
    iso_y = from_ordinal(thursday_ord)[0]
    week1_monday_ord = to_ordinal(iso_y, 1, 4) - (to_ordinal(iso_y, 1, 4) - 1) % 7
    days_since = ord_val - week1_monday_ord
    iso_w = days_since // 7 + 1
    return (iso_y, iso_w, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    week1_monday_ord = to_ordinal(iso_year, 1, 4) - (to_ordinal(iso_year, 1, 4) - 1) % 7
    target_ord = week1_monday_ord + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError("result out of supported range")
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    # Extended calendar: YYYY-MM-DD
    m = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _dim(y, mo):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD
    m = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    # Extended week: YYYY-Www-D
    m = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"iso_year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range")
        week1_monday_ord = to_ordinal(y, 1, 4) - (to_ordinal(y, 1, 4) - 1) % 7
        target_ord = week1_monday_ord + (wk - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError("date out of range")
        return from_ordinal(target_ord)

    # Basic calendar: YYYYMMDD
    m = re.fullmatch(r'([0-9]{4})([0-9]{2})([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _dim(y, mo):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    # Basic ordinal: YYYYDDD
    m = re.fullmatch(r'([0-9]{4})([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    # Basic week: YYYYWwwD
    m = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"iso_year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range")
        week1_monday_ord = to_ordinal(y, 1, 4) - (to_ordinal(y, 1, 4) - 1) % 7
        target_ord = week1_monday_ord + (wk - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError("date out of range")
        return from_ordinal(target_ord)

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_valid_date(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a str, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"
    else:
        raise ValueError(f"invalid form: {form!r}")


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        years, months, days = diff(b, a)
        return (-years, -months, -days)

    # a < b: binary search for largest K >= 0 with add_months(a, K) <= b
    hi = (by - ay) * 12 + (12 - am)
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if add_months(a, mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)