import re


# ─── internal helpers ────────────────────────────────────────────────────────

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _check_date_type(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(date[i]).__name__}")


def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month_raw(y, m):
    if m == 2:
        return 29 if _is_leap_raw(y) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30


def _days_before_year(y):
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


_CUM = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def _days_before_month(y, m):
    r = _CUM[m - 1]
    if m > 2 and _is_leap_raw(y):
        r += 1
    return r


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _days_in_month_raw(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


def _to_ordinal_raw(y, m, d):
    return _days_before_year(y) + _days_before_month(y, m) + d


def _from_ordinal_raw(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) <= n - 1:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    rem = n - 1 - _days_before_year(y)
    m = 1
    while m <= 12:
        dim = _days_in_month_raw(y, m)
        if rem < dim:
            break
        rem -= dim
        m += 1
    d = rem + 1
    return (y, m, d)


def _iso_weeks_in_year_raw(y):
    jan1_wd = (_to_ordinal_raw(y, 1, 1) - 1) % 7
    if jan1_wd == 3 or (_is_leap_raw(y) and jan1_wd == 2):
        return 53
    return 52


def _iso_week_raw(y, m, d):
    ord_val = _to_ordinal_raw(y, m, d)
    wd = (ord_val - 1) % 7
    iso_weekday = wd + 1
    thu_ord = ord_val + (3 - wd)
    iso_year = _from_ordinal_raw(thu_ord)[0]
    jan4_ord = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_monday = jan4_ord - jan4_wd
    iso_week_num = (ord_val - first_monday) // 7 + 1
    return (iso_year, iso_week_num, iso_weekday)


def _add_months_raw(y, m, d, n):
    """Return (ty, tm, td) or None if out of year range."""
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total >= 9999 * 12:
        return None
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = min(d, _days_in_month_raw(ty, tm))
    return (ty, tm, td)


def _diff_positive(earlier, later):
    """earlier <= later by ordinal. Returns (years, months, days)."""
    ey, em, ed = earlier
    ly, lm, ld = later
    l_ord = _to_ordinal_raw(ly, lm, ld)
    hi = (ly - ey) * 12 + 12
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        r = _add_months_raw(ey, em, ed, mid)
        if r is None or _to_ordinal_raw(r[0], r[1], r[2]) > l_ord:
            hi = mid - 1
        else:
            lo = mid
    K = lo
    years, months = divmod(K, 12)
    r = _add_months_raw(ey, em, ed, K)
    days = l_ord - _to_ordinal_raw(r[0], r[1], r[2])
    return (years, months, days)


# ─── public API ──────────────────────────────────────────────────────────────

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
    return _days_in_month_raw(y, m)


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
    return (_to_ordinal_raw(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_type(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ord_val = _to_ordinal_raw(y, m, d) + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError(f"result ordinal {ord_val} out of range 1..3652059")
    return _from_ordinal_raw(ord_val)


def add_months(date, n):
    _check_date_type(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    r = _add_months_raw(y, m, d, n)
    if r is None:
        raise OverflowError("result year out of range 1..9999")
    return r


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
    max_w = _iso_weeks_in_year_raw(iso_year)
    if week < 1 or week > max_w:
        raise ValueError(f"week {week} out of range 1..{max_w} for ISO year {iso_year}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    first_monday = jan4_ord - jan4_wd
    target = first_monday + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError(f"result ordinal {target} out of range 1..3652059")
    return _from_ordinal_raw(target)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    L = len(s)

    if L == 10:
        m = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
        if m:
            y = int(m.group(1))
            mo = int(m.group(2))
            d = int(m.group(3))
            if y < 1:
                raise ValueError("year 0000 is not valid")
            if mo < 1 or mo > 12:
                raise ValueError(f"month {mo:02d} out of range")
            if d < 1 or d > _days_in_month_raw(y, mo):
                raise ValueError(f"day {d:02d} out of range for {y:04d}-{mo:02d}")
            return (y, mo, d)
        raise ValueError(f"invalid date string: {s!r}")

    elif L == 9:
        m = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
        if m:
            y = int(m.group(1))
            w = int(m.group(2))
            wd = int(m.group(3))
            if y < 1:
                raise ValueError("year 0000 is not valid")
            max_w = _iso_weeks_in_year_raw(y)
            if w < 1 or w > max_w:
                raise ValueError(f"week {w:02d} out of range 1..{max_w} for ISO year {y}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            jan4_ord = _to_ordinal_raw(y, 1, 4)
            jan4_wd = (jan4_ord - 1) % 7
            first_monday = jan4_ord - jan4_wd
            target = first_monday + (w - 1) * 7 + (wd - 1)
            if target < 1 or target > 3652059:
                raise ValueError(f"week date out of supported range")
            return _from_ordinal_raw(target)
        raise ValueError(f"invalid date string: {s!r}")

    elif L == 8:
        # YYYY-DDD (ordinal extended)
        m = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
        if m:
            y = int(m.group(1))
            doy = int(m.group(2))
            if y < 1:
                raise ValueError("year 0000 is not valid")
            max_doy = 366 if _is_leap_raw(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError(f"day of year {doy:03d} out of range 1..{max_doy}")
            rem = doy
            mo = 1
            while mo <= 12:
                dim = _days_in_month_raw(y, mo)
                if rem <= dim:
                    return (y, mo, rem)
                rem -= dim
                mo += 1
            raise ValueError("internal error")

        # YYYYWwwD (week basic)
        m = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
        if m:
            y = int(m.group(1))
            w = int(m.group(2))
            wd = int(m.group(3))
            if y < 1:
                raise ValueError("year 0000 is not valid")
            max_w = _iso_weeks_in_year_raw(y)
            if w < 1 or w > max_w:
                raise ValueError(f"week {w:02d} out of range 1..{max_w} for ISO year {y}")
            if wd < 1 or wd > 7:
                raise ValueError(f"weekday {wd} out of range 1..7")
            jan4_ord = _to_ordinal_raw(y, 1, 4)
            jan4_wd = (jan4_ord - 1) % 7
            first_monday = jan4_ord - jan4_wd
            target = first_monday + (w - 1) * 7 + (wd - 1)
            if target < 1 or target > 3652059:
                raise ValueError(f"week date out of supported range")
            return _from_ordinal_raw(target)

        # YYYYMMDD (calendar basic)
        m = re.fullmatch(r'([0-9]{4})([0-9]{2})([0-9]{2})', s)
        if m:
            y = int(m.group(1))
            mo = int(m.group(2))
            d = int(m.group(3))
            if y < 1:
                raise ValueError("year 0000 is not valid")
            if mo < 1 or mo > 12:
                raise ValueError(f"month {mo:02d} out of range")
            if d < 1 or d > _days_in_month_raw(y, mo):
                raise ValueError(f"day {d:02d} out of range for {y:04d}-{mo:02d}")
            return (y, mo, d)

        raise ValueError(f"invalid date string: {s!r}")

    elif L == 7:
        # YYYYDDD (ordinal basic)
        m = re.fullmatch(r'([0-9]{4})([0-9]{3})', s)
        if m:
            y = int(m.group(1))
            doy = int(m.group(2))
            if y < 1:
                raise ValueError("year 0000 is not valid")
            max_doy = 366 if _is_leap_raw(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError(f"day of year {doy:03d} out of range 1..{max_doy}")
            rem = doy
            mo = 1
            while mo <= 12:
                dim = _days_in_month_raw(y, mo)
                if rem <= dim:
                    return (y, mo, rem)
                rem -= dim
                mo += 1
            raise ValueError("internal error")
        raise ValueError(f"invalid date string: {s!r}")

    else:
        raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_type(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)

    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'; got {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_wd = _iso_week_raw(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date_type(a, 'a')
    _check_date_type(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    a_ord = _to_ordinal_raw(ay, am, ad)
    b_ord = _to_ordinal_raw(by, bm, bd)

    if a_ord <= b_ord:
        return _diff_positive(a, b)
    else:
        y, mo, d = _diff_positive(b, a)
        return (-y, -mo, -d)
