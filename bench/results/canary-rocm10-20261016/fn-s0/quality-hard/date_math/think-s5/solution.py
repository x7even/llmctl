"""Proleptic-Gregorian calendar arithmetic for years 1 through 9999."""

_MONTH_PREFIX = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_DAYS_IN_MONTH = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MAX_ORD = 3652059


# --------------- internal helpers (no validation) ---------------

def _is_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def _dim(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _DAYS_IN_MONTH[m]


def _ordinal(y, m, d):
    y1 = y - 1
    return (365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
            + _MONTH_PREFIX[m] + d + (1 if m > 2 and _is_leap(y) else 0))


def _from_ord(n):
    z = n + 305
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    if m <= 2:
        y += 1
    return (y, m, d)


def _weekday_raw(y, m, d):
    return (_ordinal(y, m, d) - 1) % 7


def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        return None
    nd = d
    lim = _dim(ny, nm)
    if nd > lim:
        nd = lim
    return (ny, nm, nd)


def _iso_wks(iy):
    wd = _weekday_raw(iy, 1, 1)
    if wd == 3:
        return 53
    if wd == 2 and _is_leap(iy):
        return 53
    return 52


def _iso_week_raw(y, m, d):
    o = _ordinal(y, m, d)
    wd = (o - 1) % 7
    thu = o + (3 - wd)
    iy, _, _ = _from_ord(thu)
    j4 = _ordinal(iy, 1, 4)
    j4wd = (j4 - 1) % 7
    w1mon = j4 - j4wd
    wk = (o - w1mon) // 7 + 1
    return (iy, wk, wd + 1)


def _from_iso_raw(iy, wk, wd):
    j4 = _ordinal(iy, 1, 4)
    j4wd = (j4 - 1) % 7
    w1mon = j4 - j4wd
    target = w1mon + (wk - 1) * 7 + (wd - 1)
    if target < 1 or target > _MAX_ORD:
        return None
    return _from_ord(target)


# --------------- validation helpers ---------------

def _ck_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _ck_date_types(y, m, d):
    _ck_int(y, 'year')
    _ck_int(m, 'month')
    _ck_int(d, 'day')


def _ck_date_ranges(y, m, d):
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if not 1 <= m <= 12:
        raise ValueError(f"month {m} out of range 1..12")
    if not 1 <= d <= _dim(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


def _ck_date_full(y, m, d):
    _ck_date_types(y, m, d)
    _ck_date_ranges(y, m, d)


def _ck_tuple(t, name):
    if type(t) is not tuple:
        raise TypeError(f"{name} must be a tuple, got {type(t).__name__}")
    if len(t) != 3:
        raise TypeError(f"{name} must have exactly 3 elements, got {len(t)}")
    _ck_int(t[0], f"{name}[0]")
    _ck_int(t[1], f"{name][1]" if False else f"{name}[1]")
    _ck_int(t[2], f"{name}[2]")


def _ck_date_tuple(t, name):
    _ck_tuple(t, name)
    _ck_date_ranges(t[0], t[1], t[2])


# --------------- public API ---------------

def is_leap(y):
    _ck_int(y, 'year')
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _ck_int(y, 'year')
    _ck_int(m, 'month')
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if not 1 <= m <= 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _ck_date_full(y, m, d)
    return _ordinal(y, m, d)


def from_ordinal(n):
    _ck_int(n, 'n')
    if not 1 <= n <= _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ord(n)


def weekday(y, m, d):
    _ck_date_full(y, m, d)
    return (_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _ck_tuple(date, 'date')
    _ck_int(n, 'n')
    _ck_date_ranges(date[0], date[1], date[2])
    o = _ordinal(date[0], date[1], date[2]) + n
    if o < 1 or o > _MAX_ORD:
        raise OverflowError("result date out of range")
    return _from_ord(o)


def add_months(date, n):
    _ck_tuple(date, 'date')
    _ck_int(n, 'n')
    _ck_date_ranges(date[0], date[1], date[2])
    result = _add_months_raw(date[0], date[1], date[2], n)
    if result is None:
        raise OverflowError("target year out of range 1..9999")
    return result


def iso_weeks_in_year(iso_year):
    _ck_int(iso_year, 'iso_year')
    if not 1 <= iso_year <= 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_wks(iso_year)


def iso_week(y, m, d):
    _ck_date_full(y, m, d)
    return _iso_week_raw(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _ck_int(iso_year, 'iso_year')
    _ck_int(week, 'week')
    _ck_int(weekday, 'weekday')
    if not 1 <= iso_year <= 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = _iso_wks(iso_year)
    if not 1 <= week <= max_wk:
        raise ValueError(f"week {week} out of range 1..{max_wk}")
    if not 1 <= weekday <= 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    result = _from_iso_raw(iso_year, week, weekday)
    if result is None:
        raise OverflowError("result date out of range")
    return result


def _parse_int(s, start, length):
    val = 0
    for i in range(start, start + length):
        c = s[i]
        if c < '0' or c > '9':
            raise ValueError(f"non-digit character at position {i}")
        val = val * 10 + (ord(c) - 48)
    return val


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")
    n = len(s)
    if n == 10:
        if s[4] != '-':
            raise ValueError("invalid format")
        if s[5] == 'W':
            # YYYY-Www-D
            if s[8] != '-':
                raise ValueError("invalid format")
            iy = _parse_int(s, 0, 4)
            wk = _parse_int(s, 6, 2)
            wd = _parse_int(s, 9, 1)
            return _parse_week(iy, wk, wd)
        else:
            # YYYY-MM-DD
            if s[7] != '-':
                raise ValueError("invalid format")
            y = _parse_int(s, 0, 4)
            m = _parse_int(s, 5, 2)
            d = _parse_int(s, 8, 2)
            return _parse_cal(y, m, d)
    elif n == 8:
        if s[4] == '-':
            # YYYY-DDD
            y = _parse_int(s, 0, 4)
            doy = _parse_int(s, 5, 3)
            return _parse_ord(y, doy)
        elif s[4] == 'W':
            # YYYYWwwD
            iy = _parse_int(s, 0, 4)
            wk = _parse_int(s, 5, 2)
            wd = _parse_int(s, 7, 1)
            return _parse_week(iy, wk, wd)
        else:
            # YYYYMMDD
            y = _parse_int(s, 0, 4)
            m = _parse_int(s, 4, 2)
            d = _parse_int(s, 6, 2)
            return _parse_cal(y, m, d)
    elif n == 7:
        # YYYYDDD
        y = _parse_int(s, 0, 4)
        doy = _parse_int(s, 4, 3)
        return _parse_ord(y, doy)
    else:
        raise ValueError("invalid format length")


def _parse_cal(y, m, d):
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range")
    if not 1 <= m <= 12:
        raise ValueError(f"month {m} out of range")
    if not 1 <= d <= _dim(y, m):
        raise ValueError(f"day {d} out of range")
    return (y, m, d)


def _parse_ord(y, doy):
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range")
    max_doy = 366 if _is_leap(y) else 365
    if not 1 <= doy <= max_doy:
        raise ValueError(f"day-of-year {doy} out of range")
    # convert ordinal to date
    o = _ordinal(y, 1, 1) + doy - 1
    return _from_ord(o)


def _parse_week(iy, wk, wd):
    if not 1 <= iy <= 9999:
        raise ValueError(f"iso_year {iy} out of range")
    max_wk = _iso_wks(iy)
    if not 1 <= wk <= max_wk:
        raise ValueError(f"week {wk} out of range 1..{max_wk}")
    if not 1 <= wd <= 7:
        raise ValueError(f"weekday {wd} out of range 1..7")
    result = _from_iso_raw(iy, wk, wd)
    if result is None:
        raise ValueError("week date falls outside supported range")
    return result


def format_date(date, form):
    _ck_tuple(date, 'date')
    _ck_date_ranges(date[0], date[1], date[2])
    if form != 'calendar' and form != 'ordinal' and form != 'week':
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    y, m, d = date
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _ordinal(y, m, d) - _ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, iwd = _iso_week_raw(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _ck_tuple(a, 'a')
    _ck_tuple(b, 'b')
    _ck_date_ranges(a[0], a[1], a[2])
    _ck_date_ranges(b[0], b[1], b[2])
    oa = _ordinal(a[0], a[1], a[2])
    ob = _ordinal(b[0], b[1], b[2])
    if oa > ob:
        ry, rm, rd = diff(b, a)
        return (-ry, -rm, -rd)
    if oa == ob:
        return (0, 0, 0)
    # a < b: find largest K >= 0 with shift(a, K) <= b
    ay, am, ad = a
    lo, hi = 0, (b[0] - ay + 1) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _add_months_raw(ay, am, ad, mid)
        if shifted is None:
            hi = mid - 1
        else:
            so = _ordinal(shifted[0], shifted[1], shifted[2])
            if so <= ob:
                lo = mid
            else:
                hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_raw(ay, am, ad, K)
    so = _ordinal(shifted[0], shifted[1], shifted[2])
    days = ob - so
    return (years, months, days)
