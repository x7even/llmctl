import re

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------
_DAYS_BEFORE_MONTH_COMMON = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_DAYS_BEFORE_MONTH_LEAP   = (0, 0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
_DAYS_IN_MONTH_COMMON = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_DAYS_IN_MONTH_LEAP   = (0, 31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

_MAX_ORDINAL = 3652059

# ---------------------------------------------------------------------------
# Internal helpers (no redundant checks)
# ---------------------------------------------------------------------------

def _is_int(x):
    return type(x) is int


def _is_date(d):
    return (type(d) is tuple and len(d) == 3
            and _is_int(d[0]) and _is_int(d[1]) and _is_int(d[2]))


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    return _DAYS_IN_MONTH_LEAP[m] if _leap(y) else _DAYS_IN_MONTH_COMMON[m]


def _ordinal(y, m, d):
    cum = _DAYS_BEFORE_MONTH_LEAP[m] if _leap(y) else _DAYS_BEFORE_MONTH_COMMON[m]
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400 + cum + d


def _from_ord(n):
    """n is 1-based ordinal; returns (y, m, d)."""
    n -= 1  # 0-based
    n400, n = divmod(n, 146097)

    if n < 109572:
        n100 = n // 36524
        n -= n100 * 36524
    else:
        n100 = 3
        n -= 109572

    if n < 35064:
        n4 = n // 1461
        n -= n4 * 1461
    else:
        n4 = 24
        n -= 35064

    if n4 < 24:
        if n < 1095:
            n1 = n // 365
            n -= n1 * 365
        else:
            n1 = 3
            n -= 1095
    else:
        n1 = n // 365
        n -= n1 * 365

    year = n400 * 400 + n100 * 100 + n4 * 4 + n1 + 1
    doy0 = n  # 0-based day of year

    cum = _DAYS_BEFORE_MONTH_LEAP if _leap(year) else _DAYS_BEFORE_MONTH_COMMON
    for m in range(12, 0, -1):
        if cum[m] <= doy0:
            return (year, m, doy0 - cum[m] + 1)


def _wd(y, m, d):
    """Weekday 0=Mon .. 6=Sun."""
    return (_ordinal(y, m, d) - 1) % 7


def _iso_wks(iso_year):
    w = _wd(iso_year, 1, 1)
    if w == 3:
        return 53
    if w == 2 and _leap(iso_year):
        return 53
    return 52


def _iso_wk(y, m, d):
    o = _ordinal(y, m, d)
    w = (o - 1) % 7
    thu = o - w + 3
    iy = _from_ord(thu)[0]
    jan1 = _ordinal(iy, 1, 1)
    return (iy, (thu - jan1) // 7 + 1, w + 1)


def _shift(a, k):
    """add_months without checks (internal)."""
    total = (a[0] - 1) * 12 + (a[1] - 1) + k
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = a[2]
    dim = _dim(ty, tm)
    if td > dim:
        td = dim
    return (ty, tm, td)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _chk_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


# ---------------------------------------------------------------------------
# Regex patterns for parse (ASCII digits only)
# ---------------------------------------------------------------------------
_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BAS = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BAS = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WK_EXT  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BAS  = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    if not _is_int(y):
        raise TypeError("year must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _leap(y)


def days_in_month(y, m):
    if not _is_int(y):
        raise TypeError("year must be int")
    if not _is_int(m):
        raise TypeError("month must be int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _dim(y, m)


def to_ordinal(y, m, d):
    if not _is_int(y):
        raise TypeError("year must be int")
    if not _is_int(m):
        raise TypeError("month must be int")
    if not _is_int(d):
        raise TypeError("day must be int")
    _chk_date_range(y, m, d)
    return _ordinal(y, m, d)


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be int")
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError("ordinal out of range")
    return _from_ord(n)


def weekday(y, m, d):
    if not _is_int(y):
        raise TypeError("year must be int")
    if not _is_int(m):
        raise TypeError("month must be int")
    if not _is_int(d):
        raise TypeError("day must be int")
    _chk_date_range(y, m, d)
    return _wd(y, m, d)


def add_days(date, n):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    _chk_date_range(date[0], date[1], date[2])
    new_o = _ordinal(date[0], date[1], date[2]) + n
    if new_o < 1 or new_o > _MAX_ORDINAL:
        raise OverflowError("result date out of range")
    return _from_ord(new_o)


def add_months(date, n):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    if not _is_int(n):
        raise TypeError("n must be int")
    _chk_date_range(date[0], date[1], date[2])
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("target year out of range")
    td = d
    dim = _dim(ty, tm)
    if td > dim:
        td = dim
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    return _iso_wks(iso_year)


def iso_week(y, m, d):
    if not _is_int(y):
        raise TypeError("year must be int")
    if not _is_int(m):
        raise TypeError("month must be int")
    if not _is_int(d):
        raise TypeError("day must be int")
    _chk_date_range(y, m, d)
    return _iso_wk(y, m, d)


def from_iso_week(iso_year, week, weekday):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be int")
    if not _is_int(week):
        raise TypeError("week must be int")
    if not _is_int(weekday):
        raise TypeError("weekday must be int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    if week < 1 or week > _iso_wks(iso_year):
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4 = _ordinal(iso_year, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4_wd
    o = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if o < 1 or o > _MAX_ORDINAL:
        raise OverflowError("result date out of range")
    return _from_ord(o)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    # Extended calendar: YYYY-MM-DD
    mt = _RE_CAL_EXT.fullmatch(s)
    if mt:
        y, mo, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _dim(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    # Basic calendar: YYYYMMDD
    mt = _RE_CAL_BAS.fullmatch(s)
    if mt:
        y, mo, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _dim(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD
    mt = _RE_ORD_EXT.fullmatch(s)
    if mt:
        y, doy = int(mt.group(1)), int(mt.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        mx = 366 if _leap(y) else 365
        if doy < 1 or doy > mx:
            raise ValueError("day of year out of range")
        doy0 = doy - 1
        cum = _DAYS_BEFORE_MONTH_LEAP if _leap(y) else _DAYS_BEFORE_MONTH_COMMON
        for mo in range(12, 0, -1):
            if cum[mo] <= doy0:
                return (y, mo, doy0 - cum[mo] + 1)

    # Basic ordinal: YYYYDDD
    mt = _RE_ORD_BAS.fullmatch(s)
    if mt:
        y, doy = int(mt.group(1)), int(mt.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        mx = 366 if _leap(y) else 365
        if doy < 1 or doy > mx:
            raise ValueError("day of year out of range")
        doy0 = doy - 1
        cum = _DAYS_BEFORE_MONTH_LEAP if _leap(y) else _DAYS_BEFORE_MONTH_COMMON
        for mo in range(12, 0, -1):
            if cum[mo] <= doy0:
                return (y, mo, doy0 - cum[mo] + 1)

    # Extended week: YYYY-Www-D
    mt = _RE_WK_EXT.fullmatch(s)
    if mt:
        y, wk, wd = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if wk < 1 or wk > _iso_wks(y):
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        jan4 = _ordinal(y, 1, 4)
        jan4_wd = (jan4 - 1) % 7
        mon_w1 = jan4 - jan4_wd
        o = mon_w1 + (wk - 1) * 7 + (wd - 1)
        if o < 1 or o > _MAX_ORDINAL:
            raise ValueError("date out of range")
        return _from_ord(o)

    # Basic week: YYYYWwwD
    mt = _RE_WK_BAS.fullmatch(s)
    if mt:
        y, wk, wd = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if wk < 1 or wk > _iso_wks(y):
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        jan4 = _ordinal(y, 1, 4)
        jan4_wd = (jan4 - 1) % 7
        mon_w1 = jan4 - jan4_wd
        o = mon_w1 + (wk - 1) * 7 + (wd - 1)
        if o < 1 or o > _MAX_ORDINAL:
            raise ValueError("date out of range")
        return _from_ord(o)

    raise ValueError("unrecognized date format")


def format_date(date, form):
    if not _is_date(date):
        raise TypeError("date must be a tuple of 3 ints")
    _chk_date_range(date[0], date[1], date[2])
    if form != 'calendar' and form != 'ordinal' and form != 'week':
        raise ValueError("form must be 'calendar', 'ordinal', or 'week'")

    y, m, d = date
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        cum = _DAYS_BEFORE_MONTH_LEAP[m] if _leap(y) else _DAYS_BEFORE_MONTH_COMMON[m]
        doy = cum + d
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, iwd = _iso_wk(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    if not _is_date(a):
        raise TypeError("a must be a tuple of 3 ints")
    if not _is_date(b):
        raise TypeError("b must be a tuple of 3 ints")
    _chk_date_range(a[0], a[1], a[2])
    _chk_date_range(b[0], b[1], b[2])

    if a == b:
        return (0, 0, 0)

    negate = False
    if a > b:
        a, b = b, a
        negate = True

    # a < b: find largest K >= 0 with _shift(a, K) <= b
    K0 = (b[0] - a[0]) * 12 + (b[1] - a[1])
    shifted = _shift(a, K0)
    if shifted <= b:
        K = K0
    else:
        K = K0 - 1

    years, months = divmod(K, 12)
    shifted = _shift(a, K)
    days = _ordinal(b[0], b[1], b[2]) - _ordinal(shifted[0], shifted[1], shifted[2])

    if negate:
        return (-years, -months, -days)
    return (years, months, days)
