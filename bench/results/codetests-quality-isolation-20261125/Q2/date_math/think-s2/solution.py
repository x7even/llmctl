import re

_MDAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MDAYS_CUM = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORDINAL = 3652059


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    return _MDAYS[m]


def _days_before_year(y):
    yy = y - 1
    return yy * 365 + yy // 4 - yy // 100 + yy // 400


def _to_ordinal(y, m, d):
    return _days_before_year(y) + _MDAYS_CUM[m] + (1 if m > 2 and _is_leap(y) else 0) + d


def _from_ordinal(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        if _days_before_year(mid + 1) < n:
            lo = mid + 1
        else:
            hi = mid
    y = lo
    doy = n - _days_before_year(y)
    if _is_leap(y):
        cum = (0, 0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
    else:
        cum = (0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    lo2, hi2 = 1, 12
    while lo2 < hi2:
        mid2 = (lo2 + hi2) // 2
        if cum[mid2 + 1] < doy:
            lo2 = mid2 + 1
        else:
            hi2 = mid2
    m = lo2
    d = doy - cum[m]
    return (y, m, d)


def _weekday(y, m, d):
    return (_to_ordinal(y, m, d) - 1) % 7


def _iso_weeks_in_year(iso_y):
    wd = _weekday(iso_y, 1, 1)
    if wd == 3:
        return 53
    if _is_leap(iso_y) and wd == 2:
        return 53
    return 52


def _iso_week(y, m, d):
    ord_ = _to_ordinal(y, m, d)
    wd = (ord_ - 1) % 7
    thu_ord = ord_ + (3 - wd)
    iso_y = _from_ordinal(thu_ord)[0]
    jan4_ord = _to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    mon_cur = ord_ - wd
    week = (mon_cur - mon_w1) // 7 + 1
    iso_wd = wd + 1
    return (iso_y, week, iso_wd)


def _from_iso_week(iso_y, week, iso_wd):
    jan4_ord = _to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target_ord = mon_w1 + (week - 1) * 7 + (iso_wd - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return _from_ordinal(target_ord)


def _add_months_internal(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        return None
    nd = min(d, _days_in_month(ny, nm))
    return (ny, nm, nd)


# --- checking helpers ---

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date_tuple(date, name="date"):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, x in enumerate(date):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(x).__name__}")


def _check_date_range(date):
    y, m, d = date
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y:04d}-{m:02d}")


# --- public API ---

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
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range((y, m, d))
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    _check_int(n, "n")
    if not (1 <= n <= _MAX_ORDINAL):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    return _from_ordinal(n)


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range((y, m, d))
    return _weekday(y, m, d)


def add_days(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    _check_date_range(date)
    ord_ = _to_ordinal(date[0], date[1], date[2]) + n
    if ord_ < 1 or ord_ > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return _from_ordinal(ord_)


def add_months(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    _check_date_range(date)
    result = _add_months_internal(date[0], date[1], date[2], n)
    if result is None:
        raise OverflowError("result out of range")
    return result


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range((y, m, d))
    return _iso_week(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = _iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    return _from_iso_week(iso_year, week, weekday)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    # Extended calendar: YYYY-MM-DD
    m = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _days_in_month(y, mo)):
            raise ValueError(f"day {d} out of range for {y:04d}-{mo:02d}")
        return (y, mo, d)

    # Extended week: YYYY-Www-D
    m = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= w <= _iso_weeks_in_year(y)):
            raise ValueError(f"week {w} out of range for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return _from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError("date out of range")

    # Extended ordinal: YYYY-DDD
    m = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ordinal(_to_ordinal(y, 1, 1) + doy - 1)

    # Basic week: YYYYWwwD
    m = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= w <= _iso_weeks_in_year(y)):
            raise ValueError(f"week {w} out of range for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return _from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError("date out of range")

    # Basic calendar: YYYYMMDD (try first among 8-digit all-digit strings)
    m = re.fullmatch(r'([0-9]{4})([0-9]{2})([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= y <= 9999 and 1 <= mo <= 12 and 1 <= d <= _days_in_month(y, mo):
            return (y, mo, d)
        # fall through to try as ordinal

    # Basic ordinal: YYYYDDD
    m = re.fullmatch(r'([0-9]{4})([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _from_ordinal(_to_ordinal(y, 1, 1) + doy - 1)

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, "date")
    _check_date_range(date)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")
    y, m, d = date
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_wd = _iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    _check_date_range(a)
    _check_date_range(b)

    if a == b:
        return (0, 0, 0)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a < b: find largest K >= 0 with add_months(a, K) <= b
    lo, hi = 0, (b[0] - a[0]) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        shifted = _add_months_internal(a[0], a[1], a[2], mid)
        if shifted is not None and shifted <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_internal(a[0], a[1], a[2], K)
    days = _to_ordinal(b[0], b[1], b[2]) - _to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)