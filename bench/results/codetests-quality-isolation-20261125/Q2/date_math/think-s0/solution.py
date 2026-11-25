"""Proleptic-Gregorian calendar arithmetic for years 1..9999.

No imports from datetime, calendar, time, dateutil, or email.utils.
"""

import re

# ---------------------------------------------------------------------------
# Internal helpers (no public checking)
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
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400

_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)

def _month_offset(y, m):
    r = _CUM[m - 1]
    if m > 2 and _is_leap(y):
        r += 1
    return r

def _to_ordinal(y, m, d):
    return _days_before_year(y) + _month_offset(y, m) + d

def _weekday(y, m, d):
    return (_to_ordinal(y, m, d) - 1) % 7

def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)

def _iso_weeks_in_year(iy):
    w = _weekday(iy, 1, 1)
    if w == 3:
        return 53
    if _is_leap(iy) and w == 2:
        return 53
    return 52

def _iso_week(y, m, d):
    ord_ = _to_ordinal(y, m, d)
    w = (ord_ - 1) % 7
    thu = ord_ + (3 - w)
    iy = _from_ordinal_internal(thu)[0]
    jan4 = _to_ordinal(iy, 1, 4)
    jan4w = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4w
    week = (ord_ - mon_w1) // 7 + 1
    return (iy, week, w + 1)

def _from_ordinal_internal(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    if _is_leap(y):
        cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
    else:
        cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    m = 1
    while m < 12 and cum[m] < doy:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)

# ---------------------------------------------------------------------------
# Type / range check helpers
# ---------------------------------------------------------------------------

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")

def _chk_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i in range(3):
        if type(x[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int")

def _chk_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _chk_int(y, "y")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)

def days_in_month(y, m):
    _chk_int(y, "y")
    _chk_int(m, "m")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)

def to_ordinal(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_date_range(y, m, d)
    return _to_ordinal(y, m, d)

def from_ordinal(n):
    _chk_int(n, "n")
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ordinal_internal(n)

def weekday(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_date_range(y, m, d)
    return _weekday(y, m, d)

def add_days(date, n):
    _chk_date(date, "date")
    _chk_int(n, "n")
    y, m, d = date
    _chk_date_range(y, m, d)
    o = _to_ordinal(y, m, d) + n
    if o < 1 or o > 3652059:
        raise OverflowError("result out of range 1..9999")
    return _from_ordinal_internal(o)

def add_months(date, n):
    _chk_date(date, "date")
    _chk_int(n, "n")
    y, m, d = date
    _chk_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("result year out of range 1..9999")
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)

def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)

def iso_week(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_date_range(y, m, d)
    return _iso_week(y, m, d)

def from_iso_week(iso_year, week, weekday_):
    _chk_int(iso_year, "iso_year")
    _chk_int(week, "week")
    _chk_int(weekday_, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = _iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw}")
    if weekday_ < 1 or weekday_ > 7:
        raise ValueError(f"weekday {weekday_} out of range 1..7")
    jan4 = _to_ordinal(iso_year, 1, 4)
    jan4w = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4w
    target = mon_w1 + (week - 1) * 7 + (weekday_ - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range 1..9999")
    return _from_ordinal_internal(target)

# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

_RE_CAL_EXT = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_CAL_BAS = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_ORD_EXT = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_ORD_BAS = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_WK_EXT = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_WK_BAS = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    n = len(s)

    if n == 10:
        mt = _RE_CAL_EXT.match(s)
        if mt:
            y, m, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
            _validate_date(y, m, d)
            return (y, m, d)
        mt = _RE_WK_EXT.match(s)
        if mt:
            y, w, dw = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
            return _validate_week(y, w, dw)
        raise ValueError(f"invalid date string: {s!r}")

    if n == 8:
        mt = _RE_ORD_EXT.match(s)
        if mt:
            y, doy = int(mt.group(1)), int(mt.group(2))
            return _validate_ordinal(y, doy)
        mt = _RE_WK_BAS.match(s)
        if mt:
            y, w, dw = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
            return _validate_week(y, w, dw)
        mt = _RE_CAL_BAS.match(s)
        if mt:
            y, m, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
            _validate_date(y, m, d)
            return (y, m, d)
        raise ValueError(f"invalid date string: {s!r}")

    if n == 7:
        mt = _RE_ORD_BAS.match(s)
        if mt:
            y, doy = int(mt.group(1)), int(mt.group(2))
            return _validate_ordinal(y, doy)
        raise ValueError(f"invalid date string: {s!r}")

    raise ValueError(f"invalid date string: {s!r}")

def _validate_date(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range")

def _validate_ordinal(y, doy):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range")
    max_doy = 366 if _is_leap(y) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError(f"day of year {doy} out of range")
    return _from_ordinal_internal(_days_before_year(y) + doy)

def _validate_week(y, w, dw):
    if y < 1 or y > 9999:
        raise ValueError(f"iso_year {y} out of range")
    nw = _iso_weeks_in_year(y)
    if w < 1 or w > nw:
        raise ValueError(f"week {w} out of range 1..{nw}")
    if dw < 1 or dw > 7:
        raise ValueError(f"weekday {dw} out of range 1..7")
    jan4 = _to_ordinal(y, 1, 4)
    jan4w = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4w
    target = mon_w1 + (w - 1) * 7 + (dw - 1)
    if target < 1 or target > 3652059:
        raise ValueError(f"date out of supported range")
    return _from_ordinal_internal(target)

# ---------------------------------------------------------------------------
# format_date
# ---------------------------------------------------------------------------

def format_date(date, form):
    _chk_date(date, "date")
    y, m, d = date
    _chk_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    # week
    iy, iw, idw = _iso_week(y, m, d)
    return f"{iy:04d}-W{iw:02d}-{idw}"

# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def diff(a, b):
    _chk_date(a, "a")
    _chk_date(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _chk_date_range(ay, am, ad)
    _chk_date_range(by, bm, bd)

    if _to_ordinal(ay, am, ad) == _to_ordinal(by, bm, bd):
        return (0, 0, 0)

    if _to_ordinal(ay, am, ad) < _to_ordinal(by, bm, bd):
        # a < b
        k_cand = (by - ay) * 12 + (bm - am)
        shifted = _add_months_raw(ay, am, ad, k_cand)
        if _to_ordinal(*shifted) <= _to_ordinal(by, bm, bd):
            k = k_cand
        else:
            k = k_cand - 1
        years, months = divmod(k, 12)
        shifted_k = _add_months_raw(ay, am, ad, k)
        days = _to_ordinal(by, bm, bd) - _to_ordinal(*shifted_k)
        return (years, months, days)
    else:
        # a > b
        r = diff(b, a)
        return (-r[0], -r[1], -r[2])
