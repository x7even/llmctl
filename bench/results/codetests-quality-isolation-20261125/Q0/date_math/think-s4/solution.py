import re

# ─── Constants ─────────────────────────────────────────────────────────────────

_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORDINAL = 3652059  # ordinal of (9999, 12, 31)

# ─── Internal arithmetic helpers (no validation) ──────────────────────────────

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _dim(y, m):
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if m in (4, 6, 9, 11):
        return 30
    return 29 if _is_leap(y) else 28

def _days_before_year(y):
    n = y - 1
    return n * 365 + n // 4 - n // 100 + n // 400

def _days_before_month(y, m):
    r = _CUM[m - 1]
    if _is_leap(y) and m > 2:
        r += 1
    return r

def _to_ordinal(y, m, d):
    return _days_before_year(y) + _days_before_month(y, m) + d

def _from_ordinal(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    m = 1
    while m <= 12:
        if doy <= _dim(y, m):
            return (y, m, doy)
        doy -= _dim(y, m)
        m += 1

def _weekday(y, m, d):
    return (_to_ordinal(y, m, d) - 1) % 7

def _iso_weeks_in_year(y):
    jan1 = _weekday(y, 1, 1)
    if jan1 == 3:
        return 53
    if _is_leap(y) and jan1 == 2:
        return 53
    return 52

def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        return None
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)

# ─── Validation helpers ────────────────────────────────────────────────────────

def _require_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")

def _require_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i in range(3):
        if type(x[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int")

def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range for {y:04d}-{m:02d}")

# ─── Public API ────────────────────────────────────────────────────────────────

def is_leap(y):
    _require_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)

def days_in_month(y, m):
    _require_int(y, 'y')
    _require_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)

def to_ordinal(y, m, d):
    _require_int(y, 'y')
    _require_int(m, 'm')
    _require_int(d, 'd')
    _check_date_range(y, m, d)
    return _to_ordinal(y, m, d)

def from_ordinal(n):
    _require_int(n, 'n')
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    return _from_ordinal(n)

def weekday(y, m, d):
    _require_int(y, 'y')
    _require_int(m, 'm')
    _require_int(d, 'd')
    _check_date_range(y, m, d)
    return _weekday(y, m, d)

def add_days(date, n):
    _require_date(date, 'date')
    _require_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ordinal = _to_ordinal(y, m, d) + n
    if ordinal < 1 or ordinal > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {ordinal} out of range 1..{_MAX_ORDINAL}")
    return _from_ordinal(ordinal)

def add_months(date, n):
    _require_date(date, 'date')
    _require_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    result = _add_months_raw(y, m, d, n)
    if result is None:
        raise OverflowError("result year out of range 1..9999")
    return result

def iso_weeks_in_year(iso_year):
    _require_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)

def iso_week(y, m, d):
    _require_int(y, 'y')
    _require_int(m, 'm')
    _require_int(d, 'd')
    _check_date_range(y, m, d)
    ord_ = _to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7
    jan4_ord = _to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_week1_y = jan4_ord - jan4_wd
    monday = ord_ - wd
    if monday < monday_week1_y:
        iso_y = y - 1
        jan4_prev = _to_ordinal(iso_y, 1, 4)
        jan4_prev_wd = (jan4_prev - 1) % 7
        monday_week1_prev = jan4_prev - jan4_prev_wd
        iso_w = (monday - monday_week1_prev) // 7 + 1
    else:
        iso_y = y
        iso_w = (monday - monday_week1_y) // 7 + 1
    return (iso_y, iso_w, wd + 1)

def from_iso_week(iso_year, week, weekday):
    _require_int(iso_year, 'iso_year')
    _require_int(week, 'week')
    _require_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = _iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_week1 = jan4_ord - jan4_wd
    target = monday_week1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {target} out of range")
    return _from_ordinal(target)

# ─── Parse ─────────────────────────────────────────────────────────────────────

_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BASIC_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BASIC_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WEEK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BASIC_WEEK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')

def _parse_week(iso_y, week, wd):
    if iso_y < 1 or iso_y > 9999:
        raise ValueError(f"iso_year {iso_y} out of range 1..9999")
    max_week = _iso_weeks_in_year(iso_y)
    if week < 1 or week > max_week:
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if wd < 1 or wd > 7:
        raise ValueError(f"weekday {wd} out of range 1..7")
    jan4_ord = _to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_week1 = jan4_ord - jan4_wd
    target = monday_week1 + (week - 1) * 7 + (wd - 1)
    if target < 1 or target > _MAX_ORDINAL:
        raise ValueError("date out of range")
    return _from_ordinal(target)

def _parse_ord(y, doy):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    max_doy = 366 if _is_leap(y) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
    return _from_ordinal(_days_before_year(y) + doy)

def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")
    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date_range(y, mo, d)
        return (y, mo, d)
    m = _RE_BASIC_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date_range(y, mo, d)
        return (y, mo, d)
    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        return _parse_ord(int(m.group(1)), int(m.group(2)))
    m = _RE_BASIC_ORD.fullmatch(s)
    if m:
        return _parse_ord(int(m.group(1)), int(m.group(2)))
    m = _RE_EXT_WEEK.fullmatch(s)
    if m:
        return _parse_week(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _RE_BASIC_WEEK.fullmatch(s)
    if m:
        return _parse_week(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    raise ValueError(f"invalid date string: {s!r}")

# ─── Format ────────────────────────────────────────────────────────────────────

def format_date(date, form):
    _require_date(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    # form == 'week'
    iso_y, iso_w, iso_wd = iso_week(y, m, d)
    return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"

# ─── Diff ──────────────────────────────────────────────────────────────────────

def _diff_nonneg(a, b):
    hi = (b[0] - a[0]) * 12 + (b[1] - a[1]) + 12
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _add_months_raw(a[0], a[1], a[2], mid)
        if shifted is not None and shifted <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_raw(a[0], a[1], a[2], K)
    days = _to_ordinal(b[0], b[1], b[2]) - _to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)

def diff(a, b):
    _require_date(a, 'a')
    _require_date(b, 'b')
    _check_date_range(a[0], a[1], a[2])
    _check_date_range(b[0], b[1], b[2])
    if a <= b:
        return _diff_nonneg(a, b)
    r = _diff_nonneg(b, a)
    return (-r[0], -r[1], -r[2])
