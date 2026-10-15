import re

_CUM_NONLEAP = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
_CUM_LEAP = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366)
_MD_NONLEAP = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MD_LEAP = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_MAX_ORDINAL = 3652059
_CYCLE_DAYS = 146097


def _ci(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int")


def _cd(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for x in date:
        if type(x) is not int:
            raise TypeError(f"{name} must contain only ints")


def _cv(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _MD_LEAP[m - 1] if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else _MD_NONLEAP[m - 1]
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range for {y:04d}-{m:02d}")


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    return _MD_LEAP[m - 1] if _leap(y) else _MD_NONLEAP[m - 1]


def _cum(y):
    return _CUM_LEAP if _leap(y) else _CUM_NONLEAP


def _ordinal(y, m, d):
    leaps = (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    return (y - 1) * 365 + leaps + _cum(y)[m - 1] + d


def _year_from_ord(ordinal):
    t = ordinal - 1
    fc = t // _CYCLE_DAYS
    tc = t % _CYCLE_DAYS
    lo, hi = 1, 400
    while lo < hi:
        mid = (lo + hi + 1) // 2
        db = (mid - 1) * 365 + (mid - 1) // 4 - (mid - 1) // 100
        if db <= tc:
            lo = mid
        else:
            hi = mid - 1
    return fc * 400 + lo


def _month_day(y, doy):
    cum = _cum(y)
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < doy:
            lo = mid + 1
        else:
            hi = mid
    return lo, doy - cum[lo - 1]


def _from_iso_inner(iy, w, wd):
    leaps = (iy - 1) // 4 - (iy - 1) // 100 + (iy - 1) // 400
    db = (iy - 1) * 365 + leaps
    j4 = db + 4
    j4w = (j4 - 1) % 7
    mw1 = j4 - j4w
    tgt = mw1 + (w - 1) * 7 + (wd - 1)
    if tgt < 1 or tgt > _MAX_ORDINAL:
        return None
    return _from_ord_internal(tgt)


def _from_ord_internal(n):
    t = n - 1
    fc = t // _CYCLE_DAYS
    tc = t % _CYCLE_DAYS
    lo, hi = 1, 400
    while lo < hi:
        mid = (lo + hi + 1) // 2
        db = (mid - 1) * 365 + (mid - 1) // 4 - (mid - 1) // 100
        if db <= tc:
            lo = mid
        else:
            hi = mid - 1
    yc = lo
    y = fc * 400 + yc
    db = (yc - 1) * 365 + (yc - 1) // 4 - (yc - 1) // 100
    doy = tc - db + 1
    m, d = _month_day(y, doy)
    return (y, m, d)


def is_leap(y):
    _ci(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _leap(y)


def days_in_month(y, m):
    _ci(y, 'y')
    _ci(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cv(y, m, d)
    return _ordinal(y, m, d)


def from_ordinal(n):
    _ci(n, 'n')
    if not (1 <= n <= _MAX_ORDINAL):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    return _from_ord_internal(n)


def weekday(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cv(y, m, d)
    return (_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _cd(date, 'date')
    _ci(n, 'n')
    y, m, d = date
    _cv(y, m, d)
    ord_ = _ordinal(y, m, d) + n
    if ord_ < 1 or ord_ > _MAX_ORDINAL:
        raise OverflowError("result out of supported range")
    return _from_ord_internal(ord_)


def add_months(date, n):
    _cd(date, 'date')
    _ci(n, 'n')
    y, m, d = date
    _cv(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if not (1 <= ty <= 9999):
        raise OverflowError(f"result year {ty} out of range 1..9999")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _ci(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    leaps = (iso_year - 1) // 4 - (iso_year - 1) // 100 + (iso_year - 1) // 400
    wd = ((iso_year - 1) * 365 + leaps) % 7
    if wd == 3:
        return 53
    if wd == 2 and _leap(iso_year):
        return 53
    return 52


def iso_week(y, m, d):
    _ci(y, 'y')
    _ci(m, 'm')
    _ci(d, 'd')
    _cv(y, m, d)
    ord_ = _ordinal(y, m, d)
    wd = (ord_ - 1) % 7
    monday = ord_ - wd
    thursday = monday + 3
    iy = _year_from_ord(thursday)
    leaps = (iy - 1) // 4 - (iy - 1) // 100 + (iy - 1) // 400
    db = (iy - 1) * 365 + leaps
    j4 = db + 4
    j4w = (j4 - 1) % 7
    mw1 = j4 - j4w
    iw = (monday - mw1) // 7 + 1
    return (iy, iw, wd + 1)


def from_iso_week(iso_year, week, weekday):
    _ci(iso_year, 'iso_year')
    _ci(week, 'week')
    _ci(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    mw = iso_weeks_in_year(iso_year)
    if not (1 <= week <= mw):
        raise ValueError(f"week {week} out of range 1..{mw} for ISO year {iso_year}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    result = _from_iso_inner(iso_year, week, weekday)
    if result is None:
        raise OverflowError("result out of supported range")
    return result


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    # Extended calendar: YYYY-MM-DD
    mt = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
    if mt:
        y, mo, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError(f"day {d} out of range for {y:04d}-{mo:02d}")
        return (y, mo, d)

    # Extended week: YYYY-Www-D
    mt = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
    if mt:
        y, w, wd = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        if not (1 <= w <= iso_weeks_in_year(y)):
            raise ValueError(f"week {w} invalid for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        r = _from_iso_inner(y, w, wd)
        if r is None:
            raise ValueError("date out of supported range")
        return r

    # Basic calendar: YYYYMMDD
    mt = re.fullmatch(r'([0-9]{4})([0-9]{2})([0-9]{2})', s)
    if mt:
        y, mo, d = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError(f"day {d} out of range for {y:04d}-{mo:02d}")
        return (y, mo, d)

    # Extended ordinal: YYYY-DDD
    mt = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
    if mt:
        y, doy = int(mt.group(1)), int(mt.group(2))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        maxd = 366 if _leap(y) else 365
        if not (1 <= doy <= maxd):
            raise ValueError(f"day of year {doy} out of range 1..{maxd}")
        mo, d = _month_day(y, doy)
        return (y, mo, d)

    # Basic week: YYYYWwwD
    mt = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
    if mt:
        y, w, wd = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        if not (1 <= w <= iso_weeks_in_year(y)):
            raise ValueError(f"week {w} invalid for ISO year {y}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        r = _from_iso_inner(y, w, wd)
        if r is None:
            raise ValueError("date out of supported range")
        return r

    # Basic ordinal: YYYYDDD
    mt = re.fullmatch(r'([0-9]{4})([0-9]{3})', s)
    if mt:
        y, doy = int(mt.group(1)), int(mt.group(2))
        if y < 1:
            raise ValueError("year 0000 is not valid")
        maxd = 366 if _leap(y) else 365
        if not (1 <= doy <= maxd):
            raise ValueError(f"day of year {doy} out of range 1..{maxd}")
        mo, d = _month_day(y, doy)
        return (y, mo, d)

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _cd(date, 'date')
    y, m, d = date
    _cv(y, m, d)

    if type(form) is not str:
        raise ValueError(f"form must be a string, got {type(form).__name__}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _cum(y)[m - 1] + d
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"
    else:
        raise ValueError(f"unknown form: {form!r}")


def diff(a, b):
    _cd(a, 'a')
    _cd(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _cv(ay, am, ad)
    _cv(by, bm, bd)

    a_ord = _ordinal(ay, am, ad)
    b_ord = _ordinal(by, bm, bd)

    if a_ord <= b_ord:
        return _diff_pos(ay, am, ad, by, bm, bd, a_ord, b_ord)
    else:
        r = _diff_pos(by, bm, bd, ay, am, ad, b_ord, a_ord)
        return (-r[0], -r[1], -r[2])


def _diff_pos(ay, am, ad, by, bm, bd, a_ord, b_ord):
    K_max = (by - ay) * 12 + (bm - am)
    clamped = ad if ad <= _dim(by, bm) else _dim(by, bm)
    if clamped <= bd:
        K = K_max
    else:
        K = K_max - 1

    years, months = divmod(K, 12)
    total = (ay - 1) * 12 + (am - 1) + K
    sy = total // 12 + 1
    sm = total % 12 + 1
    sd = ad if ad <= _dim(sy, sm) else _dim(sy, sm)
    days = b_ord - _ordinal(sy, sm, sd)
    return (years, months, days)