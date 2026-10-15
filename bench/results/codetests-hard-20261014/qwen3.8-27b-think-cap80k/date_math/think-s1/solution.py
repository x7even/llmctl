import re

# --- Internal helpers (no public API) ---

_MONTH_DAYS_COMMON = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTH_DAYS_LEAP = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# Cumulative days before each month (index 0 = before Jan, index 11 = before Dec)
_CUM_COMMON = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)

_MAX_ORDINAL = 3652059  # ordinal of (9999, 12, 31)


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date_tuple(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(date[i]).__name__}")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    dim = _days_in_month_raw(y, m)
    if d < 1 or d > dim:
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m:02d}")


def _days_in_month_raw(y, m):
    if m == 2 and _is_leap_raw(y):
        return 29
    return _MONTH_DAYS_COMMON[m - 1]


def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_before_year(y):
    """Number of days in years 1..y-1 (i.e., days before Jan 1 of year y)."""
    n = y - 1
    return n * 365 + n // 4 - n // 100 + n // 400


def _to_ordinal_raw(y, m, d):
    cum = _CUM_LEAP if _is_leap_raw(y) else _CUM_COMMON
    return _days_before_year(y) + cum[m - 1] + d


def _from_ordinal_raw(n):
    """n is 1-based. Returns (y, m, d)."""
    # Binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) <= n - 1:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    day_in_year = n - 1 - _days_before_year(y)  # 0-based
    cum = _CUM_LEAP if _is_leap_raw(y) else _CUM_COMMON
    # Find month (at most 12 iterations)
    m = 1
    while m < 12 and day_in_year >= cum[m]:
        m += 1
    d = day_in_year - cum[m - 1] + 1
    return (y, m, d)


def _add_months_raw(date, k):
    """Compute add_months without type/range checks. Assumes valid date and valid k
    such that target year is in 1..9999."""
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + k
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = d if d <= _days_in_month_raw(ty, tm) else _days_in_month_raw(ty, tm)
    return (ty, tm, td)


# --- Regex patterns for parse ---
_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BASIC_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BASIC_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BASIC_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


# --- Public API ---

def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _days_in_month_raw(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _to_ordinal_raw(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    return _from_ordinal_raw(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (_to_ordinal_raw(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ord_result = _to_ordinal_raw(y, m, d) + n
    if ord_result < 1 or ord_result > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {ord_result} out of range 1..{_MAX_ORDINAL}")
    return _from_ordinal_raw(ord_result)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError(f"target year {ty} out of range 1..9999")
    td = d if d <= _days_in_month_raw(ty, tm) else _days_in_month_raw(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = (_to_ordinal_raw(iso_year, 1, 1) - 1) % 7  # 0=Mon..6=Sun
    if wd == 3:  # Thursday
        return 53
    if _is_leap_raw(iso_year) and wd == 2:  # Wednesday in leap year
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ord_ = _to_ordinal_raw(y, m, d)
    wd = (ord_ - 1) % 7  # 0=Mon..6=Sun
    iso_weekday = wd + 1  # 1=Mon..7=Sun
    monday_ord = ord_ - wd
    thursday_ord = monday_ord + 3
    iso_year = _from_ordinal_raw(thursday_ord)[0]
    # Monday of week 1 of iso_year
    jan4_ord = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    iso_week_num = (monday_ord - week1_monday) // 7 + 1
    return (iso_year, iso_week_num, iso_weekday)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError(f"week {week} out of range 1..{max_week} for ISO year {iso_year}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    # Compute the ordinal
    jan4_ord = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target_ord = week1_monday + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {target_ord} out of range 1..{_MAX_ORDINAL}")
    return _from_ordinal_raw(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y = int(m.group(1))
        mo = int(m.group(2))
        d = int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range 1..12")
        if d < 1 or d > _days_in_month_raw(y, mo):
            raise ValueError(f"day {d} invalid for {y}-{mo:02d}")
        return (y, mo, d)

    m = _RE_BASIC_CAL.fullmatch(s)
    if m:
        y = int(m.group(1))
        mo = int(m.group(2))
        d = int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range 1..12")
        if d < 1 or d > _days_in_month_raw(y, mo):
            raise ValueError(f"day {d} invalid for {y}-{mo:02d}")
        return (y, mo, d)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y = int(m.group(1))
        doy = int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ordinal_raw(_days_before_year(y) + doy)

    m = _RE_BASIC_ORD.fullmatch(s)
    if m:
        y = int(m.group(1))
        doy = int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ordinal_raw(_days_before_year(y) + doy)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y = int(m.group(1))
        wk = int(m.group(2))
        wd = int(m.group(3))
        if y < 1:
            raise ValueError(f"ISO year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range 1..{max_wk} for ISO year {y}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_ord = _to_ordinal_raw(y, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        week1_monday = jan4_ord - jan4_wd
        target_ord = week1_monday + (wk - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > _MAX_ORDINAL:
            raise ValueError(f"date out of supported range")
        return _from_ordinal_raw(target_ord)

    m = _RE_BASIC_WK.fullmatch(s)
    if m:
        y = int(m.group(1))
        wk = int(m.group(2))
        wd = int(m.group(3))
        if y < 1:
            raise ValueError(f"ISO year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range 1..{max_wk} for ISO year {y}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_ord = _to_ordinal_raw(y, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        week1_monday = jan4_ord - jan4_wd
        target_ord = week1_monday + (wk - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > _MAX_ORDINAL:
            raise ValueError(f"date out of supported range")
        return _from_ordinal_raw(target_ord)

    raise ValueError(f"unrecognized date string: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)

    if form != 'calendar' and form != 'ordinal' and form != 'week':
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week', got {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        cum = _CUM_LEAP if _is_leap_raw(y) else _CUM_COMMON
        doy = cum[m - 1] + d
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    ord_a = _to_ordinal_raw(ay, am, ad)
    ord_b = _to_ordinal_raw(by, bm, bd)

    if ord_a <= ord_b:
        # Find largest K >= 0 such that _add_months_raw(a, K) <= b
        hi = (by - ay) * 12 + 12 - am
        if hi < 0:
            hi = 0
        lo = 0
        while lo < hi:
            mid = (lo + hi + 1) // 2
            shifted = _add_months_raw(a, mid)
            if shifted <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _add_months_raw(a, K)
        days = ord_b - _to_ordinal_raw(*shifted)
        return (years, months, days)
    else:
        y, mo, d = diff(b, a)
        return (-y, -mo, -d)