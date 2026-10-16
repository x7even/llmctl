import re

__all__ = [
    'is_leap', 'days_in_month', 'to_ordinal', 'from_ordinal', 'weekday',
    'add_days', 'add_months', 'iso_weeks_in_year', 'iso_week', 'from_iso_week',
    'parse', 'format_date', 'diff',
]

_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)
_DIM_NONLEAP = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_DIM_LEAP = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MAX_ORD = 3652059


def _ci(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int")


def _cd(date, name='date'):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if type(date[0]) is not int or type(date[1]) is not int or type(date[2]) is not int:
        raise TypeError(f"{name} must be a tuple of 3 ints")


def _cdr(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range")
    if d < 1 or d > (_DIM_LEAP[m - 1] if (y % 4 == 0 and y % 100 != 0 or y % 400 == 0) else _DIM_NONLEAP[m - 1]):
        raise ValueError(f"day {d} out of range for month {m} of year {y}")


def is_leap(y):
    _ci(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range")
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)


def days_in_month(y, m):
    _ci(y, 'y')
    _ci(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range")
    if (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0):
        return _DIM_LEAP[m - 1]
    return _DIM_NONLEAP[m - 1]


def to_ordinal(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cdr(y, m, d)
    y1 = y - 1
    days = 365 * y1 + y1 // 4 - y1 // 100 + y1 // 400
    if (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0):
        days += _CUM_LEAP[m - 1]
    else:
        days += _CUM_NONLEAP[m - 1]
    return days + d


def from_ordinal(n):
    _ci(n, 'n')
    if n < 1 or n > _MAX_ORD:
        raise ValueError(f"ordinal {n} out of range")
    z = n - 1
    n400, z = divmod(z, 146097)
    if z >= 109572:
        z -= 109572
        n4, z = divmod(z, 1461)
        n1, z = divmod(z, 365)
        if n1 == 4:
            n1 = 3
            z += 365
        year = n400 * 400 + 300 + n4 * 4 + n1
    else:
        n100, z = divmod(z, 36524)
        n4, z = divmod(z, 1461)
        n1, z = divmod(z, 365)
        year = n400 * 400 + n100 * 100 + n4 * 4 + n1
    year += 1
    leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    cum = _CUM_LEAP if leap else _CUM_NONLEAP
    month = 12
    for i in range(11, -1, -1):
        if z >= cum[i]:
            month = i + 1
            break
    day = z - cum[month - 1] + 1
    return (year, month, day)


def weekday(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cdr(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _cd(date)
    _ci(n, 'n')
    _cdr(date[0], date[1], date[2])
    o = to_ordinal(date[0], date[1], date[2]) + n
    if o < 1 or o > _MAX_ORD:
        raise OverflowError("result date out of range")
    return from_ordinal(o)


def add_months(date, n):
    _cd(date)
    _ci(n, 'n')
    _cdr(date[0], date[1], date[2])
    y, m, d = date
    tm = (y - 1) * 12 + (m - 1) + n
    ty = tm // 12 + 1
    tmo = tm % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result year out of range")
    if (ty % 4 == 0 and ty % 100 != 0) or (ty % 400 == 0):
        md = _DIM_LEAP[tmo - 1]
    else:
        md = _DIM_NONLEAP[tmo - 1]
    return (ty, tmo, min(d, md))


def iso_weeks_in_year(iso_year):
    _ci(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if jan1_wd == 2 and ((iso_year % 4 == 0 and iso_year % 100 != 0) or (iso_year % 400 == 0)):
        return 53
    return 52


def iso_week(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cdr(y, m, d)
    o = to_ordinal(y, m, d)
    wd = (o - 1) % 7
    iso_wd = wd + 1
    thu_o = o + (3 - wd)
    iso_y = from_ordinal(thu_o)[0]
    jan4_o = to_ordinal(iso_y, 1, 4)
    jan4_wd = (jan4_o - 1) % 7
    mon_w1 = jan4_o - jan4_wd
    iso_wk = (thu_o - mon_w1) // 7 + 1
    return (iso_y, iso_wk, iso_wd)


def from_iso_week(iso_year, week, weekday):
    _ci(iso_year, 'iso_year')
    _ci(week, 'week')
    _ci(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range")
    mw = iso_weeks_in_year(iso_year)
    if week < 1 or week > mw:
        raise ValueError(f"week {week} out of range 1..{mw}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_o = to_ordinal(iso_year, 1, 4)
    jan4_wd = (jan4_o - 1) % 7
    mon_w1 = jan4_o - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > _MAX_ORD:
        raise OverflowError("result date out of range")
    return from_ordinal(target)


_PARSE_RE = re.compile(
    r'\A(?:'
    r'([0-9]{4})-([0-9]{2})-([0-9]{2})'
    r'|'
    r'([0-9]{4})([0-9]{2})([0-9]{2})'
    r'|'
    r'([0-9]{4})-([0-9]{3})'
    r'|'
    r'([0-9]{4})([0-9]{3})'
    r'|'
    r'([0-9]{4})-W([0-9]{2})-([0-9]{1})'
    r'|'
    r'([0-9]{4})W([0-9]{2})([0-9]{1})'
    r')\Z'
)


def _parse_week_date(iy, wk, wkd):
    if iy < 1 or iy > 9999:
        raise ValueError("ISO year out of range")
    if wkd < 1 or wkd > 7:
        raise ValueError("weekday out of range")
    mw = iso_weeks_in_year(iy)
    if wk < 1 or wk > mw:
        raise ValueError("week out of range")
    jan4_o = to_ordinal(iy, 1, 4)
    jan4_wd = (jan4_o - 1) % 7
    mon_w1 = jan4_o - jan4_wd
    target = mon_w1 + (wk - 1) * 7 + (wkd - 1)
    if target < 1 or target > _MAX_ORD:
        raise ValueError("date out of range")
    return from_ordinal(target)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")
    m = _PARSE_RE.match(s)
    if m is None:
        raise ValueError(f"invalid date string: {s!r}")
    g = m.groups()
    if g[0] is not None:
        y, mo, d = int(g[0]), int(g[1]), int(g[2])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)
    if g[3] is not None:
        y, mo, d = int(g[3]), int(g[4]), int(g[5])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        if mo < 1 or mo > 12:
            raise ValueError("month out of range")
        if d < 1 or d > days_in_month(y, mo):
            raise ValueError("day out of range")
        return (y, mo, d)
    if g[6] is not None:
        y, doy = int(g[6]), int(g[7])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        mx = 366 if ((y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)) else 365
        if doy < 1 or doy > mx:
            raise ValueError("day of year out of range")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)
    if g[8] is not None:
        y, doy = int(g[8]), int(g[9])
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        mx = 366 if ((y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)) else 365
        if doy < 1 or doy > mx:
            raise ValueError("day of year out of range")
        return from_ordinal(to_ordinal(y, 1, 1) + doy - 1)
    if g[10] is not None:
        return _parse_week_date(int(g[10]), int(g[11]), int(g[12]))
    return _parse_week_date(int(g[13]), int(g[14]), int(g[15]))


def format_date(date, form):
    _cd(date)
    _cdr(date[0], date[1], date[2])
    if form == 'calendar':
        return f'{date[0]:04d}-{date[1]:02d}-{date[2]:02d}'
    if form == 'ordinal':
        doy = to_ordinal(date[0], date[1], date[2]) - to_ordinal(date[0], 1, 1) + 1
        return f'{date[0]:04d}-{doy:03d}'
    if form == 'week':
        iy, iw, iwd = iso_week(date[0], date[1], date[2])
        return f'{iy:04d}-W{iw:02d}-{iwd}'
    raise ValueError(f"invalid format: {form!r}")


def _shift(date, k):
    y, m, d = date
    tm = (y - 1) * 12 + (m - 1) + k
    ty = tm // 12 + 1
    tmo = tm % 12 + 1
    if (ty % 4 == 0 and ty % 100 != 0) or (ty % 400 == 0):
        md = _DIM_LEAP[tmo - 1]
    else:
        md = _DIM_NONLEAP[tmo - 1]
    return (ty, tmo, min(d, md))


def diff(a, b):
    _cd(a, 'a')
    _cd(b, 'b')
    _cdr(a[0], a[1], a[2])
    _cdr(b[0], b[1], b[2])
    if a == b:
        return (0, 0, 0)
    if a > b:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
    K = (b[0] - a[0]) * 12 + (b[1] - a[1])
    if _shift(a, K) > b:
        K -= 1
    years, months = divmod(K, 12)
    shifted = _shift(a, K)
    days = to_ordinal(b[0], b[1], b[2]) - to_ordinal(shifted[0], shifted[1], shifted[2])
    return (years, months, days)
