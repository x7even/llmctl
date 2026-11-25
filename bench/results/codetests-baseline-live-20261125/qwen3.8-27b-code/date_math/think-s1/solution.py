import re


def _check_int(x, name='value'):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date(date, name='date'):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(v).__name__}")


def _check_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= days_in_month(y, m)):
        raise ValueError(f"day {d} out of range for {y:04d}-{m:02d}")


def _days_before_month(y, m):
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    days = cum[m - 1]
    if m > 2 and is_leap(y):
        days += 1
    return days


def _doy_to_date(y, doy):
    md = (31, 28 + (1 if is_leap(y) else 0), 31, 30, 31, 30,
          31, 31, 30, 31, 30, 31)
    for m in range(1, 13):
        if doy <= md[m - 1]:
            return (y, m, doy)
        doy -= md[m - 1]
    raise ValueError("internal error")


def is_leap(y):
    _check_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if m == 2:
        return 29 if is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    yp = y - 1
    days = 365 * yp + yp // 4 - yp // 100 + yp // 400
    days += _days_before_month(y, m)
    days += d
    return days


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    # Estimate year using 400-year cycle (146097 days)
    y = (n - 1) * 400 // 146097 + 1
    # Adjust (at most 1-2 iterations)
    while y > 1 and 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400 + 1 > n:
        y -= 1
    while y < 9999 and 365 * y + y // 4 - y // 100 + y // 400 + 1 <= n:
        y += 1
    day_of_year = n - (365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400 + 1) + 1
    return _doy_to_date(y, day_of_year)


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
    ord_result = to_ordinal(y, m, d) + n
    if ord_result < 1 or ord_result > 3652059:
        raise OverflowError(f"result out of range for add_days")
    return from_ordinal(ord_result)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError(f"target year {ty} out of range 1..9999")
    td = d if d <= days_in_month(ty, tm) else days_in_month(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = weekday(iso_year, 1, 1)
    if wd == 3:
        return 53
    if wd == 2 and is_leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    ord_val = to_ordinal(y, m, d)
    iso_wd = (ord_val - 1) % 7 + 1  # Monday=1 .. Sunday=7
    # Thursday of this week
    thu_ord = ord_val - (iso_wd - 1) + 3
    # ISO year is the year containing that Thursday
    iso_y = from_ordinal(thu_ord)[0]
    # First Thursday of iso_y
    jan1_wd = weekday(iso_y, 1, 1)  # 0=Mon
    first_thu_day = (3 - jan1_wd) % 7 + 1
    first_thu_ord = to_ordinal(iso_y, 1, first_thu_day)
    iso_wk = (thu_ord - first_thu_ord) // 7 + 1
    return (iso_y, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday_):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday_, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week} for ISO year {iso_year}")
    if not (1 <= weekday_ <= 7):
        raise ValueError(f"weekday {weekday_} out of range 1..7")
    # Find first Thursday of iso_year
    jan1_wd = weekday(iso_year, 1, 1)
    first_thu_day = (3 - jan1_wd) % 7 + 1
    first_thu_ord = to_ordinal(iso_year, 1, first_thu_day)
    # Monday of the given week
    mon_ord = first_thu_ord - 3 + (week - 1) * 7
    # Target day
    target_ord = mon_ord + (weekday_ - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError(f"result out of range for from_iso_week")
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    # Extended calendar: YYYY-MM-DD (10 chars)
    m = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
    if m:
        y, mm, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_valid_date(y, mm, d)
        return (y, mm, d)

    # Extended ordinal: YYYY-DDD (8 chars with hyphen)
    m = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _doy_to_date(y, doy)

    # Extended week: YYYY-Www-D (11 chars)
    m = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        if not (1 <= w <= iso_weeks_in_year(y)):
            raise ValueError(f"week {w} out of range for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError(f"date out of range: {s}")

    # Basic week: YYYYWwwD (9 chars)
    m = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        if not (1 <= w <= iso_weeks_in_year(y)):
            raise ValueError(f"week {w} out of range for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError(f"date out of range: {s}")

    # 8-digit string: basic calendar (YYYYMMDD) or basic ordinal (YYYYDDD)
    m = re.fullmatch(r'([0-9]{8})', s)
    if m:
        s8 = m.group(1)
        y = int(s8[0:4])
        # Try basic calendar first
        mm = int(s8[4:6])
        d = int(s8[6:8])
        if 1 <= y <= 9999 and 1 <= mm <= 12:
            if 1 <= d <= days_in_month(y, mm):
                return (y, mm, d)
        # Try basic ordinal
        doy = int(s8[4:8])
        if 1 <= y <= 9999:
            max_doy = 366 if is_leap(y) else 365
            if 1 <= doy <= max_doy:
                return _doy_to_date(y, doy)
        raise ValueError(f"invalid date string: {s}")

    raise ValueError(f"invalid date string: {s}")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_valid_date(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a str, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"
    else:
        raise ValueError(f"invalid form: {form!r}")


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ya, ma, da = a
    yb, mb, db = b
    _check_valid_date(ya, ma, da)
    _check_valid_date(yb, mb, db)

    if a > b:
        years, months, days = diff(b, a)
        return (-years, -months, -days)

    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    A = (ya - 1) * 12 + (ma - 1)
    B = (yb - 1) * 12 + (mb - 1)
    clamped_day = da if da <= days_in_month(yb, mb) else days_in_month(yb, mb)
    if clamped_day <= db:
        K = B - A
    else:
        K = B - A - 1

    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = to_ordinal(yb, mb, db) - to_ordinal(*shifted)
    return (years, months, days)
