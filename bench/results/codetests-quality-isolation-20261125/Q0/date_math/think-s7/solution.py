"""Proleptic-Gregorian calendar arithmetic for years 1..9999."""

# Cumulative days before each month (index 0 = before January)
_CUM_NL = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_L  = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)

_ORD_MAX = 3652059  # to_ordinal(9999, 12, 31)


# ---------- internal helpers (no public type-checking) ----------

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _days_before_year(y):
    """Days in years 1..y-1."""
    y -= 1
    return 365 * y + y // 4 - y // 100 + y // 400


def _days_before_month(y, m):
    cum = _CUM_L if _is_leap(y) else _CUM_NL
    return cum[m - 1]


def _to_ord(y, m, d):
    return _days_before_year(y) + _days_before_month(y, m) + d


def _from_ord(n):
    # Find year
    y = n // 365 + 1
    while _days_before_year(y) + 365 + (1 if _is_leap(y) else 0) < n:
        y += 1
    while _days_before_year(y) >= n:
        y -= 1
    doy = n - _days_before_year(y)
    cum = _CUM_L if _is_leap(y) else _CUM_NL
    m = 1
    while m <= 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def _shift_leq(a, k, b):
    """Return True if add_months(a, k) <= b (tuple comparison)."""
    total = (a[0] - 1) * 12 + (a[1] - 1) + k
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = a[2] if a[2] <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td) <= b


def _all_ascii_digits(s):
    for c in s:
        if c < '0' or c > '9':
            return False
    return True


# ---------- public API ----------

def is_leap(y):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    return _is_leap(y)


def days_in_month(y, m):
    if type(y) is not int or type(m) is not int:
        raise TypeError("y and m must be ints")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= m <= 12):
        raise ValueError("month out of range")
    return _dim(y, m)


def to_ordinal(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be ints")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= m <= 12):
        raise ValueError("month out of range")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError("day out of range")
    return _to_ord(y, m, d)


def from_ordinal(n):
    if type(n) is not int:
        raise TypeError("n must be an int")
    if not (1 <= n <= _ORD_MAX):
        raise ValueError("ordinal out of range")
    return _from_ord(n)


def weekday(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be ints")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= m <= 12):
        raise ValueError("month out of range")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError("day out of range")
    return (_to_ord(y, m, d) - 1) % 7


def add_days(date, n):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError("date elements must be ints")
    if type(n) is not int:
        raise TypeError("n must be an int")
    y, m, d = date
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= m <= 12):
        raise ValueError("month out of range")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError("day out of range")
    o = _to_ord(y, m, d) + n
    if o < 1 or o > _ORD_MAX:
        raise OverflowError("result out of range")
    return _from_ord(o)


def add_months(date, n):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError("date elements must be ints")
    if type(n) is not int:
        raise TypeError("n must be an int")
    y, m, d = date
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= m <= 12):
        raise ValueError("month out of range")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError("day out of range")
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError("result out of range")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be an int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range")
    jan1_wd = (_to_ord(iso_year, 1, 1) - 1) % 7  # 0=Mon
    if jan1_wd == 3:
        return 53
    if _is_leap(iso_year) and jan1_wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    if type(y) is not int or type(m) is not int or type(d) is not int:
        raise TypeError("y, m, d must be ints")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= m <= 12):
        raise ValueError("month out of range")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError("day out of range")
    o = _to_ord(y, m, d)
    wd = (o - 1) % 7  # 0=Mon..6=Sun
    thursday_o = o + (3 - wd)
    iso_y = _from_ord(thursday_o)[0]
    jan4_o = _to_ord(iso_y, 1, 4)
    jan4_wd = (jan4_o - 1) % 7
    monday_w1 = jan4_o - jan4_wd
    week = (o - monday_w1) // 7 + 1
    iso_wd = wd + 1  # 1=Mon..7=Sun
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday):
    if type(iso_year) is not int or type(week) is not int or type(weekday) is not int:
        raise TypeError("iso_year, week, weekday must be ints")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range")
    max_w = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_w):
        raise ValueError("week out of range")
    if not (1 <= weekday <= 7):
        raise ValueError("weekday out of range")
    jan4_o = _to_ord(iso_year, 1, 4)
    jan4_wd = (jan4_o - 1) % 7
    monday_w1 = jan4_o - jan4_wd
    target_o = monday_w1 + (week - 1) * 7 + (weekday - 1)
    if target_o < 1 or target_o > _ORD_MAX:
        raise OverflowError("result out of range")
    return _from_ord(target_o)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")
    n = len(s)

    if n == 10:
        if s[4] != '-':
            raise ValueError("invalid format")
        if s[5] == 'W':
            # Extended week: YYYY-Www-D
            if s[8] != '-':
                raise ValueError("invalid format")
            if not _all_ascii_digits(s[0:4]) or not _all_ascii_digits(s[6:8]) or not _all_ascii_digits(s[9:10]):
                raise ValueError("invalid format")
            iy = int(s[0:4])
            ww = int(s[6:8])
            wd = int(s[9])
            if not (1 <= iy <= 9999):
                raise ValueError("year out of range")
            max_w = iso_weeks_in_year(iy)
            if not (1 <= ww <= max_w):
                raise ValueError("week out of range")
            if not (1 <= wd <= 7):
                raise ValueError("weekday out of range")
            jan4_o = _to_ord(iy, 1, 4)
            jan4_wd = (jan4_o - 1) % 7
            monday_w1 = jan4_o - jan4_wd
            target_o = monday_w1 + (ww - 1) * 7 + (wd - 1)
            if target_o < 1 or target_o > _ORD_MAX:
                raise ValueError("date out of range")
            return _from_ord(target_o)
        elif s[7] == '-':
            # Extended calendar: YYYY-MM-DD
            if not _all_ascii_digits(s[0:4]) or not _all_ascii_digits(s[5:7]) or not _all_ascii_digits(s[8:10]):
                raise ValueError("invalid format")
            y = int(s[0:4])
            m = int(s[5:7])
            d = int(s[8:10])
            if not (1 <= y <= 9999):
                raise ValueError("year out of range")
            if not (1 <= m <= 12):
                raise ValueError("month out of range")
            if not (1 <= d <= _dim(y, m)):
                raise ValueError("day out of range")
            return (y, m, d)
        else:
            raise ValueError("invalid format")

    elif n == 8:
        if s[4] == '-':
            # Extended ordinal: YYYY-DDD
            if not _all_ascii_digits(s[0:4]) or not _all_ascii_digits(s[5:8]):
                raise ValueError("invalid format")
            y = int(s[0:4])
            doy = int(s[5:8])
            if not (1 <= y <= 9999):
                raise ValueError("year out of range")
            max_doy = 366 if _is_leap(y) else 365
            if not (1 <= doy <= max_doy):
                raise ValueError("day of year out of range")
            return _from_ord(_days_before_year(y) + doy)
        elif s[4] == 'W':
            # Basic week: YYYYWwwD
            if not _all_ascii_digits(s[0:4]) or not _all_ascii_digits(s[5:7]) or not _all_ascii_digits(s[7:8]):
                raise ValueError("invalid format")
            iy = int(s[0:4])
            ww = int(s[5:7])
            wd = int(s[7])
            if not (1 <= iy <= 9999):
                raise ValueError("year out of range")
            max_w = iso_weeks_in_year(iy)
            if not (1 <= ww <= max_w):
                raise ValueError("week out of range")
            if not (1 <= wd <= 7):
                raise ValueError("weekday out of range")
            jan4_o = _to_ord(iy, 1, 4)
            jan4_wd = (jan4_o - 1) % 7
            monday_w1 = jan4_o - jan4_wd
            target_o = monday_w1 + (ww - 1) * 7 + (wd - 1)
            if target_o < 1 or target_o > _ORD_MAX:
                raise ValueError("date out of range")
            return _from_ord(target_o)
        elif _all_ascii_digits(s):
            # 8 digits: try basic calendar YYYYMMDD, then basic ordinal YYYYDDD
            y = int(s[0:4])
            m = int(s[4:6])
            d = int(s[6:8])
            if 1 <= y <= 9999 and 1 <= m <= 12 and 1 <= d <= _dim(y, m):
                return (y, m, d)
            # Try ordinal
            if 1 <= y <= 9999:
                doy = int(s[4:8])
                max_doy = 366 if _is_leap(y) else 365
                if 1 <= doy <= max_doy:
                    return _from_ord(_days_before_year(y) + doy)
            raise ValueError("invalid date")
        else:
            raise ValueError("invalid format")
    else:
        raise ValueError("invalid format")


def format_date(date, form):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError("date elements must be ints")
    y, m, d = date
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= m <= 12):
        raise ValueError("month out of range")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError("day out of range")
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ord(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, ww, wd = iso_week(y, m, d)
        return f"{iy:04d}-W{ww:02d}-{wd}"


def diff(a, b):
    if type(a) is not tuple or len(a) != 3:
        raise TypeError("a must be a tuple of 3 ints")
    for x in a:
        if type(x) is not int:
            raise TypeError("a elements must be ints")
    if type(b) is not tuple or len(b) != 3:
        raise TypeError("b must be a tuple of 3 ints")
    for x in b:
        if type(x) is not int:
            raise TypeError("b elements must be ints")
    ay, am, ad = a
    by, bm, bd = b
    if not (1 <= ay <= 9999):
        raise ValueError("year out of range")
    if not (1 <= am <= 12):
        raise ValueError("month out of range")
    if not (1 <= ad <= _dim(ay, am)):
        raise ValueError("day out of range")
    if not (1 <= by <= 9999):
        raise ValueError("year out of range")
    if not (1 <= bm <= 12):
        raise ValueError("month out of range")
    if not (1 <= bd <= _dim(by, bm)):
        raise ValueError("day out of range")

    if a > b:
        yr, mo, dy = diff(b, a)
        return (-yr, -mo, -dy)

    # a <= b: find largest K >= 0 with add_months(a, K) <= b
    lo = 0
    hi = (by - ay) * 12 + 12
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _shift_leq(a, mid, b):
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    # Compute shifted date
    total = (ay - 1) * 12 + (am - 1) + K
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = ad if ad <= _dim(ty, tm) else _dim(ty, tm)
    days = _to_ord(by, bm, bd) - _to_ord(ty, tm, td)
    return (years, months, days)
