_MD = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORD = 3652059


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2 and _is_leap(y):
        return 29
    return _MD[m - 1]


def _days_before_year(y):
    y -= 1
    return y * 365 + y // 4 - y // 100 + y // 400


def _doy(y, m, d):
    s = _CUM[m - 1] + d
    if m > 2 and _is_leap(y):
        s += 1
    return s


def _to_ordinal(y, m, d):
    return _days_before_year(y) + _doy(y, m, d)


def _from_ordinal(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    m = 1
    while m < 12 and doy > _dim(y, m):
        doy -= _dim(y, m)
        m += 1
    return (y, m, doy)


def _weekday(y, m, d):
    return (_to_ordinal(y, m, d) - 1) % 7


def _shift(y, m, d, k):
    total = (y - 1) * 12 + (m - 1) + k
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        return (ny, nm, 1)
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)


def _iso_weeks_in_year(y):
    w = _weekday(y, 1, 1)
    if w == 3:
        return 53
    if w == 2 and _is_leap(y):
        return 53
    return 52


def _mon_w1_ord(iy):
    jan1 = _days_before_year(iy) + 1
    jan4 = jan1 + 3
    jan4_wd = (jan4 - 1) % 7
    return jan4 - jan4_wd


def _iso_week(y, m, d):
    ord_ = _to_ordinal(y, m, d)
    wd = _weekday(y, m, d)
    iso_wd = wd + 1
    thu_ord = ord_ + (3 - wd)
    thu = _from_ordinal(thu_ord)
    iso_year = thu[0]
    mon_w1 = _mon_w1_ord(iso_year)
    week = (ord_ - mon_w1) // 7 + 1
    return (iso_year, week, iso_wd)


def _from_iso_week(iy, week, wd):
    mon_w1 = _mon_w1_ord(iy)
    target = mon_w1 + (week - 1) * 7 + (wd - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ordinal(target)


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date_tuple(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _check_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range for {y:04d}-{m:02d}")


def _parse_digits(s, pos, count):
    for i in range(pos, pos + count):
        c = s[i]
        if c < '0' or c > '9':
            raise ValueError("invalid character in date string")
    return int(s[pos:pos + count])


# ─── Public API ────────────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y, "y")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return _to_ordinal(y, m, d)


def from_ordinal(n):
    _check_int(n, "n")
    if n < 1 or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORD}")
    return _from_ordinal(n)


def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return _weekday(y, m, d)


def add_days(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    ord_ = _to_ordinal(y, m, d) + n
    if ord_ < 1 or ord_ > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ordinal(ord_)


def add_months(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_range(y, m, d)
    result = _shift(y, m, d, n)
    if result[0] < 1 or result[0] > 9999:
        raise OverflowError("result out of range")
    return result


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_range(y, m, d)
    return _iso_week(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_wk = _iso_weeks_in_year(iso_year)
    if week < 1 or week > max_wk:
        raise ValueError(f"week {week} out of range 1..{max_wk}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    return _from_iso_week(iso_year, week, weekday)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")
    n = len(s)

    if n == 10:
        if s[4] != '-':
            raise ValueError("invalid date format")
        if s[5] == 'W':
            if s[7] != '-':
                raise ValueError("invalid date format")
            y = _parse_digits(s, 0, 4)
            ww = _parse_digits(s, 6, 2)
            wd = _parse_digits(s, 9, 1)
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if ww < 1 or ww > _iso_weeks_in_year(y):
                raise ValueError("week out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            try:
                return _from_iso_week(y, ww, wd)
            except OverflowError:
                raise ValueError("date out of range")
        else:
            if s[7] != '-':
                raise ValueError("invalid date format")
            y = _parse_digits(s, 0, 4)
            m = _parse_digits(s, 5, 2)
            d = _parse_digits(s, 8, 2)
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if m < 1 or m > 12:
                raise ValueError("month out of range")
            if d < 1 or d > _dim(y, m):
                raise ValueError("day out of range")
            return (y, m, d)

    elif n == 8:
        if s[4] == '-':
            y = _parse_digits(s, 0, 4)
            ddd = _parse_digits(s, 5, 3)
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            max_doy = 366 if _is_leap(y) else 365
            if ddd < 1 or ddd > max_doy:
                raise ValueError("day of year out of range")
            return _from_ordinal(_days_before_year(y) + ddd)
        elif s[4] == 'W':
            y = _parse_digits(s, 0, 4)
            ww = _parse_digits(s, 5, 2)
            wd = _parse_digits(s, 7, 1)
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if ww < 1 or ww > _iso_weeks_in_year(y):
                raise ValueError("week out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            try:
                return _from_iso_week(y, ww, wd)
            except OverflowError:
                raise ValueError("date out of range")
        else:
            y = _parse_digits(s, 0, 4)
            m = _parse_digits(s, 4, 2)
            d = _parse_digits(s, 6, 2)
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if m < 1 or m > 12:
                raise ValueError("month out of range")
            if d < 1 or d > _dim(y, m):
                raise ValueError("day out of range")
            return (y, m, d)

    elif n == 7:
        y = _parse_digits(s, 0, 4)
        ddd = _parse_digits(s, 4, 3)
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if ddd < 1 or ddd > max_doy:
            raise ValueError("day of year out of range")
        return _from_ordinal(_days_before_year(y) + ddd)

    else:
        raise ValueError("invalid date format")


def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str:
        raise ValueError("form must be a string")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _doy(y, m, d)
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, id_ = _iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"
    else:
        raise ValueError(f"invalid form {form!r}")


def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    ay, am, ad = a
    _check_date_range(ay, am, ad)
    by, bm, bd = b
    _check_date_range(by, bm, bd)

    if a <= b:
        lo, hi = 0, (by - ay) * 12 + 12
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _shift(ay, am, ad, mid) <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _shift(ay, am, ad, K)
        days = _to_ordinal(by, bm, bd) - _to_ordinal(shifted[0], shifted[1], shifted[2])
        return (years, months, days)
    else:
        y, m, d = diff(b, a)
        return (-y, -m, -d)