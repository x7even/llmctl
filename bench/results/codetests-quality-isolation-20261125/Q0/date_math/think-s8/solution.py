import re

# ─── internal helpers (no type-checking; assume correct types) ───────────────

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)


def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_raw(y, m):
    if m == 2 and _is_leap_raw(y):
        return 29
    return _MONTH_DAYS[m - 1]


def _days_before_year(y):
    yp = y - 1
    return 365 * yp + yp // 4 - yp // 100 + yp // 400


def _days_before_month(y, m):
    total = _CUM[m - 1]
    if m > 2 and _is_leap_raw(y):
        total += 1
    return total


def _to_ordinal_raw(y, m, d):
    return _days_before_year(y) + _days_before_month(y, m) + d


def _from_ordinal_raw(n):
    # binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        last = _days_before_year(mid) + (366 if _is_leap_raw(mid) else 365)
        if n > last:
            lo = mid + 1
        else:
            hi = mid
    y = lo
    doy = n - _days_before_year(y)  # 1-based day of year
    cum = _CUM_LEAP if _is_leap_raw(y) else _CUM
    m = 1
    while m < 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def _iso_weeks_raw(y):
    jan1 = _days_before_year(y) + 1
    wd = (jan1 - 1) % 7  # Mon=0
    if wd == 3:
        return 53
    if wd == 2 and _is_leap_raw(y):
        return 53
    return 52


def _from_iso_week_raw(iso_year, week, weekday):
    jan4 = _to_ordinal_raw(iso_year, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    week1_mon = jan4 - jan4_wd
    target = week1_mon + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return _from_ordinal_raw(target)


# ─── type / range checking helpers ───────────────────────────────────────────

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _chk_date(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(v).__name__}")


def _chk_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim_raw(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim_raw(y, m)}")


# ─── public API ──────────────────────────────────────────────────────────────

def is_leap(y):
    _chk_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim_raw(y, m)


def to_ordinal(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_range(y, m, d)
    return _to_ordinal_raw(y, m, d)


def from_ordinal(n):
    _chk_int(n, 'n')
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ordinal_raw(n)


def weekday(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_range(y, m, d)
    return (_to_ordinal_raw(y, m, d) - 1) % 7


def add_days(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _chk_range(y, m, d)
    ord_result = _to_ordinal_raw(y, m, d) + n
    if ord_result < 1 or ord_result > 3652059:
        raise OverflowError("result out of range")
    return _from_ordinal_raw(ord_result)


def add_months(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _chk_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of range")
    td = d if d <= _dim_raw(ty, tm) else _dim_raw(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_raw(iso_year)


def iso_week(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_range(y, m, d)
    ordinal = _to_ordinal_raw(y, m, d)
    iso_wd = (ordinal - 1) % 7 + 1  # Mon=1..Sun=7
    jan4 = _to_ordinal_raw(y, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    week1_mon = jan4 - jan4_wd
    days_since = ordinal - week1_mon
    wk = days_since // 7 + 1
    if wk < 1:
        iy = y - 1
        wk = _iso_weeks_raw(iy)
    elif wk > _iso_weeks_raw(y):
        iy = y + 1
        wk = 1
    else:
        iy = y
    return (iy, wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, 'iso_year')
    _chk_int(week, 'week')
    _chk_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    mw = _iso_weeks_raw(iso_year)
    if week < 1 or week > mw:
        raise ValueError(f"week {week} out of range 1..{mw}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    return _from_iso_week_raw(iso_year, week, weekday)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    # Extended calendar: YYYY-MM-DD
    m = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _dim_raw(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    # Extended week: YYYY-Www-D
    m = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if w < 1 or w > _iso_weeks_raw(y):
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        try:
            return _from_iso_week_raw(y, w, wd)
        except OverflowError:
            raise ValueError("date out of range")

    # Extended ordinal: YYYY-DDD
    m = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        mx = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > mx:
            raise ValueError("day of year out of range")
        return _from_ordinal_raw(_to_ordinal_raw(y, 1, 1) + doy - 1)

    # Basic calendar: YYYYMMDD
    m = re.fullmatch(r'([0-9]{4})([0-9]{2})([0-9]{2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _dim_raw(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    # Basic week: YYYYWwwD
    m = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if w < 1 or w > _iso_weeks_raw(y):
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        try:
            return _from_iso_week_raw(y, w, wd)
        except OverflowError:
            raise ValueError("date out of range")

    # Basic ordinal: YYYYDDD
    m = re.fullmatch(r'([0-9]{4})([0-9]{3})', s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        mx = 366 if _is_leap_raw(y) else 365
        if doy < 1 or doy > mx:
            raise ValueError("day of year out of range")
        return _from_ordinal_raw(_to_ordinal_raw(y, 1, 1) + doy - 1)

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _chk_date(date, 'date')
    y, m, d = date
    _chk_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _chk_date(a, 'a')
    _chk_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _chk_range(ay, am, ad)
    _chk_range(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    def shift(a, K):
        total = (ay - 1) * 12 + (am - 1) + K
        ty = total // 12 + 1
        tm = total % 12 + 1
        td = ad if ad <= _dim_raw(ty, tm) else _dim_raw(ty, tm)
        return (ty, tm, td)

    lo, hi = 0, (by - ay) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if shift(a, mid) <= b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    days = _to_ordinal_raw(by, bm, bd) - _to_ordinal_raw(*shift(a, K))
    return (years, months, days)
