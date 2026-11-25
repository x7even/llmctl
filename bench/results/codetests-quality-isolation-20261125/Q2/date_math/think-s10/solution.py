"""Proleptic-Gregorian calendar arithmetic for years 1..9999."""

# ─── Internal constants ───────────────────────────────────────────────────────

_CUM = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]
_MAX_ORD = 3652059  # to_ordinal(9999, 12, 31)

# ─── Internal raw helpers (no type/range checking) ───────────────────────────

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _days_before(y):
    t = y - 1
    return 365 * t + t // 4 - t // 100 + t // 400


def _ordinal(y, m, d):
    r = _days_before(y) + _CUM[m - 1] + d
    if m > 2 and _is_leap(y):
        r += 1
    return r


def _from_ord(n):
    y = (n - 1) * 400 // 146097 + 1
    while _days_before(y) >= n:
        y -= 1
    while _days_before(y + 1) < n:
        y += 1
    doy = n - _days_before(y)
    leap = _is_leap(y)
    md = (31, 29 if leap else 28, 31, 30, 31, 30,
          31, 31, 30, 31, 30, 31)
    for m in range(1, 13):
        if doy <= md[m - 1]:
            return (y, m, doy)
        doy -= md[m - 1]
    raise ValueError("internal error")


def _weekday(y, m, d):
    return (_ordinal(y, m, d) - 1) % 7


def _iso_weeks(y):
    w = _weekday(y, 1, 1)
    return 53 if (w == 3 or (w == 2 and _is_leap(y))) else 52


def _iso_week(y, m, d):
    o = _ordinal(y, m, d)
    wd = (o - 1) % 7
    iso_wd = wd + 1
    thu_o = o + (3 - wd)
    iso_y = _from_ord(thu_o)[0]
    j4 = _ordinal(iso_y, 1, 4)
    j4w = (j4 - 1) % 7
    mon_w1 = j4 - j4w
    mon_cur = o - wd
    iso_w = (mon_cur - mon_w1) // 7 + 1
    return (iso_y, iso_w, iso_wd)


def _from_iso(iso_y, week, wd):
    j4 = _ordinal(iso_y, 1, 4)
    j4w = (j4 - 1) % 7
    mon_w1 = j4 - j4w
    o = mon_w1 + (week - 1) * 7 + (wd - 1)
    if o < 1 or o > _MAX_ORD:
        raise OverflowError("date out of range")
    return _from_ord(o)


def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("date out of range")
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


# ─── Type / range checking helpers ───────────────────────────────────────────

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _chk_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(v).__name__}")


def _chk_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")


def _chk_year(y):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")


# ─── Public API ──────────────────────────────────────────────────────────────

def is_leap(y):
    _chk_int(y, "y")
    _chk_year(y)
    return _is_leap(y)


def days_in_month(y, m):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_year(y)
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _chk_int(y, "y")
    _chk_int(m, "m")
    _chk_int(d, "d")
    _chk_date_range(y, m, d)
    return _ordinal(y, m, d)


def from_ordinal(n):
    _chk_int(n, "n")
    if n < 1 or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ord(n)


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
    o = _ordinal(y, m, d) + n
    if o < 1 or o > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(o)


def add_months(date, n):
    _chk_date(date, "date")
    _chk_int(n, "n")
    y, m, d = date
    _chk_date_range(y, m, d)
    return _add_months_raw(y, m, d, n)


def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, "iso_year")
    _chk_year(iso_year)
    return _iso_weeks(iso_year)


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
    _chk_year(iso_year)
    nw = _iso_weeks(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    return _from_iso(iso_year, week, weekday)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    def _dig(c):
        return '0' <= c <= '9'

    n = len(s)

    if n == 10:
        if s[4] == '-' and s[7] == '-':
            # Extended calendar YYYY-MM-DD
            for i in (0, 1, 2, 3, 5, 6, 8, 9):
                if not _dig(s[i]):
                    raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4]); m = int(s[5:7]); d = int(s[8:10])
            _chk_year(y)
            if m < 1 or m > 12:
                raise ValueError(f"month {m} out of range 1..12")
            if d < 1 or d > _dim(y, m):
                raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")
            return (y, m, d)
        elif s[4] == '-' and s[5] == 'W':
            # Extended week YYYY-Www-D
            for i in (0, 1, 2, 3, 6, 7, 9):
                if not _dig(s[i]):
                    raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4]); w = int(s[6:8]); wd = int(s[9])
            _chk_year(y)
            nw = _iso_weeks(y)
            if w < 1 or w > nw:
                raise ValueError(f"week {w} out of range 1..{nw}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            try:
                return _from_iso(y, w, wd)
            except OverflowError:
                raise ValueError(f"date out of range: {s!r}")
        else:
            raise ValueError(f"invalid date string: {s!r}")

    elif n == 8:
        if s[4] == '-':
            # Extended ordinal YYYY-DDD
            for i in (0, 1, 2, 3, 5, 6, 7):
                if not _dig(s[i]):
                    raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4]); doy = int(s[5:8])
            _chk_year(y)
            mx = 366 if _is_leap(y) else 365
            if doy < 1 or doy > mx:
                raise ValueError(f"day of year {doy} out of range 1..{mx}")
            return _from_ord(_days_before(y) + doy)
        elif s[4] == 'W':
            # Basic week YYYYWwwD
            for i in (0, 1, 2, 3, 5, 6, 7):
                if not _dig(s[i]):
                    raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4]); w = int(s[5:7]); wd = int(s[7])
            _chk_year(y)
            nw = _iso_weeks(y)
            if w < 1 or w > nw:
                raise ValueError(f"week {w} out of range 1..{nw}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            try:
                return _from_iso(y, w, wd)
            except OverflowError:
                raise ValueError(f"date out of range: {s!r}")
        else:
            # Basic calendar YYYYMMDD
            for i in range(8):
                if not _dig(s[i]):
                    raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4]); m = int(s[4:6]); d = int(s[6:8])
            _chk_year(y)
            if m < 1 or m > 12:
                raise ValueError(f"month {m} out of range 1..12")
            if d < 1 or d > _dim(y, m):
                raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")
            return (y, m, d)

    elif n == 7:
        # Basic ordinal YYYYDDD
        for i in range(7):
            if not _dig(s[i]):
                raise ValueError(f"invalid date string: {s!r}")
        y = int(s[0:4]); doy = int(s[4:7])
        _chk_year(y)
        mx = 366 if _is_leap(y) else 365
        if doy < 1 or doy > mx:
            raise ValueError(f"day of year {doy} out of range 1..{mx}")
        return _from_ord(_days_before(y) + doy)

    else:
        raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _chk_date(date, "date")
    y, m, d = date
    _chk_date_range(y, m, d)

    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _CUM[m - 1] + d
        if m > 2 and _is_leap(y):
            doy += 1
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, iwd = _iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _chk_date(a, "a")
    _chk_date(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _chk_date_range(ay, am, ad)
    _chk_date_range(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a < b
    a_total = (ay - 1) * 12 + (am - 1)
    b_total = (by - 1) * 12 + (bm - 1)
    K = b_total - a_total
    # Check whether shift(a, K) overshoots b's day
    target_d = ad if ad <= _dim(by, bm) else _dim(by, bm)
    if target_d > bd:
        K -= 1
    years, months = divmod(K, 12)
    shifted = _add_months_raw(ay, am, ad, K)
    days = _ordinal(by, bm, bd) - _ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)