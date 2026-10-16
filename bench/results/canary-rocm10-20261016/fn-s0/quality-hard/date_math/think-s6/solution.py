import re

_MAX_ORD = 3652059

_CUM_NORM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
_DIM_NORM = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_DIM_LEAP = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def _dim(y, m):
    return _DIM_LEAP[m - 1] if _is_leap(y) else _DIM_NORM[m - 1]


def _to_ord(y, m, d):
    yy = y - 1
    ld = yy // 4 - yy // 100 + yy // 400
    cum = _CUM_LEAP[m - 1] if _is_leap(y) else _CUM_NORM[m - 1]
    return 365 * yy + ld + cum + d


def _from_ord(n):
    z = (n - 1) * 400 // 146097
    # adjust z so that _db(z) <= n-1 < _db(z+1) where _db(z) = days before year z+1
    def _db(z):
        return 365 * z + z // 4 - z // 100 + z // 400
    while _db(z + 1) > n - 1:
        z -= 1
    while _db(z + 2) <= n - 1:
        z += 1
    y = z + 1
    doy = n - _db(z)
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NORM
    m = 1
    while m < 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def _weekday(y, m, d):
    return (_to_ord(y, m, d) - 1) % 7


def _iso_weeks_in_year(iy):
    dow = _weekday(iy, 1, 1)  # Mon=0..Sun=6
    if dow == 3:
        return 53
    if dow == 2 and _is_leap(iy):
        return 53
    return 52


def _iso_week(y, m, d):
    o = _to_ord(y, m, d)
    iso_dow = _weekday(y, m, d) + 1  # Mon=1..Sun=7
    thu = o + (4 - iso_dow)
    iso_year = _from_ord(thu)[0]
    jan1 = _to_ord(iso_year, 1, 1)
    jan1_dow = _weekday(iso_year, 1, 1) + 1
    first_thu = jan1 + (4 - jan1_dow) % 7
    week = (thu - first_thu) // 7 + 1
    return (iso_year, week, iso_dow)


# --- type / range checking helpers ---

def _ck_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _ck_date(d, name):
    if type(d) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(d) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i in range(3):
        if type(d[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(d[i]).__name__}")


def _ck_date_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")


# --- public API ---

def is_leap(y):
    _ck_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _ck_int(y, 'y')
    _ck_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError("year out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError("month out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _ck_int(y, 'y')
    _ck_int(m, 'm')
    _ck_int(d, 'd')
    _ck_date_range(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    _ck_int(n, 'n')
    if n < 1 or n > _MAX_ORD:
        raise ValueError("ordinal out of range 1..3652059")
    return _from_ord(n)


def weekday(y, m, d):
    _ck_int(y, 'y')
    _ck_int(m, 'm')
    _ck_int(d, 'd')
    _ck_date_range(y, m, d)
    return _weekday(y, m, d)


def add_days(date, n):
    _ck_date(date, 'date')
    _ck_int(n, 'n')
    y, m, d = date
    _ck_date_range(y, m, d)
    o = _to_ord(y, m, d) + n
    if o < 1 or o > _MAX_ORD:
        raise OverflowError("result date out of range")
    return _from_ord(o)


def add_months(date, n):
    _ck_date(date, 'date')
    _ck_int(n, 'n')
    y, m, d = date
    _ck_date_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("target year out of range 1..9999")
    td = min(d, _dim(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _ck_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range 1..9999")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    _ck_int(y, 'y')
    _ck_int(m, 'm')
    _ck_int(d, 'd')
    _ck_date_range(y, m, d)
    return _iso_week(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _ck_int(iso_year, 'iso_year')
    _ck_int(week, 'week')
    _ck_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range 1..9999")
    nw = _iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError("week out of range")
    if weekday < 1 or weekday > 7:
        raise ValueError("weekday out of range 1..7")
    jan1 = _to_ord(iso_year, 1, 1)
    jan1_dow = _weekday(iso_year, 1, 1) + 1
    first_thu = jan1 + (4 - jan1_dow) % 7
    mon_w1 = first_thu - 3
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError("result date out of range")
    return _from_ord(target)


# --- parse / format ---

_RE_CAL_EXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_CAL_BASIC = re.compile(r'([0-9]{8})')
_RE_ORD_EXT = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_ORD_BASIC = re.compile(r'([0-9]{7})')
_RE_WK_EXT = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_WK_BASIC = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def _parse_cal(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    if m < 1 or m > 12:
        raise ValueError("month out of range")
    if d < 1 or d > _dim(y, m):
        raise ValueError("day out of range")
    return (y, m, d)


def _parse_ord(y, doy):
    if y < 1 or y > 9999:
        raise ValueError("year out of range")
    max_doy = 366 if _is_leap(y) else 365
    if doy < 1 or doy > max_doy:
        raise ValueError("day of year out of range")
    cum = _CUM_LEAP if _is_leap(y) else _CUM_NORM
    m = 1
    while m < 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def _parse_week(iso_year, week, wd):
    if iso_year < 1 or iso_year > 9999:
        raise ValueError("iso_year out of range")
    nw = _iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError("week out of range")
    if wd < 1 or wd > 7:
        raise ValueError("weekday out of range")
    jan1 = _to_ord(iso_year, 1, 1)
    jan1_dow = _weekday(iso_year, 1, 1) + 1
    first_thu = jan1 + (4 - jan1_dow) % 7
    mon_w1 = first_thu - 3
    target = mon_w1 + (week - 1) * 7 + (wd - 1)
    if target < 1 or target > _MAX_ORD:
        raise ValueError("date out of range")
    return _from_ord(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    n = len(s)
    if n == 10:
        if s[4] == '-' and s[5] == 'W':
            mt = _RE_WK_EXT.fullmatch(s)
            if mt is None:
                raise ValueError("invalid date string")
            return _parse_week(int(mt.group(1)), int(mt.group(2)), int(mt.group(3)))
        elif s[4] == '-':
            mt = _RE_CAL_EXT.fullmatch(s)
            if mt is None:
                raise ValueError("invalid date string")
            return _parse_cal(int(mt.group(1)), int(mt.group(2)), int(mt.group(3)))
        else:
            raise ValueError("invalid date string")
    elif n == 8:
        if s[4] == '-':
            mt = _RE_ORD_EXT.fullmatch(s)
            if mt is None:
                raise ValueError("invalid date string")
            return _parse_ord(int(mt.group(1)), int(mt.group(2)))
        elif s[4] == 'W':
            mt = _RE_WK_BASIC.fullmatch(s)
            if mt is None:
                raise ValueError("invalid date string")
            return _parse_week(int(mt.group(1)), int(mt.group(2)), int(mt.group(3)))
        else:
            mt = _RE_CAL_BASIC.fullmatch(s)
            if mt is None:
                raise ValueError("invalid date string")
            return _parse_cal(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    elif n == 7:
        mt = _RE_ORD_BASIC.fullmatch(s)
        if mt is None:
            raise ValueError("invalid date string")
        return _parse_ord(int(s[0:4]), int(s[4:7]))
    else:
        raise ValueError("invalid date string")


def format_date(date, form):
    _ck_date(date, 'date')
    y, m, d = date
    _ck_date_range(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError("invalid form")
    if form == 'calendar':
        return f'{y:04d}-{m:02d}-{d:02d}'
    elif form == 'ordinal':
        doy = _to_ord(y, m, d) - _to_ord(y, 1, 1) + 1
        return f'{y:04d}-{doy:03d}'
    else:
        iy, iw, iwd = _iso_week(y, m, d)
        return f'{iy:04d}-W{iw:02d}-{iwd}'


def diff(a, b):
    _ck_date(a, 'a')
    _ck_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _ck_date_range(ay, am, ad)
    _ck_date_range(by, bm, bd)

    if a == b:
        return (0, 0, 0)

    negate = False
    if a > b:
        ay, am, ad, by, bm, bd = by, bm, bd, ay, am, ad
        negate = True

    # Now a < b (strictly). Find largest K >= 0 with shift(a,K) <= b.
    K_est = (by - ay) * 12 + (bm - am)

    # compute shift(a, K_est)
    total = (ay - 1) * 12 + (am - 1) + K_est
    ty = total // 12 + 1
    tm = total % 12 + 1
    td = min(ad, _dim(ty, tm))
    shift_ord = _to_ord(ty, tm, td)
    b_ord = _to_ord(by, bm, bd)

    if shift_ord <= b_ord:
        K = K_est
    else:
        K = K_est - 1
        total = (ay - 1) * 12 + (am - 1) + K
        ty = total // 12 + 1
        tm = total % 12 + 1
        td = min(ad, _dim(ty, tm))
        shift_ord = _to_ord(ty, tm, td)

    years, months = divmod(K, 12)
    days = b_ord - shift_ord

    if negate:
        return (-years, -months, -days)
    return (years, months, days)
