import re

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTH_PREFIX = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_MAX_ORDINAL = 3652059


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_before_year(y):
    y1 = y - 1
    return 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400


def _check_int(v, name):
    if type(v) is not int:
        raise TypeError(f"{name} must be an int, got {type(v).__name__}")


def _check_date_tuple(date, name):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _validate_date(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    dim = 29 if (m == 2 and _is_leap(y)) else _MONTH_DAYS[m - 1]
    if d < 1 or d > dim:
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m:02d}")


def is_leap(y):
    _check_int(y, "y")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if m == 2 and _is_leap(y):
        return 29
    return _MONTH_DAYS[m - 1]


def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate_date(y, m, d)
    days = _days_before_year(y)
    days += _MONTH_PREFIX[m - 1]
    if m > 2 and _is_leap(y):
        days += 1
    days += d
    return days


def from_ordinal(n):
    _check_int(n, "n")
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        if _days_before_year(mid + 1) <= n:
            lo = mid + 1
        else:
            hi = mid
    y = lo
    doy = n - _days_before_year(y)
    leap = _is_leap(y)
    for m in range(1, 13):
        cum = _MONTH_PREFIX[m] + (1 if m >= 2 and leap else 0)
        if doy <= cum:
            prev = _MONTH_PREFIX[m - 1] + (1 if m - 1 >= 2 and leap else 0)
            d = doy - prev
            return (y, m, d)
    raise ValueError("internal error")  # unreachable


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _validate_date(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {ord_val} out of range 1..{_MAX_ORDINAL}")
    return from_ordinal(ord_val)


def add_months(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _validate_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total >= 9999 * 12:
        raise OverflowError("result date out of range 1..9999")
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(d, days_in_month(ny, nm))
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if wd == 3 or (_is_leap(iso_year) and wd == 2):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate_date(y, m, d)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    iso_wd = wd + 1
    jan4_ord = to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    week = (ord_val - monday_w1) // 7 + 1
    if week < 1:
        iso_y = y - 1
        iso_w = iso_weeks_in_year(iso_y)
    elif week > iso_weeks_in_year(y):
        iso_y = y + 1
        iso_w = 1
    else:
        iso_y = y
        iso_w = week
    return (iso_y, iso_w, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw} for ISO year {iso_year}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target_ord = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {target_ord} out of range 1..{_MAX_ORDINAL}")
    return from_ordinal(target_ord)


_D = r'[0-9]'
_RE_EXT_CAL = re.compile(rf'^{_D}{{4}}-{_D}{{2}}-{_D}{{2}}\Z')
_RE_BAS_CAL = re.compile(rf'^{_D}{{8}}\Z')
_RE_EXT_ORD = re.compile(rf'^{_D}{{4}}-{_D}{{3}}\Z')
_RE_BAS_ORD = re.compile(rf'^{_D}{{7}}\Z')
_RE_EXT_WK = re.compile(rf'^{_D}{{4}}-W{_D}{{2}}-{_D}\Z')
_RE_BAS_WK = re.compile(rf'^{_D}{{4}}W{_D}{{2}}{_D}\Z')


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    # Extended calendar: YYYY-MM-DD
    if _RE_EXT_CAL.match(s):
        y = int(s[0:4]); mo = int(s[5:7]); d = int(s[8:10])
        _validate_date(y, mo, d)
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD
    if _RE_EXT_ORD.match(s):
        y = int(s[0:4]); doy = int(s[5:8])
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    # Extended week: YYYY-Www-D
    if _RE_EXT_WK.match(s):
        y = int(s[0:4]); wk = int(s[6:8]); wd = int(s[9])
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        nw = iso_weeks_in_year(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw} for ISO year {y}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date {s!r} out of supported range")

    # Basic calendar: YYYYMMDD
    if _RE_BAS_CAL.match(s):
        y = int(s[0:4]); mo = int(s[4:6]); d = int(s[6:8])
        _validate_date(y, mo, d)
        return (y, mo, d)

    # Basic week: YYYYWwwD
    if _RE_BAS_WK.match(s):
        y = int(s[0:4]); wk = int(s[5:7]); wd = int(s[7])
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        nw = iso_weeks_in_year(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw} for ISO year {y}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date {s!r} out of supported range")

    # Basic ordinal: YYYYDDD
    if _RE_BAS_ORD.match(s):
        y = int(s[0:4]); doy = int(s[4:7])
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _validate_date(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a str, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"
    else:
        raise ValueError(f"invalid form: {form!r}")


def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _validate_date(ay, am, ad)
    _validate_date(by, bm, bd)
    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    lo = 0
    hi = (9999 - ay) * 12 + (12 - am)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if add_months(a, mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(*shifted)
    return (years, months, days)
