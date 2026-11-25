import re

# ---------------------------------------------------------------------------
# Internal helpers (no public API)
# ---------------------------------------------------------------------------

def _check_int(x, name='value'):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date_tuple(date, name='date'):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_raw(y, m):
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if m in (4, 6, 9, 11):
        return 30
    # m == 2
    return 29 if _is_leap_raw(y) else 28


def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim_raw(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m}")


# Cumulative days before each month (index 0 = before Jan, 1 = before Feb, …)
_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP    = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)

_MAX_ORDINAL = 3652059  # ordinal of (9999, 12, 31)


def _to_ordinal_raw(y, m, d):
    """No validation; caller guarantees valid date."""
    yy = y - 1
    days = 365 * yy + yy // 4 - yy // 100 + yy // 400
    cum = _CUM_LEAP if _is_leap_raw(y) else _CUM_NONLEAP
    days += cum[m - 1] + d
    return days


def _from_ordinal_raw(n):
    """No validation; caller guarantees 1 <= n <= _MAX_ORDINAL."""
    n0 = n - 1
    # Estimate year
    y = 1 + n0 // 365
    # Adjust (converges in <= ~7 steps)
    while True:
        yy = y - 1
        d_before = 365 * yy + yy // 4 - yy // 100 + yy // 400
        ylen = 366 if _is_leap_raw(y) else 365
        if d_before > n0:
            y -= 1
        elif d_before + ylen <= n0:
            y += 1
        else:
            break
    yy = y - 1
    d_before = 365 * yy + yy // 4 - yy // 100 + yy // 400
    doy = n0 - d_before  # 1-based day of year
    cum = _CUM_LEAP if _is_leap_raw(y) else _CUM_NONLEAP
    # Binary search for month (at most 4 iterations)
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < doy:
            lo = mid + 1
        else:
            hi = mid
    m = lo
    d = doy - cum[m - 1]
    return (y, m, d)


def _add_months_raw(date, n):
    """No validation; caller guarantees result year in 1..9999."""
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = d if d <= _dim_raw(ty, tm) else _dim_raw(ty, tm)
    return (ty, tm, td)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_leap(y):
    _check_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim_raw(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _to_ordinal_raw(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= _MAX_ORDINAL):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    return _from_ordinal_raw(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (_to_ordinal_raw(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ord_ = _to_ordinal_raw(y, m, d) + n
    if ord_ < 1 or ord_ > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {ord_} out of range 1..{_MAX_ORDINAL}")
    return _from_ordinal_raw(ord_)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError(f"result year {ty} out of range 1..9999")
    td = d if d <= _dim_raw(ty, tm) else _dim_raw(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = (_to_ordinal_raw(iso_year, 1, 1) - 1) % 7  # Mon=0
    if jan1_wd == 3:  # Thursday
        return 53
    if _is_leap_raw(iso_year) and jan1_wd == 2:  # Wednesday in leap year
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ord_ = _to_ordinal_raw(y, m, d)
    wd = (ord_ - 1) % 7  # Mon=0
    iso_weekday = wd + 1  # Mon=1
    mon_ord = ord_ - wd
    thu_ord = mon_ord + 3
    iso_y = _from_ordinal_raw(thu_ord)[0]
    # Monday of ISO week 1 of iso_y
    jan4_ord = _to_ordinal_raw(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1_ord = jan4_ord - jan4_wd
    iso_w = (mon_ord - mon_w1_ord) // 7 + 1
    return (iso_y, iso_w, iso_weekday)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_wk):
        raise ValueError(f"week {week} out of range 1..{max_wk} for ISO year {iso_year}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1_ord = jan4_ord - jan4_wd
    day_ord = mon_w1_ord + (week - 1) * 7 + (weekday - 1)
    if day_ord < 1 or day_ord > _MAX_ORDINAL:
        raise OverflowError(f"result ordinal {day_ord} out of range 1..{_MAX_ORDINAL}")
    return _from_ordinal_raw(day_ord)


# ---------------------------------------------------------------------------
# parse / format_date
# ---------------------------------------------------------------------------

_PARSE_RE = re.compile(
    r'^(?:'
    r'(\d{4})-(\d{2})-(\d{2})'        # 1-3: calendar extended  YYYY-MM-DD
    r'|(\d{4})(\d{2})(\d{2})'         # 4-6: calendar basic     YYYYMMDD
    r'|(\d{4})-(\d{3})'               # 7-8: ordinal extended   YYYY-DDD
    r'|(\d{4})(\d{3})'                # 9-10: ordinal basic     YYYYDDD
    r'|(\d{4})-W(\d{2})-(\d{1})'     # 11-13: week extended    YYYY-Www-D
    r'|(\d{4})W(\d{2})(\d{1})'       # 14-16: week basic       YYYYWwwD
    r')$',
    re.ASCII,
)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")
    mo = _PARSE_RE.match(s)
    if mo is None:
        raise ValueError(f"unrecognized date string: {s!r}")
    g = mo.groups()
    # Determine which form matched
    if g[0] is not None:
        # calendar extended
        y, m, d = int(g[0]), int(g[1]), int(g[2])
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= m <= 12):
            raise ValueError(f"month {m} out of range")
        if not (1 <= d <= _dim_raw(y, m)):
            raise ValueError(f"day {d} out of range for {y}-{m:02d}")
        return (y, m, d)
    elif g[3] is not None:
        # calendar basic
        y, m, d = int(g[3]), int(g[4]), int(g[5])
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= m <= 12):
            raise ValueError(f"month {m} out of range")
        if not (1 <= d <= _dim_raw(y, m)):
            raise ValueError(f"day {d} out of range for {y}-{m:02d}")
        return (y, m, d)
    elif g[6] is not None:
        # ordinal extended
        y, doy = int(g[6]), int(g[7])
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap_raw(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ordinal_raw(_to_ordinal_raw(y, 1, 1) + doy - 1)
    elif g[8] is not None:
        # ordinal basic
        y, doy = int(g[8]), int(g[9])
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap_raw(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ordinal_raw(_to_ordinal_raw(y, 1, 1) + doy - 1)
    elif g[10] is not None:
        # week extended
        y, wk, wd = int(g[10]), int(g[11]), int(g[12])
        if not (1 <= y <= 9999):
            raise ValueError(f"iso_year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk} for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_ord = _to_ordinal_raw(y, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        mon_w1_ord = jan4_ord - jan4_wd
        day_ord = mon_w1_ord + (wk - 1) * 7 + (wd - 1)
        if day_ord < 1 or day_ord > _MAX_ORDINAL:
            raise ValueError(f"week date out of supported range")
        return _from_ordinal_raw(day_ord)
    else:
        # week basic
        y, wk, wd = int(g[13]), int(g[14]), int(g[15])
        if not (1 <= y <= 9999):
            raise ValueError(f"iso_year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk} for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_ord = _to_ordinal_raw(y, 1, 4)
        jan4_wd = (jan4_ord - 1) % 7
        mon_w1_ord = jan4_ord - jan4_wd
        day_ord = mon_w1_ord + (wk - 1) * 7 + (wd - 1)
        if day_ord < 1 or day_ord > _MAX_ORDINAL:
            raise ValueError(f"week date out of supported range")
        return _from_ordinal_raw(day_ord)


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if not (type(form) is str and form in ('calendar', 'ordinal', 'week')):
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal_raw(y, m, d) - _to_ordinal_raw(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:  # 'week'
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    ord_a = _to_ordinal_raw(ay, am, ad)
    ord_b = _to_ordinal_raw(by, bm, bd)

    if ord_a == ord_b:
        return (0, 0, 0)

    if ord_a < ord_b:
        # a <= b: find largest K >= 0 with shift(a, K) <= b
        K0 = (by - ay) * 12 + (bm - am)
        shifted = _add_months_raw(a, K0)
        if _to_ordinal_raw(*shifted) <= ord_b:
            K = K0
        else:
            K = K0 - 1
        years, months = divmod(K, 12)
        shifted_K = _add_months_raw(a, K)
        days = ord_b - _to_ordinal_raw(*shifted_K)
        return (years, months, days)
    else:
        # a > b: negate diff(b, a)
        r = diff(b, a)
        return (-r[0], -r[1], -r[2])
