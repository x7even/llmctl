"""Proleptic-Gregorian calendar arithmetic for years 1..9999."""


# ---------- internal helpers (no type/range checking) ----------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30


def _days_before(y):
    """Number of days in years 1..y-1 (i.e. ordinal of Dec 31 of year y-1)."""
    if y <= 1:
        return 0
    y -= 1
    return y * 365 + y // 4 - y // 100 + y // 400


def _month_day_offset(y, m):
    """Days before month m in year y (0 for January)."""
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    r = cum[m - 1]
    if m > 2 and _is_leap(y):
        r += 1
    return r


def _to_ord(y, m, d):
    return _days_before(y) + _month_day_offset(y, m) + d


def _from_ord(n):
    """Inverse of _to_ord; n in 1..3652059."""
    y = n // 365 + 1
    while _days_before(y) >= n:
        y -= 1
    while n > _days_before(y + 1):
        y += 1
    doy = n - _days_before(y)
    leap = _is_leap(y)
    mdays = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    for i in range(12):
        if doy <= mdays[i]:
            return (y, i + 1, doy)
        doy -= mdays[i]
    # unreachable


def _add_months_raw(date, n):
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = d if d <= _days_in_month(ty, tm) else _days_in_month(ty, tm)
    return (ty, tm, td)


def _iso_weeks_raw(iso_year):
    w = _days_before(iso_year) % 7  # weekday of Jan 1, 0=Mon
    if w == 3:
        return 53
    if w == 2 and _is_leap(iso_year):
        return 53
    return 52


# ---------- type / range checking helpers ----------

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _chk_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i in range(3):
        if type(x[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _chk_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m:02d}")


# ---------- public API ----------

def is_leap(y):
    _chk_int(y, "y")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _chk_int(y, "y")
    _chk_int(m, "m")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_range(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    _chk_int(n, "n")
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ord(n)


def weekday(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_range(y, m, d)
    return (_to_ord(y, m, d) - 1) % 7


def add_days(date, n):
    _chk_date(date, "date")
    _chk_int(n, "n")
    _chk_range(*date)
    o = _to_ord(*date) + n
    if o < 1 or o > 3652059:
        raise OverflowError("result out of range 1..9999")
    return _from_ord(o)


def add_months(date, n):
    _chk_date(date, "date")
    _chk_int(n, "n")
    _chk_range(*date)
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError("result year out of range 1..9999")
    td = d if d <= _days_in_month(ty, tm) else _days_in_month(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, "iso_year")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_raw(iso_year)


def iso_week(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_range(y, m, d)
    o = _to_ord(y, m, d)
    w = (o - 1) % 7  # 0=Mon .. 6=Sun
    thu_o = o + (3 - w)
    # find year of Thursday
    iso_y = thu_o // 365 + 1
    while _days_before(iso_y) >= thu_o:
        iso_y -= 1
    while thu_o > _days_before(iso_y + 1):
        iso_y += 1
    jan4_o = _days_before(iso_y) + 4
    jan4_w = (jan4_o - 1) % 7
    mon_w1 = jan4_o - jan4_w
    iso_w = (o - mon_w1) // 7 + 1
    iso_d = w + 1
    return (iso_y, iso_w, iso_d)


def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, "iso_year")
    _chk_int(week, "week")
    _chk_int(weekday, "weekday")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_w = _iso_weeks_raw(iso_year)
    if not (1 <= week <= max_w):
        raise ValueError(f"week {week} out of range 1..{max_w} for ISO year {iso_year}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_o = _days_before(iso_year) + 4
    jan4_w = (jan4_o - 1) % 7
    mon_w1 = jan4_o - jan4_w
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range 1..9999")
    return _from_ord(target)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    n = len(s)

    if n == 10:
        if s[4] == '-' and s[7] == '-':
            if s[5] == 'W':
                # Extended week: YYYY-Www-D
                if not _all_digits(s[0:4]) or not _all_digits(s[6:8]) or not _all_digits(s[9:10]):
                    raise ValueError(f"invalid date string: {s!r}")
                y = int(s[0:4]); w = int(s[6:8]); dw = int(s[9])
                if not (1 <= y <= 9999):
                    raise ValueError(f"year {y} out of range")
                max_w = _iso_weeks_raw(y)
                if not (1 <= w <= max_w):
                    raise ValueError(f"week {w} out of range 1..{max_w}")
                if not (1 <= dw <= 7):
                    raise ValueError(f"weekday {dw} out of range 1..7")
                jan4_o = _days_before(y) + 4
                jan4_w = (jan4_o - 1) % 7
                mon_w1 = jan4_o - jan4_w
                target = mon_w1 + (w - 1) * 7 + (dw - 1)
                if target < 1 or target > 3652059:
                    raise ValueError(f"date out of range: {s!r}")
                return _from_ord(target)
            else:
                # Extended calendar: YYYY-MM-DD
                if not _all_digits(s[0:4]) or not _all_digits(s[5:7]) or not _all_digits(s[8:10]):
                    raise ValueError(f"invalid date string: {s!r}")
                y = int(s[0:4]); m = int(s[5:7]); d = int(s[8:10])
                _chk_range(y, m, d)
                return (y, m, d)
        else:
            raise ValueError(f"invalid date string: {s!r}")

    elif n == 8:
        if s[4] == '-':
            # Extended ordinal: YYYY-DDD
            if not _all_digits(s[0:4]) or not _all_digits(s[5:8]):
                raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4]); doy = int(s[5:8])
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range")
            max_doy = 366 if _is_leap(y) else 365
            if not (1 <= doy <= max_doy):
                raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
            return _from_ord(_days_before(y) + doy)
        elif s[4] == 'W':
            # Basic week: YYYYWwwD
            if not _all_digits(s[0:4]) or not _all_digits(s[5:7]) or not _all_digits(s[7:8]):
                raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4]); w = int(s[5:7]); dw = int(s[7])
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range")
            max_w = _iso_weeks_raw(y)
            if not (1 <= w <= max_w):
                raise ValueError(f"week {w} out of range 1..{max_w}")
            if not (1 <= dw <= 7):
                raise ValueError(f"weekday {dw} out of range 1..7")
            jan4_o = _days_before(y) + 4
            jan4_w = (jan4_o - 1) % 7
            mon_w1 = jan4_o - jan4_w
            target = mon_w1 + (w - 1) * 7 + (dw - 1)
            if target < 1 or target > 3652059:
                raise ValueError(f"date out of range: {s!r}")
            return _from_ord(target)
        elif _all_digits(s):
            # Basic calendar YYYYMMDD or basic ordinal YYYYDDD
            y = int(s[0:4])
            # Try calendar first
            m = int(s[4:6]); d = int(s[6:8])
            if 1 <= y <= 9999 and 1 <= m <= 12 and 1 <= d <= _days_in_month(y, m):
                return (y, m, d)
            # Try ordinal
            doy = int(s[4:8])
            if 1 <= y <= 9999:
                max_doy = 366 if _is_leap(y) else 365
                if 1 <= doy <= max_doy:
                    return _from_ord(_days_before(y) + doy)
            raise ValueError(f"invalid date string: {s!r}")
        else:
            raise ValueError(f"invalid date string: {s!r}")
    else:
        raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _chk_date(date, "date")
    _chk_range(*date)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    y, m, d = date
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _month_day_offset(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, idw = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{idw}"


def diff(a, b):
    _chk_date(a, "a")
    _chk_date(b, "b")
    _chk_range(*a)
    _chk_range(*b)

    if a == b:
        return (0, 0, 0)

    if a > b:
        y, m, d = _diff_pos(b, a)
        return (-y, -m, -d)
    else:
        return _diff_pos(a, b)


def _diff_pos(a, b):
    """a < b (chronologically). Return (years, months, days)."""
    lo = 0
    hi = (b[0] - a[0]) * 12 + (b[1] - a[1]) + 1
    if hi < 0:
        hi = 0

    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _add_months_raw(a, mid)
        if shifted <= b:
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_raw(a, K)
    days = _to_ord(*b) - _to_ord(*shifted)
    return (years, months, days)


# ---------- small utility ----------

def _all_digits(s):
    for c in s:
        if c < '0' or c > '9':
            return False
    return True