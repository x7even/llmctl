import re

__all__ = [
    'is_leap', 'days_in_month', 'to_ordinal', 'from_ordinal', 'weekday',
    'add_days', 'add_months', 'iso_weeks_in_year', 'iso_week', 'from_iso_week',
    'parse', 'format_date', 'diff',
]

_MAX_ORD = 3652059  # ordinal of (9999, 12, 31)

# Cumulative days at start of each month (0-indexed), for non-leap and leap years
_CUM = (
    (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334),   # non-leap
    (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335),   # leap
)
# Days in each month, 1-indexed (index 0 unused)
_MLEN = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# Regex for ISO 8601 date parsing (six accepted forms)
_PARSE_RE = re.compile(
    r'([0-9]{4})'
    r'(?:'
    r'-(W)([0-9]{2})-([0-9])'    # form 5: YYYY-Www-D
    r'|-([0-9]{2})-([0-9]{2})'   # form 1: YYYY-MM-DD
    r'|-([0-9]{3})'              # form 3: YYYY-DDD
    r'|(W)([0-9]{2})([0-9])'     # form 6: YYYYWwwD
    r'|([0-9]{2})([0-9]{2})'     # form 2: YYYYMMDD
    r'|([0-9]{3})'               # form 4: YYYYDDD
    r')'
)


# ---------- internal helpers (no type/range checks) ----------

def _is_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def _dim(y, m):
    """days_in_month without checks"""
    if m == 2 and _is_leap(y):
        return 29
    return _MLEN[m]


def _ordinal(y, m, d):
    """to_ordinal without checks"""
    return (365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
            + _CUM[_is_leap(y)][m - 1] + d)


def _from_ord(n):
    """from_ordinal without checks (n in 1.._MAX_ORD)"""
    n0 = n - 1
    y = n0 * 400 // 146097 + 1
    if 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400 >= n:
        y -= 1
    if 365 * y + y // 4 - y // 100 + y // 400 < n:
        y += 1
    doy = n - (365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400)
    cum = _CUM[_is_leap(y)]
    lo, hi = 0, 11
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if cum[mid] < doy:
            lo = mid
        else:
            hi = mid - 1
    return (y, lo + 1, doy - cum[lo])


def _add_months_raw(y, m, d, n):
    """add_months without checks; may raise OverflowError"""
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("year out of range")
    td = min(d, _dim(ty, tm))
    return (ty, tm, td)


# ---------- type / range checking helpers ----------

def _ci(x, name):
    """Check that x is exactly int."""
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _cd(date, name):
    """Check that date is a 3-tuple of ints."""
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(date[i]).__name__}")


def _cr(y, m, d):
    """Check calendar date range."""
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError(f"day {d} out of range for year {y} month {m}")


# ---------- public API ----------

def is_leap(y):
    _ci(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _ci(y, 'y')
    _ci(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cr(y, m, d)
    return _ordinal(y, m, d)


def from_ordinal(n):
    _ci(n, 'n')
    if not (1 <= n <= _MAX_ORD):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ord(n)


def weekday(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cr(y, m, d)
    return (_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _cd(date, 'date')
    _ci(n, 'n')
    y, m, d = date
    _cr(y, m, d)
    res = _ordinal(y, m, d) + n
    if res < 1 or res > _MAX_ORD:
        raise OverflowError("result date out of range")
    return _from_ord(res)


def add_months(date, n):
    _cd(date, 'date')
    _ci(n, 'n')
    y, m, d = date
    _cr(y, m, d)
    return _add_months_raw(y, m, d, n)


def iso_weeks_in_year(iso_year):
    _ci(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = (_ordinal(iso_year, 1, 1) - 1) % 7  # Mon=0..Sun=6
    if jan1_wd == 3:  # Thursday
        return 53
    if jan1_wd == 2 and _is_leap(iso_year):  # Wednesday + leap
        return 53
    return 52


def iso_week(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cr(y, m, d)
    ord_ = _ordinal(y, m, d)
    wd = (ord_ - 1) % 7  # Mon=0..Sun=6
    # Thursday of the current week
    thu_ord = ord_ - wd + 3
    iso_y = _from_ord(thu_ord)[0]
    # Monday of ISO week 1 (week containing Jan 4)
    jan4_ord = _ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    # Monday of current week
    mon_cur = ord_ - wd
    week = (mon_cur - mon_w1) // 7 + 1
    return (iso_y, week, wd + 1)


def from_iso_week(iso_year, week, weekday):
    _ci(iso_year, 'iso_year')
    _ci(week, 'week')
    _ci(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_wk):
        raise ValueError(f"week {week} out of range 1..{max_wk}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError("result date out of range")
    return _from_ord(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    m = _PARSE_RE.fullmatch(s)
    if m is None:
        raise ValueError(f"invalid date string: {s!r}")
    year = int(m.group(1))
    if year < 1 or year > 9999:
        raise ValueError(f"year {year} out of range")

    # Determine which form matched
    if m.group(2) is not None:
        # Form 5: YYYY-Www-D (week extended)
        ww = int(m.group(3))
        dd = int(m.group(4))
        try:
            return from_iso_week(year, ww, dd)
        except (ValueError, OverflowError):
            raise ValueError(f"invalid week date: {s!r}") from None
    elif m.group(5) is not None:
        # Form 1: YYYY-MM-DD (calendar extended)
        mm = int(m.group(5))
        dd = int(m.group(6))
        if not (1 <= mm <= 12):
            raise ValueError(f"month {mm} out of range")
        if not (1 <= dd <= _dim(year, mm)):
            raise ValueError(f"day {dd} out of range for {year}-{mm}")
        return (year, mm, dd)
    elif m.group(7) is not None:
        # Form 3: YYYY-DDD (ordinal extended)
        doy = int(m.group(7))
        max_doy = 366 if _is_leap(year) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range")
        return _from_ord(_ordinal(year, 1, 1) + doy - 1)
    elif m.group(8) is not None:
        # Form 6: YYYYWwwD (week basic)
        ww = int(m.group(9))
        dd = int(m.group(10))
        try:
            return from_iso_week(year, ww, dd)
        except (ValueError, OverflowError):
            raise ValueError(f"invalid week date: {s!r}") from None
    elif m.group(11) is not None:
        # Form 2: YYYYMMDD (calendar basic)
        mm = int(m.group(11))
        dd = int(m.group(12))
        if not (1 <= mm <= 12):
            raise ValueError(f"month {mm} out of range")
        if not (1 <= dd <= _dim(year, mm)):
            raise ValueError(f"day {dd} out of range for {year}-{mm}")
        return (year, mm, dd)
    else:
        # Form 4: YYYYDDD (ordinal basic)
        doy = int(m.group(13))
        max_doy = 366 if _is_leap(year) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range")
        return _from_ord(_ordinal(year, 1, 1) + doy - 1)


def format_date(date, form):
    _cd(date, 'date')
    y, m, d = date
    _cr(y, m, d)
    if form != 'calendar' and form != 'ordinal' and form != 'week':
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f'{y:04d}-{m:02d}-{d:02d}'
    elif form == 'ordinal':
        doy = _ordinal(y, m, d) - _ordinal(y, 1, 1) + 1
        return f'{y:04d}-{doy:03d}'
    else:  # 'week'
        iy, iw, iwd = iso_week(y, m, d)
        return f'{iy:04d}-W{iw:02d}-{iwd}'


def diff(a, b):
    _cd(a, 'a')
    _cd(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _cr(ay, am, ad)
    _cr(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        yrs, mos, dys = diff(b, a)
        return (-yrs, -mos, -dys)

    # a < b: find largest K >= 0 with add_months(a, K) <= b
    b_ord = _ordinal(by, bm, bd)
    lo = 0
    hi = (by - ay) * 12 + (bm - am) + 12

    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            shifted = _add_months_raw(ay, am, ad, mid)
            if _ordinal(*shifted) <= b_ord:
                lo = mid
            else:
                hi = mid - 1
        except OverflowError:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    days = b_ord - _ordinal(*_add_months_raw(ay, am, ad, K))
    return (years, months, days)
