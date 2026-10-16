import re

__all__ = [
    'is_leap', 'days_in_month', 'to_ordinal', 'from_ordinal', 'weekday',
    'add_days', 'add_months', 'iso_weeks_in_year', 'iso_week', 'from_iso_week',
    'parse', 'format_date', 'diff',
]

_MONTH_DAYS = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM_DAYS = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_MAX_ORD = 3652059


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MONTH_DAYS[m]


def _to_ordinal(y, m, d):
    y1 = y - 1
    days = 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
    days += _CUM_DAYS[m - 1]
    if m > 2 and _is_leap(y):
        days += 1
    days += d
    return days


def _from_ordinal(n):
    z = n - 1
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400 + 1
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    leap = 1 if _is_leap(y) else 0
    threshold = 59 + leap
    if doy >= threshold:
        shifted = doy - threshold
    else:
        shifted = doy + 306
    mp = (5 * shifted + 2) // 153
    d = shifted - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return (y, m, d)


def _weekday(y, m, d):
    return (_to_ordinal(y, m, d) - 1) % 7


def _iso_weeks_in_year(y):
    wd = _weekday(y, 1, 1)
    if wd == 3:
        return 53
    if wd == 2 and _is_leap(y):
        return 53
    return 52


def _add_months(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    max_d = _days_in_month(new_y, new_m)
    new_d = d if d <= max_d else max_d
    return (new_y, new_m, new_d)


def _iso_week_calc(y, m, d):
    ord_ = _to_ordinal(y, m, d)
    wd = _weekday(y, m, d)
    iso_wd = wd + 1
    monday_ord = ord_ - wd
    jan4_ord = _to_ordinal(y, 1, 4)
    jan4_wd = _weekday(y, 1, 4)
    week1_monday = jan4_ord - jan4_wd
    week = (monday_ord - week1_monday) // 7 + 1
    if week < 1:
        iso_year = y - 1
        jan4_prev = _to_ordinal(iso_year, 1, 4)
        jan4_prev_wd = _weekday(iso_year, 1, 4)
        week1_prev = jan4_prev - jan4_prev_wd
        week = (monday_ord - week1_prev) // 7 + 1
    elif week > _iso_weeks_in_year(y):
        iso_year = y + 1
        week = 1
    else:
        iso_year = y
    return (iso_year, week, iso_wd)


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _check_date(date, name):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple, got {type(date).__name__}")
    if len(date) != 3:
        raise TypeError(f"{name} must have exactly 3 elements, got {len(date)}")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(date[i]).__name__}")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError("day out of range")


# ─── Public API ───────────────────────────────────────────────────────────────


def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > _MAX_ORD:
        raise ValueError("ordinal out of range")
    return _from_ordinal(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _weekday(y, m, d)


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    result_ord = _to_ordinal(y, m, d) + n
    if result_ord < 1 or result_ord > _MAX_ORD:
        raise OverflowError("result date out of range")
    return _from_ordinal(result_ord)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    new_y, new_m, new_d = _add_months(y, m, d, n)
    if new_y < 1 or new_y > 9999:
        raise OverflowError("result year out of range")
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return _iso_week_calc(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    if week < 1 or week > _iso_weeks_in_year(iso_year):
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")
    jan4_ord = _to_ordinal(iso_year, 1, 4)
    jan4_wd = _weekday(iso_year, 1, 4)
    week1_monday = jan4_ord - jan4_wd
    target_ord = week1_monday + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORD:
        raise OverflowError("result date out of range")
    return _from_ordinal(target_ord)


_DATE_RE = re.compile(
    r'(?:'
    r'([0-9]{4})-([0-9]{2})-([0-9]{2})'
    r'|([0-9]{4})([0-9]{2})([0-9]{2})'
    r'|([0-9]{4})-([0-9]{3})'
    r'|([0-9]{4})([0-9]{3})'
    r'|([0-9]{4})-W([0-9]{2})-([0-9])'
    r'|([0-9]{4})W([0-9]{2})([0-9])'
    r')'
)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    m = _DATE_RE.fullmatch(s)
    if m is None:
        raise ValueError("invalid date string")
    g = m.groups()
    if g[0] is not None:
        y, mo, d = int(g[0]), int(g[1]), int(g[2])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)
    if g[3] is not None:
        y, mo, d = int(g[3]), int(g[4]), int(g[5])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)
    if g[6] is not None:
        y, doy = int(g[6]), int(g[7])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return _from_ordinal(_to_ordinal(y, 1, 1) + doy - 1)
    if g[8] is not None:
        y, doy = int(g[8]), int(g[9])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return _from_ordinal(_to_ordinal(y, 1, 1) + doy - 1)
    if g[10] is not None:
        iy, wk, wd = int(g[10]), int(g[11]), int(g[12])
    else:
        iy, wk, wd = int(g[13]), int(g[14]), int(g[15])
    if iy < 1 or iy > 9999:
        raise ValueError("iso_year out of range")
    if wk < 1 or wk > _iso_weeks_in_year(iy):
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    jan4_ord = _to_ordinal(iy, 1, 4)
    jan4_wd = _weekday(iy, 1, 4)
    week1_monday = jan4_ord - jan4_wd
    target_ord = week1_monday + (wk - 1) * 7 + (wd - 1)
    if target_ord < 1 or target_ord > _MAX_ORD:
        raise ValueError("result date out of range")
    return _from_ordinal(target_ord)


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str:
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == 'ordinal':
        doy = _to_ordinal(y, m, d) - _to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    if form == 'week':
        iso_y, iso_w, iso_wd = _iso_week_calc(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"
    raise ValueError("invalid form")


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ya, ma, da = a
    yb, mb, db = b
    _check_date_range(ya, ma, da)
    _check_date_range(yb, mb, db)
    ord_a = _to_ordinal(ya, ma, da)
    ord_b = _to_ordinal(yb, mb, db)
    if ord_a > ord_b:
        years, months, days = diff(b, a)
        return (-years, -months, -days)
    lo, hi = 0, 119988
    while lo < hi:
        mid = (lo + hi + 1) // 2
        sy, sm, sd = _add_months(ya, ma, da, mid)
        if sy < 1 or sy > 9999:
            hi = mid - 1
        elif _to_ordinal(sy, sm, sd) <= ord_b:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    sy, sm, sd = _add_months(ya, ma, da, K)
    days = ord_b - _to_ordinal(sy, sm, sd)
    return (years, months, days)
