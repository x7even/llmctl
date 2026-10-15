import re


# ─── internal helpers (no type-checking; assume valid ints) ───────────────────

def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_raw(y, m):
    if m == 2:
        return 29 if _is_leap_raw(y) else 28
    return (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[m - 1]


def _days_before_year(y):
    """Total days in years 1 through y-1."""
    t = y - 1
    return t * 365 + t // 4 - t // 100 + t // 400


def _month_days_before(y, m):
    """Total days in months 1 through m-1 of year y."""
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    r = cum[m - 1]
    if m > 2 and _is_leap_raw(y):
        r += 1
    return r


def _to_ordinal_raw(y, m, d):
    return _days_before_year(y) + _month_days_before(y, m) + d


def _weekday_raw(y, m, d):
    return (_to_ordinal_raw(y, m, d) - 1) % 7


def _from_ordinal_raw(n):
    # Find year: need t = y-1 such that f(t) < n <= f(t+1)
    # f(t) = t*365 + t//4 - t//100 + t//400
    t = (n - 1) // 365
    # decrease t while f(t) >= n
    while t > 0:
        ft = t * 365 + t // 4 - t // 100 + t // 400
        if ft < n:
            break
        t -= 1
    # increase t while f(t+1) < n
    while True:
        ft1 = (t + 1) * 365 + (t + 1) // 4 - (t + 1) // 100 + (t + 1) // 400
        if ft1 >= n:
            break
        t += 1
    y = t + 1
    doy = n - _days_before_year(y)
    # Find month and day
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    if _is_leap_raw(y):
        cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
    m = 1
    while m <= 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def _iso_weeks_in_year_raw(y):
    wd = _weekday_raw(y, 1, 1)  # Mon=0
    if wd == 3:  # Thursday
        return 53
    if wd == 2 and _is_leap_raw(y):  # Wednesday in leap year
        return 53
    return 52


def _iso_week_raw(y, m, d):
    ord_ = _to_ordinal_raw(y, m, d)
    wd_iso = _weekday_raw(y, m, d) + 1  # Mon=1..Sun=7
    # Thursday of this week
    thu_ord = ord_ + (4 - wd_iso)
    thu_date = _from_ordinal_raw(thu_ord)
    iso_year = thu_date[0]
    # Monday of week 1 of iso_year
    jan4_ord = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = _weekday_raw(iso_year, 1, 4)  # Mon=0
    mon_w1_ord = jan4_ord - jan4_wd
    week = (ord_ - mon_w1_ord) // 7 + 1
    return (iso_year, week, wd_iso)


def _from_iso_week_raw(iso_year, week, weekday):
    jan4_ord = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = _weekday_raw(iso_year, 1, 4)
    mon_w1_ord = jan4_ord - jan4_wd
    target_ord = mon_w1_ord + (week - 1) * 7 + (weekday - 1)
    return _from_ordinal_raw(target_ord)


# ─── type / range checking helpers ────────────────────────────────────────────

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _check_date_tuple(date, name):
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
    dim = _dim_raw(y, m)
    if d < 1 or d > dim:
        raise ValueError(f"day {d} out of range 1..{dim}")


# ─── regex patterns for parse ─────────────────────────────────────────────────

_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BASIC_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BASIC_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WEEK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BASIC_WEEK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


# ─── public API ───────────────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
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
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ordinal_raw(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _weekday_raw(y, m, d)


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ord_ = _to_ordinal_raw(y, m, d) + n
    if ord_ < 1 or ord_ > 3652059:
        raise OverflowError("result out of range 1..9999")
    return _from_ordinal_raw(ord_)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total >= 9999 * 12:
        raise OverflowError("result out of range 1..9999")
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = min(d, _dim_raw(ny, nm))
    return (ny, nm, nd)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year_raw(iso_year)


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _iso_week_raw(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = _iso_weeks_in_year_raw(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw} for ISO year {iso_year}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = _weekday_raw(iso_year, 1, 4)
    mon_w1_ord = jan4_ord - jan4_wd
    target_ord = mon_w1_ord + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError("result out of range 1..9999")
    return _from_ordinal_raw(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date_range(y, mo, d)
        return (y, mo, d)

    m = _RE_BASIC_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date_range(y, mo, d)
        return (y, mo, d)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ordinal_raw(_to_ordinal_raw(y, 1, 1) + doy - 1)

    m = _RE_BASIC_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ordinal_raw(_to_ordinal_raw(y, 1, 1) + doy - 1)

    m = _RE_EXT_WEEK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        nw = _iso_weeks_in_year_raw(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw} for ISO year {y}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_ord = _to_ordinal_raw(y, 1, 4)
        jan4_wd = _weekday_raw(y, 1, 4)
        mon_w1_ord = jan4_ord - jan4_wd
        target_ord = mon_w1_ord + (wk - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError("week date out of range")
        return _from_ordinal_raw(target_ord)

    m = _RE_BASIC_WEEK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        nw = _iso_weeks_in_year_raw(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw} for ISO year {y}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_ord = _to_ordinal_raw(y, 1, 4)
        jan4_wd = _weekday_raw(y, 1, 4)
        mon_w1_ord = jan4_ord - jan4_wd
        target_ord = mon_w1_ord + (wk - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError("week date out of range")
        return _from_ordinal_raw(target_ord)

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _month_days_before(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iso_y, iso_w, iso_wd = _iso_week_raw(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    a_ord = _to_ordinal_raw(ay, am, ad)
    b_ord = _to_ordinal_raw(by, bm, bd)

    if a_ord > b_ord:
        years, months, days = _diff_nonneg(by, bm, bd, ay, am, ad, b_ord, a_ord)
        return (-years, -months, -days)
    else:
        return _diff_nonneg(ay, am, ad, by, bm, bd, a_ord, b_ord)


def _diff_nonneg(ay, am, ad, by, bm, bd, a_ord, b_ord):
    """Compute diff for a <= b (ordinal order)."""
    K_est = (by - ay) * 12 + (bm - am)
    if K_est < 0:
        K_est = 0
    # add_months(a, K_est) lands in month bm of year by
    target_day = min(ad, _dim_raw(by, bm))
    if target_day <= bd:
        K = K_est
    else:
        K = K_est - 1
    # K >= 0 guaranteed
    years, months = divmod(K, 12)
    # Compute shifted date: add_months(a, K)
    shifted_mi = (ay - 1) * 12 + (am - 1) + K
    shifted_y = shifted_mi // 12 + 1
    shifted_m = shifted_mi % 12 + 1
    shifted_d = min(ad, _dim_raw(shifted_y, shifted_m))
    days = b_ord - _to_ordinal_raw(shifted_y, shifted_m, shifted_d)
    return (years, months, days)
