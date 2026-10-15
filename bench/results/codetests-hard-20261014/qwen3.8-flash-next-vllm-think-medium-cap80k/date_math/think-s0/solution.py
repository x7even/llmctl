import re

_MONTHS_NORMAL = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTHS_LEAP = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_PREFIX_NORMAL = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_PREFIX_LEAP = (0, 0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
_MIN_ORD = 1
_MAX_ORD = 3652059


def _check_int(v, name='arg'):
    if type(v) is not int:
        raise TypeError(f"{name} must be int, got {type(v).__name__}")


def _check_date(date, name='date'):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(v).__name__}")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")


def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if m == 2:
        return 29 if is_leap(y) else 28
    return _MONTHS_NORMAL[m - 1]


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    y1 = y - 1
    days = 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
    if is_leap(y):
        days += _PREFIX_LEAP[m]
    else:
        days += _PREFIX_NORMAL[m]
    days += d
    return days


def from_ordinal(n):
    _check_int(n, 'n')
    if n < _MIN_ORD or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    n0 = n - 1
    n400, n0 = divmod(n0, 146097)
    n100, n0 = divmod(n0, 36524)
    n4, n0 = divmod(n0, 1461)
    n1, n0 = divmod(n0, 365)
    year = n400 * 400 + n100 * 100 + n4 * 4 + n1 + 1
    if n100 == 4:
        year -= 1
        n0 = 365
    elif n1 == 4:
        year -= 1
        if n4 == 24:
            n0 = 364
        else:
            n0 = 365
    month = 1
    mlen = _MONTHS_LEAP if is_leap(year) else _MONTHS_NORMAL
    for i in range(12):
        if n0 < mlen[i]:
            break
        n0 -= mlen[i]
        month += 1
    day = n0 + 1
    return (year, month, day)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ord_new = to_ordinal(y, m, d) + n
    if ord_new < _MIN_ORD or ord_new > _MAX_ORD:
        raise OverflowError("result out of range")
    return from_ordinal(ord_new)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError("result year out of range")
    new_d = min(d, days_in_month(new_y, new_m))
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if wd == 3:
        return 53
    if wd == 2 and is_leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ord_ = to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7
    thursday_ord = ord_ + (3 - wd)
    iso_y, _, _ = from_ordinal(thursday_ord)
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    iso_w = (thursday_ord - week1_monday) // 7 + 1
    iso_wd = wd + 1
    return (iso_y, iso_w, iso_wd)


def from_iso_week(iso_year, week, weekday_val):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday_val, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    max_week = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError("week out of range")
    if weekday_val < 1 or weekday_val > 7:
        raise ValueError("weekday out of range")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target_ord = week1_monday + (week - 1) * 7 + (weekday_val - 1)
    if target_ord < _MIN_ORD or target_ord > _MAX_ORD:
        raise OverflowError("result out of range")
    return from_ordinal(target_ord)


def _parse_week_date(y, w, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if w < 1 or w > iso_weeks_in_year(y):
        raise ValueError("week out of range")
    if d < 1 or d > 7:
        raise ValueError("weekday out of range")
    jan4_ord = to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target_ord = week1_monday + (w - 1) * 7 + (d - 1)
    if target_ord < _MIN_ORD or target_ord > _MAX_ORD:
        raise ValueError("date out of range")
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    m = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        ord_ = to_ordinal(y, 1, 1) + doy - 1
        return from_ordinal(ord_)

    m = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
    if m:
        y, w, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _parse_week_date(y, w, d)

    m = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
    if m:
        y, w, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _parse_week_date(y, w, d)

    m = re.fullmatch(r'([0-9]{4})([0-9]{2})([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = re.fullmatch(r'([0-9]{4})([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        ord_ = to_ordinal(y, 1, 1) + doy - 1
        return from_ordinal(ord_)

    raise ValueError("invalid date string")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    _check_date_range(a[0], a[1], a[2])
    _check_date_range(b[0], b[1], b[2])

    if a == b:
        return (0, 0, 0)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    b_ord = to_ordinal(b[0], b[1], b[2])

    lo, hi = 0, 120000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            shifted = add_months(a, mid)
            shifted_ord = to_ordinal(shifted[0], shifted[1], shifted[2])
        except OverflowError:
            shifted_ord = b_ord + 1
        if shifted_ord <= b_ord:
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = b_ord - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
