import re

# ─── Internal helpers ───────────────────────────────────────────────────────

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31

def _dbefore_year(y):
    """Total days in years 1 through y-1."""
    t = y - 1
    return 365 * t + t // 4 - t // 100 + t // 400

def _dbefore_month(y, m):
    """Total days in months 1 through m-1 of year y."""
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    r = cum[m - 1]
    if m > 2 and _is_leap(y):
        r += 1
    return r

def _to_ord(y, m, d):
    return _dbefore_year(y) + _dbefore_month(y, m) + d

def _from_ord(n):
    """Inverse of _to_ord. n is in 1..3652059."""
    y = (n * 400) // 146097
    if y < 1:
        y = 1
    while _dbefore_year(y + 1) < n:
        y += 1
    while _dbefore_year(y) >= n:
        y -= 1
    doy = n - _dbefore_year(y)
    m = 1
    while m <= 12:
        dm = _dim(y, m)
        if doy <= dm:
            break
        doy -= dm
        m += 1
    return (y, m, doy)

def _weekday(y, m, d):
    """Monday=0 … Sunday=6."""
    return (_to_ord(y, m, d) - 1) % 7

def _add_months_raw(y, m, d, n):
    """add_months arithmetic without range-checking the result year."""
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)

def _iso_weeks_in_year(iy):
    wd = _weekday(iy, 1, 1)
    if wd == 3:
        return 53
    if wd == 2 and _is_leap(iy):
        return 53
    return 52

def _monday_of_week1(iy):
    """Ordinal of the Monday of ISO week 1 of ISO year iy."""
    o1 = _to_ord(iy, 1, 1)
    o4 = o1 + 3
    wd4 = (o4 - 1) % 7
    return o4 - wd4

# ─── Regex patterns for parse ───────────────────────────────────────────────

_RE_CAL_EXT = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_CAL_BAS = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_ORD_EXT = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_ORD_BAS = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_WK_EXT  = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9]{1})$')
_RE_WK_BAS  = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9]{1})$')

_MAX_ORD = 3652059

# ─── Public API ─────────────────────────────────────────────────────────────

def is_leap(y):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    return _is_leap(y)

def days_in_month(y, m):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= m <= 12):
        raise ValueError("month out of range")
    return _dim(y, m)

def to_ordinal(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if type(d) is not int:
        raise TypeError("d must be an int")
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
    if not (1 <= n <= _MAX_ORD):
        raise ValueError("n out of range")
    return _from_ord(n)

def weekday(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if type(d) is not int:
        raise TypeError("d must be an int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= m <= 12):
        raise ValueError("month out of range")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError("day out of range")
    return _weekday(y, m, d)

def add_days(date, n):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError("date must be a tuple of 3 ints")
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
    if o < 1 or o > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(o)

def add_months(date, n):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError("date must be a tuple of 3 ints")
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
    if total < 0 or total >= 9999 * 12:
        raise OverflowError("result out of range")
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)

def iso_weeks_in_year(iso_year):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be an int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range")
    return _iso_weeks_in_year(iso_year)

def iso_week(y, m, d):
    if type(y) is not int:
        raise TypeError("y must be an int")
    if type(m) is not int:
        raise TypeError("m must be an int")
    if type(d) is not int:
        raise TypeError("d must be an int")
    if not (1 <= y <= 9999):
        raise ValueError("year out of range")
    if not (1 <= m <= 12):
        raise ValueError("month out of range")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError("day out of range")
    o = _to_ord(y, m, d)
    wd = (o - 1) % 7
    iso_wd = wd + 1
    mow = o - wd
    thu = mow + 3
    iy = _from_ord(thu)[0]
    mw1 = _monday_of_week1(iy)
    week = (mow - mw1) // 7 + 1
    return (iy, week, iso_wd)

def from_iso_week(iso_year, week, weekday):
    if type(iso_year) is not int:
        raise TypeError("iso_year must be an int")
    if type(week) is not int:
        raise TypeError("week must be an int")
    if type(weekday) is not int:
        raise TypeError("weekday must be an int")
    if not (1 <= iso_year <= 9999):
        raise ValueError("iso_year out of range")
    max_week = _iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError("week out of range")
    if not (1 <= weekday <= 7):
        raise ValueError("weekday out of range")
    mw1 = _monday_of_week1(iso_year)
    o = mw1 + (week - 1) * 7 + (weekday - 1)
    if o < 1 or o > _MAX_ORD:
        raise OverflowError("result out of range")
    return _from_ord(o)

def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    m = _RE_CAL_EXT.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_CAL_BAS.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        if not (1 <= mo <= 12):
            raise ValueError("month out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError("day out of range")
        return (y, mo, d)

    m = _RE_ORD_EXT.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return _from_ord(_dbefore_year(y) + doy)

    m = _RE_ORD_BAS.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError("day of year out of range")
        return _from_ord(_dbefore_year(y) + doy)

    m = _RE_WK_EXT.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_wk = _iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        mw1 = _monday_of_week1(y)
        o = mw1 + (wk - 1) * 7 + (wd - 1)
        if o < 1 or o > _MAX_ORD:
            raise ValueError("date out of range")
        return _from_ord(o)

    m = _RE_WK_BAS.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError("year out of range")
        max_wk = _iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError("week out of range")
        if not (1 <= wd <= 7):
            raise ValueError("weekday out of range")
        mw1 = _monday_of_week1(y)
        o = mw1 + (wk - 1) * 7 + (wd - 1)
        if o < 1 or o > _MAX_ORD:
            raise ValueError("date out of range")
        return _from_ord(o)

    raise ValueError("unrecognized date format")

def format_date(date, form):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a tuple of 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError("date must be a tuple of 3 ints")
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
        doy = _dbefore_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    else:
        iy, wk, wd = iso_week(y, m, d)
        return f"{iy:04d}-W{wk:02d}-{wd:01d}"

def diff(a, b):
    if type(a) is not tuple or len(a) != 3:
        raise TypeError("a must be a tuple of 3 ints")
    for x in a:
        if type(x) is not int:
            raise TypeError("a must be a tuple of 3 ints")
    if type(b) is not tuple or len(b) != 3:
        raise TypeError("b must be a tuple of 3 ints")
    for x in b:
        if type(x) is not int:
            raise TypeError("b must be a tuple of 3 ints")
    ay, am, ad = a
    if not (1 <= ay <= 9999):
        raise ValueError("year out of range")
    if not (1 <= am <= 12):
        raise ValueError("month out of range")
    if not (1 <= ad <= _dim(ay, am)):
        raise ValueError("day out of range")
    by, bm, bd = b
    if not (1 <= by <= 9999):
        raise ValueError("year out of range")
    if not (1 <= bm <= 12):
        raise ValueError("month out of range")
    if not (1 <= bd <= _dim(by, bm)):
        raise ValueError("day out of range")

    if a <= b:
        K_approx = (by - ay) * 12 + (bm - am)
        if K_approx < 0:
            K = 0
        else:
            s = _add_months_raw(ay, am, ad, K_approx)
            if s <= b:
                K = K_approx
            else:
                K = K_approx - 1
        years, months = divmod(K, 12)
        shifted = _add_months_raw(ay, am, ad, K)
        days = _to_ord(by, bm, bd) - _to_ord(shifted[0], shifted[1], shifted[2])
        return (years, months, days)
    else:
        years, months, days = diff(b, a)
        return (-years, -months, -days)