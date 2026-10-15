import re

_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORDINAL = 3652059


def _days_in_years(k):
    """Number of days in k full proleptic-Gregorian years (years 1..k)."""
    return 365 * k + k // 4 - k // 100 + k // 400


def _check_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= days_in_month(y, m)):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


def _is_date_tuple(x):
    return (type(x) is tuple and len(x) == 3
            and type(x[0]) is int and type(x[1]) is int and type(x[2]) is int)


def is_leap(y):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def to_ordinal(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if type(d) is not int:
        raise TypeError("d must be an int")
    _check_date(y, m, d)
    days = _days_in_years(y - 1) + _DAYS_BEFORE_MONTH[m - 1] + d
    if m > 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        days += 1
    return days


def from_ordinal(n):
    if type(n) is not int:
        raise TypeError("n must be an int")
    if not (1 <= n <= _MAX_ORDINAL):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        if _days_in_years(mid) >= n:
            hi = mid
        else:
            lo = mid + 1
    y = lo
    doy = n - _days_in_years(y - 1)
    m = 1
    while m <= 12:
        dim = days_in_month(y, m)
        if doy <= dim:
            break
        doy -= dim
        m += 1
    return (y, m, doy)


def weekday(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if type(d) is not int:
        raise TypeError("d must be an int")
    _check_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    if not _is_date_tuple(date):
        raise TypeError("date must be a tuple of 3 ints")
    if type(n) is not int:
        raise TypeError("n must be an int")
    y, m, d = date
    _check_date(y, m, d)
    ordinal = to_ordinal(y, m, d) + n
    if ordinal < 1 or ordinal > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(ordinal)


def add_months(date, n):
    if not _is_date_tuple(date):
        raise TypeError("date must be a tuple of 3 ints")
    if type(n) is not int:
        raise TypeError("n must be an int")
    y, m, d = date
    _check_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError("result out of range")
    td = d if d <= days_in_month(ty, tm) else days_in_month(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be an int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if wd == 3:
        return 53
    if (iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0)) and wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if type(d) is not int:
        raise TypeError("d must be an int")
    _check_date(y, m, d)
    ord_ = to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7
    iso_wd = wd + 1
    thursday_ord = ord_ + 3 - wd
    iso_y = from_ordinal(thursday_ord)[0]
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    iso_wk = (ord_ - monday_w1) // 7 + 1
    return (iso_y, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be an int")
    if type(week) is not int:
        raise TypeError("week must be an int")
    if type(weekday) is not int:
        raise TypeError("weekday must be an int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    # Extended calendar: YYYY-MM-DD
    m = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= days_in_month(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    # Basic calendar: YYYYMMDD
    m = re.fullmatch(r'([0-9]{4})([0-9]{2})([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= days_in_month(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD
    m = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(_days_in_years(y - 1) + doy)

    # Basic ordinal: YYYYDDD
    m = re.fullmatch(r'([0-9]{4})([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(_days_in_years(y - 1) + doy)

    # Extended week: YYYY-Www-D
    m = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        jan4_ord = to_ordinal(y, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        monday_w1 = jan4_ord - jan4_wd
        target = monday_w1 + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > _MAX_ORDINAL:
            raise ValueError("date out of range")
        return from_ordinal(target)

    # Basic week: YYYYWwwD
    m = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        jan4_ord = to_ordinal(y, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        monday_w1 = jan4_ord - jan4_wd
        target = monday_w1 + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > _MAX_ORDINAL:
            raise ValueError("date out of range")
        return from_ordinal(target)

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    if not _is_date_tuple(date):
        raise TypeError("date must be a tuple of 3 ints")
    y, m, d = date
    _check_date(y, m, d)
    if type(form) is not str:
        raise ValueError("form must be a string")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_in_years(y - 1)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iso_y, iso_wk, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_wk:02d}-{iso_wd}"
    else:
        raise ValueError(f"invalid form: {form!r}")


def diff(a, b):
    if not _is_date_tuple(a):
        raise TypeError("a must be a tuple of 3 ints")
    if not _is_date_tuple(b):
        raise TypeError("b must be a tuple of 3 ints")
    ay, am, ad = a
    by, bm, bd = b
    _check_date(ay, am, ad)
    _check_date(by, bm, bd)

    if a <= b:
        lo, hi = 0, 119987
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
    else:
        y, m, d = diff(b, a)
        return (-y, -m, -d)