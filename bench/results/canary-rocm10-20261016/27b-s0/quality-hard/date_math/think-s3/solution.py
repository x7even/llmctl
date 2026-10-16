import re


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date_tuple(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(v).__name__}")


def _check_date_range(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = days_in_month(y, m)
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
    if m in (4, 6, 9, 11):
        return 30
    return 31


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    yy = y - 1
    days = 365 * yy + yy // 4 - yy // 100 + yy // 400
    if is_leap(y):
        cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
    else:
        cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    days += cum[m - 1] + d
    return days


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi) // 2
        dm = 365 * mid + mid // 4 - mid // 100 + mid // 400
        if dm < n:
            lo = mid + 1
        else:
            hi = mid
    y = lo
    prev = 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    doy = n - prev
    if is_leap(y):
        cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
    else:
        cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    m = 1
    while m < 12 and cum[m] < doy:
        m += 1
    d = doy - cum[m - 1]
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
    result = to_ordinal(y, m, d) + n
    if result < 1 or result > 3652059:
        raise OverflowError("result out of supported range")
    return from_ordinal(result)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    if total < 0 or total > 9999 * 12 + 11:
        raise OverflowError("result out of supported range")
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = min(d, days_in_month(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if wd == 3 or (is_leap(iso_year) and wd == 2):
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date_range(y, m, d)
    ord_ = to_ordinal(y, m, d)
    jan4_ord = to_ordinal(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    delta = ord_ - monday_w1
    iso_wd = delta % 7 + 1
    iso_wk = delta // 7 + 1
    if iso_wk < 1:
        iso_yr = y - 1
        iso_wk = iso_weeks_in_year(iso_yr)
    elif iso_wk > iso_weeks_in_year(y):
        iso_yr = y + 1
        iso_wk = 1
    else:
        iso_yr = y
    return (iso_yr, iso_wk, iso_wd)


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
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    monday_w1 = jan4_ord - jan4_wd
    target = monday_w1 + (week - 1) * 7 + (weekday_ - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of supported range")
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
        _validate_cal(y, mo, d)
        return (y, mo, d)

    m = _RE_BAS_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _validate_cal(y, mo, d)
        return (y, mo, d)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        _validate_ord(y, doy)
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_BAS_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        _validate_ord(y, doy)
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _validate_wk(y, wk, wd)
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("week date resolves outside supported range")

    m = _RE_BAS_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _validate_wk(y, wk, wd)
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError("week date resolves outside supported range")

    raise ValueError(f"invalid date string: {s!r}")


def _validate_cal(y, mo, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= mo <= 12):
        raise ValueError(f"month {mo} out of range 1..12")
    if not (1 <= d <= days_in_month(y, mo)):
        raise ValueError(f"day {d} out of range for {y}-{mo:02d}")


def _validate_ord(y, doy):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    max_doy = 366 if is_leap(y) else 365
    if not (1 <= doy <= max_doy):
        raise ValueError(f"day of year {doy} out of range 1..{max_doy}")


def _validate_wk(y, wk, wd):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    max_wk = iso_weeks_in_year(y)
    if not (1 <= wk <= max_wk):
        raise ValueError(f"week {wk} out of range 1..{max_wk}")
    if not (1 <= wd <= 7):
        raise ValueError(f"weekday {wd} out of range 1..7")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date_range(y, m, d)
    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date_range(ay, am, ad)
    _check_date_range(by, bm, bd)

    a_ord = to_ordinal(ay, am, ad)
    b_ord = to_ordinal(by, bm, bd)

    if a_ord > b_ord:
        years, months, days = diff(b, a)
        return (-years, -months, -days)

    # a <= b: find largest K >= 0 with shift(a, K) <= b
    max_K = 119987 - (ay - 1) * 12 - (am - 1)
    hi = (by - ay) * 12 + (bm - am) + 13
    if hi > max_K:
        hi = max_K
    if hi < 0:
        hi = 0

    def shift_ord(K):
        total = (ay - 1) * 12 + (am - 1) + K
        ty = total // 12 + 1
        tm = total % 12 + 1
        td = ad if ad <= days_in_month(ty, tm) else days_in_month(ty, tm)
        yy = ty - 1
        days = 365 * yy + yy // 4 - yy // 100 + yy // 400
        if is_leap(ty):
            cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
        else:
            cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
        return days + cum[tm - 1] + td

    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if shift_ord(mid) <= b_ord:
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    days = b_ord - shift_ord(K)
    return (years, months, days)