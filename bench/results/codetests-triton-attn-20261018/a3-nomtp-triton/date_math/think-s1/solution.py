import re

_MIN_ORD = 1
_MAX_ORD = 3652059  # to_ordinal(9999, 12, 31)

_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _days_in_month(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _days_before_year(y):
    ym1 = y - 1
    return ym1 * 365 + ym1 // 4 - ym1 // 100 + ym1 // 400


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date_tuple(date, name):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, x in enumerate(date):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _check_date_values(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _days_in_month(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


def _check_date(date, name):
    _check_date_tuple(date, name)
    y, m, d = date
    _check_date_values(y, m, d)


def _iso_weeks_in_year_raw(iso_year):
    wd = (_days_before_year(iso_year) + 1 - 1) % 7
    if wd == 3:
        return 53
    if _is_leap(iso_year) and wd == 2:
        return 53
    return 52


# ─── Public API ───────────────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _days_in_month(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_values(y, m, d)
    result = _days_before_year(y) + _DAYS_BEFORE_MONTH[m - 1]
    if m > 2 and _is_leap(y):
        result += 1
    result += d
    return result


def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    day_of_year = n - _days_before_year(y)
    leap = _is_leap(y)
    m = 1
    while m < 12:
        cum_next = _DAYS_BEFORE_MONTH[m] + (1 if m >= 2 and leap else 0)
        if day_of_year <= cum_next:
            break
        m += 1
    d = day_of_year - (_DAYS_BEFORE_MONTH[m - 1] + (1 if m > 2 and leap else 0))
    return (y, m, d)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_values(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_values(y, m, d)
    ord_result = to_ordinal(y, m, d) + n
    if ord_result < _MIN_ORD or ord_result > _MAX_ORD:
        raise OverflowError("result out of range 1..9999")
    return from_ordinal(ord_result)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_values(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of range 1..9999")
    td = min(d, _days_in_month(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year_raw(iso_year)


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_values(y, m, d)
    o = to_ordinal(y, m, d)
    wd = (o - 1) % 7
    o_thu = o + (3 - wd)
    iso_year = from_ordinal(o_thu)[0]
    jan4 = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    monday_w1 = jan4 - jan4_wd
    o_mon = o - wd
    iso_wk = (o_mon - monday_w1) // 7 + 1
    iso_wd = wd + 1
    return (iso_year, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_weeks = _iso_weeks_in_year_raw(iso_year)
    if week < 1 or week > max_weeks:
        raise ValueError(f"week {week} out of range 1..{max_weeks}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4 = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    monday_w1 = jan4 - jan4_wd
    target = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target < _MIN_ORD or target > _MAX_ORD:
        raise OverflowError("result out of range 1..9999")
    return from_ordinal(target)


_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BAS_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _days_in_month(y, mo):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_BAS_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _days_in_month(y, mo):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_BAS_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        max_weeks = _iso_weeks_in_year_raw(y)
        if w < 1 or w > max_weeks:
            raise ValueError(f"week {w} out of range 1..{max_weeks}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4 = to_ordinal(y, 1, 4)
        jan4_wd = (jan4 - 1) % 7
        monday_w1 = jan4 - jan4_wd
        target = monday_w1 + (w - 1) * 7 + (wd - 1)
        if target < _MIN_ORD or target > _MAX_ORD:
            raise ValueError("date out of range")
        return from_ordinal(target)

    m = _RE_BAS_WK.fullmatch(s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range")
        max_weeks = _iso_weeks_in_year_raw(y)
        if w < 1 or w > max_weeks:
            raise ValueError(f"week {w} out of range 1..{max_weeks}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4 = to_ordinal(y, 1, 4)
        jan4_wd = (jan4 - 1) % 7
        monday_w1 = jan4 - jan4_wd
        target = monday_w1 + (w - 1) * 7 + (wd - 1)
        if target < _MIN_ORD or target > _MAX_ORD:
            raise ValueError("date out of range")
        return from_ordinal(target)

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_values(y, m, d)

    if type(form) is not str:
        raise ValueError(f"form must be a string, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"
    else:
        raise ValueError(f"invalid form: {form!r}")


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_values(ay, am, ad)
    _check_date_values(by, bm, bd)

    if to_ordinal(ay, am, ad) > to_ordinal(by, bm, bd):
        y, mo, d = diff(b, a)
        return (-y, -mo, -d)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    lo, hi = 0, (by - ay) * 12 + (bm - am) + 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        total = (ay - 1) * 12 + (am - 1) + mid
        sy = total // 12 + 1
        sm = total % 12 + 1
        sd = min(ad, _days_in_month(sy, sm))
        if (sy, sm, sd) <= (by, bm, bd):
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    total = (ay - 1) * 12 + (am - 1) + K
    sy = total // 12 + 1
    sm = total % 12 + 1
    sd = min(ad, _days_in_month(sy, sm))
    days = to_ordinal(by, bm, bd) - to_ordinal(sy, sm, sd)
    return (years, months, days)