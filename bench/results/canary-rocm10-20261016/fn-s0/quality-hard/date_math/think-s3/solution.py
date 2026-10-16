"""Proleptic Gregorian calendar arithmetic for years 1..9999.

Plain integer arithmetic only — no datetime, calendar, time, dateutil, or email.utils.
"""

import re

# ---------------------------------------------------------------------------
# Internal constants and helpers (no type/range checking)
# ---------------------------------------------------------------------------

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_DAYS = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_DAYS_LEAP = (0, 0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)

_MIN_ORD = 1
_MAX_ORD = 3652059


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    return _MONTH_DAYS[m]


def _to_ordinal(y, m, d):
    yy = y - 1
    return (yy * 365 + yy // 4 - yy // 100 + yy // 400
            + (_CUM_DAYS_LEAP[m] if _is_leap(y) else _CUM_DAYS[m]) + d)


def _from_ordinal(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if _to_ordinal(mid, 1, 1) <= n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if _to_ordinal(y, mid, 1) <= n:
            lo = mid
        else:
            hi = mid - 1
    m = lo
    d = n - _to_ordinal(y, m, 1) + 1
    return (y, m, d)


def _weekday(y, m, d):
    return (_to_ordinal(y, m, d) - 1) % 7


def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError("result year out of range")
    dim = _days_in_month(new_y, new_m)
    new_d = d if d <= dim else dim
    return (new_y, new_m, new_d)


def _iso_weeks_in_year(iso_year):
    jan1_wd = _weekday(iso_year, 1, 1)
    if jan1_wd == 3:
        return 53
    if jan1_wd == 2 and _is_leap(iso_year):
        return 53
    return 52


def _iso_week_calc(y, m, d):
    ord_val = _to_ordinal(y, m, d)
    wd = _weekday(y, m, d)
    thu_ord = ord_val - wd + 3
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if _to_ordinal(mid, 1, 1) <= thu_ord:
            lo = mid
        else:
            hi = mid - 1
    iso_y = lo
    jan4_ord = _to_ordinal(iso_y, 1, 4)
    jan4_wd = _weekday(iso_y, 1, 4)
    monday_w1_ord = jan4_ord - jan4_wd
    iso_wk = (ord_val - monday_w1_ord) // 7 + 1
    return (iso_y, iso_wk, wd + 1)


def _iso_week_to_ordinal(iso_year, week, wd):
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = _weekday(iso_year, 1, 4)
    monday_w1_ord = jan4_ord - jan4_wd
    return monday_w1_ord + (week - 1) * 7 + (wd - 1)


# ---------------------------------------------------------------------------
# Type / range checking helpers
# ---------------------------------------------------------------------------

def _check_int(*args):
    for x in args:
        if type(x) is not int:
            raise TypeError(
                f"expected int, got {type(x).__name__}")


def _check_date(date):
    if type(date) is not tuple:
        raise TypeError("date must be a tuple")
    if len(date) != 3:
        raise TypeError("date tuple must have exactly 3 elements")
    for item in date:
        if type(item) is not int:
            raise TypeError("date tuple elements must be int")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    """Return True if year *y* is a Gregorian leap year."""
    _check_int(y)
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    """Return the number of days in month *m* of year *y*."""
    _check_int(y, m)
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    """Return the proleptic-Gregorian ordinal (1 = 0001-01-01)."""
    _check_int(y, m, d)
    _check_date_range(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    """Inverse of to_ordinal."""
    _check_int(n)
    if n < _MIN_ORD or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ordinal(n)


def weekday(y, m, d):
    """Return the weekday: Monday=0 … Sunday=6."""
    _check_int(y, m, d)
    _check_date_range(y, m, d)
    return _weekday(y, m, d)


def add_days(date, n):
    """Return the date *n* days after *date*."""
    _check_date(date)
    _check_int(n)
    _check_date_range(date[0], date[1], date[2])
    ord_val = _to_ordinal(date[0], date[1], date[2]) + n
    if ord_val < _MIN_ORD or ord_val > _MAX_ORD:
        raise OverflowError("result date out of range")
    return _from_ordinal(ord_val)


def add_months(date, n):
    """Return the date *n* calendar months after *date* (day clamped once)."""
    _check_date(date)
    _check_int(n)
    _check_date_range(date[0], date[1], date[2])
    return _add_months_raw(date[0], date[1], date[2], n)


def iso_weeks_in_year(iso_year):
    """Return 52 or 53 — the number of ISO-8601 weeks in *iso_year*."""
    _check_int(iso_year)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    """Return (iso_year, iso_week, iso_weekday) with weekday Mon=1..Sun=7."""
    _check_int(y, m, d)
    _check_date_range(y, m, d)
    return _iso_week_calc(y, m, d)


def from_iso_week(iso_year, week, weekday):
    """Inverse of iso_week; returns (y, m, d)."""
    _check_int(iso_year, week, weekday)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"year {iso_year} out of range 1..9999")
    if week < 1 or week > _iso_weeks_in_year(iso_year):
        raise ValueError(f"week {week} out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    target_ord = _iso_week_to_ordinal(iso_year, week, weekday)
    if target_ord < _MIN_ORD or target_ord > _MAX_ORD:
        raise OverflowError("result date out of range")
    return _from_ordinal(target_ord)


# ---------------------------------------------------------------------------
# Parse / Format
# ---------------------------------------------------------------------------

_EXT_CAL_RE = re.compile(r'\A([0-9]{4})-([0-9]{2})-([0-9]{2})\Z')
_BASIC_CAL_RE = re.compile(r'\A([0-9]{4})([0-9]{2})([0-9]{2})\Z')
_EXT_ORD_RE = re.compile(r'\A([0-9]{4})-([0-9]{3})\Z')
_BASIC_ORD_RE = re.compile(r'\A([0-9]{7})\Z')
_EXT_WEEK_RE = re.compile(r'\A([0-9]{4})-W([0-9]{2})-([0-9])\Z')
_BASIC_WEEK_RE = re.compile(r'\A([0-9]{4})W([0-9]{2})([0-9])\Z')


def _parse_week_to_date(y, w, wd):
    """Helper for parse: convert ISO week fields to (y,m,d) or raise ValueError."""
    target_ord = _iso_week_to_ordinal(y, w, wd)
    if target_ord < _MIN_ORD or target_ord > _MAX_ORD:
        raise ValueError("date out of range")
    return _from_ordinal(target_ord)


def _parse_ordinal_to_date(y, doy):
    """Helper for parse: convert year + day-of-year to (y,m,d) or raise ValueError."""
    max_doy = 366 if _is_leap(y) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError("day-of-year out of range")
    return _from_ordinal(_to_ordinal(y, 1, 1) + doy - 1)


def parse(s):
    """Parse an ISO-8601 date string into (year, month, day)."""
    if type(s) is not str:
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = len(s)

    if n == 10:
        m = _EXT_CAL_RE.match(s)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if mo < 1 or mo > 12:
                raise ValueError("month out of range")
            if d < 1 or d > _days_in_month(y, mo):
                raise ValueError("day out of range")
            return (y, mo, d)
        m = _EXT_WEEK_RE.match(s)
        if m:
            y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            if w < 1 or w > _iso_weeks_in_year(y):
                raise ValueError("week out of range")
            return _parse_week_to_date(y, w, wd)
        raise ValueError("invalid date string")

    elif n == 8:
        if s[4] == '-':
            m = _EXT_ORD_RE.match(s)
            if m:
                y, doy = int(m.group(1)), int(m.group(2))
                if y < 1 or y > 9999:
                    raise ValueError("year out of range")
                return _parse_ordinal_to_date(y, doy)
            raise ValueError("invalid date string")
        elif s[4] == 'W':
            m = _BASIC_WEEK_RE.match(s)
            if m:
                y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 1 or y > 9999:
                    raise ValueError("year out of range")
                if wd < 1 or wd > 7:
                    raise ValueError("weekday out of range")
                if w < 1 or w > _iso_weeks_in_year(y):
                    raise ValueError("week out of range")
                return _parse_week_to_date(y, w, wd)
            raise ValueError("invalid date string")
        else:
            m = _BASIC_CAL_RE.match(s)
            if m:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if y < 1 or y > 9999:
                    raise ValueError("year out of range")
                if mo < 1 or mo > 12:
                    raise ValueError("month out of range")
                if d < 1 or d > _days_in_month(y, mo):
                    raise ValueError("day out of range")
                return (y, mo, d)
            raise ValueError("invalid date string")

    elif n == 7:
        m = _BASIC_ORD_RE.match(s)
        if m:
            y, doy = int(m.group(1)), int(m.group(2))
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            return _parse_ordinal_to_date(y, doy)
        raise ValueError("invalid date string")

    else:
        raise ValueError("invalid date string")


def format_date(date, form):
    """Format *date* in extended notation: 'calendar', 'ordinal', or 'week'."""
    _check_date(date)
    _check_date_range(date[0], date[1], date[2])
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid format: {form!r}")

    y, m, d = date
    if form == 'calendar':
        return f'{y:04d}-{m:02d}-{d:02d}'
    elif form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _to_ordinal(y, 1, 1) + 1
        return f'{y:04d}-{doy:03d}'
    else:
        iy, iw, iwd = _iso_week_calc(y, m, d)
        return f'{iy:04d}-W{iw:02d}-{iwd}'


def diff(a, b):
    """Calendar difference (years, months, days) from *a* to *b*."""
    _check_date(a)
    _check_date(b)
    _check_date_range(a[0], a[1], a[2])
    _check_date_range(b[0], b[1], b[2])

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with _add_months_raw(a, K) <= b
    lo, hi = 0, 120000
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        try:
            shifted = _add_months_raw(a[0], a[1], a[2], mid)
            if shifted <= b:
                lo = mid
            else:
                hi = mid - 1
        except OverflowError:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_raw(a[0], a[1], a[2], K)
    days = _to_ordinal(b[0], b[1], b[2]) - _to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
