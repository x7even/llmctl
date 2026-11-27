import re

_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORD = 3652059

_RE_CAL_EXT = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_CAL_BAS = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_ORD_EXT = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_ORD_BAS = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_WK_EXT = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9]{1})$')
_RE_WK_BAS = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9]{1})$')


def _is_int(x):
    return type(x) is int


def _check_date_tuple(date):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a tuple of exactly 3 ints")
    for e in date:
        if type(e) is not int:
            raise TypeError("date elements must be ints")


def _check_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError("day out of range for given month and year")


def _dim(y, m):
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    return _MDAYS[m - 1]


def _days_before_year(y):
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


def _days_before_month(y, m):
    s = _CUM[m - 1]
    if m > 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        s += 1
    return s


def _ord(y, m, d):
    return _days_before_year(y) + _days_before_month(y, m) + d


def is_leap(y):
    if type(y) is not int:
        raise TypeError("y must be int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if type(y) is not int:
        raise TypeError("y must be int")
    if type(m) is not int:
        raise TypeError("m must be int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be int")
    if type(m) is not int:
        raise TypeError("m must be int")
    if type(d) is not int:
        raise TypeError("d must be int")
    _check_valid_date(y, m, d)
    return _ord(y, m, d)


def from_ordinal(n):
    if type(n) is not int:
        raise TypeError("n must be int")
    if not (1 <= n <= _MAX_ORD):
        raise ValueError("ordinal out of range 1..3652059")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) <= n - 1:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    day_in_year = n - _days_before_year(y)
    m = 1
    while m <= 12:
        dim = _dim(y, m)
        if day_in_year <= dim:
            break
        day_in_year -= dim
        m += 1
    return (y, m, day_in_year)


def weekday(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be int")
    if type(m) is not int:
        raise TypeError("m must be int")
    if type(d) is not int:
        raise TypeError("d must be int")
    _check_valid_date(y, m, d)
    return (_ord(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    _check_valid_date(y, m, d)
    target = _ord(y, m, d) + n
    if target < 1 or target > _MAX_ORD:
        raise OverflowError("result out of range")
    return from_ordinal(target)


def add_months(date, n):
    _check_date_tuple(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError("result out of range")
    new_d = d if d <= _dim(new_y, new_m) else _dim(new_y, new_m)
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    wd = (_ord(iso_year, 1, 1) - 1) % 7
    if wd == 3:
        return 53
    if iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0) and wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be int")
    if type(m) is not int:
        raise TypeError("m must be int")
    if type(d) is not int:
        raise TypeError("d must be int")
    _check_valid_date(y, m, d)
    ord_n = _ord(y, m, d)
    wd = (ord_n - 1) % 7
    iso_weekday = wd + 1
    thu_ord = ord_n + (3 - wd)
    iso_y = from_ordinal(thu_ord)[0]
    jan4_ord = _ord(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    mon_this = ord_n - wd
    week = (mon_this - mon_w1) // 7 + 1
    return (iso_y, week, iso_weekday)


def from_iso_week(iso_year, week, weekday):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be int")
    if type(week) is not int:
        raise TypeError("week must be int")
    if type(weekday) is not int:
        raise TypeError("weekday must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_wk):
        raise ValueError("week out of range")
    if not (1 <= weekday <= 7):
        raise ValueError("weekday out of range 1..7")
    jan4_ord = _ord(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError("result out of range")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    m = _RE_CAL_EXT.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_valid_date(y, mo, d)
        return (y, mo, d)

    m = _RE_CAL_BAS.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_valid_date(y, mo, d)
        return (y, mo, d)

    m = _RE_ORD_EXT.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_ORD_BAS.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_WK_EXT.match(s)
    if m:
        iy, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= iy <= 9999):
            raise ValueError("ISO year out of range")
        max_wk = iso_weeks_in_year(iy)
        if not (1 <= wk <= max_wk):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        jan4_ord = _ord(iy, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        mon_w1 = jan4_ord - jan4_wd
        target = mon_w1 + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > _MAX_ORD:
            raise ValueError("date out of range")
        return from_ordinal(target)

    m = _RE_WK_BAS.match(s)
    if m:
        iy, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= iy <= 9999):
            raise ValueError("ISO year out of range")
        max_wk = iso_weeks_in_year(iy)
        if not (1 <= wk <= max_wk):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        jan4_ord = _ord(iy, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        mon_w1 = jan4_ord - jan4_wd
        target = mon_w1 + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > _MAX_ORD:
            raise ValueError("date out of range")
        return from_ordinal(target)

    raise ValueError("unrecognized date format")


def format_date(date, form):
    _check_date_tuple(date)
    y, m, d = date
    _check_valid_date(y, m, d)
    if type(form) is not str:
        raise ValueError("form must be a string")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _ord(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"
    else:
        raise ValueError(f"unknown form: {form!r}")


def diff(a, b):
    _check_date_tuple(a)
    _check_date_tuple(b)
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    ord_a = _ord(ay, am, ad)
    ord_b = _ord(by, bm, bd)

    if ord_a > ord_b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    max_K = (9999 - 1) * 12 + 11 - ((ay - 1) * 12 + (am - 1))
    lo, hi = 0, max_K
    while lo < hi:
        mid = (lo + hi + 1) // 2
        total = (ay - 1) * 12 + (am - 1) + mid
        ny = total // 12 + 1
        nm = total % 12 + 1
        nd = ad if ad <= _dim(ny, nm) else _dim(ny, nm)
        if _ord(ny, nm, nd) <= ord_b:
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)

    total = (ay - 1) * 12 + (am - 1) + K
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = ad if ad <= _dim(ny, nm) else _dim(ny, nm)

    days = ord_b - _ord(ny, nm, nd)
    return (years, months, days)