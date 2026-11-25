import re


# ---------- internal helpers (no public exposure) ----------

def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month_raw(y, m):
    if m == 2:
        return 29 if _is_leap_raw(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _days_before_year(y):
    """Number of days in years 1 through y-1."""
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


def _days_in_year(y):
    return 366 if _is_leap_raw(y) else 365


def _month_offset(y, m):
    """Days from Jan 1 to the first day of month m (0 for January)."""
    feb = 29 if _is_leap_raw(y) else 28
    cum = (0, 31, 31 + feb, 31 + feb + 31, 31 + feb + 31 + 30,
           31 + feb + 31 + 30 + 31, 31 + feb + 31 + 30 + 31 + 30,
           31 + feb + 31 + 30 + 31 + 30 + 31, 31 + feb + 31 + 30 + 31 + 30 + 31 + 31,
           31 + feb + 31 + 30 + 31 + 30 + 31 + 31 + 30,
           31 + feb + 31 + 30 + 31 + 30 + 31 + 31 + 30 + 31,
           31 + feb + 31 + 30 + 31 + 30 + 31 + 31 + 30 + 31 + 30)
    return cum[m - 1]


def _to_ordinal_raw(y, m, d):
    return _days_before_year(y) + _month_offset(y, m) + d - 1


def _from_ordinal_raw(n):
    # Estimate year
    y = (n * 400 - 1) // 146097 + 1
    # Adjust (at most a couple of steps)
    while _days_before_year(y) >= n:
        y -= 1
    while _days_before_year(y) + _days_in_year(y) < n:
        y += 1
    day_of_year = n - _days_before_year(y)
    feb = 29 if _is_leap_raw(y) else 28
    md = (31, feb, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    m = 1
    for days in md:
        if day_of_year <= days:
            break
        day_of_year -= days
        m += 1
    return (y, m, day_of_year)


def _weekday_raw(y, m, d):
    return (_to_ordinal_raw(y, m, d) - 1) % 7


def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = d if d <= _days_in_month_raw(ty, tm) else _days_in_month_raw(ty, tm)
    return (ty, tm, td)


def _iso_weeks_in_year_raw(iso_year):
    wd = _weekday_raw(iso_year, 1, 1)
    if wd == 3:
        return 53
    if wd == 2 and _is_leap_raw(iso_year):
        return 53
    return 52


def _iso_week_raw(y, m, d):
    ord_ = _to_ordinal_raw(y, m, d)
    wd = _weekday_raw(y, m, d)
    iso_wd = wd + 1
    monday_ord = ord_ - wd
    thursday_ord = monday_ord + 3
    iso_y, _, _ = _from_ordinal_raw(thursday_ord)
    jan4_ord = _to_ordinal_raw(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_week1_ord = jan4_ord - jan4_wd
    week = (monday_ord - monday_week1_ord) // 7 + 1
    return (iso_y, week, iso_wd)


# ---------- type / range validation helpers ----------

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(v).__name__}")


def _check_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _days_in_month_raw(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m:02d}")


# ---------- public API ----------

def is_leap(y):
    _check_int(y, "y")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _days_in_month_raw(y, m)


def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid_date(y, m, d)
    return _to_ordinal_raw(y, m, d)


def from_ordinal(n):
    _check_int(n, "n")
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ordinal_raw(n)


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid_date(y, m, d)
    return _weekday_raw(y, m, d)


def add_days(date, n):
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_valid_date(y, m, d)
    target = _to_ordinal_raw(y, m, d) + n
    if target < 1 or target > 3652059:
        raise OverflowError(f"result ordinal {target} out of range 1..3652059")
    return _from_ordinal_raw(target)


def add_months(date, n):
    _check_date(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total > 9999 * 12 - 1:
        raise OverflowError("result month out of range 1..9999")
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = d if d <= _days_in_month_raw(ty, tm) else _days_in_month_raw(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year_raw(iso_year)


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_valid_date(y, m, d)
    return _iso_week_raw(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = _iso_weeks_in_year_raw(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week} for ISO year {iso_year}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_week1_ord = jan4_ord - jan4_wd
    target_ord = monday_week1_ord + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError(f"result ordinal {target_ord} out of range 1..3652059")
    return _from_ordinal_raw(target_ord)


# ---------- parse ----------

_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_BAS_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    ln = len(s)

    if ln == 10:
        m = _RE_EXT_CAL.fullmatch(s)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range 1..9999")
            if not (1 <= mo <= 12):
                raise ValueError(f"month {mo} out of range 1..12")
            dim = _days_in_month_raw(y, mo)
            if not (1 <= d <= dim):
                raise ValueError(f"day {d} out of range 1..{dim}")
            return (y, mo, d)
        m = _RE_EXT_WK.fullmatch(s)
        if m:
            y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range 1..9999")
            max_wk = _iso_weeks_in_year_raw(y)
            if not (1 <= wk <= max_wk):
                raise ValueError(f"week {wk} out of range 1..{max_wk} for ISO year {y}")
            if not (1 <= wd <= 7):
                raise ValueError(f"weekday {wd} out of range 1..7")
            jan4_ord = _to_ordinal_raw(y, 1, 4)
            jan4_wd = (jan4_ord - 1) % 7
            monday_w1 = jan4_ord - jan4_wd
            target = monday_w1 + (wk - 1) * 7 + (wd - 1)
            if target < 1 or target > 3652059:
                raise ValueError(f"week date resolves outside supported range")
            return _from_ordinal_raw(target)
        raise ValueError(f"unrecognized date format: {s!r}")

    elif ln == 8:
        m = _RE_EXT_ORD.fullmatch(s)
        if m:
            y, doy = int(m.group(1)), int(m.group(2))
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range 1..9999")
            max_doy = _days_in_year(y)
            if not (1 <= doy <= max_doy):
                raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
            return _from_ordinal_raw(_days_before_year(y) + doy)
        m = _RE_BAS_WK.fullmatch(s)
        if m:
            y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range 1..9999")
            max_wk = _iso_weeks_in_year_raw(y)
            if not (1 <= wk <= max_wk):
                raise ValueError(f"week {wk} out of range 1..{max_wk} for ISO year {y}")
            if not (1 <= wd <= 7):
                raise ValueError(f"weekday {wd} out of range 1..7")
            jan4_ord = _to_ordinal_raw(y, 1, 4)
            jan4_wd = (jan4_ord - 1) % 7
            monday_w1 = jan4_ord - jan4_wd
            target = monday_w1 + (wk - 1) * 7 + (wd - 1)
            if target < 1 or target > 3652059:
                raise ValueError(f"week date resolves outside supported range")
            return _from_ordinal_raw(target)
        m = _RE_BAS_CAL.fullmatch(s)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range 1..9999")
            if not (1 <= mo <= 12):
                raise ValueError(f"month {mo} out of range 1..12")
            dim = _days_in_month_raw(y, mo)
            if not (1 <= d <= dim):
                raise ValueError(f"day {d} out of range 1..{dim}")
            return (y, mo, d)
        raise ValueError(f"unrecognized date format: {s!r}")

    elif ln == 7:
        m = _RE_BAS_ORD.fullmatch(s)
        if m:
            y, doy = int(m.group(1)), int(m.group(2))
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range 1..9999")
            max_doy = _days_in_year(y)
            if not (1 <= doy <= max_doy):
                raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
            return _from_ordinal_raw(_days_before_year(y) + doy)
        raise ValueError(f"unrecognized date format: {s!r}")

    else:
        raise ValueError(f"unrecognized date format: {s!r}")


# ---------- format_date ----------

def format_date(date, form):
    _check_date(date, "date")
    y, m, d = date
    _check_valid_date(y, m, d)

    if form != 'calendar' and form != 'ordinal' and form != 'week':
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week', got {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal_raw(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iso_y, wk, wd = _iso_week_raw(y, m, d)
        return f"{iso_y:04d}-W{wk:02d}-{wd}"


# ---------- diff ----------

def diff(a, b):
    _check_date(a, "a")
    _check_date(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    if a <= b:
        # Find largest K >= 0 with add_months(a, K) <= b
        lo = 0
        hi = (by - ay) * 12 + (bm - am) + 12
        while lo < hi:
            mid = (lo + hi + 1) // 2
            shifted = _add_months_raw(ay, am, ad, mid)
            if shifted <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _add_months_raw(ay, am, ad, K)
        days = _to_ordinal_raw(by, bm, bd) - _to_ordinal_raw(shifted[0], shifted[1], shifted[2])
        return (years, months, days)
    else:
        r = diff(b, a)
        return (-r[0], -r[1], -r[2])
