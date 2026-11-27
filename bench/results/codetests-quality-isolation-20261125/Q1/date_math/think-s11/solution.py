import re

_NONLEAP_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 242, 273, 303, 334, 365)
_LEAP_CUM = (0, 31, 60, 91, 121, 152, 182, 213, 243, 274, 304, 335, 366)

_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BASIC = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BASIC = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_WEEK_EXT = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WEEK_BASIC = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date_tuple(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")


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
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    k = y - 1
    days_years = 365 * k + k // 4 - k // 100 + k // 400
    cum = _LEAP_CUM if _is_leap(y) else _NONLEAP_CUM
    return days_years + cum[m - 1] + d


def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    k = (n - 1) * 400 // 146097
    while 365 * k + k // 4 - k // 100 + k // 400 >= n:
        k -= 1
    while 365 * (k + 1) + (k + 1) // 4 - (k + 1) // 100 + (k + 1) // 400 < n:
        k += 1
    y = k + 1
    day_of_year = n - (365 * k + k // 4 - k // 100 + k // 400)
    cum = _LEAP_CUM if _is_leap(y) else _NONLEAP_CUM
    for m in range(1, 13):
        if day_of_year <= cum[m]:
            d = day_of_year - cum[m - 1]
            return (y, m, d)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError("result out of supported range")
    return from_ordinal(ord_val)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError(f"result year {ty} out of range 1..9999")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    k = iso_year - 1
    jan1_ord = 365 * k + k // 4 - k // 100 + k // 400 + 1
    jan1_wd = (jan1_ord - 1) % 7
    if jan1_wd == 3:
        return 53
    if jan1_wd == 2 and _is_leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    iso_wd = wd + 1
    mon_ord = ord_val - wd
    thu_ord = mon_ord + 3
    iso_y = from_ordinal(thu_ord)[0]
    k = iso_y - 1
    jan4_ord = 365 * k + k // 4 - k // 100 + k // 400 + 4
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    iso_w = (mon_ord - mon_w1) // 7 + 1
    return (iso_y, iso_w, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    k = iso_year - 1
    jan4_ord = 365 * k + k // 4 - k // 100 + k // 400 + 4
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target_ord = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError("result out of supported range")
    return from_ordinal(target_ord)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    m = _RE_CAL_EXT.fullmatch(s)
    if m:
        y, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date_range(y, mm, dd)
        return (y, mm, dd)

    m = _RE_CAL_BASIC.fullmatch(s)
    if m:
        y, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _check_date_range(y, mm, dd)
        return (y, mm, dd)

    m = _RE_ORD_EXT.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        k = y - 1
        jan1 = 365 * k + k // 4 - k // 100 + k // 400 + 1
        return from_ordinal(jan1 + doy - 1)

    m = _RE_ORD_BASIC.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1 or y > 9999:
            raise ValueError(f"year {y} out of range 1..9999")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        k = y - 1
        jan1 = 365 * k + k // 4 - k // 100 + k // 400 + 1
        return from_ordinal(jan1 + doy - 1)

    m = _RE_WEEK_EXT.fullmatch(s)
    if m:
        y, ww, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return from_iso_week(y, ww, wd)
        except OverflowError:
            raise ValueError(f"week date out of supported range")

    m = _RE_WEEK_BASIC.fullmatch(s)
    if m:
        y, ww, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return from_iso_week(y, ww, wd)
        except OverflowError:
            raise ValueError(f"week date out of supported range")

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)

    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        k = y - 1
        jan1 = 365 * k + k // 4 - k // 100 + k // 400 + 1
        cum = _LEAP_CUM if _is_leap(y) else _NONLEAP_CUM
        doy = cum[m - 1] + d
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ya, ma, da = a
    yb, mb, db = b
    _check_date_range(ya, ma, da)
    _check_date_range(yb, mb, db)

    if a == b:
        return (0, 0, 0)

    if a < b:
        base = (ya - 1) * 12 + (ma - 1)
        target_total = (yb - 1) * 12 + (mb - 1)
        clamped_day = da if da <= _dim(yb, mb) else _dim(yb, mb)

        if clamped_day <= db:
            K = target_total - base
        else:
            K = target_total - 1 - base

        years, months = divmod(K, 12)
        total = base + K
        ty = total // 12 + 1
        tm = total % 12 + 1
        td = da if da <= _dim(ty, tm) else _dim(ty, tm)
        days = to_ordinal(yb, mb, db) - to_ordinal(ty, tm, td)
        return (years, months, days)
    else:
        yr, mo, dy = diff(b, a)
        return (-yr, -mo, -dy)