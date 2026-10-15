import re

# ─── internal helpers ────────────────────────────────────────────────────────

def _check_int(x):
    if type(x) is not int:
        raise TypeError(f"Expected int, got {type(x).__name__}")

def _check_date(x):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError("Expected a date tuple of exactly 3 ints")
    for v in x:
        if type(v) is not int:
            raise TypeError(f"Expected int in date tuple, got {type(v).__name__}")

def _dim(y, m):
    """Days in month, no range check (y,m assumed valid)."""
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30

def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"Year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"Month {m} out of range 1..12")
    dim = _dim(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"Day {d} out of range 1..{dim}")

def _days_before(y):
    """Number of days in years 1..y-1."""
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400

def _add_months_unchecked(date, n):
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(d, _dim(ny, nm))
    return (ny, nm, nd)

_CUM = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]

# ─── public API ──────────────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y)
    if not (1 <= y <= 9999):
        raise ValueError(f"Year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def days_in_month(y, m):
    _check_int(y)
    _check_int(m)
    if not (1 <= y <= 9999):
        raise ValueError(f"Year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"Month {m} out of range 1..12")
    return _dim(y, m)

def to_ordinal(y, m, d):
    _check_int(y)
    _check_int(m)
    _check_int(d)
    _check_date_range(y, m, d)
    days = _days_before(y) + _CUM[m - 1]
    if m > 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        days += 1
    days += d
    return days

def from_ordinal(n):
    _check_int(n)
    if not (1 <= n <= 3652059):
        raise ValueError(f"Ordinal {n} out of range 1..3652059")
    # estimate year
    y = n // 365 + 1
    while _days_before(y) >= n:
        y -= 1
    while _days_before(y + 1) < n:
        y += 1
    # day of year (1-indexed)
    doy = n - _days_before(y)
    # month
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    if not leap:
        cum = _CUM
    else:
        cum = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366]
    m = 1
    while cum[m] < doy:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)

def weekday(y, m, d):
    _check_int(y)
    _check_int(m)
    _check_int(d)
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7

def add_days(date, n):
    _check_date(date)
    _check_int(n)
    y, m, d = date
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError("Result out of range 1..9999")
    return from_ordinal(ord_val)

def add_months(date, n):
    _check_date(date)
    _check_int(n)
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if not (1 <= ny <= 9999):
        raise OverflowError("Result out of range 1..9999")
    nd = min(d, _dim(ny, nm))
    return (ny, nm, nd)

def iso_weeks_in_year(iso_year):
    _check_int(iso_year)
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"Year {iso_year} out of range 1..9999")
    jan1_wd = (_days_before(iso_year) + 1 - 1) % 7  # weekday of Jan 1 (Mon=0)
    leap = (iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0))
    if jan1_wd == 3 or (leap and jan1_wd == 2):
        return 53
    return 52

def iso_week(y, m, d):
    _check_int(y)
    _check_int(m)
    _check_int(d)
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d)
    w = (ord_val - 1) % 7          # Monday = 0
    monday_ord = ord_val - w
    thursday_ord = monday_ord + 3
    # determine iso year from the Thursday
    # quick year extraction
    iy = thursday_ord // 365 + 1
    while _days_before(iy) >= thursday_ord:
        iy -= 1
    while _days_before(iy + 1) < thursday_ord:
        iy += 1
    # Monday of ISO week 1 of iy
    jan4_ord = to_ordinal(iy, 1, 4)
    jan4_w = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_w
    iso_w = (monday_ord - week1_monday) // 7 + 1
    iso_wd = w + 1                 # Monday = 1
    return (iy, iso_w, iso_wd)

def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year)
    _check_int(week)
    _check_int(weekday)
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"ISO year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"Week {week} out of range 1..{max_week}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"Weekday {weekday} out of range 1..7")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_w = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_w
    target_ord = week1_monday + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError("Result out of range 1..9999")
    return from_ordinal(target_ord)

# ─── parse ───────────────────────────────────────────────────────────────────

_RE_CAL_EXT   = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_CAL_BASIC = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_ORD_EXT   = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_ORD_BASIC = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_WK_EXT    = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9]{1})$')
_RE_WK_BASIC  = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9]{1})$')

def parse(s):
    if type(s) is not str:
        raise TypeError(f"Expected str, got {type(s).__name__}")

    m = _RE_CAL_EXT.match(s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        if not (1 <= y <= 9999):
            raise ValueError(f"Year {y} out of range 1..9999")
        if not (1 <= mo <= 12):
            raise ValueError(f"Month {mo} out of range 1..12")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError(f"Day {d} out of range for month {mo}")
        return (y, mo, d)

    m = _RE_CAL_BASIC.match(s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        if not (1 <= y <= 9999):
            raise ValueError(f"Year {y} out of range 1..9999")
        if not (1 <= mo <= 12):
            raise ValueError(f"Month {mo} out of range 1..12")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError(f"Day {d} out of range for month {mo}")
        return (y, mo, d)

    m = _RE_ORD_EXT.match(s)
    if m:
        y, doy = int(m[1]), int(m[2])
        if not (1 <= y <= 9999):
            raise ValueError(f"Year {y} out of range 1..9999")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"Day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_ORD_BASIC.match(s)
    if m:
        y, doy = int(m[1]), int(m[2])
        if not (1 <= y <= 9999):
            raise ValueError(f"Year {y} out of range 1..9999")
        max_doy = 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"Day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_WK_EXT.match(s)
    if m:
        iso_y, wk, wd = int(m[1]), int(m[2]), int(m[3])
        if not (1 <= iso_y <= 9999):
            raise ValueError(f"ISO year {iso_y} out of range 1..9999")
        max_wk = iso_weeks_in_year(iso_y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"Week {wk} out of range 1..{max_wk}")
        if not (1 <= wd <= 7):
            raise ValueError(f"Weekday {wd} out of range 1..7")
        jan4_ord = to_ordinal(iso_y, 1, 4)
        jan4_w = (jan4_ord - 1) % 7
        target_ord = jan4_ord - jan4_w + (wk - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError("Date out of range 1..9999")
        return from_ordinal(target_ord)

    m = _RE_WK_BASIC.match(s)
    if m:
        iso_y, wk, wd = int(m[1]), int(m[2]), int(m[3])
        if not (1 <= iso_y <= 9999):
            raise ValueError(f"ISO year {iso_y} out of range 1..9999")
        max_wk = iso_weeks_in_year(iso_y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"Week {wk} out of range 1..{max_wk}")
        if not (1 <= wd <= 7):
            raise ValueError(f"Weekday {wd} out of range 1..7")
        jan4_ord = to_ordinal(iso_y, 1, 4)
        jan4_w = (jan4_ord - 1) % 7
        target_ord = jan4_ord - jan4_w + (wk - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError("Date out of range 1..9999")
        return from_ordinal(target_ord)

    raise ValueError(f"Unrecognized date format: {s!r}")

# ─── format_date ─────────────────────────────────────────────────────────────

def format_date(date, form):
    _check_date(date)
    y, m, d = date
    _check_date_range(y, m, d)
    if not isinstance(form, str) or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"Invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_:01d}"

# ─── diff ────────────────────────────────────────────────────────────────────

def diff(a, b):
    _check_date(a)
    _check_date(b)
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a <= b:
        # Binary search for largest K >= 0 with add_months(a, K) <= b
        lo = 0
        hi = (by - ay) * 12 + 13
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _add_months_unchecked(a, mid) <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _add_months_unchecked(a, K)
        days = to_ordinal(by, bm, bd) - to_ordinal(shifted[0], shifted[1], shifted[2])
        return (years, months, days)
    else:
        years, months, days = diff(b, a)
        return (-years, -months, -days)