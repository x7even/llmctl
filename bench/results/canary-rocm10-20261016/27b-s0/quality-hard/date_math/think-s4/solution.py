import re


def _check_int(x, name='x'):
    if type(x) is not int:
        raise TypeError(f"expected int for {name}, got {type(x).__name__}")


def _check_date(date, name='date'):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"expected tuple of 3 ints for {name}, got {type(date).__name__}")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"expected int at position {i} of {name}, got {type(v).__name__}")


def _check_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim}")


def _dim(y, m):
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    elif m in (4, 6, 9, 11):
        return 30
    else:
        if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
            return 29
        return 28


def _days_in_years(x):
    return x * 365 + x // 4 - x // 100 + x // 400


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
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    days_before_year = _days_in_years(y - 1)
    days_before_month = 0
    for mm in range(1, m):
        days_before_month += _dim(y, mm)
    return days_before_year + days_before_month + d


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    target = n - 1
    x = target * 400 // 146097
    while _days_in_years(x) > target:
        x -= 1
    while _days_in_years(x + 1) <= target:
        x += 1
    y = x + 1
    day_of_year = n - _days_in_years(x)
    m = 1
    while m <= 12:
        dim = _dim(y, m)
        if day_of_year <= dim:
            return (y, m, day_of_year)
        day_of_year -= dim
        m += 1
    raise ValueError("internal error in from_ordinal")


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    ord_val = to_ordinal(y, m, d) + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError("result out of supported range")
    return from_ordinal(ord_val)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError(f"result year {ty} out of range 1..9999")
    td = min(d, _dim(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    w = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if w == 3 or (w == 2 and is_leap(iso_year)):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    ord_val = to_ordinal(y, m, d)
    wd = (ord_val - 1) % 7
    monday = ord_val - wd
    thursday = monday + 3
    iso_year = from_ordinal(thursday)[0]
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    week = (monday - monday_w1) // 7 + 1
    iso_wd = wd + 1
    return (iso_year, week, iso_wd)


def from_iso_week(iso_year, week, weekday_val):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday_val, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday_val <= 7):
        raise ValueError(f"weekday {weekday_val} out of range 1..7")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target_ord = monday_w1 + (week - 1) * 7 + (weekday_val - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError("result out of supported range")
    return from_ordinal(target_ord)


_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BAS_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')


def parse(s):
    if type(s) is not str:
        raise TypeError(f"expected str, got {type(s).__name__}")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mm <= 12):
            raise ValueError(f"month {mm} out of range")
        if not (1 <= dd <= _dim(y, mm)):
            raise ValueError(f"day {dd} out of range for month {mm} in year {y}")
        return (y, mm, dd)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, ww, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_week = iso_weeks_in_year(y)
        if not (1 <= ww <= max_week):
            raise ValueError(f"week {ww} out of range 1..{max_week} for ISO year {y}")
        if not (1 <= dd <= 7):
            raise ValueError(f"weekday {dd} out of range 1..7")
        try:
            return from_iso_week(y, ww, dd)
        except OverflowError:
            raise ValueError(f"week date out of supported range")

    if len(s) == 8:
        m = _RE_EXT_ORD.fullmatch(s)
        if m:
            y, ddd = int(m.group(1)), int(m.group(2))
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range")
            max_doy = 366 if is_leap(y) else 365
            if not (1 <= ddd <= max_doy):
                raise ValueError(f"day of year {ddd} out of range 1..{max_doy}")
            return from_ordinal(to_ordinal(y, 1, 1) + ddd - 1)

        m = _RE_BAS_WK.fullmatch(s)
        if m:
            y, ww, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range")
            max_week = iso_weeks_in_year(y)
            if not (1 <= ww <= max_week):
                raise ValueError(f"week {ww} out of range 1..{max_week} for ISO year {y}")
            if not (1 <= dd <= 7):
                raise ValueError(f"weekday {dd} out of range 1..7")
            try:
                return from_iso_week(y, ww, dd)
            except OverflowError:
                raise ValueError(f"week date out of supported range")

        m = _RE_BAS_CAL.fullmatch(s)
        if m:
            y, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range")
            if not (1 <= mm <= 12):
                raise ValueError(f"month {mm} out of range")
            if not (1 <= dd <= _dim(y, mm)):
                raise ValueError(f"day {dd} out of range for month {mm} in year {y}")
            return (y, mm, dd)

    if len(s) == 7:
        m = _RE_BAS_ORD.fullmatch(s)
        if m:
            y, ddd = int(m.group(1)), int(m.group(2))
            if not (1 <= y <= 9999):
                raise ValueError(f"year {y} out of range")
            max_doy = 366 if is_leap(y) else 365
            if not (1 <= ddd <= max_doy):
                raise ValueError(f"day of year {ddd} out of range 1..{max_doy}")
            return from_ordinal(to_ordinal(y, 1, 1) + ddd - 1)

    raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_valid_date(y, m, d)

    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        days_before_month = 0
        for mm in range(1, m):
            days_before_month += _dim(y, mm)
        doy = days_before_month + d
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    if a > b:
        years, months, days = diff(b, a)
        return (-years, -months, -days)

    # a <= b: find largest K >= 0 such that shift(a, K) <= b
    base = (ay - 1) * 12 + (am - 1)

    def shift_le_b(K):
        total = base + K
        ty = total // 12 + 1
        tm = total % 12 + 1
        if ty > 9999:
            return False
        td = min(ad, _dim(ty, tm))
        return (ty, tm, td) <= (by, bm, bd)

    lo = 0
    hi = (by - ay) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if shift_le_b(mid):
            lo = mid
        else:
            hi = mid - 1

    K = lo
    years, months = divmod(K, 12)

    total = base + K
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = min(ad, _dim(ty, tm))

    days = to_ordinal(by, bm, bd) - to_ordinal(ty, tm, td)

    return (years, months, days)