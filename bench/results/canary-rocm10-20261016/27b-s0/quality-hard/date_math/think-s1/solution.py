import re

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------
_DIM = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
_MIN_ORD = 1
_MAX_ORD = 3652059

# Regex patterns (use [0-9] to match only ASCII digits)
_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9]{1})')
_RE_BAS_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9]{1})')

# ---------------------------------------------------------------------------
# Internal helpers (no type/range checking – callers must validate first)
# ---------------------------------------------------------------------------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    return _DIM[m - 1]


def _days_before_year(y):
    """Number of days from year 1 through year y-1 (i.e. before Jan 1 of y)."""
    y1 = y - 1
    return 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400


def _to_ordinal(y, m, d):
    return _days_before_year(y) + (_CUM_LEAP if _is_leap(y) else _CUM_NONLEAP)[m - 1] + d


def _from_ordinal(n):
    # Binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        if _days_before_year(mid + 1) <= n:
            lo = mid + 1
        else:
            hi = mid
    y = lo
    doy = n - _days_before_year(y)
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NONLEAP
    m = 1
    while cum[m] < doy:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def _weekday(y, m, d):
    return (_to_ordinal(y, m, d) - 1) % 7


def _iso_weeks_in_year(iso_year):
    wd = _weekday(iso_year, 1, 1)  # 0=Mon .. 6=Sun
    if wd == 3:
        return 53
    if wd == 2 and _is_leap(iso_year):
        return 53
    return 52


def _iso_week(y, m, d):
    ord_ = _to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7  # 0=Mon
    # Thursday of this week
    if wd <= 3:
        thu_ord = ord_ + (3 - wd)
    else:
        thu_ord = ord_ - (wd - 3)
    iso_year = _from_ordinal(thu_ord)[0]
    # Monday of week 1 of iso_year
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    week = (ord_ - mon_w1) // 7 + 1
    iso_wd = wd + 1  # 1=Mon .. 7=Sun
    return (iso_year, week, iso_wd)


def _from_iso_week(iso_year, week, weekday):
    """Return (y, m, d) or raise OverflowError if out of range."""
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target_ord = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target_ord < _MIN_ORD or target_ord > _MAX_ORD:
        raise OverflowError("result out of supported date range")
    return _from_ordinal(target_ord)


def _add_months(y, m, d, n):
    """Return (ty, tm, td) or raise OverflowError."""
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of supported date range")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _chk_date(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int")


def _chk_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    dm = _dim(y, m)
    if d < 1 or d > dm:
        raise ValueError(f"day {d} out of range 1..{dm}")


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
    if n < _MIN_ORD or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range {_MIN_ORD}..{_MAX_ORD}")
    return _from_ordinal(n)


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
    ord_ = _to_ordinal(y, m, d) + n
    if ord_ < _MIN_ORD or ord_ > _MAX_ORD:
        raise OverflowError("result out of supported date range")
    return _from_ordinal(ord_)


def add_months(date, n):
    _chk_date(date, "date")
    _chk_int(n, "n")
    y, m, d = date
    _chk_date_range(y, m, d)
    return _add_months(y, m, d, n)


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


def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, "iso_year")
    _chk_int(week, "week")
    _chk_int(weekday, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = _iso_weeks_in_year(iso_year)
    if week < 1 or week > max_wk:
        raise ValueError(f"week {week} out of range 1..{max_wk}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    return _from_iso_week(iso_year, week, weekday)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _dim(y, mo):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_BAS_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _dim(y, mo):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range")
        return _from_ordinal(_days_before_year(y) + doy)

    m = _RE_BAS_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range")
        return _from_ordinal(_days_before_year(y) + doy)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        max_wk = _iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range")
        try:
            return _from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of supported range")

    m = _RE_BAS_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        max_wk = _iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range")
        try:
            return _from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of supported range")

    raise ValueError(f"unrecognized date string: {s!r}")


def format_date(date, form):
    _chk_date(date, "date")
    y, m, d = date
    _chk_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = (_CUM_LEAP if _is_leap(y) else _CUM_NONLEAP)[m - 1] + d
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, id_ = _iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"


def diff(a, b):
    _chk_date(a, "a")
    _chk_date(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _chk_date_range(ay, am, ad)
    _chk_date_range(by, bm, bd)

    if (ay, am, ad) <= (by, bm, bd):
        # a <= b: find largest K >= 0 with shift(a, K) <= b
        base = (ay - 1) * 12 + (am - 1)
        target = (by - 1) * 12 + (bm - 1)
        # Check if at target month, the clamped day <= bd
        if min(ad, _dim(by, bm)) <= bd:
            K = target - base
        else:
            K = target - 1 - base
        years, months = divmod(K, 12)
        # shift(a, K)
        total = base + K
        sy = total // 12 + 1
        sm = total % 12 + 1
        sd = ad if ad <= _dim(sy, sm) else _dim(sy, sm)
        days = _to_ordinal(by, bm, bd) - _to_ordinal(sy, sm, sd)
        return (years, months, days)
    else:
        # a > b: negate diff(b, a)
        by2, bm2, bd2 = b
        ay2, am2, ad2 = a
        base = (by2 - 1) * 12 + (bm2 - 1)
        target = (ay2 - 1) * 12 + (am2 - 1)
        if min(bd2, _dim(ay2, am2)) <= ad2:
            K = target - base
        else:
            K = target - 1 - base
        years, months = divmod(K, 12)
        total = base + K
        sy = total // 12 + 1
        sm = total % 12 + 1
        sd = bd2 if bd2 <= _dim(sy, sm) else _dim(sy, sm)
        days = _to_ordinal(ay2, am2, ad2) - _to_ordinal(sy, sm, sd)
        return (-years, -months, -days)
