import re


# ---------- internal helpers ----------

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)  # days before month m (Feb=28)


def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_raw(y, m):
    if m == 2:
        return 29 if _is_leap_raw(y) else 28
    return _MONTH_DAYS[m - 1]


def _days_before_year(y):
    yp = y - 1
    return 365 * yp + yp // 4 - yp // 100 + yp // 400


def _days_before_month(y, m):
    d = _CUM[m - 1]
    if m > 2 and _is_leap_raw(y):
        d += 1
    return d


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for v in x:
        if type(v) is not int:
            raise TypeError(f"{name} must be a tuple of 3 ints")


def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim_raw(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m}")


# ---------- public API ----------

def is_leap(y):
    _check_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim_raw(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    lo, hi = 1, 10000
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid
    y = lo
    doy = n - _days_before_year(y)
    leap = _is_leap_raw(y)
    m = 1
    for i in range(12):
        dim = _MONTH_DAYS[i] + (1 if i == 1 and leap else 0)
        if doy <= dim:
            m = i + 1
            d = doy
            break
        doy -= dim
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
    ord_ = to_ordinal(y, m, d) + n
    if ord_ < 1 or ord_ > 3652059:
        raise OverflowError(f"result ordinal {ord_} out of range 1..3652059")
    return from_ordinal(ord_)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError(f"target year {ty} out of range 1..9999")
    tm = total % 12 + 1
    td = d if d <= _dim_raw(ty, tm) else _dim_raw(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd_jan1 = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if wd_jan1 == 3:
        return 53
    if wd_jan1 == 2 and _is_leap_raw(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ord_ = to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7  # Mon=0
    mon_ord = ord_ - wd
    jan4_ord = to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    iso_wk = (mon_ord - mon_w1) // 7 + 1
    if iso_wk <= 0:
        iso_yr = y - 1
        iso_wk += iso_weeks_in_year(iso_yr)
    elif iso_wk > iso_weeks_in_year(y):
        iso_yr = y + 1
        iso_wk -= iso_weeks_in_year(y)
    else:
        iso_yr = y
    iso_wd = wd + 1  # Mon=1
    return (iso_yr, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_wk):
        raise ValueError(f"week {week} out of range 1..{max_wk} for ISO year {iso_year}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError(f"result ordinal {target} out of range 1..3652059")
    return from_ordinal(target)


# ---------- parse ----------

_RE_EXT_CAL = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_EXT_ORD = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_EXT_WK = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_BAS_CAL = re.compile(r'^([0-9]{8})$')
_RE_BAS_ORD = re.compile(r'^([0-9]{7})$')
_RE_BAS_WK = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    # Extended calendar: YYYY-MM-DD
    mt = _RE_EXT_CAL.match(s)
    if mt:
        y, mo, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range 1..12")
        if not (1 <= d <= _dim_raw(y, mo)):
            raise ValueError(f"day {d} out of range for {y}-{mo}")
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD
    mt = _RE_EXT_ORD.match(s)
    if mt:
        y, doy = int(mt.group(1)), int(mt.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap_raw(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day-of-year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    # Extended week: YYYY-Www-D
    mt = _RE_EXT_WK.match(s)
    if mt:
        y, w, wd = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"iso_year {y} out of range 1..9999")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= w <= max_wk):
            raise ValueError(f"week {w} out of range 1..{max_wk} for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError(f"week date {s} resolves outside supported range")

    # Basic calendar: YYYYMMDD
    mt = _RE_BAS_CAL.match(s)
    if mt:
        s8 = mt.group(1)
        y, mo, d = int(s8[:4]), int(s8[4:6]), int(s8[6:8])
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range 1..12")
        if not (1 <= d <= _dim_raw(y, mo)):
            raise ValueError(f"day {d} out of range for {y}-{mo}")
        return (y, mo, d)

    # Basic ordinal: YYYYDDD
    mt = _RE_BAS_ORD.match(s)
    if mt:
        s7 = mt.group(1)
        y, doy = int(s7[:4]), int(s7[4:7])
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap_raw(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day-of-year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    # Basic week: YYYYWwwD
    mt = _RE_BAS_WK.match(s)
    if mt:
        y, w, wd = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"iso_year {y} out of range 1..9999")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= w <= max_wk):
            raise ValueError(f"week {w} out of range 1..{max_wk} for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError(f"week date {s} resolves outside supported range")

    raise ValueError(f"unrecognized date format: {s!r}")


# ---------- format_date ----------

def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week', got {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, iday = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iday}"


# ---------- diff ----------

def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        ny, nm, nd = diff(b, a)
        return (-ny, -nm, -nd)

    # a < b: find largest K >= 0 with add_months(a, K) <= b
    lo = 0
    hi = (by - ay) * 12 + (bm - am) + 1  # add_months(a, hi) is definitely > b (or OOR)

    while hi - lo > 1:
        mid = (lo + hi) // 2
        total = (ay - 1) * 12 + (am - 1) + mid
        ty = total // 12 + 1
        if ty > 9999:
            hi = mid
            continue
        tm = total % 12 + 1
        td = ad if ad <= _dim_raw(ty, tm) else _dim_raw(ty, tm)
        if (ty, tm, td) <= b:
            lo = mid
        else:
            hi = mid

    K = lo
    years, months = divmod(K, 12)
    # Compute shift(a, K)
    total = (ay - 1) * 12 + (am - 1) + K
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = ad if ad <= _dim_raw(ty, tm) else _dim_raw(ty, tm)
    days = to_ordinal(by, bm, bd) - to_ordinal(ty, tm, td)
    return (years, months, days)