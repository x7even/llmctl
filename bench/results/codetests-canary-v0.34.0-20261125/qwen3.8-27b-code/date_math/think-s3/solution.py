import re

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

_RE_CAL_EXT = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_CAL_BASIC = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_ORD_EXT = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_ORD_BASIC = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_WK_EXT = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_WK_BASIC = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')


def _is_int(x):
    return type(x) is int


def _is_date_tuple(x):
    return type(x) is tuple and len(x) == 3 and all(type(v) is int for v in x)


def _days_in_month(y, m):
    if m == 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        return 29
    return _MONTH_DAYS[m - 1]


def _days_before_year(y):
    y1 = y - 1
    return 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400


def _check_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m:02d}")


def is_leap(y):
    if not _is_int(y):
        raise TypeError("y must be int")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if not _is_int(y):
        raise TypeError("y must be int")
    if not _is_int(m):
        raise TypeError("m must be int")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    if not _is_int(y):
        raise TypeError("y must be int")
    if not _is_int(m):
        raise TypeError("m must be int")
    if not _is_int(d):
        raise TypeError("d must be int")
    _check_date(y, m, d)
    days = d
    for i in range(m - 1):
        days += _MONTH_DAYS[i]
    if m > 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        days += 1
    return _days_before_year(y) + days


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be int")
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    n0 = n - 1
    y = 1 + n0 // 365
    while _days_before_year(y) > n0:
        y -= 1
    while _days_before_year(y + 1) <= n0:
        y += 1
    doy = n0 - _days_before_year(y) + 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    m = 1
    d = doy
    for i in range(12):
        dim = 29 if (i == 1 and leap) else _MONTH_DAYS[i]
        if d <= dim:
            m = i + 1
            break
        d -= dim
    return (y, m, d)


def weekday(y, m, d):
    if not _is_int(y):
        raise TypeError("y must be int")
    if not _is_int(m):
        raise TypeError("m must be int")
    if not _is_int(d):
        raise TypeError("d must be int")
    _check_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    if not _is_date_tuple(date):
        raise TypeError("date must be a tuple of 3 ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    _check_date(y, m, d)
    ord_n = to_ordinal(y, m, d) + n
    if ord_n < 1 or ord_n > 3652059:
        raise OverflowError(f"result ordinal {ord_n} out of range 1..3652059")
    return from_ordinal(ord_n)


def add_months(date, n):
    if not _is_date_tuple(date):
        raise TypeError("date must be a tuple of 3 ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    _check_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total >= 9999 * 12:
        raise OverflowError(f"result month index {total} out of range")
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(d, _days_in_month(ny, nm))
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_ord = _days_before_year(iso_year) + 1
    jan1_wd = (jan1_ord - 1) % 7
    leap = (iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0))
    if jan1_wd == 3 or (leap and jan1_wd == 2):
        return 53
    return 52


def iso_week(y, m, d):
    if not _is_int(y):
        raise TypeError("y must be int")
    if not _is_int(m):
        raise TypeError("m must be int")
    if not _is_int(d):
        raise TypeError("d must be int")
    _check_date(y, m, d)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    iso_wd = wd + 1
    monday_ord = ord_val - wd
    thursday_ord = monday_ord + 3
    iso_y = from_ordinal(thursday_ord)[0]
    jan4_ord = _days_before_year(iso_y) + 4
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    iso_wk = (monday_ord - monday_w1) // 7 + 1
    return (iso_y, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday_val):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if not _is_int(week):
        raise TypeError("week must be int")
    if not _is_int(weekday_val):
        raise TypeError("weekday must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = iso_weeks_in_year(iso_year)
    if not (1 <= week <= nw):
        raise ValueError(f"week {week} out of range 1..{nw}")
    if not (1 <= weekday_val <= 7):
        raise ValueError(f"weekday {weekday_val} out of range 1..7")
    jan4_ord = _days_before_year(iso_year) + 4
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target = monday_w1 + (week - 1) * 7 + (weekday_val - 1)
    if target < 1 or target > 3652059:
        raise OverflowError(f"result ordinal {target} out of range 1..3652059")
    return from_ordinal(target)


def parse(s):
    if not type(s) is str:
        raise TypeError("s must be str")

    m = _RE_CAL_EXT.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        dim = _days_in_month(y, mo)
        if not (1 <= d <= dim):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_WK_EXT.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    m = _RE_ORD_EXT.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
        max_doy = 366 if leap else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range for year {y}")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_WK_BASIC.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    m = _RE_CAL_BASIC.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        dim = _days_in_month(y, mo)
        if not (1 <= d <= dim):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_ORD_BASIC.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
        max_doy = 366 if leap else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range for year {y}")
        return from_ordinal(_days_before_year(y) + doy)

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    if not _is_date_tuple(date):
        raise TypeError("date must be a tuple of 3 ints")
    y, m, d = date
    _check_date(y, m, d)

    if not type(form) is str:
        raise ValueError("form must be a string")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        days = d
        for i in range(m - 1):
            days += _MONTH_DAYS[i]
        if m > 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
            days += 1
        return f"{y:04d}-{days:03d}"
    elif form == 'week':
        iso_y, iso_wk, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_wk:02d}-{iso_wd}"
    else:
        raise ValueError(f"unknown form: {form!r}")


def diff(a, b):
    if not _is_date_tuple(a):
        raise TypeError("a must be a tuple of 3 ints")
    if not _is_date_tuple(b):
        raise TypeError("b must be a tuple of 3 ints")
    ay, am, ad = a
    by, bm, bd = b
    _check_date(ay, am, ad)
    _check_date(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        yr, mo, dy = diff(b, a)
        return (-yr, -mo, -dy)

    # a < b: binary search for largest K >= 0 with add_months(a, K) <= b
    hi = (by - ay) * 12 + (bm - am) + 12
    lo = 0

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