import re


def _is_int(x):
    return type(x) is int


def _is_date(x):
    return type(x) is tuple and len(x) == 3 and all(type(v) is int for v in x)


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


_CUM_C = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_L = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)


def _check_date(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("expected int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")


def _days_before_year(y):
    yp = y - 1
    return yp * 365 + yp // 4 - yp // 100 + yp // 400


def _jan4_ordinal(y):
    return _days_before_year(y) + 4


def _wd_of_ord(n):
    return (n - 1) % 7


def is_leap(y):
    if not _is_int(y):
        raise TypeError("expected int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _leap(y)


def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("expected int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_date(y, m, d)
    cum = _CUM_L if _leap(y) else _CUM_C
    return _days_before_year(y) + cum[m - 1] + d


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("expected int")
    if n < 1 or n > 3652059:
        raise ValueError("ordinal out of range")
    n0 = n - 1
    y = n0 // 365 + 1
    while True:
        db = _days_before_year(y)
        if db > n0:
            y -= 1
        elif db + (366 if _leap(y) else 365) <= n0:
            y += 1
        else:
            break
    doy = n0 - db  # 0-based day of year
    cum = _CUM_L if _leap(y) else _CUM_C
    m = 1
    while doy >= cum[m]:
        m += 1
    dd = doy - cum[m - 1] + 1
    return (y, m, dd)


def weekday(y, m, d):
    _check_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    if not _is_date(date):
        raise TypeError("expected date tuple")
    if not _is_int(n):
        raise TypeError("expected int")
    y, m, d = date
    _check_date(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(ord_val)


def add_months(date, n):
    if not _is_date(date):
        raise TypeError("expected date tuple")
    if not _is_int(n):
        raise TypeError("expected int")
    y, m, d = date
    _check_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("result out of range")
    nd = min(d, _dim(ny, nm))
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("expected int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("year out of range")
    jan1_wd = _wd_of_ord(_days_before_year(iso_year) + 1)
    if jan1_wd == 3:
        return 53
    if _leap(iso_year) and jan1_wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    _check_date(y, m, d)
    ord_val = to_ordinal(y, m, d)
    j4 = _jan4_ordinal(y)
    monday_w1 = j4 - _wd_of_ord(j4)
    iso_ord = ord_val - monday_w1 + 1
    if iso_ord < 1:
        iy = y - 1
        j4p = _jan4_ordinal(iy)
        monday_w1p = j4p - _wd_of_ord(j4p)
        iso_ord = ord_val - monday_w1p + 1
    elif iso_ord > iso_weeks_in_year(y) * 7:
        iy = y + 1
        j4n = _jan4_ordinal(iy)
        monday_w1n = j4n - _wd_of_ord(j4n)
        iso_ord = ord_val - monday_w1n + 1
    else:
        iy = y
    iso_w = (iso_ord - 1) // 7 + 1
    iso_d = (iso_ord - 1) % 7 + 1
    return (iy, iso_w, iso_d)


def from_iso_week(iso_year, week, weekday_val):
    if not _is_int(iso_year) or not _is_int(week) or not _is_int(weekday_val):
        raise TypeError("expected int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    max_w = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_w:
        raise ValueError("week out of range")
    if weekday_val < 1 or weekday_val > 7:
        raise ValueError("weekday out of range")
    j4 = _jan4_ordinal(iso_year)
    monday_w1 = j4 - _wd_of_ord(j4)
    target = monday_w1 + (week - 1) * 7 + (weekday_val - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target)


_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})\Z')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})\Z')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})\Z')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})\Z')
_RE_WK_EXT = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])\Z')
_RE_WK_BAS = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])\Z')


def parse(s):
    if not type(s) is str:
        raise TypeError("expected str")

    m = _RE_CAL_EXT.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid year")
        if mo < 1 or mo > 12:
            raise ValueError("invalid month")
        if d < 1 or d > _dim(y, mo):
            raise ValueError("invalid day")
        return (y, mo, d)

    m = _RE_CAL_BAS.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid year")
        if mo < 1 or mo > 12:
            raise ValueError("invalid month")
        if d < 1 or d > _dim(y, mo):
            raise ValueError("invalid day")
        return (y, mo, d)

    m = _RE_ORD_EXT.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("invalid year")
        max_doy = 366 if _leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("invalid day of year")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_ORD_BAS.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("invalid year")
        max_doy = 366 if _leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("invalid day of year")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_WK_EXT.fullmatch(s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid iso year")
        max_w = iso_weeks_in_year(y)
        if w < 1 or w > max_w:
            raise ValueError("invalid week")
        if wd < 1 or wd > 7:
            raise ValueError("invalid weekday")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError("date out of range")

    m = _RE_WK_BAS.fullmatch(s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("invalid iso year")
        max_w = iso_weeks_in_year(y)
        if w < 1 or w > max_w:
            raise ValueError("invalid week")
        if wd < 1 or wd > 7:
            raise ValueError("invalid weekday")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError("date out of range")

    raise ValueError("invalid format")


def format_date(date, form):
    if not _is_date(date):
        raise TypeError("expected date tuple")
    y, m, d = date
    _check_date(y, m, d)
    if not type(form) is str:
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"
    else:
        raise ValueError("invalid form")


def diff(a, b):
    if not _is_date(a) or not _is_date(b):
        raise TypeError("expected date tuple")
    ay, am, ad = a
    by, bm, bd = b
    _check_date(ay, am, ad)
    _check_date(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a < b: binary search for largest K with add_months(a, K) <= b
    upper = (by - ay) * 12 + (bm - am) + 1
    lo, hi = 0, upper
    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = add_months(a, mid)
        if shifted <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
