import re


def _is_int(x):
    return type(x) is int


def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month_raw(y, m):
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    elif m in (4, 6, 9, 11):
        return 30
    else:
        return 29 if _is_leap_raw(y) else 28


_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _to_ordinal_raw(y, m, d):
    yy = y - 1
    days_years = 365 * yy + yy // 4 - yy // 100 + yy // 400
    days_months = _CUM[m - 1]
    if m > 2 and _is_leap_raw(y):
        days_months += 1
    return days_years + days_months + d


def _weekday_raw(y, m, d):
    return (_to_ordinal_raw(y, m, d) - 1) % 7


def _check_date(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("expected int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _days_in_month_raw(y, m):
        raise ValueError("day out of range")


def _check_date_tuple(date, name):
    if not isinstance(date, tuple) or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for v in date:
        if not _is_int(v):
            raise TypeError(f"{name} must contain only ints")


def _add_months_raw(date, n):
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = d if d <= _days_in_month_raw(ty, tm) else _days_in_month_raw(ty, tm)
    return (ty, tm, td)


def is_leap(y):
    if not _is_int(y):
        raise TypeError("expected int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap_raw(y)


def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("expected int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _days_in_month_raw(y, m)


def to_ordinal(y, m, d):
    _check_date(y, m, d)
    return _to_ordinal_raw(y, m, d)


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("expected int")
    if n < 1 or n > 3652059:
        raise ValueError("ordinal out of range")
    t = n - 1
    q, r = divmod(t, 146097)
    year = q * 400 + 1 + r // 365
    if _to_ordinal_raw(year, 1, 1) > n:
        year -= 1
    day_of_year = n - _to_ordinal_raw(year, 1, 1) + 1
    if _is_leap_raw(year):
        cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
    else:
        cum = _CUM
    month = 1
    for i in range(1, 12):
        if day_of_year > cum[i]:
            month = i + 1
        else:
            break
    day = day_of_year - cum[month - 1]
    return (year, month, day)


def weekday(y, m, d):
    _check_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, "date")
    if not _is_int(n):
        raise TypeError("expected int")
    y, m, d = date
    _check_date(y, m, d)
    ordinal = to_ordinal(y, m, d) + n
    if ordinal < 1 or ordinal > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(ordinal)


def add_months(date, n):
    _check_date_tuple(date, "date")
    if not _is_int(n):
        raise TypeError("expected int")
    y, m, d = date
    _check_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total > 9999 * 12 - 1:
        raise OverflowError("result out of range")
    return _add_months_raw(date, n)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("expected int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("year out of range")
    w = _weekday_raw(iso_year, 1, 1)
    if w == 3:
        return 53
    if w == 2 and _is_leap_raw(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _check_date(y, m, d)
    wd = _weekday_raw(y, m, d) + 1
    ord_d = _to_ordinal_raw(y, m, d)
    jan4_monday = _to_ordinal_raw(y, 1, 4) - _weekday_raw(y, 1, 4)
    week = (ord_d - jan4_monday) // 7 + 1
    if week <= 0:
        iso_y = y - 1
        week = iso_weeks_in_year(iso_y) + week
    elif week > iso_weeks_in_year(y):
        iso_y = y + 1
        week = week - iso_weeks_in_year(y)
    else:
        iso_y = y
    return (iso_y, week, wd)


def from_iso_week(iso_year, week, weekday_arg):
    if not _is_int(iso_year) or not _is_int(week) or not _is_int(weekday_arg):
        raise TypeError("expected int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    max_week = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError("week out of range")
    if weekday_arg < 1 or weekday_arg > 7:
        raise ValueError("weekday out of range")
    jan4_monday = _to_ordinal_raw(iso_year, 1, 4) - _weekday_raw(iso_year, 1, 4)
    target = jan4_monday + (week - 1) * 7 + (weekday_arg - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target)


_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BAS_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def parse(s):
    if not isinstance(s, str):
        raise TypeError("expected str")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _days_in_month_raw(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_BAS_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _days_in_month_raw(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return from_ordinal(_to_ordinal_raw(y, 1, 1) + doy - 1)

    m = _RE_BAS_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return from_ordinal(_to_ordinal_raw(y, 1, 1) + doy - 1)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        if wk < 1 or wk > iso_weeks_in_year(y):
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    m = _RE_BAS_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        if wk < 1 or wk > iso_weeks_in_year(y):
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    raise ValueError("invalid date string")


def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _check_date(y, m, d)
    if not isinstance(form, str) or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _CUM[m - 1] + d
        if m > 2 and _is_leap_raw(y):
            doy += 1
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_date(ay, am, ad)
    _check_date(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    negate = a > b
    if negate:
        a, b = b, a
        ay, am, ad = a
        by, bm, bd = b

    lo = 0
    hi = (by - ay) * 12 + (bm - am) + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _add_months_raw(a, mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_raw(a, K)
    days = _to_ordinal_raw(by, bm, bd) - _to_ordinal_raw(shifted[0], shifted[1], shifted[2])

    if negate:
        return (-years, -months, -days)
    return (years, months, days)
