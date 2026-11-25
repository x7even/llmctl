import re

# ---------------------------------------------------------------------------
# Internal helpers (no validation)
# ---------------------------------------------------------------------------

_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORD = 3652059  # ordinal of (9999, 12, 31)


def _dim(y, m):
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30


def _days_before_year(y):
    n = y - 1
    return n * 365 + n // 4 - n // 100 + n // 400


def _to_ordinal(y, m, d):
    r = _days_before_year(y) + _CUM[m - 1] + d
    if m > 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        r += 1
    return r


def _validate_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")


def _check_int(x, name='x'):
    if type(x) is not int:
        raise TypeError(f"argument {name} must be int, got {type(x).__name__}")


def _check_date(x, name='date'):
    if type(x) is not tuple:
        raise TypeError(f"argument {name} must be a tuple of 3 ints, got {type(x).__name__}")
    if len(x) != 3:
        raise TypeError(f"argument {name} must be a tuple of 3 ints, got length {len(x)}")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"element {i} of {name} must be int, got {type(v).__name__}")


# ---------------------------------------------------------------------------
# Pre-compiled regexes for parse
# ---------------------------------------------------------------------------

_RE_CAL_EXT = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_CAL_BAS = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_ORD_EXT = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_ORD_BAS = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_WK_EXT = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_WK_BAS = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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
    _validate_date(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= _MAX_ORD):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    n0 = n - 1
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) <= n0:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    day_in_year = n0 - _days_before_year(y)
    m = 1
    while True:
        dim = _dim(y, m)
        if day_in_year < dim:
            break
        day_in_year -= dim
        m += 1
    d = day_in_year + 1
    return (y, m, d)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)
    return (_to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _validate_date(y, m, d)
    ord_ = _to_ordinal(y, m, d) + n
    if ord_ < 1 or ord_ > _MAX_ORD:
        raise OverflowError(f"result ordinal {ord_} out of range")
    return from_ordinal(ord_)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _validate_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError(f"target year {ty} out of range")
    td = min(d, _dim(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = (_to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:  # Thursday
        return 53
    if jan1_wd == 2 and (iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0)):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)
    ord_ = _to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7  # 0=Mon .. 6=Sun
    iso_weekday = wd + 1
    monday_ord = ord_ - wd
    thursday_ord = monday_ord + 3
    # Determine ISO year
    if thursday_ord < _days_before_year(y) + 1:
        iso_year = y - 1
    elif thursday_ord > _days_before_year(y + 1):
        iso_year = y + 1
    else:
        iso_year = y
    # Week-1 Monday for iso_year
    jan4 = _days_before_year(iso_year) + 4
    jan4_wd = (jan4 - 1) % 7
    week1_monday = jan4 - jan4_wd
    iso_week_num = (monday_ord - week1_monday) // 7 + 1
    return (iso_year, iso_week_num, iso_weekday)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_wk):
        raise ValueError(f"week {week} out of range 1..{max_wk}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4 = _days_before_year(iso_year) + 4
    jan4_wd = (jan4 - 1) % 7
    week1_monday = jan4 - jan4_wd
    target = week1_monday + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError(f"result ordinal {target} out of range")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"argument s must be str, got {type(s).__name__}")

    # Try each pattern
    m = _RE_CAL_EXT.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_CAL_BAS.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_ORD_EXT.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range")
        return from_ordinal(_to_ordinal(y, 1, 1) - 1 + doy)

    m = _RE_ORD_BAS.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range")
        return from_ordinal(_to_ordinal(y, 1, 1) - 1 + doy)

    m = _RE_WK_EXT.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4 = _days_before_year(y) + 4
        jan4_wd = (jan4 - 1) % 7
        week1_monday = jan4 - jan4_wd
        target = week1_monday + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > _MAX_ORD:
            raise ValueError(f"week date out of supported range")
        return from_ordinal(target)

    m = _RE_WK_BAS.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4 = _days_before_year(y) + 4
        jan4_wd = (jan4 - 1) % 7
        week1_monday = jan4 - jan4_wd
        target = week1_monday + (wk - 1) * 7 + (wd - 1)
        if target < 1 or target > _MAX_ORD:
            raise ValueError(f"week date out of supported range")
        return from_ordinal(target)

    raise ValueError(f"unrecognized date string: {s!r}")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _validate_date(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a string, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, iday = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iday}"
    else:
        raise ValueError(f"unknown form {form!r}")


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ya, ma, da = a
    yb, mb, db = b
    _validate_date(ya, ma, da)
    _validate_date(yb, mb, db)

    if a == b:
        return (0, 0, 0)

    if a > b:
        ya, ma, da, yb, mb, db = yb, mb, db, ya, ma, da
        sign = -1
    else:
        sign = 1

    # Now (ya,ma,da) <= (yb,mb,db)
    K = (yb - ya) * 12 + (mb - ma)
    cand_day = min(da, _dim(yb, mb))
    if cand_day > db:
        K -= 1

    years, months = divmod(K, 12)
    total_m = (ya - 1) * 12 + (ma - 1) + K
    ty = total_m // 12 + 1
    tm = total_m % 12 + 1
    td = min(da, _dim(ty, tm))
    days = _to_ordinal(yb, mb, db) - _to_ordinal(ty, tm, td)

    return (sign * years, sign * months, sign * days)