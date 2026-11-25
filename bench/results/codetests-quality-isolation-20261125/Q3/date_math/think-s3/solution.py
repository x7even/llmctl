import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# Cumulative days before month index (1-indexed month m uses index m-1)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)

_MAX_ORDINAL = 3652059  # ordinal of (9999, 12, 31)

# Regexes for parse (fullmatch)
_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BAS  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')

# ---------------------------------------------------------------------------
# Internal helpers (no type/range checking; callers guarantee validity)
# ---------------------------------------------------------------------------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MDAYS[m - 1]


def _year_start(y):
    """Ordinal of (y, 1, 1)."""
    yp = y - 1
    return 365 * yp + yp // 4 - yp // 100 + yp // 400 + 1


def _add_months_inner(y, m, d, n):
    """Return (ny, nm, nd) without any checks. n is the month offset."""
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


# ---------------------------------------------------------------------------
# Type / range checking helpers
# ---------------------------------------------------------------------------

def _chk_int(val, name):
    if type(val) is not int:
        raise TypeError(f"{name} must be an int, got {type(val).__name__}")


def _chk_date_tuple(val, name):
    if type(val) is not tuple or len(val) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, x in enumerate(val):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(x).__name__}")


def _chk_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)} for {y}-{m:02d}")


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
    yp = y - 1
    days_before_year = 365 * yp + yp // 4 - yp // 100 + yp // 400
    cum = _CUM_LEAP if _is_leap(y) else _CUM
    return days_before_year + cum[m - 1] + d


def from_ordinal(n):
    _chk_int(n, "n")
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    # Estimate year using 400-year cycle (146097 days)
    y = (n * 400) // 146097 + 1
    # Adjust (at most a couple of iterations)
    while _year_start(y + 1) <= n:
        y += 1
    while _year_start(y) > n:
        y -= 1
    # Day-of-year (1-indexed)
    doy = n - _year_start(y) + 1
    cum = _CUM_LEAP if _is_leap(y) else _CUM
    m = 1
    while m < 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def weekday(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _chk_date_tuple(date, "date")
    _chk_int(n, "n")
    y, m, d = date
    _chk_date_range(y, m, d)
    ord_ = to_ordinal(y, m, d) + n
    if ord_ < 1 or ord_ > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {ord_} out of range 1..{_MAX_ORDINAL}")
    return from_ordinal(ord_)


def add_months(date, n):
    _chk_date_tuple(date, "date")
    _chk_int(n, "n")
    y, m, d = date
    _chk_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError(f"target year {ny} out of range 1..9999")
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    yp = iso_year - 1
    wd = (365 * yp + yp // 4 - yp // 100 + yp // 400) % 7  # Mon=0
    if wd == 3 or (_is_leap(iso_year) and wd == 2):
        return 53
    return 52


def iso_week(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_date_range(y, m, d)
    ord_ = to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7  # Mon=0
    monday_ordinal = ord_ - wd
    thursday_ordinal = monday_ordinal + 3
    iso_y, _, _ = from_ordinal(thursday_ordinal)
    # Monday of week 1 of iso_y
    jan4 = _year_start(iso_y) + 3
    jan4_wd = (jan4 - 1) % 7
    monday_w1 = jan4 - jan4_wd
    iso_w = (monday_ordinal - monday_w1) // 7 + 1
    iso_wd = wd + 1  # Mon=1
    return (iso_y, iso_w, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, "iso_year")
    _chk_int(week, "week")
    _chk_int(weekday, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_w = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_w:
        raise ValueError(f"week {week} out of range 1..{max_w}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    # Monday of week 1
    jan4 = _year_start(iso_year) + 3
    jan4_wd = (jan4 - 1) % 7
    monday_w1 = jan4 - jan4_wd
    ord_ = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if ord_ < 1 or ord_ > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {ord_} out of range 1..{_MAX_ORDINAL}")
    return from_ordinal(ord_)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    # Try each form via fullmatch
    # 10-char forms
    if len(s) == 10:
        mt = _RE_CAL_EXT.fullmatch(s)
        if mt:
            y = int(mt.group(1)); m = int(mt.group(2)); d = int(mt.group(3))
            if y < 1:
                raise ValueError(f"year 0000 is out of range")
            if m < 1 or m > 12:
                raise ValueError(f"month {m:02d} out of range 01..12")
            if d < 1 or d > _dim(y, m):
                raise ValueError(f"day {d:02d} out of range for {y:04d}-{m:02d}")
            return (y, m, d)
        mt = _RE_WK_EXT.fullmatch(s)
        if mt:
            y = int(mt.group(1)); w = int(mt.group(2)); wd = int(mt.group(3))
            if y < 1:
                raise ValueError(f"year 0000 is out of range")
            if w < 1 or w > iso_weeks_in_year(y):
                raise ValueError(f"week {w:02d} out of range for ISO year {y}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            ord_ = _iso_week_ordinal(y, w, wd)
            if ord_ < 1 or ord_ > _MAX_ORDINAL:
                raise ValueError(f"week date out of supported range")
            return from_ordinal(ord_)
        raise ValueError(f"unrecognized date format: {s!r}")

    # 8-char forms
    if len(s) == 8:
        mt = _RE_CAL_BAS.fullmatch(s)
        if mt:
            y = int(mt.group(1)); m = int(mt.group(2)); d = int(mt.group(3))
            if y < 1:
                raise ValueError(f"year 0000 is out of range")
            if m < 1 or m > 12:
                raise ValueError(f"month {m:02d} out of range 01..12")
            if d < 1 or d > _dim(y, m):
                raise ValueError(f"day {d:02d} out of range for {y:04d}-{m:02d}")
            return (y, m, d)
        mt = _RE_ORD_EXT.fullmatch(s)
        if mt:
            y = int(mt.group(1)); doy = int(mt.group(2))
            if y < 1:
                raise ValueError(f"year 0000 is out of range")
            max_doy = 366 if _is_leap(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError(f"day of year {doy:03d} out of range 001..{max_doy}")
            return from_ordinal(_year_start(y) + doy - 1)
        mt = _RE_WK_BAS.fullmatch(s)
        if mt:
            y = int(mt.group(1)); w = int(mt.group(2)); wd = int(mt.group(3))
            if y < 1:
                raise ValueError(f"year 0000 is out of range")
            if w < 1 or w > iso_weeks_in_year(y):
                raise ValueError(f"week {w:02d} out of range for ISO year {y}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            ord_ = _iso_week_ordinal(y, w, wd)
            if ord_ < 1 or ord_ > _MAX_ORDINAL:
                raise ValueError(f"week date out of supported range")
            return from_ordinal(ord_)
        raise ValueError(f"unrecognized date format: {s!r}")

    # 7-char form: ordinal basic
    if len(s) == 7:
        mt = _RE_ORD_BAS.fullmatch(s)
        if mt:
            y = int(mt.group(1)); doy = int(mt.group(2))
            if y < 1:
                raise ValueError(f"year 0000 is out of range")
            max_doy = 366 if _is_leap(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError(f"day of year {doy:03d} out of range 001..{max_doy}")
            return from_ordinal(_year_start(y) + doy - 1)
        raise ValueError(f"unrecognized date format: {s!r}")

    raise ValueError(f"unrecognized date format: {s!r}")


def _iso_week_ordinal(iso_year, week, wd):
    """Internal: compute ordinal for ISO week date (no validation)."""
    jan4 = _year_start(iso_year) + 3
    jan4_wd = (jan4 - 1) % 7
    monday_w1 = jan4 - jan4_wd
    return monday_w1 + (week - 1) * 7 + (wd - 1)


def format_date(date, form):
    _chk_date_tuple(date, "date")
    y, m, d = date
    _chk_date_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week', got {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _year_start(y) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # 'week'
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _chk_date_tuple(a, "a")
    _chk_date_tuple(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _chk_date_range(ay, am, ad)
    _chk_date_range(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        # Negate diff(b, a)
        K_max = (by - am) * 0 + (bm - am)  # placeholder, compute properly below
        # Actually compute diff(b, a) inline
        K_max = (ay - by) * 12 + (am - bm)
        shift = _add_months_inner(by, bm, bd, K_max)
        if shift > a:
            K = K_max - 1
            shift = _add_months_inner(by, bm, bd, K)
        else:
            K = K_max
        years, months = divmod(K, 12)
        days = to_ordinal(ay, am, ad) - to_ordinal(*shift)
        return (-years, -months, -days)

    # a < b
    K_max = (by - ay) * 12 + (bm - am)
    shift = _add_months_inner(ay, am, ad, K_max)
    if shift > b:
        K = K_max - 1
        shift = _add_months_inner(ay, am, ad, K)
    else:
        K = K_max
    years, months = divmod(K, 12)
    days = to_ordinal(by, bm, bd) - to_ordinal(*shift)
    return (years, months, days)
