import re


# ---------------------------------------------------------------------------
# Internal helpers (no public exposure)
# ---------------------------------------------------------------------------

_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MDAYS[m - 1]


def _days_before_year(y):
    """Total days in years 1..y-1."""
    x = y - 1
    return x * 365 + x // 4 - x // 100 + x // 400


def _month_offset(y, m):
    """Days in months 1..m-1 of year y."""
    r = _CUM[m - 1]
    if m > 2 and _is_leap(y):
        r += 1
    return r


def _to_ord(y, m, d):
    return _days_before_year(y) + _month_offset(y, m) + d


def _from_ord(n):
    """Convert 1-based ordinal to (y, m, d).  Assumes 1 <= n <= 3652059."""
    # Close estimate: x = y-1 ≈ n * 400 / 146097
    x = (n * 400) // 146097
    y = x + 1
    if y < 1:
        y = 1
    elif y > 9999:
        y = 9999
    # At most a couple of corrections
    while _days_before_year(y) >= n:
        y -= 1
    while y < 9999 and _days_before_year(y + 1) < n:
        y += 1
    doy = n - _days_before_year(y)
    leap = 1 if _is_leap(y) else 0
    cum = (0, 31, 59 + leap, 90 + leap, 120 + leap, 151 + leap,
           181 + leap, 212 + leap, 243 + leap, 273 + leap,
           304 + leap, 334 + leap)
    for m in range(12, 0, -1):
        if doy > cum[m - 1]:
            return (y, m, doy - cum[m - 1])
    return (y, 1, doy)


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int")


def _check_date(x, name):
    if type(x) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i in range(3):
        if type(x[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int")


def _check_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")


def _iso_weeks(y):
    """Number of ISO weeks in ISO year y (assumes 1<=y<=9999)."""
    wd = _days_before_year(y) % 7  # weekday of Jan 1 (Mon=0)
    if wd == 3:
        return 53
    if _is_leap(y) and wd == 2:
        return 53
    return 52


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_range(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ord(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_range(y, m, d)
    return (_to_ord(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_range(y, m, d)
    o = _to_ord(y, m, d) + n
    if o < 1 or o > 3652059:
        raise OverflowError("result out of supported range")
    return _from_ord(o)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_range(y, m, d)
    tm = (y - 1) * 12 + (m - 1) + n
    if tm < 0 or tm > 119987:
        raise OverflowError("result out of supported range")
    ny = tm // 12 + 1
    nm = tm % 12 + 1
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks(iso_year)


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_range(y, m, d)
    o = _to_ord(y, m, d)
    iso_wd = (o - 1) % 7 + 1          # 1=Mon .. 7=Sun
    thu_o = o + (4 - iso_wd)          # Thursday of this ISO week
    thu = _from_ord(thu_o)
    iso_y = thu[0]
    jan4_o = _to_ord(iso_y, 1, 4)
    jan4_wd = (jan4_o - 1) % 7        # 0=Mon
    mon_w1 = jan4_o - jan4_wd
    iso_wk = (thu_o - mon_w1) // 7 + 1
    return (iso_y, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = _iso_weeks(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_o = _to_ord(iso_year, 1, 4)
    jan4_wd = (jan4_o - 1) % 7
    mon_w1 = jan4_o - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of supported range")
    return _from_ord(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    n = len(s)

    # ---- 10 chars: extended calendar or extended week ----
    if n == 10:
        if s[5] == 'W':
            # YYYY-Www-D
            if s[4] != '-' or s[8] != '-':
                raise ValueError(f"invalid date string: {s!r}")
            for i in range(10):
                if i in (4, 5, 8):
                    continue
                if not ('0' <= s[i] <= '9'):
                    raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            wk = int(s[6:8])
            wd = int(s[9])
            if y < 1:
                raise ValueError(f"year {y} out of range")
            nw = _iso_weeks(y)
            if wk < 1 or wk > nw:
                raise ValueError(f"week {wk} out of range 1..{nw}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            jan4_o = _to_ord(y, 1, 4)
            jan4_wd = (jan4_o - 1) % 7
            mon_w1 = jan4_o - jan4_wd
            target = mon_w1 + (wk - 1) * 7 + (wd - 1)
            if target < 1 or target > 3652059:
                raise ValueError(f"date out of supported range")
            return _from_ord(target)
        else:
            # YYYY-MM-DD
            if s[4] != '-' or s[7] != '-':
                raise ValueError(f"invalid date string: {s!r}")
            for i in range(10):
                if i in (4, 7):
                    continue
                if not ('0' <= s[i] <= '9'):
                    raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            m = int(s[5:7])
            d = int(s[8:10])
            if y < 1:
                raise ValueError(f"year {y} out of range")
            _check_range(y, m, d)
            return (y, m, d)

    # ---- 8 chars: basic calendar, extended ordinal, or basic week ----
    elif n == 8:
        c4 = s[4]
        if c4 == '-':
            # YYYY-DDD (extended ordinal)
            for i in range(8):
                if i == 4:
                    continue
                if not ('0' <= s[i] <= '9'):
                    raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            doy = int(s[5:8])
            if y < 1:
                raise ValueError(f"year {y} out of range")
            max_doy = 366 if _is_leap(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError(f"day of year {doy} out of range")
            return _from_ord(_days_before_year(y) + doy)
        elif c4 == 'W':
            # YYYYWwwD (basic week)
            for i in range(8):
                if i == 4:
                    continue
                if not ('0' <= s[i] <= '9'):
                    raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            wk = int(s[5:7])
            wd = int(s[7])
            if y < 1:
                raise ValueError(f"year {y} out of range")
            nw = _iso_weeks(y)
            if wk < 1 or wk > nw:
                raise ValueError(f"week {wk} out of range 1..{nw}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            jan4_o = _to_ord(y, 1, 4)
            jan4_wd = (jan4_o - 1) % 7
            mon_w1 = jan4_o - jan4_wd
            target = mon_w1 + (wk - 1) * 7 + (wd - 1)
            if target < 1 or target > 3652059:
                raise ValueError(f"date out of supported range")
            return _from_ord(target)
        elif '0' <= c4 <= '9':
            # YYYYMMDD (basic calendar)
            for i in range(8):
                if not ('0' <= s[i] <= '9'):
                    raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            m = int(s[4:6])
            d = int(s[6:8])
            if y < 1:
                raise ValueError(f"year {y} out of range")
            _check_range(y, m, d)
            return (y, m, d)
        else:
            raise ValueError(f"invalid date string: {s!r}")

    # ---- 7 chars: basic ordinal YYYYDDD ----
    elif n == 7:
        for i in range(7):
            if not ('0' <= s[i] <= '9'):
                raise ValueError(f"invalid date string: {s!r}")
        y = int(s[0:4])
        doy = int(s[4:7])
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range")
        return _from_ord(_days_before_year(y) + doy)

    else:
        raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _month_offset(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_range(ay, am, ad)
    _check_range(by, bm, bd)

    if _to_ord(ay, am, ad) > _to_ord(by, bm, bd):
        # a > b: negate diff(b, a)
        ry, rm, rd = diff(b, a)
        return (-ry, -rm, -rd)

    # a <= b
    tm_a = (ay - 1) * 12 + (am - 1)
    tm_b = (by - 1) * 12 + (bm - 1)
    K = tm_b - tm_a
    if K > 0:
        target_dim = _dim(by, bm)
        clamped = ad if ad <= target_dim else target_dim
        if clamped > bd:
            K -= 1
    years, months = divmod(K, 12)
    # Compute shift(a, K)
    tm_k = tm_a + K
    sy = tm_k // 12 + 1
    sm = tm_k % 12 + 1
    sd = ad if ad <= _dim(sy, sm) else _dim(sy, sm)
    days = _to_ord(by, bm, bd) - _to_ord(sy, sm, sd)
    return (years, months, days)
