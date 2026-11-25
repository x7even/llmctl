"""Proleptic-Gregorian calendar arithmetic for years 1..9999 (pure integer math)."""

__all__ = [
    "is_leap", "days_in_month", "to_ordinal", "from_ordinal", "weekday",
    "add_days", "add_months", "iso_weeks_in_year", "iso_week",
    "from_iso_week", "parse", "format_date", "diff",
]

# ---------------------------------------------------------------------------
# Internal helpers (no public API)
# ---------------------------------------------------------------------------

def _is_int(x):
    return type(x) is int

def _is_date_tuple(x):
    return (type(x) is tuple and len(x) == 3
            and type(x[0]) is int and type(x[1]) is int and type(x[2]) is int)

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _dim(y, m):
    """Days in month m of year y (no validation)."""
    if m == 2:
        return 29 if _is_leap(y) else 28
    return (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[m - 1]

def _days_before_year(y):
    """Total days in years 1..y-1."""
    t = y - 1
    return t * 365 + t // 4 - t // 100 + t // 400

def _days_before_month(y, m):
    """Days in months 1..m-1 of year y."""
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    r = cum[m - 1]
    if m > 2 and _is_leap(y):
        r += 1
    return r

def _validate_date(y, m, d):
    """Raise ValueError if (y,m,d) is not a valid date in range."""
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)} for {y}-{m}")

def _year_from_ordinal(n):
    """Return the year containing ordinal n (1-indexed)."""
    y = (n * 400) // 146097 + 1
    while _days_before_year(y) >= n:
        y -= 1
    while n > _days_before_year(y + 1):
        y += 1
    return y

def _shift(a, k):
    """add_months(a, k) without range checks; None if target year out of 1..9999."""
    y, m, d = a
    total = (y - 1) * 12 + (m - 1) + k
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        return None
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)

def _check_ascii_digits(s, start, end):
    for i in range(start, end):
        if not ('0' <= s[i] <= '9'):
            raise ValueError(f"invalid character at position {i}")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    if not _is_int(y):
        raise TypeError("y must be an int")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)

def days_in_month(y, m):
    if not _is_int(y) or not _is_int(m):
        raise TypeError("y and m must be ints")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)

def to_ordinal(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("y, m, d must be ints")
    _validate_date(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d

def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be an int")
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    y = _year_from_ordinal(n)
    doy = n - _days_before_year(y)
    # Find month
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    if _is_leap(y):
        cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
    m = 1
    while m < 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)

def weekday(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("y, m, d must be ints")
    _validate_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7

def add_days(date, n):
    if not _is_date_tuple(date) or not _is_int(n):
        raise TypeError("date must be a tuple of 3 ints; n must be an int")
    y, m, d = date
    _validate_date(y, m, d)
    ord_n = to_ordinal(y, m, d) + n
    if ord_n < 1 or ord_n > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(ord_n)

def add_months(date, n):
    if not _is_date_tuple(date) or not _is_int(n):
        raise TypeError("date must be a tuple of 3 ints; n must be an int")
    y, m, d = date
    _validate_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of range")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)

def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be an int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if _is_leap(iso_year) and jan1_wd == 2:
        return 53
    return 52

def iso_week(y, m, d):
    if not _is_int(y) or not _is_int(m) or not _is_int(d):
        raise TypeError("y, m, d must be ints")
    _validate_date(y, m, d)
    ord_ = to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7  # 0=Mon
    # Thursday of current week
    thur_ord = ord_ + (3 - wd)
    iso_y = _year_from_ordinal(thur_ord)
    # Monday of week 1 of iso_y
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    # Monday of current week
    mon_cur = ord_ - wd
    iso_w = (mon_cur - mon_w1) // 7 + 1
    iso_wd = wd + 1
    return (iso_y, iso_w, iso_wd)

def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year) or not _is_int(week) or not _is_int(weekday):
        raise TypeError("iso_year, week, weekday must be ints")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_w = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_w:
        raise ValueError(f"week {week} out of range 1..{max_w}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target)

def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")
    n = len(s)

    if n == 10:
        if s[4] == '-' and s[7] == '-':
            # YYYY-MM-DD
            _check_ascii_digits(s, 0, 4)
            _check_ascii_digits(s, 5, 7)
            _check_ascii_digits(s, 8, 10)
            y = int(s[0:4]); m = int(s[5:7]); d = int(s[8:10])
            _validate_date(y, m, d)
            return (y, m, d)
        if s[4] == '-' and s[5] == 'W' and s[8] == '-':
            # YYYY-Www-D
            _check_ascii_digits(s, 0, 4)
            _check_ascii_digits(s, 6, 8)
            _check_ascii_digits(s, 9, 10)
            y = int(s[0:4]); w = int(s[6:8]); wd = int(s[9:10])
            if y < 1 or y > 9999:
                raise ValueError(f"year {y} out of range")
            max_w = iso_weeks_in_year(y)
            if w < 1 or w > max_w:
                raise ValueError(f"week {w} out of range 1..{max_w}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            try:
                return from_iso_week(y, w, wd)
            except OverflowError:
                raise ValueError("date out of supported range")
        raise ValueError(f"unrecognized format: {s!r}")

    if n == 8:
        # Check if all ASCII digits
        all_digits = True
        for i in range(8):
            if not ('0' <= s[i] <= '9'):
                all_digits = False
                break
        if all_digits:
            # YYYYMMDD or YYYYDDD
            y = int(s[0:4])
            if y < 1 or y > 9999:
                raise ValueError(f"year {y} out of range")
            m = int(s[4:6]); d = int(s[6:8])
            if 1 <= m <= 12 and 1 <= d <= _dim(y, m):
                return (y, m, d)
            doy = int(s[4:8])
            max_doy = 366 if _is_leap(y) else 365
            if 1 <= doy <= max_doy:
                return from_ordinal(_days_before_year(y) + doy)
            raise ValueError(f"invalid date: {s!r}")
        if s[4] == '-':
            # YYYY-DDD (ordinal extended)
            _check_ascii_digits(s, 0, 4)
            _check_ascii_digits(s, 5, 8)
            y = int(s[0:4]); doy = int(s[5:8])
            if y < 1 or y > 9999:
                raise ValueError(f"year {y} out of range")
            max_doy = 366 if _is_leap(y) else 365
            if 1 <= doy <= max_doy:
                return from_ordinal(_days_before_year(y) + doy)
            raise ValueError(f"invalid ordinal date: {s!r}")
        if s[4] == 'W':
            # YYYYWwwD (week basic)
            _check_ascii_digits(s, 0, 4)
            _check_ascii_digits(s, 5, 7)
            _check_ascii_digits(s, 7, 8)
            y = int(s[0:4]); w = int(s[5:7]); wd = int(s[7:8])
            if y < 1 or y > 9999:
                raise ValueError(f"year {y} out of range")
            max_w = iso_weeks_in_year(y)
            if w < 1 or w > max_w:
                raise ValueError(f"week {w} out of range 1..{max_w}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            try:
                return from_iso_week(y, w, wd)
            except OverflowError:
                raise ValueError("date out of supported range")
        raise ValueError(f"unrecognized format: {s!r}")

    raise ValueError(f"unrecognized format: {s!r}")

def format_date(date, form):
    if not _is_date_tuple(date):
        raise TypeError("date must be a tuple of 3 ints")
    y, m, d = date
    _validate_date(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    # week
    iy, iw, iwd = iso_week(y, m, d)
    return f"{iy:04d}-W{iw:02d}-{iwd}"

def diff(a, b):
    if not _is_date_tuple(a) or not _is_date_tuple(b):
        raise TypeError("a and b must be tuples of 3 ints")
    _validate_date(*a)
    _validate_date(*b)
    if a == b:
        return (0, 0, 0)
    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
    # a < b: binary search for largest K >= 0 with shift(a, K) <= b
    lo = 0
    hi = (b[0] - a[0]) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _shift(a, mid)
        if shifted is not None and shifted <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _shift(a, K)
    days = to_ordinal(*b) - to_ordinal(*shifted)
    return (years, months, days)