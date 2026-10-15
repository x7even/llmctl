import re

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MONTH_PREFIX = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORDINAL = 3652059  # ordinal of (9999, 12, 31)


def _is_int(x):
    return type(x) is int


def _is_date(x):
    return type(x) is tuple and len(x) == 3 and all(type(v) is int for v in x)


def _check_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    dim = _MONTH_DAYS[m - 1]
    if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        dim = 29
    if not (1 <= d <= dim):
        raise ValueError("day out of range for the given month")


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_before_year(y):
    """Number of days in years 1..y-1."""
    yy = y - 1
    return yy * 365 + yy // 4 - yy // 100 + yy // 400


def is_leap(y):
    if not _is_int(y):
        raise TypeError("y must be int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    return _leap(y)


def days_in_month(y, m):
    if not _is_int(y):
        raise TypeError("y must be int")
    if not _is_int(m):
        raise TypeError("m must be int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    if m == 2:
        return 29 if _leap(y) else 28
    return _MONTH_DAYS[m - 1]


def to_ordinal(y, m, d):
    if not _is_int(y):
        raise TypeError("y must be int")
    if not _is_int(m):
        raise TypeError("m must be int")
    if not _is_int(d):
        raise TypeError("d must be int")
    _check_date(y, m, d)
    db = _days_before_year(y)
    dm = _MONTH_PREFIX[m - 1]
    if m > 2 and _leap(y):
        dm += 1
    return db + dm + d


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be int")
    if not (1 <= n <= _MAX_ORDINAL):
        raise ValueError("ordinal out of range 1..3652059")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    leap = _leap(y)
    m = 1
    for m in range(1, 13):
        md = _MONTH_DAYS[m - 1] + (1 if m == 2 and leap else 0)
        if doy <= md:
            break
        doy -= md
    return (y, m, doy)


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
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    _check_date(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(ord_val)


def add_months(date, n):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    y, m, d = date
    _check_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of range")
    dim = _MONTH_DAYS[tm - 1] + (1 if tm == 2 and _leap(ty) else 0)
    td = d if d <= dim else dim
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    w = (_days_before_year(iso_year)) % 7  # weekday of Jan 1 (0=Mon)
    if w == 3 or (w == 2 and _leap(iso_year)):
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
    wd = (ord_val - 1) % 7  # 0=Mon .. 6=Sun
    mon_ord = ord_val - wd
    thu_ord = mon_ord + 3
    iso_y = from_ordinal(thu_ord)[0]
    jan4_ord = _days_before_year(iso_y) + 3
    jan4_wd = jan4_ord % 7  # (jan4_ord - 1) % 7 == (jan4_ord) % 7 since _days_before_year(1)=0
    # Actually: weekday = (ordinal - 1) % 7. jan4_ord = _days_before_year(iso_y) + 3.
    # weekday of Jan 4 = (jan4_ord - 1) % 7
    jan4_wd = (jan4_ord - 1) % 7
    mon_week1 = jan4_ord - jan4_wd
    week = (mon_ord - mon_week1) // 7 + 1
    iso_wd = wd + 1
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if not _is_int(week):
        raise TypeError("week must be int")
    if not _is_int(weekday):
        raise TypeError("weekday must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError("week out of range")
    if not (1 <= weekday <= 7):
        raise ValueError("weekday out of range")
    jan4_ord = _days_before_year(iso_year) + 3
    jan4_wd = (jan4_ord - 1) % 7
    mon_week1 = jan4_ord - jan4_wd
    target_ord = mon_week1 + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(target_ord)


_RE_EXT_WEEK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9]{1})')
_RE_BAS_WEEK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9]{1})')
_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')


def _parse_week_date(y, w, wd):
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    max_week = iso_weeks_in_year(y)
    if not (1 <= w <= max_week):
        raise ValueError("week out of range")
    if not (1 <= wd <= 7):
        raise ValueError("weekday out of range")
    jan4_ord = _days_before_year(y) + 3
    jan4_wd = (jan4_ord - 1) % 7
    mon_week1 = jan4_ord - jan4_wd
    target_ord = mon_week1 + (w - 1) * 7 + (wd - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise ValueError("date out of range")
    return from_ordinal(target_ord)


def _parse_ord_date(y, doy):
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    max_doy = 366 if _leap(y) else 365
    if not (1 <= doy <= max_doy):
        raise ValueError("day of year out of range")
    return from_ordinal(_days_before_year(y) + doy)


def parse(s):
    if not isinstance(s, str):
        raise TypeError("s must be str")
    m = _RE_EXT_WEEK.fullmatch(s)
    if m:
        return _parse_week_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _RE_BAS_WEEK.fullmatch(s)
    if m:
        return _parse_week_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date(y, mo, dd)
        return (y, mo, dd)
    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        return _parse_ord_date(int(m.group(1)), int(m.group(2)))
    m = _RE_BAS_CAL.fullmatch(s)
    if m:
        y, mo, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date(y, mo, dd)
        return (y, mo, dd)
    m = _RE_BAS_ORD.fullmatch(s)
    if m:
        return _parse_ord_date(int(m.group(1)), int(m.group(2)))
    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    y, m, d = date
    _check_date(y, m, d)
    if not isinstance(form, str):
        raise ValueError("form must be a string")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iso_y, iso_w, iso_d = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_d:01d}"
    else:
        raise ValueError(f"invalid form: {form!r}")


def diff(a, b):
    if not _is_date(a):
        raise TypeError("a must be a tuple of 3 ints")
    if not _is_date(b):
        raise TypeError("b must be a tuple of 3 ints")
    ay, am, ad = a
    by, bm, bd = b
    _check_date(ay, am, ad)
    _check_date(by, bm, bd)

    if a > b:
        years, months, days = diff(b, a)
        return (-years, -months, -days)

    # a <= b: find largest K >= 0 such that add_months(a, K) <= b
    total_a = (ay - 1) * 12 + (am - 1)
    total_max = (9999 - 1) * 12 + 11
    K_max = total_max - total_a

    lo, hi = 0, K_max
    while lo < hi:
        mid = (lo + hi + 1) // 2
        total = total_a + mid
        ty = total // 12 + 1
        tm = total % 12 + 1
        dim = _MONTH_DAYS[tm - 1] + (1 if tm == 2 and _leap(ty) else 0)
        td = ad if ad <= dim else dim
        if (ty, tm, td) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)

    total = total_a + K
    ty = total // 12 + 1
    tm = total % 12 + 1
    dim = _MONTH_DAYS[tm - 1] + (1 if tm == 2 and _leap(ty) else 0)
    td = ad if ad <= dim else dim

    days = to_ordinal(by, bm, bd) - to_ordinal(ty, tm, td)
    return (years, months, days)