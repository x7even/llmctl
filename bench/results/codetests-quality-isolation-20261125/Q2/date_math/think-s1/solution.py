import re

_D = r'[0-9]'
_RE_EXT_CAL = re.compile(rf'^({_D}{{4}})-({_D}{{2}})-({_D}{{2}})$')
_RE_BASIC_CAL = re.compile(rf'^({_D}{{4}})({_D}{{2}})({_D}{{2}})$')
_RE_EXT_ORD = re.compile(rf'^({_D}{{4}})-({_D}{{3}})$')
_RE_BASIC_ORD = re.compile(rf'^({_D}{{4}})({_D}{{3}})$')
_RE_EXT_WEEK = re.compile(rf'^({_D}{{4}})-W({_D}{{2}})-({_D})$')
_RE_BASIC_WEEK = re.compile(rf'^({_D}{{4}})W({_D}{{2}})({_D})$')

_MONTH_START = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MAX_ORDINAL = 3652059


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i, v in enumerate(x):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(v).__name__}")


def _check_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim}")


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
    if m in (4, 6, 9, 11):
        return 30
    return 31


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    o = 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    o += _MONTH_START[m - 1]
    if is_leap(y) and m > 2:
        o += 1
    o += d
    return o


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= _MAX_ORDINAL):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    t = n - 1
    # Estimate year
    y = (t * 400 + 146097) // 146097 + 1
    # Adjust
    while 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400 > t:
        y -= 1
    while 365 * y + y // 4 - y // 100 + y // 400 <= t:
        y += 1
    f_y = 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    doy = t - f_y  # 0-indexed day of year
    # Find month and day
    if is_leap(y):
        md = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    else:
        md = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    cum = 0
    for i in range(12):
        if doy < cum + md[i]:
            return (y, i + 1, doy - cum + 1)
        cum += md[i]
    # Should not reach here
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
    o = to_ordinal(y, m, d) + n
    if o < 1 or o > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(o)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0:
        raise OverflowError("result out of range")
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty > 9999:
        raise OverflowError("result out of range")
    td = min(d, days_in_month(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = weekday(iso_year, 1, 1)
    if wd == 3:
        return 53
    if is_leap(iso_year) and wd == 2:
        return 53
    return 52


def _week1_monday_ordinal(iso_year):
    jan1 = to_ordinal(iso_year, 1, 1)
    jan1_wd = (jan1 - 1) % 7
    return jan1 + (3 - jan1_wd) % 7 - 3


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    o = to_ordinal(y, m, d)
    wd = (o - 1) % 7
    monday_o = o - wd
    thursday_o = monday_o + 3
    iso_y = from_ordinal(thursday_o)[0]
    w1m = _week1_monday_ordinal(iso_y)
    iso_w = (monday_o - w1m) // 7 + 1
    iso_wd = wd + 1
    return (iso_y, iso_w, iso_wd)


def from_iso_week(iso_year, week, weekday_):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday_, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday_ <= 7):
        raise ValueError(f"weekday {weekday_} out of range 1..7")
    w1m = _week1_monday_ordinal(iso_year)
    target_o = w1m + (week - 1) * 7 + (weekday_ - 1)
    if target_o < 1 or target_o > _MAX_ORDINAL:
        raise OverflowError("result out of range")
    return from_ordinal(target_o)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    m = _RE_EXT_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= days_in_month(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_BASIC_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= days_in_month(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_EXT_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(to_ordinal(y, 1, 1) - 1 + doy)

    m = _RE_BASIC_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return from_ordinal(to_ordinal(y, 1, 1) - 1 + doy)

    m = _RE_EXT_WEEK.match(s)
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

    m = _RE_BASIC_WEEK.match(s)
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

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_valid_date(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a str")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"
    else:
        raise ValueError(f"unknown form: {form!r}")


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    if a > b:
        y, m, d = _diff_nonneg(b, a)
        return (-y, -m, -d)
    return _diff_nonneg(a, b)


def _diff_nonneg(a, b):
    """a <= b guaranteed. Returns (years, months, days)."""
    ay, am, ad = a
    # Upper bound for K: target year must be <= 9999
    hi = (9999 - ay) * 12 + (12 - am) + 1
    lo = 0

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
    days = to_ordinal(b[0], b[1], b[2]) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)