import re

# ---------------------------------------------------------------------------
# Internal helpers (no type/range checking – callers must validate first)
# ---------------------------------------------------------------------------

_MDAYS = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_raw(y, m):
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if m in (4, 6, 9, 11):
        return 30
    return 29 if _is_leap_raw(y) else 28


def _to_ord_raw(y, m, d):
    days = (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    days += _MDAYS[m - 1]
    if m > 2 and _is_leap_raw(y):
        days += 1
    days += d
    return days


def _from_ord_raw(n):
    y = (n - 1) // 365 + 1
    while _to_ord_raw(y + 1, 1, 1) <= n:
        y += 1
    while _to_ord_raw(y, 1, 1) > n:
        y -= 1
    doy = n - _to_ord_raw(y, 1, 1) + 1
    m = 1
    while True:
        dim = _dim_raw(y, m)
        if doy <= dim:
            break
        doy -= dim
        m += 1
    return (y, m, doy)


def _iso_weeks_raw(iso_year):
    jan1_wd = (_to_ord_raw(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if _is_leap_raw(iso_year) and jan1_wd == 2:
        return 53
    return 52


def _iso_week_raw(y, m, d):
    ord_ = _to_ord_raw(y, m, d)
    wd = (ord_ - 1) % 7
    thu_ord = ord_ - wd + 3
    iso_y = _from_ord_raw(thu_ord)[0]
    jan4_ord = _to_ord_raw(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    mon_this = ord_ - wd
    iso_w = (mon_this - mon_w1) // 7 + 1
    return (iso_y, iso_w, wd + 1)


def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(d, _dim_raw(ny, nm))
    return (ny, nm, nd)


# ---------------------------------------------------------------------------
# Type / range validation helpers
# ---------------------------------------------------------------------------

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _chk_date(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(v).__name__}")


def _chk_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim_raw(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _chk_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim_raw(y, m)


def to_ordinal(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_range(y, m, d)
    return _to_ord_raw(y, m, d)


def from_ordinal(n):
    _chk_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ord_raw(n)


def weekday(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_range(y, m, d)
    return (_to_ord_raw(y, m, d) - 1) % 7


def add_days(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _chk_range(y, m, d)
    new_ord = _to_ord_raw(y, m, d) + n
    if not (1 <= new_ord <= 3652059):
        raise OverflowError(f"resulting date out of range 1..9999")
    return _from_ord_raw(new_ord)


def add_months(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _chk_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total >= 9999 * 12:
        raise OverflowError(f"resulting date out of range 1..9999")
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(d, _dim_raw(ny, nm))
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_raw(iso_year)


def iso_week(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_range(y, m, d)
    return _iso_week_raw(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, 'iso_year')
    _chk_int(week, 'week')
    _chk_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_w = _iso_weeks_raw(iso_year)
    if not (1 <= week <= max_w):
        raise ValueError(f"week {week} out of range 1..{max_w}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _to_ord_raw(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if not (1 <= target <= 3652059):
        raise OverflowError(f"resulting date out of range 1..9999")
    return _from_ord_raw(target)


# ---------------------------------------------------------------------------
# parse / format_date
# ---------------------------------------------------------------------------

_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BASIC_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_BASIC_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')
_RE_BASIC_ORD = re.compile(r'([0-9]{4})([0-9]{3})')


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _chk_range(y, mo, d)
        return (y, mo, d)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        max_w = _iso_weeks_raw(y)
        if not (1 <= w <= max_w):
            raise ValueError(f"week {w} out of range 1..{max_w}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_ord = _to_ord_raw(y, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        mon_w1 = jan4_ord - jan4_wd
        target = mon_w1 + (w - 1) * 7 + (wd - 1)
        if not (1 <= target <= 3652059):
            raise ValueError(f"week date out of range")
        return _from_ord_raw(target)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap_raw(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ord_raw(_to_ord_raw(y, 1, 1) - 1 + doy)

    m = _RE_BASIC_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _chk_range(y, mo, d)
        return (y, mo, d)

    m = _RE_BASIC_WK.fullmatch(s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        max_w = _iso_weeks_raw(y)
        if not (1 <= w <= max_w):
            raise ValueError(f"week {w} out of range 1..{max_w}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_ord = _to_ord_raw(y, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        mon_w1 = jan4_ord - jan4_wd
        target = mon_w1 + (w - 1) * 7 + (wd - 1)
        if not (1 <= target <= 3652059):
            raise ValueError(f"week date out of range")
        return _from_ord_raw(target)

    m = _RE_BASIC_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap_raw(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ord_raw(_to_ord_raw(y, 1, 1) - 1 + doy)

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _chk_date(date, 'date')
    y, m, d = date
    _chk_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = _to_ord_raw(y, m, d) - _to_ord_raw(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    # week
    iy, iw, iwd = _iso_week_raw(y, m, d)
    return f"{iy:04d}-W{iw:02d}-{iwd}"


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def diff(a, b):
    _chk_date(a, 'a')
    _chk_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _chk_range(ay, am, ad)
    _chk_range(by, bm, bd)

    if a <= b:
        # Binary search for largest K >= 0 with shift(a, K) <= b
        lo = 0
        hi = (by - ay) * 12 + (bm - am) + 12
        while lo < hi:
            mid = (lo + hi + 1) // 2
            total = (ay - 1) * 12 + (am - 1) + mid
            ny = total // 12 + 1
            nm = total % 12 + 1
            nd = min(ad, _dim_raw(ny, nm))
            if (ny, nm, nd) <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _add_months_raw(ay, am, ad, K)
        days = _to_ord_raw(by, bm, bd) - _to_ord_raw(*shifted)
        return (years, months, days)
    else:
        y, m, d = diff(b, a)
        return (-y, -m, -d)