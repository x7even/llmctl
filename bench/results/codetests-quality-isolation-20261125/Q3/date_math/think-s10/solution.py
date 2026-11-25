import re


# ---------- internal helpers (no public API) ----------

def _is_leap_raw(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim_raw(y, m):
    if m == 2:
        return 29 if _is_leap_raw(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


# cumulative days before month m (1-indexed) in a non-leap year
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _days_before_month(y, m):
    d = _CUM[m - 1]
    if m > 2 and _is_leap_raw(y):
        d += 1
    return d


def _F(y):
    """Total days in years 1..y inclusive."""
    return y * 365 + y // 4 - y // 100 + y // 400


def _to_ord_raw(y, m, d):
    return _F(y - 1) + _days_before_month(y, m) + d


def _from_ord_raw(n):
    y = 1 + (n - 1) * 400 // 146097
    while _F(y) < n:
        y += 1
    while _F(y - 1) >= n:
        y -= 1
    doy = n - _F(y - 1)
    for m in range(1, 13):
        dim = _dim_raw(y, m)
        if doy <= dim:
            return (y, m, doy)
        doy -= dim
    raise ValueError("internal error")


def _weekday_raw(y, m, d):
    return (_to_ord_raw(y, m, d) - 1) % 7


def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError("result out of range")
    nd = d if d <= _dim_raw(ny, nm) else _dim_raw(ny, nm)
    return (ny, nm, nd)


def _iso_weeks_raw(ly):
    w = _weekday_raw(ly, 1, 1)
    if w == 3:
        return 53
    if w == 2 and _is_leap_raw(ly):
        return 53
    return 52


def _iso_week_raw(y, m, d):
    o = _to_ord_raw(y, m, d)
    w = (o - 1) % 7
    thu_o = o + (3 - w)
    iso_y = _from_ord_raw(thu_o)[0]
    jan4 = _to_ord_raw(iso_y, 1, 4)
    w4 = (jan4 - 1) % 7
    mon_w1 = jan4 - w4
    week = (o - mon_w1) // 7 + 1
    return (iso_y, week, w + 1)


def _from_iso_raw(ly, wk, wd):
    jan4 = _to_ord_raw(ly, 1, 4)
    w4 = (jan4 - 1) % 7
    mon_w1 = jan4 - w4
    target = mon_w1 + (wk - 1) * 7 + (wd - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return _from_ord_raw(target)


# ---------- type / range check helpers ----------

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int")


def _chk_date(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i in range(3):
        if type(x[i]) is not int:
            raise TypeError(f"{name}[{i}] must be an int")


def _val_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= _dim_raw(y, m)):
        raise ValueError(f"day {d} out of range 1..{_dim_raw(y, m)}")


# ---------- public API ----------

def is_leap(y):
    _chk_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap_raw(y)


def days_in_month(y, m):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim_raw(y, m)


def to_ordinal(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _val_date(y, m, d)
    return _to_ord_raw(y, m, d)


def from_ordinal(n):
    _chk_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ord_raw(n)


def weekday(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _val_date(y, m, d)
    return _weekday_raw(y, m, d)


def add_days(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _val_date(y, m, d)
    o = _to_ord_raw(y, m, d) + n
    if o < 1 or o > 3652059:
        raise OverflowError("result out of range")
    return _from_ord_raw(o)


def add_months(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _val_date(y, m, d)
    return _add_months_raw(y, m, d, n)


def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_raw(iso_year)


def iso_week(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _val_date(y, m, d)
    return _iso_week_raw(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, 'iso_year')
    _chk_int(week, 'week')
    _chk_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = _iso_weeks_raw(iso_year)
    if not (1 <= week <= nw):
        raise ValueError(f"week {week} out of range 1..{nw}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    return _from_iso_raw(iso_year, week, weekday)


# ---------- parse ----------

_RE_CAL_EXT = re.compile(r'\A([0-9]{4})-([0-9]{2})-([0-9]{2})\Z')
_RE_CAL_BAS = re.compile(r'\A([0-9]{4})([0-9]{2})([0-9]{2})\Z')
_RE_ORD_EXT = re.compile(r'\A([0-9]{4})-([0-9]{3})\Z')
_RE_ORD_BAS = re.compile(r'\A([0-9]{4})([0-9]{3})\Z')
_RE_WK_EXT = re.compile(r'\A([0-9]{4})-W([0-9]{2})-([0-9])\Z')
_RE_WK_BAS = re.compile(r'\A([0-9]{4})W([0-9]{2})([0-9])\Z')


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be a str")

    ln = len(s)

    # Determine form and extract
    if ln == 10:
        mo = _RE_CAL_EXT.match(s)
        if mo:
            y, m, d = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
            _val_date(y, m, d)
            return (y, m, d)
        mo = _RE_WK_EXT.match(s)
        if mo:
            ly, wk, wd = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
            return _parse_week(ly, wk, wd)
        raise ValueError(f"invalid date string: {s!r}")

    elif ln == 8:
        if s[4] == '-':
            mo = _RE_ORD_EXT.match(s)
            if mo:
                y, doy = int(mo.group(1)), int(mo.group(2))
                return _parse_ordinal(y, doy)
            raise ValueError(f"invalid date string: {s!r}")
        elif s[4] == 'W':
            mo = _RE_WK_BAS.match(s)
            if mo:
                ly, wk, wd = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
                return _parse_week(ly, wk, wd)
            raise ValueError(f"invalid date string: {s!r}")
        else:
            mo = _RE_CAL_BAS.match(s)
            if mo:
                y, m, d = int(mo.group(1)), int(mo.group(2)), int(mo.group(3))
                _val_date(y, m, d)
                return (y, m, d)
            raise ValueError(f"invalid date string: {s!r}")

    elif ln == 7:
        mo = _RE_ORD_BAS.match(s)
        if mo:
            y, doy = int(mo.group(1)), int(mo.group(2))
            return _parse_ordinal(y, doy)
        raise ValueError(f"invalid date string: {s!r}")

    else:
        raise ValueError(f"invalid date string: {s!r}")


def _parse_ordinal(y, doy):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range")
    max_doy = 366 if _is_leap_raw(y) else 365
    if not (1 <= doy <= max_doy):
        raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
    return _from_ord_raw(_F(y - 1) + doy)


def _parse_week(ly, wk, wd):
    if not (1 <= ly <= 9999):
        raise ValueError(f"iso_year {ly} out of range")
    nw = _iso_weeks_raw(ly)
    if not (1 <= wk <= nw):
        raise ValueError(f"week {wk} out of range 1..{nw}")
    if not (1 <= wd <= 7):
        raise ValueError(f"weekday {wd} out of range 1..7")
    try:
        return _from_iso_raw(ly, wk, wd)
    except OverflowError:
        raise ValueError(f"week date out of range: {ly}-W{wk:02d}-{wd}")


# ---------- format_date ----------

def format_date(date, form):
    _chk_date(date, 'date')
    y, m, d = date
    _val_date(y, m, d)

    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ord_raw(y, m, d) - _F(y - 1)
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, id_ = _iso_week_raw(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_}"


# ---------- diff ----------

def diff(a, b):
    _chk_date(a, 'a')
    _chk_date(b, 'b')
    _val_date(*a)
    _val_date(*b)

    if a <= b:
        return _diff_nn(a, b)
    else:
        y, m, d = _diff_nn(b, a)
        return (-y, -m, -d)


def _diff_nn(a, b):
    # a <= b; find largest K >= 0 s.t. add_months(a, K) <= b
    ay, am, ad = a
    lo, hi = 0, 120000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            shifted = _add_months_raw(ay, am, ad, mid)
            if shifted <= b:
                lo = mid
            else:
                hi = mid - 1
        except OverflowError:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shifted = _add_months_raw(ay, am, ad, K)
    days = _to_ord_raw(*b) - _to_ord_raw(*shifted)
    return (years, months, days)