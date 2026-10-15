import re

MAXORD = 3652059
_DIM = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _int(*vals):
    for v in vals:
        if type(v) is not int:
            raise TypeError(f"expected int, got {type(v).__name__}")


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    return 29 if m == 2 and _leap(y) else _DIM[m - 1]


def _check(y, m, d):
    if not (1 <= y <= 9999 and 1 <= m <= 12 and 1 <= d <= _dim(y, m)):
        raise ValueError(f"invalid date {(y, m, d)}")


def _date(date):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError("date must be a 3-tuple")
    _int(*date)
    return date


def _ord(y, m, d):
    y1 = y - 1
    return y1 * 365 + y1 // 4 - y1 // 100 + y1 // 400 + _CUM[m - 1] + (1 if m > 2 and _leap(y) else 0) + d


def _fromord(n):
    n -= 1
    c400, n = divmod(n, 146097)
    c100, n = divmod(n, 36524)
    if c100 == 4:  # last day of a 400-year cycle
        c100, n = 3, n + 36524
    c4, n = divmod(n, 1461)
    c1, n = divmod(n, 365)
    if c1 == 4:  # last day of a 4-year cycle
        c1, n = 3, n + 365
    y = c400 * 400 + c100 * 100 + c4 * 4 + c1 + 1
    # n is now the 0-based day of year
    m = 1
    while True:
        dim = _dim(y, m)
        if n < dim:
            return (y, m, n + 1)
        n -= dim
        m += 1


def _wd(o):
    return (o - 1) % 7


def _weeks(iso_year):
    jan1 = _wd(_ord(iso_year, 1, 1))
    return 53 if jan1 == 3 or (jan1 == 2 and _leap(iso_year)) else 52


def _isoweek(o):
    wd = _wd(o)
    thu = o - wd + 3
    iy = _fromord(thu)[0]
    return (iy, (thu - _ord(iy, 1, 1)) // 7 + 1, wd + 1)


def _from_iso(iy, w, wd):
    jan4 = _ord(iy, 1, 4)
    mon1 = jan4 - _wd(jan4)
    return mon1 + (w - 1) * 7 + (wd - 1)


def _addmonths(date, n):
    y, m, d = date
    t = y * 12 + (m - 1) + n
    ny, nm = divmod(t, 12)
    if not (1 <= ny <= 9999):
        raise OverflowError("year out of range")
    nm += 1
    return (ny, nm, min(d, _dim(ny, nm)))


def is_leap(y):
    _int(y)
    if not 1 <= y <= 9999:
        raise ValueError("year out of range")
    return _leap(y)


def days_in_month(y, m):
    _int(y, m)
    if not (1 <= y <= 9999 and 1 <= m <= 12):
        raise ValueError("bad year/month")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _int(y, m, d)
    _check(y, m, d)
    return _ord(y, m, d)


def from_ordinal(n):
    _int(n)
    if not 1 <= n <= MAXORD:
        raise ValueError("ordinal out of range")
    return _fromord(n)


def weekday(y, m, d):
    _int(y, m, d)
    _check(y, m, d)
    return _wd(_ord(y, m, d))


def add_days(date, n):
    _date(date)
    _int(n)
    _check(*date)
    o = _ord(*date) + n
    if not 1 <= o <= MAXORD:
        raise OverflowError("date out of range")
    return _fromord(o)


def add_months(date, n):
    _date(date)
    _int(n)
    _check(*date)
    return _addmonths(date, n)


def iso_weeks_in_year(iso_year):
    _int(iso_year)
    if not 1 <= iso_year <= 9999:
        raise ValueError("year out of range")
    return _weeks(iso_year)


def iso_week(y, m, d):
    _int(y, m, d)
    _check(y, m, d)
    return _isoweek(_ord(y, m, d))


def from_iso_week(iso_year, week, weekday):
    _int(iso_year, week, weekday)
    if not 1 <= iso_year <= 9999:
        raise ValueError("iso year out of range")
    if not 1 <= weekday <= 7:
        raise ValueError("weekday out of range")
    if not 1 <= week <= _weeks(iso_year):
        raise ValueError("week out of range")
    o = _from_iso(iso_year, week, weekday)
    if not 1 <= o <= MAXORD:
        raise OverflowError("date out of range")
    return _fromord(o)


_CAL_EXT = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_CAL_BAS = re.compile(r"([0-9]{4})([0-9]{2})([0-9]{2})")
_ORD_EXT = re.compile(r"([0-9]{4})-([0-9]{3})")
_ORD_BAS = re.compile(r"([0-9]{4})([0-9]{3})")
_WK_EXT = re.compile(r"([0-9]{4})-W([0-9]{2})-([0-9])")
_WK_BAS = re.compile(r"([0-9]{4})W([0-9]{2})([0-9])")


def parse(s):
    if type(s) is not str:
        raise TypeError("expected str")
    for rx in (_CAL_EXT, _CAL_BAS):
        mo = rx.fullmatch(s)
        if mo:
            y, m, d = map(int, mo.groups())
            try:
                _check(y, m, d)
            except ValueError:
                raise ValueError(f"invalid date: {s!r}") from None
            return (y, m, d)
    for rx in (_ORD_EXT, _ORD_BAS):
        mo = rx.fullmatch(s)
        if mo:
            y, doy = map(int, mo.groups())
            if not (1 <= y <= 9999 and 1 <= doy <= (366 if _leap(y) else 365)):
                raise ValueError(f"invalid ordinal date: {s!r}")
            return _fromord(_ord(y, 1, 1) + doy - 1)
    for rx in (_WK_EXT, _WK_BAS):
        mo = rx.fullmatch(s)
        if mo:
            iy, w, wd = map(int, mo.groups())
            try:
                return from_iso_week(iy, w, wd)
            except OverflowError:
                raise ValueError(f"week date beyond range: {s!r}") from None
    raise ValueError(f"unrecognised date: {s!r}")


def format_date(date, form):
    _date(date)
    _check(*date)
    y, m, d = date
    if form == "calendar" and type(form) is str:
        return f"{y:04d}-{m:02d}-{d:02d}"
    if form == "ordinal" and type(form) is str:
        return f"{y:04d}-{_ord(y, m, d) - _ord(y, 1, 1) + 1:03d}"
    if form == "week" and type(form) is str:
        iy, w, wd = _isoweek(_ord(y, m, d))
        return f"{iy:04d}-W{w:02d}-{wd}"
    raise ValueError(f"unknown form {form!r}")


def diff(a, b):
    _date(a)
    _date(b)
    _check(*a)
    _check(*b)
    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
    k = (b[0] - a[0]) * 12 + (b[1] - a[1])
    s = _addmonths(a, k)
    if s > b:
        k -= 1
        s = _addmonths(a, k)
    return (k // 12, k % 12, _ord(*b) - _ord(*s))
