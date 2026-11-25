import re

_MAX_ORDINAL = 3652059  # to_ordinal(9999, 12, 31)


def _dim(y, m):
    """Days in month y-m. Assumes y in 1..9999, m in 1..12."""
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _check_date_types(date, name):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints, got {type(date).__name__}")
    if len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints, got length {len(date)}")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(date[i]).__name__}")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")


def _days_before_year(y):
    """Number of days in years 1..y-1."""
    t = y - 1
    return 365 * t + t // 4 - t // 100 + t // 400


def _days_before_month(y, m):
    """Number of days in months 1..m-1 of year y."""
    if m <= 1:
        return 0
    feb = _dim(y, 2)
    cum = (0, 31, 31 + feb, 31 + feb + 31, 31 + feb + 31 + 30,
           31 + feb + 31 + 30 + 31, 31 + feb + 31 + 30 + 31 + 30,
           31 + feb + 31 + 30 + 31 + 30 + 31, 31 + feb + 31 + 30 + 31 + 30 + 31 + 31,
           31 + feb + 31 + 30 + 31 + 30 + 31 + 31 + 30,
           31 + feb + 31 + 30 + 31 + 30 + 31 + 31 + 30 + 31,
           31 + feb + 31 + 30 + 31 + 30 + 31 + 31 + 30 + 31 + 30)
    return cum[m - 1]


def is_leap(y):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if type(y) is not int or type(m) is not int:
        raise TypeError("y and m must be ints")
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be ints")
    _check_date_range(y, m, d)
    return _days_before_year(y) + _days_before_month(y, m) + d


def from_ordinal(n):
    if type(n) is not int:
        raise TypeError("n must be an int")
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    # Estimate t = y - 1
    t = (n - 1) * 400 // 146097
    # Adjust (at most a couple of iterations)
    while 365 * t + t // 4 - t // 100 + t // 400 >= n:
        t -= 1
    while 365 * (t + 1) + (t + 1) // 4 - (t + 1) // 100 + (t + 1) // 400 < n:
        t += 1
    y = t + 1
    day_of_year = n - (365 * t + t // 4 - t // 100 + t // 400)
    m = 1
    while m <= 12:
        dm = _dim(y, m)
        if day_of_year <= dm:
            break
        day_of_year -= dm
        m += 1
    return (y, m, day_of_year)


def weekday(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be ints")
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_types(date, "date")
    if type(n) is not int:
        raise TypeError("n must be an int")
    y, m, d = date
    _check_date_range(y, m, d)
    new_ord = to_ordinal(y, m, d) + n
    if new_ord < 1 or new_ord > _MAX_ORDINAL:
        raise OverflowError("result out of range 1..9999")
    return from_ordinal(new_ord)


def add_months(date, n):
    _check_date_types(date, "date")
    if type(n) is not int:
        raise TypeError("n must be an int")
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of range 1..9999")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be an int")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range 1..9999")
    ord_jan1 = _days_before_year(iso_year) + 1
    wd = (ord_jan1 - 1) % 7  # Mon=0..Sun=6
    if wd == 3:
        return 53
    if wd == 2 and (iso_year % 4 == 0 and (iso_year % 100 != 0 or iso_year % 400 == 0)):
        return 53
    return 52


def iso_week(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be ints")
    _check_date_range(y, m, d)
    n = to_ordinal(y, m, d)
    w = (n - 1) % 7  # Mon=0..Sun=6
    thursday_ord = n + (3 - w)
    iso_year = from_ordinal(thursday_ord)[0]
    jan4_ord = _days_before_year(iso_year) + _days_before_month(iso_year, 1) + 4
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    date_monday = n - w
    iso_wk = (date_monday - week1_monday) // 7 + 1
    iso_wd = w + 1
    return (iso_year, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if type(iso_year) is not int or type(week) is not int or type(weekday) is not int:
        raise TypeError("iso_year, week, weekday must be ints")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range 1..9999")
    max_wk = iso_weeks_in_year(iso_year)
    if week < 1 or week > max_wk:
        raise ValueError(f"week {week} out of range 1..{max_wk}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _days_before_year(iso_year) + _days_before_month(iso_year, 1) + 4
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target = week1_monday + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORDINAL:
        raise OverflowError("result out of range 1..9999")
    return from_ordinal(target)


_RE_EXT_CAL = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_BAS_CAL = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_EXT_ORD = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_BAS_ORD = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_EXT_WK = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_BAS_WK = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    # Extended calendar: YYYY-MM-DD
    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _dim(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    # Basic calendar: YYYYMMDD
    m = _RE_BAS_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > _dim(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)

    # Extended week: YYYY-Www-D
    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of supported range")

    # Basic week: YYYYWwwD
    m = _RE_BAS_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year out of range")
        max_wk = iso_weeks_in_year(y)
        if wk < 1 or wk > max_wk:
            raise ValueError("week out of range")
        if wd < 1 or wd > 7:
            raise ValueError("weekday out of range")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of supported range")

    # Extended ordinal: YYYY-DDD
    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year out of range")
        max_doy = 366 if is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return from_ordinal(_days_before_year(y) + doy)

    # Basic ordinal: YYYYDDD
    m = _RE_BAS_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year out of range")
        max_doy = 366 if is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        return from_ordinal(_days_before_year(y) + doy)

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_types(date, "date")
    y, m, d = date
    _check_date_range(y, m, d)
    if form != 'calendar' and form != 'ordinal' and form != 'week':
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date_types(a, "a")
    _check_date_types(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    a_ord = to_ordinal(ay, am, ad)
    b_ord = to_ordinal(by, bm, bd)

    if a_ord == b_ord:
        return (0, 0, 0)

    if a_ord > b_ord:
        result = diff(b, a)
        return (-result[0], -result[1], -result[2])

    # a < b: find largest K >= 0 with add_months(a, K) <= b
    lo = 0
    hi = (9999 - ay) * 12 + (12 - am)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        total = (ay - 1) * 12 + (am - 1) + mid
        ty = total // 12 + 1
        tm = total % 12 + 1
        if ty < 1 or ty > 9999:
            hi = mid - 1
            continue
        td = ad if ad <= _dim(ty, tm) else _dim(ty, tm)
        shifted_ord = _days_before_year(ty) + _days_before_month(ty, tm) + td
        if shifted_ord <= b_ord:
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)
    total = (ay - 1) * 12 + (am - 1) + K
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = ad if ad <= _dim(ty, tm) else _dim(ty, tm)
    shifted_ord = _days_before_year(ty) + _days_before_month(ty, tm) + td
    days = b_ord - shifted_ord
    return (years, months, days)
