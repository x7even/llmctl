import re

_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_DAYS_BEFORE_MONTH_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)


def _check_int(x, name='argument'):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _check_date_tuple(date, name='date'):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, x in enumerate(date):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(x).__name__}")


def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if m == 2:
        dim = 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    elif m in (4, 6, 9, 11):
        dim = 30
    else:
        dim = 31
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim}")


def _days_before_year(y):
    yy = y - 1
    return 365 * yy + yy // 4 - yy // 100 + yy // 400


def _ordinal_unchecked(y, m, d):
    days = _days_before_year(y)
    if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        days += _DAYS_BEFORE_MONTH_LEAP[m - 1]
    else:
        days += _DAYS_BEFORE_MONTH[m - 1]
    return days + d


def _year_from_ordinal(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        if _days_before_year(mid + 1) >= n:
            hi = mid
        else:
            lo = mid + 1
    return lo


def _month_day_from_doy(y, doy):
    if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        cum = _DAYS_BEFORE_MONTH_LEAP
    else:
        cum = _DAYS_BEFORE_MONTH
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] >= doy:
            hi = mid
        else:
            lo = mid + 1
    m = lo
    d = doy - cum[m - 1]
    return m, d


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
    _check_date_range(y, m, d)
    return _ordinal_unchecked(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    y = _year_from_ordinal(n)
    doy = n - _days_before_year(y)
    m, d = _month_day_from_doy(y, doy)
    return (y, m, d)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ord_ = to_ordinal(y, m, d) + n
    if ord_ < 1 or ord_ > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(ord_)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total >= 9999 * 12:
        raise OverflowError("result out of range")
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(d, days_in_month(ny, nm))
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if is_leap(iso_year) and jan1_wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    wd = (to_ordinal(y, m, d) - 1) % 7
    ord_ = to_ordinal(y, m, d)
    thursday_ord = ord_ - wd + 3
    if thursday_ord > 3652059:
        iso_y = 10000
    else:
        iso_y = _year_from_ordinal(thursday_ord)
    jan4_ord = _ordinal_unchecked(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    iso_w = (thursday_ord - week1_monday) // 7 + 1
    iso_d = wd + 1
    return (iso_y, iso_w, iso_d)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = iso_weeks_in_year(iso_year)
    if not (1 <= week <= nw):
        raise ValueError(f"week {week} out of range 1..{nw}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target = week1_monday + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target)


_RE_EXT_CALENDAR = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_EXT_WEEK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BASIC_CALENDAR = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORDINAL = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BASIC_WEEK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')
_RE_BASIC_ORDINAL = re.compile(r'([0-9]{4})([0-9]{3})')


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    m = _RE_EXT_CALENDAR.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date_range(y, mo, d)
        return (y, mo, d)

    m = _RE_EXT_WEEK.fullmatch(s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        nw = iso_weeks_in_year(y)
        if not (1 <= w <= nw):
            raise ValueError(f"week {w} out of range 1..{nw}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError("week date out of range")

    m = _RE_BASIC_CALENDAR.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date_range(y, mo, d)
        return (y, mo, d)

    m = _RE_EXT_ORDINAL.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_BASIC_WEEK.fullmatch(s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        nw = iso_weeks_in_year(y)
        if not (1 <= w <= nw):
            raise ValueError(f"week {w} out of range 1..{nw}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError("week date out of range")

    m = _RE_BASIC_ORDINAL.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be str, got {type(form).__name__}")
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


def _shift_leq(a, k, b):
    ya, ma, da = a
    total = (ya - 1) * 12 + (ma - 1) + k
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(da, days_in_month(ny, nm))
    return (ny, nm, nd) <= b


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ya, ma, da = a
    yb, mb, db = b
    _check_date_range(ya, ma, da)
    _check_date_range(yb, mb, db)

    if a == b:
        return (0, 0, 0)

    if a > b:
        yrs, mos, dys = diff(b, a)
        return (-yrs, -mos, -dys)

    # a < b: find largest K >= 0 with shift(a, K) <= b
    upper = (yb - ya) * 12 + (mb - ma) + 12
    lo, hi = 0, upper
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift_leq(a, mid, b):
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    total = (ya - 1) * 12 + (ma - 1) + K
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(da, days_in_month(ny, nm))
    days = to_ordinal(yb, mb, db) - to_ordinal(ny, nm, nd)
    return (years, months, days)
