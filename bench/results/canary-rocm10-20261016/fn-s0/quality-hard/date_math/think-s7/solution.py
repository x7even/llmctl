"""Proleptic-Gregorian calendar arithmetic for years 1 through 9999.

No datetime/calendar/time/dateutil/email.utils imports; pure integer arithmetic.
"""

_CUM_DAYS = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MAX_ORDINAL = 3652059  # (9999, 12, 31)


# ─── internal helpers ──────────────────────────────────────────────────────────

def _is_int(x):
    return type(x) is int


def _check_ints(*args):
    for a in args:
        if type(a) is not int:
            raise TypeError(f"expected int, got {type(a).__name__}")


def _check_date(d):
    if type(d) is not tuple or len(d) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    if type(d[0]) is not int or type(d[1]) is not int or type(d[2]) is not int:
        raise TypeError("date must be a tuple of 3 ints")


def _check_date_range(d):
    y, m, dd = d
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if dd < 1 or dd > days_in_month(y, m):
        raise ValueError("day out of range")


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _to_ord(y, m, d):
    """Un-checked ordinal (caller guarantees valid y,m,d)."""
    days = 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    days += _CUM_DAYS[m - 1]
    if m > 2 and _leap(y):
        days += 1
    return days + d


def _from_ord(n):
    """Un-checked from_ordinal (caller guarantees 1 <= n <= _MAX_ORDINAL)."""
    z = n - 1
    n400, z = divmod(z, 146097)
    n100, z = divmod(z, 36524)
    if n100 == 4:
        n100 = 3
        z = 36524
    n4, z = divmod(z, 1461)
    if z >= 1095:
        year_in_group = 3
        z -= 1095
    else:
        year_in_group = z // 365
        z %= 365
    year = 400 * n400 + 100 * n100 + 4 * n4 + year_in_group + 1
    # find month / day
    if _leap(year):
        cum = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
    else:
        cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    lo, hi = 0, 11
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if cum[mid] <= z:
            lo = mid
        else:
            hi = mid - 1
    return (year, lo + 1, z - cum[lo] + 1)


def _ascii_digit(c):
    return '0' <= c <= '9'


# ─── public API ────────────────────────────────────────────────────────────────

def is_leap(y):
    _check_ints(y)
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    return _leap(y)


def days_in_month(y, m):
    _check_ints(y, m)
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if m == 2 and _leap(y):
        return 29
    return _MONTH_DAYS[m - 1]


def to_ordinal(y, m, d):
    _check_ints(y, m, d)
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")
    return _to_ord(y, m, d)


def from_ordinal(n):
    _check_ints(n)
    if n < 1 or n > _MAX_ORDINAL:
        raise ValueError("ordinal out of range")
    return _from_ord(n)


def weekday(y, m, d):
    _check_ints(y, m, d)
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")
    return (_to_ord(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date)
    _check_date_range(date)
    _check_ints(n)
    new_ord = _to_ord(*date) + n
    if new_ord < 1 or new_ord > _MAX_ORDINAL:
        raise OverflowError("result date out of range")
    return _from_ord(new_ord)


def add_months(date, n):
    _check_date(date)
    _check_date_range(date)
    _check_ints(n)
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if new_y < 1 or new_y > 9999:
        raise OverflowError("target year out of range")
    max_d = _MONTH_DAYS[new_m - 1]
    if new_m == 2 and _leap(new_y):
        max_d = 29
    new_d = d if d <= max_d else max_d
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    _check_ints(iso_year)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("year out of range")
    wd = (_to_ord(iso_year, 1, 1) - 1) % 7  # Mon=0..Sun=6
    if wd == 3:  # Thursday
        return 53
    if wd == 2 and _leap(iso_year):  # Wednesday + leap
        return 53
    return 52


def iso_week(y, m, d):
    _check_ints(y, m, d)
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > days_in_month(y, m):
        raise ValueError("day out of range")

    ord_val = _to_ord(y, m, d)
    wd = (ord_val - 1) % 7       # Mon=0..Sun=6
    iso_wd = wd + 1              # Mon=1..Sun=7
    monday = ord_val - wd

    jan4 = _to_ord(y, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    week1_mon = jan4 - jan4_wd
    week = (monday - week1_mon) // 7 + 1

    if week < 1:
        y -= 1
        jan4 = _to_ord(y, 1, 4)
        jan4_wd = (jan4 - 1) % 7
        week1_mon = jan4 - jan4_wd
        week = (monday - week1_mon) // 7 + 1
    elif week > 52:
        if monday + 3 > _to_ord(y, 12, 31):
            y += 1
            jan4 = _to_ord(y, 1, 4)
            jan4_wd = (jan4 - 1) % 7
            week1_mon = jan4 - jan4_wd
            week = (monday - week1_mon) // 7 + 1

    return (y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _check_ints(iso_year, week, weekday)
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    if week < 1 or week > iso_weeks_in_year(iso_year):
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range")

    jan4 = _to_ord(iso_year, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    week1_mon = jan4 - jan4_wd
    target = week1_mon + (week - 1) * 7 + (weekday - 1)

    if target < 1 or target > _MAX_ORDINAL:
        raise OverflowError("result date out of range")
    return _from_ord(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("expected str")
    n = len(s)

    if n == 10:
        # YYYY-MM-DD  or  YYYY-Www-D
        if not (_ascii_digit(s[0]) and _ascii_digit(s[1]) and
                _ascii_digit(s[2]) and _ascii_digit(s[3])):
            raise ValueError("invalid format")
        if s[4] != '-':
            raise ValueError("invalid format")
        if s[5] == 'W':
            # extended week: YYYY-Www-D
            if not (_ascii_digit(s[6]) and _ascii_digit(s[7])):
                raise ValueError("invalid format")
            if s[8] != '-':
                raise ValueError("invalid format")
            if not _ascii_digit(s[9]):
                raise ValueError("invalid format")
            yr = int(s[0:4]); wk = int(s[6:8]); wd = int(s[9])
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if wk < 1 or wk > iso_weeks_in_year(yr):
                raise ValueError("week out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            jan4 = _to_ord(yr, 1, 4)
            w1m = jan4 - (jan4 - 1) % 7
            tgt = w1m + (wk - 1) * 7 + (wd - 1)
            if tgt < 1 or tgt > _MAX_ORDINAL:
                raise ValueError("date out of range")
            return _from_ord(tgt)
        else:
            # extended calendar: YYYY-MM-DD
            if not (_ascii_digit(s[5]) and _ascii_digit(s[6])):
                raise ValueError("invalid format")
            if s[7] != '-':
                raise ValueError("invalid format")
            if not (_ascii_digit(s[8]) and _ascii_digit(s[9])):
                raise ValueError("invalid format")
            yr = int(s[0:4]); mo = int(s[5:7]); dy = int(s[8:10])
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if mo < 1 or mo > 12:
                raise ValueError("month out of range")
            if dy < 1 or dy > days_in_month(yr, mo):
                raise ValueError("day out of range")
            return (yr, mo, dy)

    elif n == 8:
        if s[4] == '-':
            # extended ordinal: YYYY-DDD
            if not (_ascii_digit(s[0]) and _ascii_digit(s[1]) and
                    _ascii_digit(s[2]) and _ascii_digit(s[3])):
                raise ValueError("invalid format")
            if not (_ascii_digit(s[5]) and _ascii_digit(s[6]) and
                    _ascii_digit(s[7])):
                raise ValueError("invalid format")
            yr = int(s[0:4]); doy = int(s[5:8])
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            mx = 366 if _leap(yr) else 365
            if doy < 1 or doy > mx:
                raise ValueError("day out of range")
            return _from_ord(_to_ord(yr, 1, 1) + doy - 1)
        elif s[4] == 'W':
            # basic week: YYYYWwwD
            if not (_ascii_digit(s[0]) and _ascii_digit(s[1]) and
                    _ascii_digit(s[2]) and _ascii_digit(s[3])):
                raise ValueError("invalid format")
            if not (_ascii_digit(s[5]) and _ascii_digit(s[6])):
                raise ValueError("invalid format")
            if not _ascii_digit(s[7]):
                raise ValueError("invalid format")
            yr = int(s[0:4]); wk = int(s[5:7]); wd = int(s[7])
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if wk < 1 or wk > iso_weeks_in_year(yr):
                raise ValueError("week out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            jan4 = _to_ord(yr, 1, 4)
            w1m = jan4 - (jan4 - 1) % 7
            tgt = w1m + (wk - 1) * 7 + (wd - 1)
            if tgt < 1 or tgt > _MAX_ORDINAL:
                raise ValueError("date out of range")
            return _from_ord(tgt)
        else:
            # basic calendar: YYYYMMDD
            if not all(_ascii_digit(s[i]) for i in range(8)):
                raise ValueError("invalid format")
            yr = int(s[0:4]); mo = int(s[4:6]); dy = int(s[6:8])
            if yr < 1 or yr > 9999:
                raise ValueError("year out of range")
            if mo < 1 or mo > 12:
                raise ValueError("month out of range")
            if dy < 1 or dy > days_in_month(yr, mo):
                raise ValueError("day out of range")
            return (yr, mo, dy)

    elif n == 7:
        # basic ordinal: YYYYDDD
        if not all(_ascii_digit(s[i]) for i in range(7)):
            raise ValueError("invalid format")
        yr = int(s[0:4]); doy = int(s[4:7])
        if yr < 1 or yr > 9999:
            raise ValueError("year out of range")
        mx = 366 if _leap(yr) else 365
        if doy < 1 or doy > mx:
            raise ValueError("day out of range")
        return _from_ord(_to_ord(yr, 1, 1) + doy - 1)

    else:
        raise ValueError("invalid format")


def format_date(date, form):
    _check_date(date)
    _check_date_range(date)
    # form check (after date checks); non-strings also raise ValueError
    if form == 'calendar':
        y, m, d = date
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        y, m, d = date
        doy = _to_ord(y, m, d) - _to_ord(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        y, m, d = date
        iy, iw, iwd = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"
    else:
        raise ValueError("invalid form")


def diff(a, b):
    _check_date(a)
    _check_date_range(a)
    _check_date(b)
    _check_date_range(b)

    if a == b:
        return (0, 0, 0)
    if a > b:
        yr, mo, dy = diff(b, a)
        return (-yr, -mo, -dy)

    # a < b: binary-search largest K >= 0 with add_months(a, K) <= b
    lo = 0
    hi = (b[0] - a[0] + 2) * 12
    while lo < hi:
        mid = (lo + hi + 1) >> 1
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
    days = _to_ord(*b) - _to_ord(*shifted)
    return (years, months, days)
