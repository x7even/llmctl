import re


# ─── internal helpers ────────────────────────────────────────────────────────

def _is_int(x):
    return type(x) is int


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date_tuple(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i, x in enumerate(date):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(x).__name__}")


def _dim_raw(y, m):
    """days in month, no validation"""
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _validate_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim_raw(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y:04d}-{m:02d}")


def _db_year(y):
    """days in years 1..y-1"""
    y -= 1
    return 365 * y + y // 4 - y // 100 + y // 400


def _di_year(y):
    return 366 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 365


_CUM_NL = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_L = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)


def _db_month(y, m):
    """days before month m (1-indexed) in year y"""
    cum = _CUM_L if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else _CUM_NL
    return cum[m - 1]


def _year_from_0idx(a):
    """find year for 0-indexed day count a (a=0 → Jan 1 year 1)"""
    y = 1 + a // 365
    while _db_year(y + 1) <= a:
        y += 1
    while _db_year(y) > a:
        y -= 1
    return y


def _shift_months(date, k):
    """add_months logic without overflow check; returns None if year out of range"""
    total = (date[0] - 1) * 12 + (date[1] - 1) + k
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        return None
    td = min(date[2], _dim_raw(ty, tm))
    return (ty, tm, td)


# ─── public API ──────────────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y, "y")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim_raw(y, m)


def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate_date(y, m, d)
    return _db_year(y) + _db_month(y, m) + d


def from_ordinal(n):
    _check_int(n, "n")
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    a = n - 1
    y = _year_from_0idx(a)
    doy = a - _db_year(y)  # 0-indexed day of year
    cum = _CUM_L if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else _CUM_NL
    m = 1
    while m <= 12 and doy >= cum[m]:
        m += 1
    d = doy - cum[m - 1] + 1
    return (y, m, d)


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _validate_date(y, m, d)
    ord_ = to_ordinal(y, m, d) + n
    if ord_ < 1 or ord_ > 3652059:
        raise OverflowError(f"result ordinal {ord_} out of range 1..3652059")
    return from_ordinal(ord_)


def add_months(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _validate_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError(f"target year {ty} out of range 1..9999")
    td = min(d, _dim_raw(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = weekday(iso_year, 1, 1)  # 0=Mon..6=Sun
    if wd == 3:  # Thursday
        return 53
    if wd == 2 and is_leap(iso_year):  # Wednesday in leap year
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _validate_date(y, m, d)
    wd = weekday(y, m, d)  # 0=Mon..6=Sun
    iso_wd = wd + 1  # 1=Mon..7=Sun
    ord_ = to_ordinal(y, m, d)
    mon_ord = ord_ - wd  # Monday of this week
    thu_ord = mon_ord + 3  # Thursday of this week
    iso_year = from_ordinal(thu_ord)[0]
    # Monday of week 1 of iso_year:
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = weekday(iso_year, 1, 4)
    mon_w1_ord = jan4_ord - jan4_wd
    iso_wk = (mon_ord - mon_w1_ord) // 7 + 1
    return (iso_year, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday_):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday_, "weekday")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_wk):
        raise ValueError(f"week {week} out of range 1..{max_wk} for ISO year {iso_year}")
    if not (1 <= weekday_ <= 7):
        raise ValueError(f"weekday {weekday_} out of range 1..7")
    # Monday of week 1
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = weekday(iso_year, 1, 4)
    mon_w1_ord = jan4_ord - jan4_wd
    target_ord = mon_w1_ord + (week - 1) * 7 + (weekday_ - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError(f"result ordinal {target_ord} out of range 1..3652059")
    return from_ordinal(target_ord)


# ─── parse ───────────────────────────────────────────────────────────────────

_RE_CAL_EXT = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_CAL_BASIC = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_ORD_EXT = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_ORD_BASIC = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_WK_EXT = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_WK_BASIC = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    # Try each form
    m = _RE_CAL_EXT.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range 1..12")
        dim = _dim_raw(y, mo)
        if d < 1 or d > dim:
            raise ValueError(f"day {d} out of range 1..{dim}")
        return (y, mo, d)

    m = _RE_ORD_EXT.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = _di_year(y)
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_db_year(y) + doy)

    m = _RE_WK_EXT.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"iso_year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date {s} out of supported range")

    m = _RE_CAL_BASIC.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range 1..12")
        dim = _dim_raw(y, mo)
        if d < 1 or d > dim:
            raise ValueError(f"day {d} out of range 1..{dim}")
        return (y, mo, d)

    m = _RE_ORD_BASIC.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = _di_year(y)
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_db_year(y) + doy)

    m = _RE_WK_BASIC.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"iso_year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date {s} out of supported range")

    raise ValueError(f"unrecognized date format: {s!r}")


# ─── format_date ─────────────────────────────────────────────────────────────

def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _validate_date(y, m, d)

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _db_year(y)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"
    else:
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week', got {form!r}")


# ─── diff ────────────────────────────────────────────────────────────────────

def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _validate_date(ay, am, ad)
    _validate_date(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    K = (by - ay) * 12 + (bm - am)
    if K < 0:
        K = 0
    # try increasing
    while True:
        s = _shift_months(a, K + 1)
        if s is not None and s <= b:
            K += 1
        else:
            break
    # try decreasing (estimate may be too high)
    while K > 0:
        s = _shift_months(a, K)
        if s is None or s > b:
            K -= 1
        else:
            break

    years, months = divmod(K, 12)
    shifted = _shift_months(a, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(*shifted)
    return (years, months, days)
