import re

_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
_MAX_ORDINAL = 3652059

_RE_EXT_CAL = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})\Z')
_RE_BAS_CAL = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})\Z')
_RE_EXT_ORD = re.compile(r'^([0-9]{4})-([0-9]{3})\Z')
_RE_BAS_ORD = re.compile(r'^([0-9]{4})([0-9]{3})\Z')
_RE_EXT_WK = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])\Z')
_RE_BAS_WK = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])\Z')


def _is_int(x):
    return type(x) is int


def _check_int(x, name):
    if not _is_int(x):
        raise TypeError(f"{name} must be int")


def _check_date(date, name):
    if not (type(date) is tuple and len(date) == 3):
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(date):
        if not _is_int(v):
            raise TypeError(f"{name}[{i}] must be int")


def _check_str(x, name):
    if type(x) is not str:
        raise TypeError(f"{name} must be str")


def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError(f"day {d} out of range for month {m} of year {y}")


def _dim(y, m):
    if m == 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        return 29
    return _MDAYS[m - 1]


def _days_before_year(y):
    return (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


def _days_before_month(y, m):
    if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        return _CUM_LEAP[m - 1]
    return _CUM_NONLEAP[m - 1]


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
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= _MAX_ORDINAL):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    y = (n * 400) // 146097
    while _days_before_year(y + 1) < n:
        y += 1
    while _days_before_year(y) >= n:
        y -= 1
    doy = n - _days_before_year(y)
    cum = _CUM_LEAP if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else _CUM_NONLEAP
    m = 1
    while m < 12 and cum[m] < doy:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


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
    ord_n = to_ordinal(y, m, d) + n
    if ord_n < 1 or ord_n > _MAX_ORDINAL:
        raise OverflowError("result out of supported range")
    return from_ordinal(ord_n)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError("result out of supported range")
    td = min(d, _dim(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = (_days_before_year(iso_year) + 1 - 1) % 7
    if jan1_wd == 3:
        return 53
    if iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0) and jan1_wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ord_n = to_ordinal(y, m, d)
    iso_wd = (ord_n - 1) % 7 + 1
    jan4_ord = _days_before_year(y) + 4
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    week = (ord_n - monday_w1) // 7 + 1
    if week < 1:
        iso_y = y - 1
        week = iso_weeks_in_year(iso_y)
    elif week > iso_weeks_in_year(y):
        iso_y = y + 1
        week = 1
    else:
        iso_y = y
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _days_before_year(iso_year) + 4
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    ord_n = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if ord_n < 1 or ord_n > _MAX_ORDINAL:
        raise OverflowError("result out of supported range")
    return from_ordinal(ord_n)


def parse(s):
    _check_str(s, 's')

    m = _RE_EXT_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_BAS_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_EXT_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_BAS_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_EXT_WK.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        jan4_ord = _days_before_year(y) + 4
        jan4_wd = (jan4_ord - 1) % 7
        monday_w1 = jan4_ord - jan4_wd
        ord_n = monday_w1 + (wk - 1) * 7 + (wd - 1)
        if ord_n < 1 or ord_n > _MAX_ORDINAL:
            raise ValueError("date out of supported range")
        return from_ordinal(ord_n)

    m = _RE_BAS_WK.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        jan4_ord = _days_before_year(y) + 4
        jan4_wd = (jan4_ord - 1) % 7
        monday_w1 = jan4_ord - jan4_wd
        ord_n = monday_w1 + (wk - 1) * 7 + (wd - 1)
        if ord_n < 1 or ord_n > _MAX_ORDINAL:
            raise ValueError("date out of supported range")
        return from_ordinal(ord_n)

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be one of 'calendar', 'ordinal', 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"
    else:
        raise ValueError(f"unknown form: {form!r}")


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ya, ma, da = a
    yb, mb, db = b
    _check_date_range(ya, ma, da)
    _check_date_range(yb, mb, db)

    if a == b:
        return (0, 0, 0)

    if a > b:
        y, mo, d = diff(b, a)
        return (-y, -mo, -d)

    # a < b
    def _am(k):
        total = (ya - 1) * 12 + (ma - 1) + k
        ty = total // 12 + 1
        tm = total % 12 + 1
        if 1 <= ty <= 9999:
            dim = _MDAYS[tm - 1]
            if tm == 2 and ty % 4 == 0 and (ty % 100 != 0 or ty % 400 == 0):
                dim = 29
            td = min(da, dim)
        else:
            td = 1
        return (ty, tm, td)

    K = (yb - ya) * 12 + (mb - ma)

    while K > 0 and _am(K) > b:
        K -= 1
    while _am(K) <= b:
        K += 1
    K -= 1

    years, months = divmod(K, 12)
    shifted = _am(K)
    days = to_ordinal(yb, mb, db) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)