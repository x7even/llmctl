import re


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_str(x, name):
    if type(x) is not str:
        raise TypeError(f"{name} must be a str, got {type(x).__name__}")


def _check_date(x, name):
    if type(x) is not tuple or len(x) != 3 or not all(type(v) is int for v in x):
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")


def _check_year(y):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")


def _check_month(m):
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")


def _check_date_range(y, m, d):
    _check_year(y)
    _check_month(m)
    if not (1 <= d <= _days_in_month(y, m)):
        raise ValueError(f"day {d} out of range for month {m} of year {y}")


def _days_in_month(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_before_year(y):
    """Number of days in years 1..y-1 (i.e., days from (1,1,1) to (y,1,1) exclusive)."""
    y1 = y - 1
    return y1 * 365 + y1 // 4 - y1 // 100 + y1 // 400


def _days_before_month(y, m):
    """Number of days in months 1..m-1 of year y."""
    if m == 1:
        return 0
    # Cumulative days for non-leap: Jan=31, Feb=28, Mar=31, Apr=30, May=31, Jun=30, Jul=31, Aug=31, Sep=30, Oct=31, Nov=30
    cum = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]
    result = cum[m - 1]
    if m > 2 and _is_leap(y):
        result += 1
    return result


def is_leap(y) -> bool:
    _check_int(y, "y")
    _check_year(y)
    return _is_leap(y)


def days_in_month(y, m) -> int:
    _check_int(y, "y")
    _check_int(m, "m")
    _check_year(y)
    _check_month(m)
    return _days_in_month(y, m)


def to_ordinal(y, m, d) -> int:
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n) -> tuple:
    _check_int(n, "n")
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    d0 = n - 1
    # Estimate year
    y = 1 + (d0 * 400) // 146097
    # Adjust (at most 1-2 steps)
    while _days_before_year(y) > d0:
        y -= 1
    while _days_before_year(y + 1) <= d0:
        y += 1
    day_in_year = d0 - _days_before_year(y)  # 0-based
    # Find month
    m = 1
    while m <= 12:
        dim = _days_in_month(y, m)
        if day_in_year < dim:
            break
        day_in_year -= dim
        m += 1
    d = day_in_year + 1
    return (y, m, d)


def weekday(y, m, d) -> int:
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n) -> tuple:
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError(f"result ordinal {ord_val} out of range 1..3652059")
    return from_ordinal(ord_val)


def add_months(date, n) -> tuple:
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    total_months = (y - 1) * 12 + (m - 1) + n
    new_y = total_months // 12 + 1
    new_m = total_months % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError(f"target year {new_y} out of range 1..9999")
    new_d = d if d <= _days_in_month(new_y, new_m) else _days_in_month(new_y, new_m)
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year) -> int:
    _check_int(iso_year, "iso_year")
    _check_year(iso_year)
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7  # Mon=0
    if wd == 3:
        return 53
    if wd == 2 and _is_leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d) -> tuple:
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    n = to_ordinal(y, m, d)
    wd = (n - 1) % 7  # Mon=0
    mon_ord = n - wd  # ordinal of Monday of this week
    # First Monday of ISO year y
    jan4_ord = to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_mon_y = jan4_ord - jan4_wd
    # First Monday of ISO year y+1
    jan4_ord_next = to_ordinal(y + 1, 1, 4)
    jan4_wd_next = (jan4_ord_next - 1) % 7
    first_mon_y1 = jan4_ord_next - jan4_wd_next

    if mon_ord >= first_mon_y1:
        iso_y = y + 1
        first_mon = first_mon_y1
    elif mon_ord < first_mon_y:
        iso_y = y - 1
        # First Monday of ISO year y-1
        jan4_ord_prev = to_ordinal(y - 1, 1, 4)
        jan4_wd_prev = (jan4_ord_prev - 1) % 7
        first_mon = jan4_ord_prev - jan4_wd_prev
    else:
        iso_y = y
        first_mon = first_mon_y

    week = (mon_ord - first_mon) // 7 + 1
    iso_wd = wd + 1  # Mon=1
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday) -> tuple:
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    _check_year(iso_year)
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week} for ISO year {iso_year}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    # Compute first Monday of ISO year
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_mon = jan4_ord - jan4_wd
    ord_val = first_mon + (week - 1) * 7 + (weekday - 1)
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError(f"result ordinal {ord_val} out of range 1..3652059")
    return from_ordinal(ord_val)


def parse(s) -> tuple:
    _check_str(s, "s")

    # Extended calendar: YYYY-MM-DD (10 chars)
    m = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _days_in_month(y, mo)):
            raise ValueError(f"day {d} out of range for month {mo} of year {y}")
        return (y, mo, d)

    # Basic calendar: YYYYMMDD (8 digits)
    m = re.fullmatch(r'([0-9]{4})([0-9]{2})([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _days_in_month(y, mo)):
            raise ValueError(f"day {d} out of range for month {mo} of year {y}")
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD (8 chars with hyphen)
    m = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        ord_val = to_ordinal(y, 1, 1) + doy - 1
        return from_ordinal(ord_val)

    # Basic ordinal: YYYYDDD (7 digits)
    m = re.fullmatch(r'([0-9]{4})([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        ord_val = to_ordinal(y, 1, 1) + doy - 1
        return from_ordinal(ord_val)

    # Extended week: YYYY-Www-D (9 chars)
    m = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"ISO year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk} for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date {s} falls outside supported range")

    # Basic week: YYYYWwwD (7 chars with W)
    m = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"ISO year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk} for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date {s} falls outside supported range")

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form) -> str:
    _check_date(date, "date")
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b) -> tuple:
    _check_date(a, "a")
    _check_date(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if a > b:
        y2, m2, d2 = diff(b, a)
        return (-y2, -m2, -d2)

    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    lo, hi = 0, (by - ay) * 12 + 12
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
    days = to_ordinal(by, bm, bd) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)