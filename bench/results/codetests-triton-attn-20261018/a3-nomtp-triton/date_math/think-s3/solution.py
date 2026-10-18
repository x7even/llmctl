import re

# --- Internal constants ---
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_MAX_ORD = 3652059  # to_ordinal(9999, 12, 31)

# --- Regex patterns for parse ---
_RE_EXT_CAL   = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BASIC_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD   = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BASIC_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WEEK  = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BASIC_WEEK= re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


# --- Internal helpers (no public type/range checking) ---

def _days_before_year(y):
    """Days from year 1 through year y-1 (i.e. before Jan 1 of year y)."""
    y1 = y - 1
    return y1 * 365 + y1 // 4 - y1 // 100 + y1 // 400


def _days_before_month(y, m):
    """Days in months 1..m-1 of year y."""
    total = _CUM[m - 1]
    if m > 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        total += 1
    return total


def _from_day_of_year(y, doy):
    """Convert day-of-year (1-based) to (y, m, d)."""
    for m in range(1, 13):
        if doy <= _days_before_month(y, m) + _MONTH_DAYS[m - 1] + (1 if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 0):
            break
    d = doy - _days_before_month(y, m)
    return (y, m, d)


def _check_date_tuple(date):
    if not isinstance(date, tuple) or len(date) != 3:
        raise TypeError("date must be a tuple of exactly 3 ints")
    for v in date:
        if type(v) is not int:
            raise TypeError("date elements must be int")


def _check_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    dim = _MONTH_DAYS[m - 1]
    if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        dim = 29
    if not (1 <= d <= dim):
        raise ValueError("day out of range for given month")


# --- Public API ---

def is_leap(y):
    if type(y) is not int:
        raise TypeError("y must be int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if type(y) is not int or type(m) is not int:
        raise TypeError("y and m must be int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError("month out of range 1..12")
    if m == 2 and is_leap(y):
        return 29
    return _MONTH_DAYS[m - 1]


def to_ordinal(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be int")
    _check_valid_date(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    if type(n) is not int:
        raise TypeError("n must be int")
    if not (1 <= n <= _MAX_ORD):
        raise ValueError("ordinal out of range 1..3652059")
    # Binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    return _from_day_of_year(y, doy)


def weekday(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be int")
    _check_valid_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    _check_valid_date(y, m, d)
    new_ord = to_ordinal(y, m, d) + n
    if new_ord < 1 or new_ord > _MAX_ORD:
        raise OverflowError("result out of range")
    return from_ordinal(new_ord)


def add_months(date, n):
    _check_date_tuple(date)
    if type(n) is not int:
        raise TypeError("n must be int")
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError("result out of range")
    td = min(d, days_in_month(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    wd = weekday(iso_year, 1, 1)
    if wd == 3:
        return 53
    if is_leap(iso_year) and wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be int")
    _check_valid_date(y, m, d)
    ord_val = to_ordinal(y, m, d)
    iso_wd = (ord_val - 1) % 7 + 1  # 1=Mon .. 7=Sun
    thu_ord = ord_val + (4 - iso_wd)
    iso_y = from_ordinal(thu_ord)[0]
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7  # 0=Mon
    mon_w1_ord = jan4_ord - jan4_wd
    week = (ord_val - mon_w1_ord) // 7 + 1
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if type(iso_year) is not int or type(week) is not int or type(weekday) is not int:
        raise TypeError("iso_year, week, weekday must be int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError("week out of range")
    if not (1 <= weekday <= 7):
        raise ValueError("weekday out of range 1..7")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1_ord = jan4_ord - jan4_wd
    target_ord = mon_w1_ord + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORD:
        raise OverflowError("result out of range")
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= days_in_month(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_BASIC_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= days_in_month(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return _from_day_of_year(y, doy)

    m = _RE_BASIC_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return _from_day_of_year(y, doy)

    m = _RE_EXT_WEEK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    m = _RE_BASIC_WEEK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of range")

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_tuple(date)
    y, m, d = date
    _check_valid_date(y, m, d)
    if type(form) is not str:
        raise ValueError("form must be a string")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"
    else:
        raise ValueError(f"invalid form: {form!r}")


def diff(a, b):
    _check_date_tuple(a)
    _check_date_tuple(b)
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a < b: find largest K >= 0 such that add_months(a, K) <= b
    lo, hi = 0, (by - ay) * 12 + (bm - am) + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            shifted = add_months(a, mid)
            if shifted <= b:
                lo = mid
            else:
                hi = mid - 1
        except OverflowError:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(*shifted)
    return (years, months, days)
