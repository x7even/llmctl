"""Proleptic-Gregorian calendar arithmetic for years 1..9999."""

# ---------------------------------------------------------------------------
# Private helpers (no public API)
# ---------------------------------------------------------------------------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _days_before_year(y):
    """Number of days in years 1 .. y-1."""
    n = y - 1
    if n <= 0:
        return 0
    full = n // 400
    rem = n % 400
    return full * 146097 + rem * 365 + rem // 4 - rem // 100 + rem // 400


def _days_in_year(y):
    return 366 if _is_leap(y) else 365


_DBM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _validate_date(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")


def _to_ordinal(y, m, d):
    days = _days_before_year(y) + _DBM[m - 1] + d
    if m > 2 and _is_leap(y):
        days += 1
    return days


def _from_ordinal(n):
    """Inverse of _to_ordinal; assumes 1 <= n <= 3652059."""
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    leap = _is_leap(y)
    m = 1
    while m <= 12:
        before = _DBM[m - 1] + (1 if m > 2 and leap else 0)
        if doy <= before + _dim(y, m):
            d = doy - before
            break
        m += 1
    return (y, m, d)


def _weekday(y, m, d):
    return (_to_ordinal(y, m, d) - 1) % 7


def _iso_weeks_in_year(iy):
    wd = _weekday(iy, 1, 1)
    if wd == 3:
        return 53
    if wd == 2 and _is_leap(iy):
        return 53
    return 52


def _iso_week(y, m, d):
    ord_ = _to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7
    iso_wd = wd + 1
    mon_ord = ord_ - wd
    thu_ord = mon_ord + 3
    iso_y = _from_ordinal(thu_ord)[0]
    jan4_ord = _to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_mon = jan4_ord - jan4_wd
    iso_w = (mon_ord - first_mon) // 7 + 1
    return (iso_y, iso_w, iso_wd)


def _from_iso_week_ord(iy, w, wd):
    """Return the ordinal for the given ISO week date."""
    jan4_ord = _to_ordinal(iy, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_mon = jan4_ord - jan4_wd
    return first_mon + (w - 1) * 7 + (wd - 1)


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int")


def _check_date(x, name):
    if not (type(x) is tuple and len(x) == 3 and
            all(type(v) is int for v in x)):
        raise TypeError(f"{name} must be a tuple of 3 ints")


def _all_ascii_digits(s, start, end):
    for i in range(start, end):
        c = s[i]
        if c < '0' or c > '9':
            return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _check_int(y, "y")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate_date(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    _check_int(n, "n")
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ordinal(n)


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate_date(y, m, d)
    return _weekday(y, m, d)


def add_days(date, n):
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _validate_date(y, m, d)
    ord_ = _to_ordinal(y, m, d) + n
    if ord_ < 1 or ord_ > 3652059:
        raise OverflowError("result out of range")
    return _from_ordinal(ord_)


def add_months(date, n):
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _validate_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("result out of range")
    nd = min(d, _dim(ny, nm))
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate_date(y, m, d)
    return _iso_week(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_w = _iso_weeks_in_year(iso_year)
    if week < 1 or week > max_w:
        raise ValueError(f"week {week} out of range 1..{max_w}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    target = _from_iso_week_ord(iso_year, week, weekday)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return _from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")
    n = len(s)

    if n == 10:
        # Extended calendar YYYY-MM-DD or extended week YYYY-Www-D
        if s[4] != '-':
            raise ValueError(f"invalid date string: {s!r}")
        if s[5] == 'W':
            # YYYY-Www-D
            if s[8] != '-':
                raise ValueError(f"invalid date string: {s!r}")
            if not (_all_ascii_digits(s, 0, 4) and
                    _all_ascii_digits(s, 6, 8) and
                    _all_ascii_digits(s, 9, 10)):
                raise ValueError(f"invalid date string: {s!r}")
            iy = int(s[0:4])
            w = int(s[6:8])
            wd = int(s[9])
            if iy < 1 or iy > 9999:
                raise ValueError(f"year {iy} out of range 1..9999")
            max_w = _iso_weeks_in_year(iy)
            if w < 1 or w > max_w:
                raise ValueError(f"week {w} out of range 1..{max_w}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            target = _from_iso_week_ord(iy, w, wd)
            if target < 1 or target > 3652059:
                raise ValueError("date out of range")
            return _from_ordinal(target)
        else:
            # YYYY-MM-DD
            if s[7] != '-':
                raise ValueError(f"invalid date string: {s!r}")
            if not (_all_ascii_digits(s, 0, 4) and
                    _all_ascii_digits(s, 5, 7) and
                    _all_ascii_digits(s, 8, 10)):
                raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            m = int(s[5:7])
            d = int(s[8:10])
            _validate_date(y, m, d)
            return (y, m, d)

    elif n == 8:
        if s[4] == '-':
            # Extended ordinal YYYY-DDD
            if not (_all_ascii_digits(s, 0, 4) and
                    _all_ascii_digits(s, 5, 8)):
                raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            doy = int(s[5:8])
            if y < 1 or y > 9999:
                raise ValueError(f"year {y} out of range 1..9999")
            if doy < 1 or doy > _days_in_year(y):
                raise ValueError(f"day of year {doy} out of range")
            return _from_ordinal(_days_before_year(y) + doy)
        elif s[4] == 'W':
            # Basic week YYYYWwwD
            if not (_all_ascii_digits(s, 0, 4) and
                    _all_ascii_digits(s, 5, 8)):
                raise ValueError(f"invalid date string: {s!r}")
            iy = int(s[0:4])
            w = int(s[5:7])
            wd = int(s[7])
            if iy < 1 or iy > 9999:
                raise ValueError(f"year {iy} out of range 1..9999")
            max_w = _iso_weeks_in_year(iy)
            if w < 1 or w > max_w:
                raise ValueError(f"week {w} out of range 1..{max_w}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            target = _from_iso_week_ord(iy, w, wd)
            if target < 1 or target > 3652059:
                raise ValueError("date out of range")
            return _from_ordinal(target)
        else:
            # Basic calendar YYYYMMDD
            if not _all_ascii_digits(s, 0, 8):
                raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            m = int(s[4:6])
            d = int(s[6:8])
            _validate_date(y, m, d)
            return (y, m, d)

    elif n == 7:
        # Basic ordinal YYYYDDD
        if not _all_ascii_digits(s, 0, 7):
            raise ValueError(f"invalid date string: {s!r}")
        y = int(s[0:4])
        doy = int(s[4:7])
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        if doy < 1 or doy > _days_in_year(y):
            raise ValueError(f"day of year {doy} out of range")
        return _from_ordinal(_days_before_year(y) + doy)

    else:
        raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date(date, "date")
    y, m, d = date
    _validate_date(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a str")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _DBM[m - 1] + d + (1 if m > 2 and _is_leap(y) else 0)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, iwd = _iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"
    else:
        raise ValueError(f"unknown form: {form!r}")


def diff(a, b):
    _check_date(a, "a")
    _check_date(b, "b")
    _validate_date(*a)
    _validate_date(*b)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    lo, hi = 0, 120000

    def _shift_leq(K):
        total = (a[0] - 1) * 12 + (a[1] - 1) + K
        ny = total // 12 + 1
        nm = total % 12 + 1
        if ny > 9999:
            return False
        nd = min(a[2], _dim(ny, nm))
        return (ny, nm, nd) <= b

    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift_leq(mid):
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)

    total = (a[0] - 1) * 12 + (a[1] - 1) + K
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(a[2], _dim(ny, nm))
    shifted = (ny, nm, nd)

    days = _to_ordinal(*b) - _to_ordinal(*shifted)
    return (years, months, days)