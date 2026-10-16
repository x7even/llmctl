"""Proleptic-Gregorian calendar arithmetic for years 1–9999 (plain integer arithmetic only)."""

__all__ = [
    'is_leap', 'days_in_month', 'to_ordinal', 'from_ordinal', 'weekday',
    'add_days', 'add_months', 'iso_weeks_in_year', 'iso_week',
    'from_iso_week', 'parse', 'format_date', 'diff',
]

# ─── internal constants ───────────────────────────────────────────────
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
_MAX_ORD = 3652059  # ordinal of (9999, 12, 31)

# ─── internal helpers (no validation) ─────────────────────────────────

def _is_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def _dim(y, m):
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if m in (4, 6, 9, 11):
        return 30
    return 29 if _is_leap(y) else 28


def _days_before_year(y):
    y1 = y - 1
    return 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400


def _to_ord(y, m, d):
    t = _days_before_year(y) + _CUM[m - 1] + d
    if m > 2 and _is_leap(y):
        t += 1
    return t


def _from_ord(n):
    n0 = n - 1
    y = (n0 * 4 + 3) // 1461 + 1
    while _days_before_year(y) > n0:
        y -= 1
    while _days_before_year(y + 1) <= n0:
        y += 1
    diy = n0 - _days_before_year(y)  # 0-based day-in-year
    cum = _CUM_LEAP if _is_leap(y) else _CUM
    lo, hi = 0, 11
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if cum[mid] <= diy:
            lo = mid
        else:
            hi = mid - 1
    return (y, lo + 1, diy - cum[lo] + 1)


def _add_m(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    return (ty, tm, d if d <= _dim(ty, tm) else _dim(ty, tm))


def _iso53(iy):
    j1 = _to_ord(iy, 1, 1)
    wd = (j1 - 1) % 7
    return wd == 3 or (wd == 2 and _is_leap(iy))


def _iso_week_calc(y, m, d):
    o = _to_ord(y, m, d)
    wd = (o - 1) % 7
    thu = o + (3 - wd)
    n0 = thu - 1
    iy = (n0 * 4 + 3) // 1461 + 1
    while _days_before_year(iy) > n0:
        iy -= 1
    while _days_before_year(iy + 1) <= n0:
        iy += 1
    j4 = _to_ord(iy, 1, 4)
    w1 = j4 - (j4 - 1) % 7
    return (iy, (o - w1) // 7 + 1, wd + 1)


def _iso_ord(iy, w, d):
    j4 = _to_ord(iy, 1, 4)
    return j4 - (j4 - 1) % 7 + (w - 1) * 7 + (d - 1)


# ─── validation helpers ───────────────────────────────────────────────

def _ci(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int")


def _cd(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for v in date:
        if type(v) is not int:
            raise TypeError(f"{name} must be a tuple of 3 ints")


def _cr(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")


# ─── public API ───────────────────────────────────────────────────────

def is_leap(y):
    _ci(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap(y)


def days_in_month(y, m):
    _ci(y, 'y')
    _ci(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cr(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    _ci(n, 'n')
    if n < 1 or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    return _from_ord(n)


def weekday(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cr(y, m, d)
    return (_to_ord(y, m, d) - 1) % 7


def add_days(date, n):
    _cd(date, 'date')
    _ci(n, 'n')
    y, m, d = date
    _cr(y, m, d)
    no = _to_ord(y, m, d) + n
    if no < 1 or no > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(no)


def add_months(date, n):
    _cd(date, 'date')
    _ci(n, 'n')
    y, m, d = date
    _cr(y, m, d)
    r = _add_m(y, m, d, n)
    if r[0] < 1 or r[0] > 9999:
        raise OverflowError("result year out of range")
    return r


def iso_weeks_in_year(iso_year):
    _ci(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    return 53 if _iso53(iso_year) else 52


def iso_week(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cr(y, m, d)
    return _iso_week_calc(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _ci(iso_year, 'iso_year')
    _ci(week, 'week')
    _ci(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    if week < 1 or week > (53 if _iso53(iso_year) else 52):
        raise ValueError("week out of range")
    o = _iso_ord(iso_year, week, weekday)
    if o < 1 or o > _MAX_ORD:
        raise OverflowError("result date out of range")
    return _from_ord(o)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    n = len(s)

    if n == 10:
        if s[4] == '-' and s[7] == '-':
            _cal_ext(s)
        elif s[4] == '-' and s[5] == 'W' and s[8] == '-':
            _wk_ext(s)
        else:
            raise ValueError("invalid format")
    elif n == 8:
        if s[4] == '-':
            _ord_ext(s)
        elif s[4] == 'W':
            _wk_bas(s)
        else:
            _cal_bas(s)
    elif n == 7:
        _ord_bas(s)
    else:
        raise ValueError("invalid format")


def _dig(s):
    return all('0' <= c <= '9' for c in s)


def _cal_ext(s):
    a, b, c = s[:4], s[5:7], s[8:10]
    if not _dig(a + b + c):
        raise ValueError("invalid characters")
    y, m, d = int(a), int(b), int(c)
    _cr(y, m, d)
    return (y, m, d)


def _cal_bas(s):
    if not _dig(s):
        raise ValueError("invalid characters")
    y, m, d = int(s[:4]), int(s[4:6]), int(s[6:8])
    _cr(y, m, d)
    return (y, m, d)


def _ord_ext(s):
    a, b = s[:4], s[5:8]
    if not _dig(a + b):
        raise ValueError("invalid characters")
    return _ord_calc(int(a), int(b))


def _ord_bas(s):
    if not _dig(s):
        raise ValueError("invalid characters")
    return _ord_calc(int(s[:4]), int(s[4:7]))


def _ord_calc(y, doy):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    mx = 366 if _is_leap(y) else 365
    if doy < 1 or doy > mx:
        raise ValueError("day of year out of range")
    return _from_ord(_to_ord(y, 1, 1) + doy - 1)


def _wk_ext(s):
    a, b, c = s[:4], s[6:8], s[9:10]
    if not _dig(a + b + c):
        raise ValueError("invalid characters")
    return _wk_calc(int(a), int(b), int(c))


def _wk_bas(s):
    a, b, c = s[:4], s[5:7], s[7:8]
    if not _dig(a + b + c):
        raise ValueError("invalid characters")
    return _wk_calc(int(a), int(b), int(c))


def _wk_calc(iy, w, d):
    if iy < 1 or iy > 9999:
        raise ValueError("iso_year out of range")
    if d < 1 or d > 7:
        raise ValueError("weekday out of range")
    if w < 1 or w > (53 if _iso53(iy) else 52):
        raise ValueError("week out of range")
    o = _iso_ord(iy, w, d)
    if o < 1 or o > _MAX_ORD:
        raise ValueError("date out of range")
    return _from_ord(o)


def format_date(date, form):
    _cd(date, 'date')
    y, m, d = date
    _cr(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = _to_ord(y, m, d) - _to_ord(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    iy, iw, iwd = _iso_week_calc(y, m, d)
    return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _cd(a, 'a')
    _cd(b, 'b')
    _cr(a[0], a[1], a[2])
    _cr(b[0], b[1], b[2])
    oa = _to_ord(a[0], a[1], a[2])
    ob = _to_ord(b[0], b[1], b[2])
    if oa > ob:
        y, m, d = _diff_fwd(b, a)
        return (-y, -m, -d)
    return _diff_fwd(a, b)


def _diff_fwd(a, b):
    """a <= b by ordinal."""
    ob = _to_ord(b[0], b[1], b[2])
    lo, hi = 0, 119988
    while lo < hi:
        mid = (lo + hi) >> 1
        sh = _add_m(a[0], a[1], a[2], mid)
        if sh[0] > 9999:
            hi = mid
        elif _to_ord(sh[0], sh[1], sh[2]) <= ob:
            lo = mid + 1
        else:
            hi = mid
    K = lo - 1
    sh = _add_m(a[0], a[1], a[2], K)
    years, months = divmod(K, 12)
    days = ob - _to_ord(sh[0], sh[1], sh[2])
    return (years, months, days)
