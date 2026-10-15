import re

# ─── constants ────────────────────────────────────────────────────────────────
_MAX_ORDINAL = 3652059  # ordinal of (9999,12,31)

_DBM_NL = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
_DBM_L  = (0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)

# ─── regexes (ASCII digits only) ─────────────────────────────────────────────
_RE_CAL_EXT = re.compile(r'\A([0-9]{4})-([0-9]{2})-([0-9]{2})\Z')
_RE_CAL_BAS = re.compile(r'\A([0-9]{4})([0-9]{2})([0-9]{2})\Z')
_RE_ORD_EXT = re.compile(r'\A([0-9]{4})-([0-9]{3})\Z')
_RE_ORD_BAS = re.compile(r'\A([0-9]{4})([0-9]{3})\Z')
_RE_WK_EXT  = re.compile(r'\A([0-9]{4})-W([0-9]{2})-([0-9])\Z')
_RE_WK_BAS  = re.compile(r'\A([0-9]{4})W([0-9]{2})([0-9])\Z')

# ─── internal helpers (no type/range checking) ───────────────────────────────

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _validate_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    if not (1 <= d <= _dim(y, m)):
        raise ValueError(f"day {d} out of range for {y}-{m:02d}")


def _days_before_year(y):
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400


def _days_in_year(y):
    return 366 if _is_leap(y) else 365


def _to_ord(y, m, d):
    dbm = _DBM_L if _is_leap(y) else _DBM_NL
    return _days_before_year(y) + dbm[m - 1] + d


def _from_ord(n):
    y = (n * 400) // 146097 + 1
    while _days_before_year(y) >= n:
        y -= 1
    while _days_before_year(y + 1) < n:
        y += 1
    doy = n - _days_before_year(y)
    dbm = _DBM_L if _is_leap(y) else _DBM_NL
    m = 1
    while m < 12 and dbm[m] < doy:
        m += 1
    d = doy - dbm[m - 1]
    return (y, m, d)


def _weekday(y, m, d):
    return (_to_ord(y, m, d) - 1) % 7


def _add_months_internal(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of supported range")
    td = d if d <= _dim(ty, tm) else _dim(ty, tm)
    return (ty, tm, td)


def _iso_weeks_in_year(iso_year):
    wd = _weekday(iso_year, 1, 1)
    if wd == 3:
        return 53
    if wd == 2 and _is_leap(iso_year):
        return 53
    return 52


def _iso_week(y, m, d):
    ord_ = _to_ord(y, m, d)
    wd = (ord_ - 1) % 7
    iso_wd = wd + 1
    mon_ord = ord_ - wd
    jan4_ord = _to_ord(y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    iso_wk = (mon_ord - mon_w1) // 7 + 1
    if iso_wk < 1:
        iso_yr = y - 1
        iso_wk += _iso_weeks_in_year(iso_yr)
    elif iso_wk > _iso_weeks_in_year(y):
        iso_yr = y + 1
        iso_wk -= _iso_weeks_in_year(y)
    else:
        iso_yr = y
    return (iso_yr, iso_wk, iso_wd)


def _from_iso_week(iso_year, week, weekday):
    jan4_ord = _to_ord(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    mon_w1 = jan4_ord - jan4_wd
    target_ord = mon_w1 + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > _MAX_ORDINAL:
        raise OverflowError("result out of supported range")
    return _from_ord(target_ord)


# ─── type-checking helpers ───────────────────────────────────────────────────

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _check_date_tuple(date, name):
    if type(date) is not tuple:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    if len(date) != 3:
        raise TypeError(f"{name} must be a tuple of 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int")


# ─── public API ──────────────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= _MAX_ORDINAL):
        raise ValueError(f"ordinal {n} out of range 1..{_MAX_ORDINAL}")
    return _from_ord(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)
    return _weekday(y, m, d)


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _validate_date(y, m, d)
    ord_ = _to_ord(y, m, d) + n
    if ord_ < 1 or ord_ > _MAX_ORDINAL:
        raise OverflowError("result out of supported range")
    return _from_ord(ord_)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _validate_date(y, m, d)
    return _add_months_internal(y, m, d, n)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _validate_date(y, m, d)
    return _iso_week(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nweeks = _iso_weeks_in_year(iso_year)
    if not (1 <= week <= nweeks):
        raise ValueError(f"week {week} out of range 1..{nweeks}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    return _from_iso_week(iso_year, week, weekday)


def parse(s):
    if type(s) is not str:
        raise TypeError("s must be str")

    m = _RE_CAL_EXT.match(s)
    if m:
        y, mm, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _validate_date(y, mm, d)
        return (y, mm, d)

    m = _RE_CAL_BAS.match(s)
    if m:
        y, mm, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        _validate_date(y, mm, d)
        return (y, mm, d)

    m = _RE_ORD_EXT.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= doy <= _days_in_year(y)):
            raise ValueError(f"day of year {doy} out of range")
        return _from_ord(_days_before_year(y) + doy)

    m = _RE_ORD_BAS.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= doy <= _days_in_year(y)):
            raise ValueError(f"day of year {doy} out of range")
        return _from_ord(_days_before_year(y) + doy)

    m = _RE_WK_EXT.match(s)
    if m:
        yr, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _parse_week(yr, wk, wd)

    m = _RE_WK_BAS.match(s)
    if m:
        yr, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _parse_week(yr, wk, wd)

    raise ValueError(f"invalid date string: {s!r}")


def _parse_week(iso_year, week, weekday):
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range")
    nweeks = _iso_weeks_in_year(iso_year)
    if not (1 <= week <= nweeks):
        raise ValueError(f"week {week} out of range 1..{nweeks}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    try:
        return _from_iso_week(iso_year, week, weekday)
    except OverflowError:
        raise ValueError("date out of supported range")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _validate_date(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ord(y, m, d) - _days_before_year(y)
        return f"{y:04d}-{doy:03d}"
    else:
        iso_yr, iso_wk, iso_wd = _iso_week(y, m, d)
        return f"{iso_yr:04d}-W{iso_wk:02d}-{iso_wd}"


def _diff_internal(a, b):
    """a and b are validated tuples, a <= b (chronologically)."""
    ay, am, ad = a
    by, bm, bd = b

    lo, hi = 0, 12 * 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            s = _add_months_internal(ay, am, ad, mid)
            if s <= b:
                lo = mid
            else:
                hi = mid - 1
        except OverflowError:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    shift_result = _add_months_internal(ay, am, ad, K)
    days = _to_ord(by, bm, bd) - _to_ord(shift_result[0], shift_result[1], shift_result[2])
    return (years, months, days)


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _validate_date(ay, am, ad)
    _validate_date(by, bm, bd)

    if a > b:
        yr, mo, dy = _diff_internal(b, a)
        return (-yr, -mo, -dy)
    else:
        return _diff_internal(a, b)
