import re  # allowed but not strictly needed; kept for potential use

_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORDINAL = 3652059


# ---------- internal helpers (no type/range checking) ----------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MDAYS[m - 1]


def _ordinal(y, m, d):
    yy = y - 1
    days = yy * 365 + yy // 4 - yy // 100 + yy // 400
    days += _DAYS_BEFORE_MONTH[m - 1]
    if m > 2 and _is_leap(y):
        days += 1
    days += d
    return days


def _weekday_of(y, m, d):
    return (_ordinal(y, m, d) - 1) % 7


def _shift_months(date, k):
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + k
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


def _from_ordinal_doy(y, doy):
    leap = _is_leap(y)
    for i in range(12):
        md = _MDAYS[i] + (1 if i == 1 and leap else 0)
        if doy <= md:
            return (y, i + 1, doy)
        doy -= md
    raise ValueError("invalid day of year")


# ---------- type / range checking helpers ----------

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date_tuple(x, name):
    if type(x) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _validate_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y:04d}-{m:02d}")


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
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)
    return _ordinal(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= _MAX_ORDINAL):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        dm = mid * 365 + mid // 4 - mid // 100 + mid // 400
        if dm < n:
            lo = mid + 1
        else:
            hi = mid
    y = lo
    prev = (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    doy = n - prev
    return _from_ordinal_doy(y, doy)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)
    return _weekday_of(y, m, d)


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _validate_date(y, m, d)
    ord_ = _ordinal(y, m, d) + n
    if ord_ < 1 or ord_ > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {ord_} out of range 1..{_MAX_ORDINAL}")
    return from_ordinal(ord_)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _validate_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if not (1 <= ny <= 9999):
        raise OverflowError(f"target year {ny} out of range 1..9999")
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = _weekday_of(iso_year, 1, 1)
    if wd == 3 or (wd == 2 and _is_leap(iso_year)):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)
    ord_ = _ordinal(y, m, d)
    wd = (ord_ - 1) % 7
    mon_ord = ord_ - wd
    thu_ord = mon_ord + 3
    # determine iso_year from Thursday
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        dm = mid * 365 + mid // 4 - mid // 100 + mid // 400
        if dm < thu_ord:
            lo = mid + 1
        else:
            hi = mid
    iso_year = lo
    # Monday of ISO week 1
    jan4 = _ordinal(iso_year, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4_wd
    week = (mon_ord - mon_w1) // 7 + 1
    iso_weekday = wd + 1
    return (iso_year, week, iso_weekday)


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
    jan4 = _ordinal(iso_year, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {target} out of range 1..{_MAX_ORDINAL}")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    n = len(s)

    def _digits_at(s, indices):
        for i in indices:
            c = s[i]
            if c < '0' or c > '9':
                raise ValueError(f"invalid character {c!r} in date string")

    if n == 10:
        if s[4] == '-' and s[7] == '-':
            _digits_at(s, (0, 1, 2, 3, 5, 6, 8, 9))
            y = int(s[0:4]); m = int(s[5:7]); d = int(s[8:10])
            _validate_date(y, m, d)
            return (y, m, d)
        if s[4] == '-' and s[5] == 'W' and s[8] == '-':
            _digits_at(s, (0, 1, 2, 3, 6, 7, 9))
            y = int(s[0:4]); w = int(s[6:8]); wd = int(s[9])
            _validate_parse_week(y, w, wd)
            return _from_iso_week_parse(y, w, wd)

    elif n == 8:
        if s[4] == '-':
            _digits_at(s, (0, 1, 2, 3, 5, 6, 7))
            y = int(s[0:4]); doy = int(s[5:8])
            _validate_parse_ordinal(y, doy)
            return _from_ordinal_doy(y, doy)
        if s[4] == 'W':
            _digits_at(s, (0, 1, 2, 3, 6, 7, 8))
            y = int(s[0:4]); w = int(s[6:8]); wd = int(s[8])
            _validate_parse_week(y, w, wd)
            return _from_iso_week_parse(y, w, wd)
        # all-digit 8-char: YYYYMMDD
        _digits_at(s, (0, 1, 2, 3, 4, 5, 6, 7))
        y = int(s[0:4]); m = int(s[4:6]); d = int(s[6:8])
        _validate_date(y, m, d)
        return (y, m, d)

    elif n == 7:
        _digits_at(s, (0, 1, 2, 3, 4, 5, 6))
        y = int(s[0:4]); doy = int(s[4:7])
        _validate_parse_ordinal(y, doy)
        return _from_ordinal_doy(y, doy)

    raise ValueError(f"invalid date string: {s!r}")


def _validate_parse_ordinal(y, doy):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range")
    max_doy = 366 if _is_leap(y) else 365
    if not (1 <= doy <= max_doy):
        raise ValueError(f"day of year {doy} out of range 1..{max_doy}")


def _validate_parse_week(y, w, wd):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range")
    max_w = iso_weeks_in_year(y)
    if not (1 <= w <= max_w):
        raise ValueError(f"week {w} out of range 1..{max_w}")
    if not (1 <= wd <= 7):
        raise ValueError(f"weekday {wd} out of range 1..7")


def _from_iso_week_parse(y, w, wd):
    jan4 = _ordinal(y, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4_wd
    target = mon_w1 + (w - 1) * 7 + (wd - 1)
    if target < 1 or target > _MAX_ORDINAL:
        raise ValueError("date out of range")
    return from_ordinal(target)


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _validate_date(y, m, d)

    if type(form) is not str:
        raise ValueError(f"form must be a string, got {type(form).__name__}")
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _DAYS_BEFORE_MONTH[m - 1] + d
        if m > 2 and _is_leap(y):
            doy += 1
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    _validate_date(*a)
    _validate_date(*b)

    if a == b:
        return (0, 0, 0)

    if a <= b:
        ay, am, ad = a
        by, bm, bd = b
        max_k = (by - ay) * 12 + (bm - am)
        lo, hi = 0, max_k
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _shift_months(a, mid) <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _shift_months(a, K)
        days = _ordinal(by, bm, bd) - _ordinal(*shifted)
        return (years, months, days)
    else:
        y, m, d = diff(b, a)
        return (-y, -m, -d)