"""Proleptic Gregorian calendar arithmetic for years 1 through 9999.

No datetime/calendar/time/dateutil/email.utils imports – pure integer arithmetic.
"""

# ---------------------------------------------------------------------------
# Private constants and helpers
# ---------------------------------------------------------------------------

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MAX_ORDINAL = 3652059  # (9999, 12, 31)


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    """days_in_month without range checking (y,m assumed valid)."""
    if m == 2 and _is_leap(y):
        return 29
    return _DAYS_IN_MONTH[m - 1]


def _days_before_year(y):
    """Total days in years 1 .. y-1."""
    yy = y - 1
    return 365 * yy + yy // 4 - yy // 100 + yy // 400


def _to_ordinal(y, m, d):
    """Convert (y,m,d) to ordinal (1-based, no range check)."""
    doy = d + _CUM_DAYS[m - 1]
    if m > 2 and _is_leap(y):
        doy += 1
    return _days_before_year(y) + doy


_CUM_DAYS = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _from_ordinal(n):
    """Ordinal -> (y, m, d), no range check. O(1)."""
    # Binary search for year in [1, 9999]
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)  # 1-based day of year
    # Find month (at most 12 iterations – constant)
    leap = _is_leap(y)
    for m in range(1, 13):
        dm = 29 if m == 2 and leap else _DAYS_IN_MONTH[m - 1]
        if doy <= dm:
            return (y, m, doy)
        doy -= dm
    # Should never reach here for valid n
    raise ValueError("internal: from_ordinal out of range")


def _weekday_calc(y, m, d):
    """0=Mon .. 6=Sun (no range check)."""
    return (_to_ordinal(y, m, d) - 1) % 7


def _iso_week_calc(y, m, d):
    """Return (iso_year, iso_week, iso_weekday 1-7). No range check on input."""
    ord_val = _to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7  # 0=Mon .. 6=Sun
    # Thursday of this ISO week
    thu_ord = ord_val + 3 - wd
    # iso_year = year containing that Thursday
    thu_y, _, _ = _from_ordinal(thu_ord)
    # Monday of ISO week 1 of thu_y (Jan 4 is always in week 1)
    jan4_ord = _to_ordinal(thu_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_mon = jan4_ord - jan4_wd
    iso_wk = (thu_ord - week1_mon) // 7 + 1
    return (thu_y, iso_wk, wd + 1)


def _iso_weeks_in_year(y):
    """52 or 53 (no range check)."""
    # 53 iff Jan 1 is Thursday, or leap year and Jan 1 is Wednesday
    jan1_wd = _weekday_calc(y, 1, 1)  # 0=Mon..6=Sun; Thu=3, Wed=2
    return 53 if jan1_wd == 3 or (_is_leap(y) and jan1_wd == 2) else 52


def _shift_raw(a, K):
    """add_months(a, K) without range checking (for internal use in diff)."""
    total = (a[0] - 1) * 12 + (a[1] - 1) + K
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = a[2]
    dm = 29 if (nm == 2 and _is_leap(ny)) else _DAYS_IN_MONTH[nm - 1]
    if nd > dm:
        nd = dm
    return (ny, nm, nd)


# ---------------------------------------------------------------------------
# Type / range checking helpers
# ---------------------------------------------------------------------------

def _assert_int(*vals):
    for v in vals:
        if type(v) is not int:
            raise TypeError("expected int")


def _assert_date(*vals):
    for v in vals:
        if type(v) is not tuple or len(v) != 3:
            raise TypeError("expected tuple of 3 ints")
        if not (type(v[0]) is int and type(v[1]) is int and type(v[2]) is int):
            raise TypeError("expected tuple of 3 ints")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    """Return True if Gregorian year y is a leap year."""
    if type(y) is not int:
        raise TypeError("year must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap(y)


def days_in_month(y, m):
    """Return number of days in month m of year y."""
    _assert_int(y, m)
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _dim(y, m)


def to_ordinal(y, m, d):
    """Return the ordinal day number ((1,1,1)->1, (9999,12,31)->3652059)."""
    _assert_int(y, m, d)
    _check_date_range(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    """Inverse of to_ordinal. n must be 1..3652059."""
    if type(n) is not int:
        raise TypeError("n must be int")
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError("ordinal out of range")
    return _from_ordinal(n)


def weekday(y, m, d):
    """Weekday of a date: Monday=0 .. Sunday=6."""
    _assert_int(y, m, d)
    _check_date_range(y, m, d)
    return _weekday_calc(y, m, d)


def add_days(date, n):
    """Return the date n days after *date*. OverflowError if out of range."""
    _assert_date(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    _check_date_range(y, m, d)
    new_ord = _to_ordinal(y, m, d) + n
    if new_ord < 1 or new_ord > _MAX_ORDINAL:
        raise OverflowError("resulting date out of range")
    return _from_ordinal(new_ord)


def add_months(date, n):
    """Shift *date* by n calendar months. OverflowError if target year out of range."""
    _assert_date(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("target year out of range")
    nd = d
    dm = 29 if (nm == 2 and _is_leap(ny)) else _DAYS_IN_MONTH[nm - 1]
    if nd > dm:
        nd = dm
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    """Return 52 or 53 (the number of ISO 8601 weeks in that ISO year)."""
    if type(iso_year) is not int:
        raise TypeError("iso_year must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    """ISO 8601 week date: (iso_year, iso_week, iso_weekday 1-7)."""
    _assert_int(y, m, d)
    _check_date_range(y, m, d)
    return _iso_week_calc(y, m, d)


def from_iso_week(iso_year, week, weekday):
    """Inverse of iso_week. Returns (y, m, d)."""
    _assert_int(iso_year, week, weekday)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    max_wk = _iso_weeks_in_year(iso_year)
    if week < 1 or week > max_wk:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    # Monday of ISO week 1:
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7  # 0=Mon..6=Sun
    week1_mon_ord = jan4_ord - jan4_wd
    target_ord = week1_mon_ord + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise OverflowError("resulting date out of range")
    return _from_ordinal(target_ord)


# ---------------------------------------------------------------------------
# parse / format_date
# ---------------------------------------------------------------------------

def _is_ascii_digit(c):
    return '0' <= c <= '9'


def _ascii_digits(s, lo, hi):
    """Check s[lo:hi] are all ASCII digits and return the int."""
    for i in range(lo, hi):
        if not _is_ascii_digit(s[i]):
            raise ValueError("non-ASCII-digit character")
    return int(s[lo:hi])


def parse(s):
    """Parse an ISO 8601 date string into (y, m, d)."""
    if type(s) is not str:
        raise TypeError("s must be str")

    n = len(s)
    if n == 10:
        if s[4] == '-':
            if s[5] == 'W':
                # Extended week: YYYY-Www-D  (10 chars)
                if s[8] != '-':
                    raise ValueError("invalid week format")
                y = _ascii_digits(s, 0, 4)
                w = _ascii_digits(s, 6, 8)
                d = _ascii_digits(s, 9, 10)
                if y < 1 or y > 9999:
                    raise ValueError("year out of range")
                max_wk = _iso_weeks_in_year(y)
                if w < 1 or w > max_wk:
                    raise ValueError("week out of range")
                if d < 1 or d > 7:
                    raise ValueError("weekday out of range")
                # Compute target date
                jan4_ord = _to_ordinal(y, 1, 4)
                jan4_wd = (jan4_ord - 1) % 7
                week1_mon = jan4_ord - jan4_wd
                target_ord = week1_mon + (w - 1) * 7 + (d - 1)
                if target_ord < 1 or target_ord > _MAX_ORDINAL:
                    raise ValueError("date out of range")
                return _from_ordinal(target_ord)
            else:
                # Extended calendar: YYYY-MM-DD (10 chars)
                if s[7] != '-':
                    raise ValueError("invalid calendar format")
                y = _ascii_digits(s, 0, 4)
                m = _ascii_digits(s, 5, 7)
                d = _ascii_digits(s, 8, 10)
                if y < 1 or y > 9999:
                    raise ValueError("year out of range")
                if m < 1 or m > 12:
                    raise ValueError("month out of range")
                if d < 1 or d > _dim(y, m):
                    raise ValueError("day out of range")
                return (y, m, d)
        else:
            raise ValueError("invalid format")
    elif n == 8:
        if s[4] == '-':
            # Extended ordinal: YYYY-DDD (8 chars)
            y = _ascii_digits(s, 0, 4)
            doy = _ascii_digits(s, 5, 8)
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            max_doy = 366 if _is_leap(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError("day-of-year out of range")
            # Convert doy to (m, d)
            m = 1
            for mm in range(1, 13):
                dm = 29 if (mm == 2 and _is_leap(y)) else _DAYS_IN_MONTH[mm - 1]
                if doy <= dm:
                    return (y, mm, doy)
                doy -= dm
                m = mm + 1
            raise ValueError("day-of-year out of range")  # should not reach
        elif s[4] == 'W':
            # Basic week: YYYYWwwD (8 chars)
            y = _ascii_digits(s, 0, 4)
            w = _ascii_digits(s, 5, 7)
            d = _ascii_digits(s, 7, 8)
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            max_wk = _iso_weeks_in_year(y)
            if w < 1 or w > max_wk:
                raise ValueError("week out of range")
            if d < 1 or d > 7:
                raise ValueError("weekday out of range")
            jan4_ord = _to_ordinal(y, 1, 4)
            jan4_wd = (jan4_ord - 1) % 7
            week1_mon = jan4_ord - jan4_wd
            target_ord = week1_mon + (w - 1) * 7 + (d - 1)
            if target_ord < 1 or target_ord > _MAX_ORDINAL:
                raise ValueError("date out of range")
            return _from_ordinal(target_ord)
        else:
            # Basic calendar: YYYYMMDD (8 chars)
            y = _ascii_digits(s, 0, 4)
            m = _ascii_digits(s, 4, 6)
            d = _ascii_digits(s, 6, 8)
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if m < 1 or m > 12:
                raise ValueError("month out of range")
            if d < 1 or d > _dim(y, m):
                raise ValueError("day out of range")
            return (y, m, d)
    elif n == 7:
        # Basic ordinal: YYYYDDD (7 chars)
        y = _ascii_digits(s, 0, 4)
        doy = _ascii_digits(s, 4, 7)
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day-of-year out of range")
        for mm in range(1, 13):
            dm = 29 if (mm == 2 and _is_leap(y)) else _DAYS_IN_MONTH[mm - 1]
            if doy <= dm:
                return (y, mm, doy)
            doy -= dm
        raise ValueError("day-of-year out of range")
    else:
        raise ValueError("invalid length / format")


def format_date(date, form):
    """Format a date tuple as an ISO 8601 string in the given form."""
    _assert_date(date)
    y, m, d = date
    _check_date_range(y, m, d)
    # form validation AFTER date checks
    if form != 'calendar' and form != 'ordinal' and form != 'week':
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # 'week'
        iy, iw, iwkd = _iso_week_calc(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwkd}"


def diff(a, b):
    """Calendar difference as (years, months, days). See module docstring."""
    _assert_date(a, b)
    _check_date_range(a[0], a[1], a[2])
    _check_date_range(b[0], b[1], b[2])

    if a == b:
        return (0, 0, 0)

    if a > b:
        # Negate the result of diff(b, a)
        r = diff(b, a)
        return (-r[0], -r[1], -r[2])

    # a < b: find largest K >= 0 with _shift_raw(a, K) <= b
    lo, hi = 0, (b[0] - a[0] + 1) * 12
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if _shift_raw(a, mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _shift_raw(a, K)
    days = _to_ordinal(b[0], b[1], b[2]) - _to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
