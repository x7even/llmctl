import re


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if m == 2:
        dim = 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    elif m in (1, 3, 5, 7, 8, 10, 12):
        dim = 31
    else:
        dim = 30
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for year {y} month {m}")


def is_leap(y):
    _check_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if m == 2:
        return 29 if is_leap(y) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    yy = y - 1
    days_before_year = 365 * yy + yy // 4 - yy // 100 + yy // 400
    leap = 1 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 0
    if m == 1:
        dbm = 0
    elif m == 2:
        dbm = 31
    elif m == 3:
        dbm = 59 + leap
    elif m == 4:
        dbm = 90 + leap
    elif m == 5:
        dbm = 120 + leap
    elif m == 6:
        dbm = 151 + leap
    elif m == 7:
        dbm = 181 + leap
    elif m == 8:
        dbm = 212 + leap
    elif m == 9:
        dbm = 243 + leap
    elif m == 10:
        dbm = 273 + leap
    elif m == 11:
        dbm = 304 + leap
    else:
        dbm = 334 + leap
    return days_before_year + dbm + d


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        if 365 * mid + mid // 4 - mid // 100 + mid // 400 >= n:
            hi = mid
        else:
            lo = mid + 1
    y = lo
    days_before_year = 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    doy = n - days_before_year
    leap = 1 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 0
    md = (31, 28 + leap, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    m = 1
    while m <= 12 and doy > md[m - 1]:
        doy -= md[m - 1]
        m += 1
    return (y, m, doy)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    result = to_ordinal(y, m, d) + n
    if result < 1 or result > 3652059:
        raise OverflowError("result out of range 1..3652059")
    return from_ordinal(result)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result year out of range 1..9999")
    td = min(d, days_in_month(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if is_leap(iso_year) and jan1_wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ordinal = to_ordinal(y, m, d)
    iso_weekday = (ordinal - 1) % 7 + 1
    thu_ordinal = ordinal + (4 - iso_weekday)
    iso_year = from_ordinal(thu_ordinal)[0]
    jan1_ord = to_ordinal(iso_year, 1, 1)
    jan1_wd = (jan1_ord - 1) % 7
    first_thu = jan1_ord + (3 - jan1_wd) % 7
    mon_week1 = first_thu - 3
    iso_week_num = (thu_ordinal - mon_week1) // 7 + 1
    return (iso_year, iso_week_num, iso_weekday)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan1_ord = to_ordinal(iso_year, 1, 1)
    jan1_wd = (jan1_ord - 1) % 7
    first_thu = jan1_ord + (3 - jan1_wd) % 7
    mon_week1 = first_thu - 3
    target = mon_week1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return from_ordinal(target)


_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BASIC_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')
_RE_BASIC_8 = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is out of range")
        _check_date_range(y, mo, d)
        return (y, mo, d)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError("year 0000 is out of range")
        max_doy = 366 if is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is out of range")
        if not (1 <= wk <= iso_weeks_in_year(y)):
            raise ValueError(f"week {wk} out of range for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of supported range")

    m = _RE_BASIC_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError("year 0000 is out of range")
        if not (1 <= wk <= iso_weeks_in_year(y)):
            raise ValueError(f"week {wk} out of range for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("date out of supported range")

    m = _RE_BASIC_8.fullmatch(s)
    if m:
        y = int(m.group(1))
        mo = int(m.group(2))
        d = int(m.group(3))
        if 1 <= y <= 9999 and 1 <= mo <= 12:
            dim = days_in_month(y, mo)
            if 1 <= d <= dim:
                return (y, mo, d)
        doy = int(m.group(2) + m.group(3))
        if 1 <= y <= 9999:
            max_doy = 366 if is_leap(y) else 365
            if 1 <= doy <= max_doy:
                return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)
        raise ValueError(f"invalid date string: {s!r}")

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str:
        raise ValueError("form must be a string")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"
    else:
        raise ValueError(f"invalid form: {form!r}")


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    negative = a > b
    if negative:
        a, b = b, a
        ay, am, ad = a
        by, bm, bd = b

    lo = 0
    hi = (by - ay) * 12 + (bm - am) + 1
    while lo < hi:
        mid = (lo + hi) // 2
        try:
            if add_months(a, mid) <= b:
                lo = mid + 1
            else:
                hi = mid
        except OverflowError:
            hi = mid

    K = lo - 1
    years, months = divmod(K, 12)
    shifted = add_months(a, K)
    days = to_ordinal(by, bm, bd) - to_ordinal(shifted[0], shifted[1], shifted[2])

    if negative:
        return (-years, -months, -days)
    return (years, months, days)