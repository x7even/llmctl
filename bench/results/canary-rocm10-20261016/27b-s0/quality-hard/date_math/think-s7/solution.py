"""Proleptic-Gregorian calendar arithmetic for years 1..9999."""

import re

_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
_MAX_ORD = 3652059  # ordinal of (9999,12,31)


# ---------- internal helpers (no public range checks) ----------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MDAYS[m - 1]


def _days_before_year(y):
    """0-based day count before Jan 1 of year y."""
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


def _days_before_month(y, m):
    """0-based day count before month m in year y."""
    if m > 2 and _is_leap(y):
        return _CUM_LEAP[m - 1]
    return _CUM[m - 1]


def _ordinal(y, m, d):
    """1-based ordinal, no range check."""
    return _days_before_year(y) + _days_before_month(y, m) + d


def _from_ordinal(n):
    """Inverse of _ordinal, no range check. n >= 1."""
    # Estimate year
    y = (n * 400) // 146097 + 1
    while _days_before_year(y + 1) <= n - 1:
        y += 1
    while _days_before_year(y) > n - 1:
        y -= 1
    doy = n - _days_before_year(y)  # 1-based day of year
    cum = _CUM_LEAP if _is_leap(y) else _CUM
    # Binary search for month
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi) // 2
        if doy > cum[mid]:
            lo = mid + 1
        else:
            hi = mid
    m = lo
    d = doy - cum[m - 1]
    return (y, m, d)


# ---------- type / range checking helpers ----------

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(v).__name__}")


def _check_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= _days_in_month(y, m)):
        raise ValueError(f"day {d} out of range 1..{_days_in_month(y, m)}")


def _check_str(x, name):
    if type(x) is not str:
        raise TypeError(f"{name} must be a str, got {type(x).__name__}")


# ---------- public API ----------

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
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    return _ordinal(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= _MAX_ORD):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ordinal(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > _MAX_ORD:
        raise OverflowError(f"result ordinal {ord_val} out of range")
    return _from_ordinal(ord_val)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError(f"target year {ty} out of range 1..9999")
    td = min(d, _days_in_month(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7  # Mon=0
    if wd == 3:  # Thursday
        return 53
    if _is_leap(iso_year) and wd == 2:  # Wednesday in leap year
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    ord_val = _ordinal(y, m, d)
    w = (ord_val - 1) % 7  # Mon=0
    iso_wd = w + 1  # Mon=1 .. Sun=7
    # Thursday of this week
    thu_ord = ord_val + (3 - w)
    # Find ISO year (year of that Thursday)
    iso_y = _from_ordinal(thu_ord)[0]
    # Monday of week 1 of iso_y: the Monday of the week containing Jan 4
    jan4_ord = _ordinal(iso_y, 1, 4)
    jan4_w = (jan4_ord - 1) % 7
    week1_mon = jan4_ord - jan4_w
    # Monday of this week
    mon_ord = ord_val - w
    week = (mon_ord - week1_mon) // 7 + 1
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday_):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday_, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday_ <= 7):
        raise ValueError(f"weekday {weekday_} out of range 1..7")
    # Monday of week 1
    jan4_ord = _ordinal(iso_year, 1, 4)
    jan4_w = (jan4_ord - 1) % 7
    week1_mon = jan4_ord - jan4_w
    # Target date
    target_ord = week1_mon + (week - 1) * 7 + (weekday_ - 1)
    if target_ord < 1 or target_ord > _MAX_ORD:
        raise OverflowError(f"result ordinal {target_ord} out of range")
    return _from_ordinal(target_ord)


def parse(s):
    _check_str(s, 's')
    n = len(s)

    def _digits(s, start, end):
        """Extract integer from s[start:end], verifying all ASCII digits."""
        for i in range(start, end):
            if s[i] < '0' or s[i] > '9':
                raise ValueError(f"invalid character {s[i]!r} at position {i}")
        return int(s[start:end])

    if n == 10:
        if s[4] != '-':
            raise ValueError("invalid format")
        if s[7] == '-':
            # YYYY-MM-DD
            y = _digits(s, 0, 4)
            m = _digits(s, 5, 7)
            d = _digits(s, 8, 10)
            if s[5] != '0' or s[8] != '0':
                pass  # leading zeros required is enforced by fixed positions
            _check_valid_date(y, m, d)
            return (y, m, d)
        elif s[5] == 'W' and s[8] == '-':
            # YYYY-Www-D
            y = _digits(s, 0, 4)
            if s[6] < '0' or s[6] > '9' or s[7] < '0' or s[7] > '9':
                raise ValueError("invalid digit in week")
            if s[9] < '0' or s[9] > '9':
                raise ValueError("invalid digit in weekday")
            ww = int(s[6:8])
            wd = int(s[9])
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range")
            max_w = iso_weeks_in_year(y)
            if not (1 <= ww <= max_w):
                raise ValueError(f"week {ww} out of range 1..{max_w}")
            if not (1 <= wd <= 7):
                raise ValueError(f"weekday {wd} out of range 1..7")
            try:
                return from_iso_week(y, ww, wd)
            except OverflowError:
                raise ValueError("week date out of supported range")
        else:
            raise ValueError("invalid format")
    elif n == 8:
        if s[4] == '-':
            # YYYY-DDD (ordinal extended)
            y = _digits(s, 0, 4)
            ddd = _digits(s, 5, 8)
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range")
            max_doy = 366 if _is_leap(y) else 365
            if not (1 <= ddd <= max_doy):
                raise ValueError(f"day of year {ddd} out of range 1..{max_doy}")
            return _from_ordinal(_ordinal(y, 1, 1) - 1 + ddd)
        elif s[4] == 'W':
            # YYYYWwwD (week basic)
            y = _digits(s, 0, 4)
            if s[5] < '0' or s[5] > '9' or s[6] < '0' or s[6] > '9':
                raise ValueError("invalid digit in week")
            if s[7] < '0' or s[7] > '9':
                raise ValueError("invalid digit in weekday")
            ww = int(s[5:7])
            wd = int(s[7])
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range")
            max_w = iso_weeks_in_year(y)
            if not (1 <= ww <= max_w):
                raise ValueError(f"week {ww} out of range 1..{max_w}")
            if not (1 <= wd <= 7):
                raise ValueError(f"weekday {wd} out of range 1..7")
            try:
                return from_iso_week(y, ww, wd)
            except OverflowError:
                raise ValueError("week date out of supported range")
        else:
            # YYYYMMDD (calendar basic) - all 8 must be digits
            y = _digits(s, 0, 4)
            m = _digits(s, 4, 6)
            d = _digits(s, 6, 8)
            _check_valid_date(y, m, d)
            return (y, m, d)
    elif n == 7:
        # YYYYDDD (ordinal basic)
        y = _digits(s, 0, 4)
        ddd = _digits(s, 4, 7)
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= ddd <= max_doy):
            raise ValueError(f"day of year {ddd} out of range 1..{max_doy}")
        return _from_ordinal(_ordinal(y, 1, 1) - 1 + ddd)
    else:
        raise ValueError("invalid format")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_valid_date(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with _shift(a, K) <= b
    def _shift(K):
        total = am - 1 + K
        ty = ay + total // 12
        tm = total % 12 + 1
        td = min(ad, _days_in_month(ty, tm))
        return (ty, tm, td)

    lo, hi = 0, (by - ay) * 12 + 12
    # Ensure hi is large enough (shift(a, hi) > b)
    # (by - ay) * 12 + 12 should be more than enough since the year of
    # shift(a, hi) = ay + (am-1+hi)//12 >= ay + (am-1 + (by-ay)*12 + 12)//12
    # which is at least by + 1 (since am-1+12 >= 12, so //12 adds at least 1)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift(mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _shift(K)
    days = to_ordinal(by, bm, bd) - _ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
