import re

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORDINAL = 3652059


def is_leap(y):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if m == 2 and is_leap(y):
        return 29
    return _MONTH_DAYS[m - 1]


def _days_before_year(y):
    n = y - 1
    return n * 365 + n // 4 - n // 100 + n // 400


def _days_before_month(y, m):
    total = _CUM_MONTH[m - 1]
    if m > 2 and is_leap(y):
        total += 1
    return total


def to_ordinal(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if type(d) is not int:
        raise TypeError("d must be an int")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    if type(n) is not int:
        raise TypeError("n must be an int")
    if n < 1 or n > _MAX_ORDINAL:
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
    m = 1
    for m in range(1, 13):
        md = _MONTH_DAYS[m - 1]
        if m == 2 and is_leap(y):
            md = 29
        if doy <= md:
            break
        doy -= md
    d = doy
    return (y, m, d)


def weekday(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if type(d) is not int:
        raise TypeError("d must be an int")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")
    return (to_ordinal(y, m, d) - 1) % 7


def _check_date_tuple(x, name="date"):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for v in x:
        if type(v) is not int:
            raise TypeError(f"{name} must be a tuple of 3 ints")


def _validate_date(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


def add_days(date, n):
    _check_date_tuple(date, "date")
    if type(n) is not int:
        raise TypeError("n must be an int")
    y, m, d = date
    _validate_date(y, m, d)
    ordinal = to_ordinal(y, m, d) + n
    if ordinal < 1 or ordinal > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {ordinal} out of range 1..{_MAX_ORDINAL}")
    return from_ordinal(ordinal)


def add_months(date, n):
    _check_date_tuple(date, "date")
    if type(n) is not int:
        raise TypeError("n must be an int")
    y, m, d = date
    _validate_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    target_year = total // 12 + 1
    target_month = total % 12 + 1
    if target_year < 1 or target_year > 9999:
        raise OverflowError(f"target year {target_year} out of range 1..9999")
    target_day = min(d, days_in_month(target_year, target_month))
    return (target_year, target_month, target_day)


def iso_weeks_in_year(iso_year):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be an int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if wd == 3:
        return 53
    if is_leap(iso_year) and wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if type(d) is not int:
        raise TypeError("d must be an int")
    _validate_date(y, m, d)
    ordinal = to_ordinal(y, m, d)
    wd = (ordinal - 1) % 7
    iso_weekday = wd + 1
    monday_ordinal = ordinal - wd
    thursday_ordinal = monday_ordinal + 3
    iso_year = from_ordinal(thursday_ordinal)[0]
    jan4_ordinal = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ordinal - 1) % 7
    monday_week1 = jan4_ordinal - jan4_wd
    iso_week_num = (monday_ordinal - monday_week1) // 7 + 1
    return (iso_year, iso_week_num, iso_weekday)


def from_iso_week(iso_year, week, weekday):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be an int")
    if type(week) is not int:
        raise TypeError("week must be an int")
    if type(weekday) is not int:
        raise TypeError("weekday must be an int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ordinal = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ordinal - 1) % 7
    monday_week1 = jan4_ordinal - jan4_wd
    target_ordinal = monday_week1 + (week - 1) * 7 + (weekday - 1)
    if target_ordinal < 1 or target_ordinal > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {target_ordinal} out of range 1..{_MAX_ORDINAL}")
    return from_ordinal(target_ordinal)


_RE_EXT_CAL = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_BAS_CAL = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_EXT_ORD = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_BAS_ORD = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_EXT_WK = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_BAS_WK = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    m = _RE_EXT_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > days_in_month(y, mo):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_BAS_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > days_in_month(y, mo):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_EXT_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_BAS_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_EXT_WK.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date out of range")

    m = _RE_BAS_WK.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date out of range")

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _validate_date(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a string, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"
    else:
        raise ValueError(f"unknown form {form!r}")


def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _validate_date(ay, am, ad)
    _validate_date(by, bm, bd)

    if a > b:
        dy, dm, dd = diff(b, a)
        return (-dy, -dm, -dd)

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