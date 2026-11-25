import re

_MDAYS = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MIN_ORD = 1
_MAX_ORD = 3652059
_MAX_MONTHS = 9999 * 12  # 119988


def _is_int(x):
    return type(x) is int


def _check_date_tuple(date):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a tuple of exactly 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError("date elements must be ints")


def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= days_in_month(y, m)):
        raise ValueError(f"day {d} out of range for month {m} of year {y}")


def _days_before_year(y):
    """Days in years 1..y-1."""
    y -= 1
    return 365 * y + y // 4 - y // 100 + y // 400


def _days_before_month(y, m):
    """Days from Jan 1 to the first day of month m in year y."""
    return _MDAYS[m - 1] + (1 if m > 2 and is_leap(y) else 0)


def is_leap(y):
    if not _is_int(y):
        raise TypeError("y must be an int")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if not _is_int(y):
        raise TypeError("y must be an int")
    if not _is_int(m):
        raise TypeError("m must be an int")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if m == 2:
        return 29 if is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def to_ordinal(y, m, d):
    if not _is_int(y):
        raise TypeError("y must be an int")
    if not _is_int(m):
        raise TypeError("m must be an int")
    if not _is_int(d):
        raise TypeError("d must be an int")
    _check_date_range(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    if not _is_int(n):
        raise TypeError("n must be an int")
    if not (_MIN_ORD <= n <= _MAX_ORD):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    for m in range(1, 13):
        dim = days_in_month(y, m)
        if doy <= dim:
            return (y, m, doy)
        doy -= dim
    raise ValueError("internal error")


def weekday(y, m, d):
    if not _is_int(y):
        raise TypeError("y must be an int")
    if not _is_int(m):
        raise TypeError("m must be an int")
    if not _is_int(d):
        raise TypeError("d must be an int")
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date)
    if not _is_int(n):
        raise TypeError("n must be an int")
    y, m, d = date
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < _MIN_ORD or ord_val > _MAX_ORD:
        raise OverflowError("result out of range 1..9999")
    return from_ordinal(ord_val)


def add_months(date, n):
    _check_date_tuple(date)
    if not _is_int(n):
        raise TypeError("n must be an int")
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total >= _MAX_MONTHS:
        raise OverflowError("result out of range 1..9999")
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    new_d = d if d <= days_in_month(new_y, new_m) else days_in_month(new_y, new_m)
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be an int")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = weekday(iso_year, 1, 1)
    if wd == 3:
        return 53
    if wd == 2 and is_leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    if not _is_int(y):
        raise TypeError("y must be an int")
    if not _is_int(m):
        raise TypeError("m must be an int")
    if not _is_int(d):
        raise TypeError("d must be an int")
    _check_date_range(y, m, d)
    ord_date = to_ordinal(y, m, d)
    ord_jan4 = to_ordinal(y, 1, 4)
    wd_jan4 = weekday(y, 1, 4)
    ord_monday_w1 = ord_jan4 - wd_jan4
    days_since = ord_date - ord_monday_w1
    week = days_since // 7 + 1
    iso_wd = (days_since % 7) + 1
    if week <= 0:
        iso_y = y - 1
        week = iso_weeks_in_year(iso_y) + week
    elif week > iso_weeks_in_year(y):
        iso_y = y + 1
        week = 1
    else:
        iso_y = y
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday_val):
    if not _is_int(iso_year):
        raise TypeError("iso_year must be an int")
    if not _is_int(week):
        raise TypeError("week must be an int")
    if not _is_int(weekday_val):
        raise TypeError("weekday must be an int")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_wk):
        raise ValueError(f"week {week} out of range 1..{max_wk}")
    if not (1 <= weekday_val <= 7):
        raise ValueError(f"weekday {weekday_val} out of range 1..7")
    ord_jan4 = to_ordinal(iso_year, 1, 4)
    wd_jan4 = weekday(iso_year, 1, 4)
    ord_monday_w1 = ord_jan4 - wd_jan4
    ord_target = ord_monday_w1 + (week - 1) * 7 + (weekday_val - 1)
    if ord_target < _MIN_ORD or ord_target > _MAX_ORD:
        raise OverflowError("result out of range 1..9999")
    return from_ordinal(ord_target)


_RE_EXT_CAL = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_BASIC_CAL = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_EXT_ORD = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_BASIC_ORD = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_EXT_WEEK = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_BASIC_WEEK = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')


def _parse_week_date(y, wk, wd):
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= wk <= iso_weeks_in_year(y)):
        raise ValueError("week out of range for given ISO year")
    if not (1 <= wd <= 7):
        raise ValueError("weekday out of range")
    try:
        return from_iso_week(y, wk, wd)
    except OverflowError:
        raise ValueError("date out of supported range")


def _parse_ord_date(y, doy):
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    max_doy = 366 if is_leap(y) else 365
    if not (1 <= doy <= max_doy):
        raise ValueError("day of year out of range")
    return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)


def _parse_cal_date(y, mo, d):
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= mo <= 12):
        raise ValueError("month out of range")
    if not (1 <= d <= days_in_month(y, mo)):
        raise ValueError("day out of range for month")
    return (y, mo, d)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    m = _RE_EXT_CAL.match(s)
    if m:
        return _parse_cal_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _RE_EXT_WEEK.match(s)
    if m:
        return _parse_week_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _RE_EXT_ORD.match(s)
    if m:
        return _parse_ord_date(int(m.group(1)), int(m.group(2)))

    m = _RE_BASIC_CAL.match(s)
    if m:
        return _parse_cal_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _RE_BASIC_WEEK.match(s)
    if m:
        return _parse_week_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _RE_BASIC_ORD.match(s)
    if m:
        return _parse_ord_date(int(m.group(1)), int(m.group(2)))

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_tuple(date)
    y, m, d = date
    _check_date_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_d = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_d}"


def diff(a, b):
    _check_date_tuple(a)
    _check_date_tuple(b)
    ya, ma, da = a
    yb, mb, db = b
    _check_date_range(ya, ma, da)
    _check_date_range(yb, mb, db)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: binary search for largest K >= 0 with add_months(a, K) <= b
    lo, hi = 0, (yb - ya) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            shifted = add_months(a, mid)
        except OverflowError:
            hi = mid - 1
            continue
        if shifted <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = to_ordinal(yb, mb, db) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)