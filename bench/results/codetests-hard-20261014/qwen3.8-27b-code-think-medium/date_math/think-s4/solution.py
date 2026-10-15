import re

_DAYS_BEFORE_MONTH = [0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
_MAX_ORD = 3652059

_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BASIC = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BASIC = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BASIC = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _check_date_tuple(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(v).__name__}")


def _check_date_valid(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m:02d}")


def _dim(y, m):
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _to_ord(y, m, d):
    yy = y - 1
    return 365 * yy + yy // 4 - yy // 100 + yy // 400 + _DAYS_BEFORE_MONTH[m] + (1 if m >= 3 and _is_leap(y) else 0) + d


def _from_ord(n):
    x = n - 1
    y = (x * 400) // 146097 + 1
    while 365 * y + y // 4 - y // 100 + y // 400 <= x:
        y += 1
    while 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400 > x:
        y -= 1
    days_before_year = 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    doy = x - days_before_year
    leap = _is_leap(y)
    m = 1
    while True:
        md = _DAYS_BEFORE_MONTH[m + 1] - _DAYS_BEFORE_MONTH[m]
        if m == 2 and leap:
            md = 29
        if doy < md:
            break
        doy -= md
        m += 1
    return (y, m, doy + 1)


def _shift(y, m, d, k):
    total = (y - 1) * 12 + (m - 1) + k
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)


def _iso_weeks_in_year(iy):
    yy = iy - 1
    wd = (365 * yy + yy // 4 - yy // 100 + yy // 400) % 7
    if wd == 3 or (wd == 2 and _is_leap(iy)):
        return 53
    return 52


def is_leap(y):
    _check_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_valid(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= _MAX_ORD):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ord(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_valid(y, m, d)
    return (_to_ord(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_valid(y, m, d)
    ord_ = _to_ord(y, m, d) + n
    if ord_ < 1 or ord_ > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(ord_)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_valid(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError("result out of range")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_valid(y, m, d)
    ord_ = _to_ord(y, m, d)
    wd = (ord_ - 1) % 7
    iso_wd = wd + 1
    thu_ord = ord_ + (3 - wd)
    iso_y = _from_ord(thu_ord)[0]
    jan4 = _to_ord(iso_y, 1, 4)
    wd_jan4 = (jan4 - 1) % 7
    mon_week1 = jan4 - wd_jan4
    mon_ord = ord_ - wd
    iso_w = (mon_ord - mon_week1) // 7 + 1
    return (iso_y, iso_w, iso_wd)


def from_iso_week(iso_year, week, weekday_):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday_, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = _iso_weeks_in_year(iso_year)
    if not (1 <= week <= nw):
        raise ValueError(f"week {week} out of range 1..{nw}")
    if not (1 <= weekday_ <= 7):
        raise ValueError(f"weekday {weekday_} out of range 1..7")
    jan4 = _to_ord(iso_year, 1, 4)
    wd_jan4 = (jan4 - 1) % 7
    mon_week1 = jan4 - wd_jan4
    ord_ = mon_week1 + (week - 1) * 7 + (weekday_ - 1)
    if ord_ < 1 or ord_ > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(ord_)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    mo = _RE_CAL_EXT.fullmatch(s)
    if mo:
        y, m, d = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= m <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _dim(y, m)):
            raise ValueError("day out of range")
        return (y, m, d)

    mo = _RE_CAL_BASIC.fullmatch(s)
    if mo:
        y, m, d = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= m <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _dim(y, m)):
            raise ValueError("day out of range")
        return (y, m, d)

    mo = _RE_ORD_EXT.fullmatch(s)
    if mo:
        y, doy = int(mo.group(1)), int(mo.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return _from_ord(_to_ord(y, 1, 1) + doy - 1)

    mo = _RE_ORD_BASIC.fullmatch(s)
    if mo:
        y, doy = int(mo.group(1)), int(mo.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return _from_ord(_to_ord(y, 1, 1) + doy - 1)

    mo = _RE_WK_EXT.fullmatch(s)
    if mo:
        y, w, wd = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        nw = _iso_weeks_in_year(y)
        if not (1 <= w <= nw):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError("date out of range")

    mo = _RE_WK_BASIC.fullmatch(s)
    if mo:
        y, w, wd = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        nw = _iso_weeks_in_year(y)
        if not (1 <= w <= nw):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError("date out of range")

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_valid(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _DAYS_BEFORE_MONTH[m] + (1 if m >= 3 and _is_leap(y) else 0) + d
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_valid(ay, am, ad)
    _check_date_valid(by, bm, bd)

    if (ay, am, ad) == (by, bm, bd):
        return (0, 0, 0)

    if (ay, am, ad) < (by, bm, bd):
        # Find largest K >= 0 such that shift(a, K) <= b
        lo = 0
        hi = (by - ay) * 12 + (bm - am) + 13
        while lo < hi:
            mid = (lo + hi + 1) // 2
            sy, sm, sd = _shift(ay, am, ad, mid)
            if (sy, sm, sd) <= (by, bm, bd):
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        sy, sm, sd = _shift(ay, am, ad, K)
        days = _to_ord(by, bm, bd) - _to_ord(sy, sm, sd)
        return (years, months, days)
    else:
        years, months, days = diff(b, a)
        return (-years, -months, -days)