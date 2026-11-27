import re


def _is_int(x):
    return type(x) is int


def _check_int(x, name):
    if not _is_int(x):
        raise TypeError(f"{name} must be int")


def _check_date_tuple(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for v in date:
        if type(v) is not int:
            raise TypeError(f"{name} elements must be ints")


def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_before_year(y):
    y1 = y - 1
    return 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400


def _days_before_month(y, m):
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    if m > 2 and _is_leap(y):
        return cum[m - 1] + 1
    return cum[m - 1]


def is_leap(y):
    _check_int(y, "y")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    _check_int(n, "n")
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    m = 1
    while m <= 12:
        dm = _dim(y, m)
        if doy <= dm:
            break
        doy -= dm
        m += 1
    return (y, m, doy)


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(ord_val)


def add_months(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    total_months = (y - 1) * 12 + (m - 1) + n
    ty = total_months // 12 + 1
    tm = total_months % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError("result out of range")
    td = min(d, _dim(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = _days_before_year(iso_year) % 7
    if jan1_wd == 3:
        return 53
    if _is_leap(iso_year) and jan1_wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    monday_of_week = ord_val - wd
    jan4_ord = _days_before_year(y) + 4
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    week = (monday_of_week - monday_w1) // 7 + 1
    if week < 1:
        iso_y = y - 1
        week = iso_weeks_in_year(iso_y)
    elif week > iso_weeks_in_year(y):
        iso_y = y + 1
        week = 1
    else:
        iso_y = y
    return (iso_y, week, wd + 1)


def from_iso_week(iso_year, week, weekday_val):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday_val, "weekday")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    n_weeks = iso_weeks_in_year(iso_year)
    if not (1 <= week <= n_weeks):
        raise ValueError(f"week {week} out of range 1..{n_weeks}")
    if not (1 <= weekday_val <= 7):
        raise ValueError(f"weekday {weekday_val} out of range 1..7")
    jan4_ord = _days_before_year(iso_year) + 4
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target_ord = monday_w1 + (week - 1) * 7 + (weekday_val - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target_ord)


_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BAS_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        n_weeks = iso_weeks_in_year(y)
        if not (1 <= wk <= n_weeks):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    m = _RE_BAS_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_BAS_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        n_weeks = iso_weeks_in_year(y)
        if not (1 <= wk <= n_weeks):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_BAS_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(_days_before_year(y) + doy)

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_d = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_d:01d}"


def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if a > b:
        y, mo, d = diff(b, a)
        return (-y, -mo, -d)

    def _shift(ay, am, ad, K):
        total_months = (ay - 1) * 12 + (am - 1) + K
        ty = total_months // 12 + 1
        tm = total_months % 12 + 1
        if 1 <= ty <= 9999:
            td = min(ad, _dim(ty, tm))
        else:
            td = 31
        return (ty, tm, td)

    lo, hi = 0, (by - ay) * 12 + (bm - am) + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift(ay, am, ad, mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _shift(ay, am, ad, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)