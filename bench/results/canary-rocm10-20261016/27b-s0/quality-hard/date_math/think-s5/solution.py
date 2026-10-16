import re

# ─── Private helpers ───────────────────────────────────────────────────────────

def _check_int(x, name='x'):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")

def _check_date(date, name='date'):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(v).__name__}")

def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m}")

def _days_before_year(y):
    """Number of days in years 1 through y-1."""
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400

def _days_in_month(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    return (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[m - 1]

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _cum_before_month(y, m):
    """Days before month m in year y (0-indexed: month 1 → 0)."""
    # Non-leap cumulative: [0,31,59,90,120,151,181,212,243,273,304,334]
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    r = cum[m - 1]
    if m > 2 and _is_leap(y):
        r += 1
    return r

def _month_day_from_doy(y, doy):
    """Given day-of-year (1-based), return (month, day)."""
    if _is_leap(y):
        cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
    else:
        cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    for m in range(12, 0, -1):
        if doy > cum[m - 1]:
            return (m, doy - cum[m - 1])
    # Should not reach here for valid doy
    return (1, doy)

# ─── Public API ────────────────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)

def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _days_in_month(y, m)

def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _days_before_year(y) + _cum_before_month(y, m) + d

def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    y = n // 365 + 1
    while _days_before_year(y + 1) <= n:
        y += 1
    while _days_before_year(y) >= n:
        y -= 1
    doy = n - _days_before_year(y)
    m, d = _month_day_from_doy(y, doy)
    return (y, m, d)

def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7

def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ordinal = to_ordinal(y, m, d) + n
    if ordinal < 1 or ordinal > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(ordinal)

def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = y * 12 + (m - 1) + n
    new_y = total // 12
    new_m = total % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError("result out of range")
    new_d = d if d <= _days_in_month(new_y, new_m) else _days_in_month(new_y, new_m)
    return (new_y, new_m, new_d)

def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = _days_before_year(iso_year) % 7  # 0=Mon
    if jan1_wd == 3:  # Thursday
        return 53
    if _is_leap(iso_year) and jan1_wd == 2:  # Wednesday in leap year
        return 53
    return 52

def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ordinal = to_ordinal(y, m, d)
    wd = (ordinal - 1) % 7  # 0=Mon
    monday_ordinal = ordinal - wd
    thursday_ordinal = monday_ordinal + 3
    # Determine ISO year from the Thursday
    # Find year of thursday_ordinal
    ty = thursday_ordinal // 365 + 1
    while _days_before_year(ty + 1) <= thursday_ordinal:
        ty += 1
    while _days_before_year(ty) >= thursday_ordinal:
        ty -= 1
    iso_year = ty
    # Monday of week 1 of iso_year
    jan4_ord = _days_before_year(iso_year) + 4
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    week = (monday_ordinal - monday_w1) // 7 + 1
    iso_wd = wd + 1  # 1=Mon .. 7=Sun
    return (iso_year, week, iso_wd)

def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_week:
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    # Monday of week 1
    jan4_ord = _days_before_year(iso_year) + 4
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target)

# ─── Parse / Format ────────────────────────────────────────────────────────────

_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_WK_EXT  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_WK_BAS  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    L = len(s)

    if L == 10:
        m = _RE_CAL_EXT.fullmatch(s)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1:
                raise ValueError("year 0 not allowed")
            if mo < 1 or mo > 12:
                raise ValueError(f"month {mo} out of range")
            if d < 1 or d > _days_in_month(y, mo):
                raise ValueError(f"day {d} out of range")
            return (y, mo, d)
        m = _RE_WK_EXT.fullmatch(s)
        if m:
            y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1:
                raise ValueError("year 0 not allowed")
            if w < 1 or w > iso_weeks_in_year(y):
                raise ValueError(f"week {w} invalid for year {y}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range")
            try:
                return from_iso_week(y, w, wd)
            except OverflowError:
                raise ValueError("week date out of range")
        raise ValueError(f"unrecognized format: {s!r}")

    if L == 8:
        m = _RE_CAL_BAS.fullmatch(s)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1:
                raise ValueError("year 0 not allowed")
            if mo < 1 or mo > 12:
                raise ValueError(f"month {mo} out of range")
            if d < 1 or d > _days_in_month(y, mo):
                raise ValueError(f"day {d} out of range")
            return (y, mo, d)
        m = _RE_ORD_EXT.fullmatch(s)
        if m:
            y, doy = int(m.group(1)), int(m.group(2))
            if y < 1:
                raise ValueError("year 0 not allowed")
            max_doy = 366 if _is_leap(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError(f"day-of-year {doy} out of range")
            return from_ordinal(_days_before_year(y) + doy)
        m = _RE_WK_BAS.fullmatch(s)
        if m:
            y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 1:
                raise ValueError("year 0 not allowed")
            if w < 1 or w > iso_weeks_in_year(y):
                raise ValueError(f"week {w} invalid for year {y}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range")
            try:
                return from_iso_week(y, w, wd)
            except OverflowError:
                raise ValueError("week date out of range")
        raise ValueError(f"unrecognized format: {s!r}")

    if L == 7:
        m = _RE_ORD_BAS.fullmatch(s)
        if m:
            y, doy = int(m.group(1)), int(m.group(2))
            if y < 1:
                raise ValueError("year 0 not allowed")
            max_doy = 366 if _is_leap(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError(f"day-of-year {doy} out of range")
            return from_ordinal(_days_before_year(y) + doy)
        raise ValueError(f"unrecognized format: {s!r}")

    raise ValueError(f"unrecognized format: {s!r}")

def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    # week
    iy, iw, iday = iso_week(y, m, d)
    return f"{iy:04d}-W{iw:02d}-{iday}"

# ─── diff ──────────────────────────────────────────────────────────────────────

def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    lo = 0
    hi = (by - ay) * 12 + 12
    # Binary search
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            shifted = add_months(a, mid)
        except OverflowError:
            hi = mid - 1
            continue
        if shifted <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    shifted = add_months(a, K)
    years, months = divmod(K, 12)
    days = to_ordinal(by, bm, bd) - to_ordinal(*shifted)
    return (years, months, days)
