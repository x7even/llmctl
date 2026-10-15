"""Proleptic-Gregorian calendar arithmetic for years 1..9999."""

# ---------------------------------------------------------------------------
# Internal helpers (not part of the public API)
# ---------------------------------------------------------------------------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30


def _days_before_year(y):
    """Days from 1-Jan of year 1 through 31-Dec of year y-1."""
    return (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date_tuple(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


def _is_ascii_digit(c):
    return '0' <= c <= '9'


def _days_of_year(y, m, d):
    """1-based day-of-year."""
    s = d
    for mm in range(1, m):
        s += _dim(y, mm)
    return s


def _from_doy(y, doy):
    """Convert 1-based day-of-year to (y, m, d)."""
    for m in range(1, 13):
        dim = _dim(y, m)
        if doy <= dim:
            return (y, m, doy)
        doy -= dim
    raise ValueError("unreachable")


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
    _check_date_range(y, m, d)
    return _days_before_year(y) + _days_of_year(y, m, d)


def from_ordinal(n):
    _check_int(n, "n")
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    d = n - 1  # 0-indexed
    # Use 400-year cycle to narrow down
    cycles = d // 146097
    rem = d % 146097
    base = cycles * 400
    # Binary search within the 400-year cycle
    lo, hi = 1, 400
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(base + mid) <= d:
            lo = mid
        else:
            hi = mid - 1
    y = base + lo
    doy = d - _days_before_year(y) + 1
    return _from_doy(y, doy)


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    ord_n = to_ordinal(y, m, d) + n
    if ord_n < 1 or ord_n > 3652059:
        raise OverflowError(f"result ordinal {ord_n} out of range 1..3652059")
    return from_ordinal(ord_n)


def add_months(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError(f"result year {new_y} out of range 1..9999")
    new_d = d if d <= _dim(new_y, new_m) else _dim(new_y, new_m)
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    w = (to_ordinal(iso_year, 1, 1) - 1) % 7  # weekday of Jan 1
    if w == 3 or (_is_leap(iso_year) and w == 2):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    ord_ = to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7  # Mon=0
    iso_wd = wd + 1  # Mon=1
    # Monday of the week containing Jan 4 of year y
    jan4_ord = to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_week1 = jan4_ord - jan4_wd
    # Monday of the current week
    mon_cur = ord_ - wd
    week = (mon_cur - mon_week1) // 7 + 1
    if week < 1:
        iso_y = y - 1
        week = iso_weeks_in_year(iso_y) + week
    elif week > iso_weeks_in_year(y):
        iso_y = y + 1
        week = week - iso_weeks_in_year(y)
    else:
        iso_y = y
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_wk:
        raise ValueError(f"week {week} out of range 1..{max_wk} for ISO year {iso_year}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    # Compute the ordinal
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_week1 = jan4_ord - jan4_wd
    target = mon_week1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError(f"result ordinal {target} out of range 1..3652059")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    n = len(s)

    if n == 10:
        # YYYY-MM-DD or YYYY-Www-D
        if s[4] == '-' and s[7] == '-':
            # Extended calendar
            for i in (0, 1, 2, 3, 5, 6, 8, 9):
                if not _is_ascii_digit(s[i]):
                    raise ValueError(f"invalid character in date string: {s!r}")
            y = int(s[0:4])
            m = int(s[5:7])
            d = int(s[8:10])
            if y < 1:
                raise ValueError(f"year {y} out of range 1..9999")
            _check_date_range(y, m, d)
            return (y, m, d)
        elif s[4] == '-' and s[5] == 'W' and s[8] == '-':
            # Extended week
            for i in (0, 1, 2, 3, 6, 7, 9):
                if not _is_ascii_digit(s[i]):
                    raise ValueError(f"invalid character in date string: {s!r}")
            iso_y = int(s[0:4])
            wk = int(s[6:8])
            wd = int(s[9])
            if iso_y < 1:
                raise ValueError(f"year {iso_y} out of range 1..9999")
            max_wk = iso_weeks_in_year(iso_y)
            if wk < 1 or wk > max_wk:
                raise ValueError(f"week {wk} out of range 1..{max_wk}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            try:
                return from_iso_week(iso_y, wk, wd)
            except OverflowError:
                raise ValueError(f"week date {s!r} resolves to a date outside 1..9999")
        else:
            raise ValueError(f"unrecognized date format: {s!r}")

    elif n == 8:
        if s[4] == '-':
            # Extended ordinal: YYYY-DDD
            for i in (0, 1, 2, 3, 5, 6, 7):
                if not _is_ascii_digit(s[i]):
                    raise ValueError(f"invalid character in date string: {s!r}")
            y = int(s[0:4])
            doy = int(s[5:8])
            if y < 1:
                raise ValueError(f"year {y} out of range 1..9999")
            max_doy = 366 if _is_leap(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
            return _from_doy(y, doy)
        elif s[4] == 'W':
            # Basic week: YYYYWwwD
            for i in (0, 1, 2, 3, 5, 6, 7):
                if not _is_ascii_digit(s[i]):
                    raise ValueError(f"invalid character in date string: {s!r}")
            iso_y = int(s[0:4])
            wk = int(s[5:7])
            wd = int(s[7])
            if iso_y < 1:
                raise ValueError(f"year {iso_y} out of range 1..9999")
            max_wk = iso_weeks_in_year(iso_y)
            if wk < 1 or wk > max_wk:
                raise ValueError(f"week {wk} out of range 1..{max_wk}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            try:
                return from_iso_week(iso_y, wk, wd)
            except OverflowError:
                raise ValueError(f"week date {s!r} resolves to a date outside 1..9999")
        else:
            # Basic calendar: YYYYMMDD
            for i in range(8):
                if not _is_ascii_digit(s[i]):
                    raise ValueError(f"invalid character in date string: {s!r}")
            y = int(s[0:4])
            m = int(s[4:6])
            d = int(s[6:8])
            if y < 1:
                raise ValueError(f"year {y} out of range 1..9999")
            _check_date_range(y, m, d)
            return (y, m, d)

    elif n == 7:
        # Basic ordinal: YYYYDDD
        for i in range(7):
            if not _is_ascii_digit(s[i]):
                raise ValueError(f"invalid character in date string: {s!r}")
        y = int(s[0:4])
        doy = int(s[4:7])
        if y < 1:
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_doy(y, doy)

    else:
        raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_of_year(y, m, d)
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iso_y, iso_wk, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_wk:02d}-{iso_wd}"


def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if a > b:
        dy, dm, dd = diff(b, a)
        return (-dy, -dm, -dd)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    # shift(a, K): total = (ay-1)*12 + (am-1) + K; y = total//12+1; m = total%12+1; d = min(ad, dim(y,m))

    def _shift_leq(K):
        """Return True if shift(a, K) <= b, False otherwise (or out of range)."""
        total = (ay - 1) * 12 + (am - 1) + K
        sy = total // 12 + 1
        sm = total % 12 + 1
        if sy > 9999:
            return False
        sd = ad if ad <= _dim(sy, sm) else _dim(sy, sm)
        return (sy, sm, sd) <= (by, bm, bd)

    # Upper bound for K
    hi = (by - ay) * 12 + (bm - am) + 12
    if hi < 0:
        hi = 0
    lo = 0
    # Binary search for largest K in [0, hi] with _shift_leq(K) == True
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift_leq(mid):
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    # Compute shift(a, K)
    total = (ay - 1) * 12 + (am - 1) + K
    sy = total // 12 + 1
    sm = total % 12 + 1
    sd = ad if ad <= _dim(sy, sm) else _dim(sy, sm)
    days = to_ordinal(by, bm, bd) - to_ordinal(sy, sm, sd)
    return (years, months, days)