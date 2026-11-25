import re

# ─── Internal helpers (no public checking) ───────────────────────────────────

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _dim(y, m):
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if m in (4, 6, 9, 11):
        return 30
    return 29 if _is_leap(y) else 28

def _to_ord(y, m, d):
    ym1 = y - 1
    days_years = ym1 * 365 + ym1 // 4 - ym1 // 100 + ym1 // 400
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365)
    days_months = cum[m]
    if m > 2 and _is_leap(y):
        days_months += 1
    return days_years + days_months + d

def _from_ord(n):
    days = n - 1
    y = 1 + (days * 400) // 146097
    while y < 9999:
        if y * 365 + y // 4 - y // 100 + y // 400 <= days:
            y += 1
        else:
            break
    while y > 1:
        if (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400 > days:
            y -= 1
        else:
            break
    db = (y - 1) * 365 + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400
    doy = days - db
    leap = _is_leap(y)
    md = (31, 28 + (1 if leap else 0), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    m = 1
    while m < 12 and doy >= md[m - 1]:
        doy -= md[m - 1]
        m += 1
    return (y, m, doy + 1)

def _add_months_raw(y, m, d, n):
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)

def _iso_weeks_raw(y):
    jan1_wd = (_to_ord(y, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if _is_leap(y) and jan1_wd == 2:
        return 53
    return 52

def _iso_week_to_ord(iso_year, week, weekday):
    jan4_ord = _to_ord(iso_year, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_mon = jan4_ord - jan4_wd
    return week1_mon + (week - 1) * 7 + (weekday - 1)

def _doy_to_ymd(y, doy):
    leap = _is_leap(y)
    md = (31, 28 + (1 if leap else 0), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    m = 1
    while m < 12 and doy > md[m - 1]:
        doy -= md[m - 1]
        m += 1
    return (y, m, doy)

# ─── Type / range check helpers ──────────────────────────────────────────────

def _chk_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")

def _chk_date(d, name):
    if type(d) is not tuple:
        raise TypeError(f"{name} must be a tuple, got {type(d).__name__}")
    if len(d) != 3:
        raise TypeError(f"{name} must be a tuple of 3 elements, got {len(d)}")
    for i in range(3):
        if type(d[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(d[i]).__name__}")

def _chk_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")

# ─── Regex patterns ──────────────────────────────────────────────────────────

_RE_EXT_CAL = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_BAS_CAL = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_EXT_ORD = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_BAS_ORD = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_EXT_WK  = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_BAS_WK  = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')

# ─── Public API ──────────────────────────────────────────────────────────────

def is_leap(y):
    _chk_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)

def days_in_month(y, m):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)

def to_ordinal(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_range(y, m, d)
    return _to_ord(y, m, d)

def from_ordinal(n):
    _chk_int(n, 'n')
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ord(n)

def weekday(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_range(y, m, d)
    return (_to_ord(y, m, d) - 1) % 7

def add_days(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _chk_range(y, m, d)
    ord_val = _to_ord(y, m, d) + n
    if ord_val < 1 or ord_val > 3652059:
        raise OverflowError(f"result ordinal {ord_val} out of range 1..3652059")
    return _from_ord(ord_val)

def add_months(date, n):
    _chk_date(date, 'date')
    _chk_int(n, 'n')
    y, m, d = date
    _chk_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    if ny < 1 or ny > 9999:
        raise OverflowError(f"target year {ny} out of range 1..9999")
    nm = total % 12 + 1
    nd = d if d <= _dim(ny, nm) else _dim(ny, nm)
    return (ny, nm, nd)

def iso_weeks_in_year(iso_year):
    _chk_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_raw(iso_year)

def iso_week(y, m, d):
    _chk_int(y, 'y')
    _chk_int(m, 'm')
    _chk_int(d, 'd')
    _chk_range(y, m, d)
    ord_val = _to_ord(y, m, d)
    wd = (ord_val - 1) % 7
    iso_wd = wd + 1
    thu_ord = ord_val - wd + 3
    iso_y = _from_ord(thu_ord)[0]
    jan4_ord = _to_ord(iso_y, 1, 4)
    jan4_wd = (jan4_ord - 1) % 7
    week1_mon = jan4_ord - jan4_wd
    iso_w = (ord_val - week1_mon) // 7 + 1
    return (iso_y, iso_w, iso_wd)

def from_iso_week(iso_year, week, weekday):
    _chk_int(iso_year, 'iso_year')
    _chk_int(week, 'week')
    _chk_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = _iso_weeks_raw(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    target = _iso_week_to_ord(iso_year, week, weekday)
    if target < 1 or target > 3652059:
        raise OverflowError(f"result ordinal {target} out of range 1..3652059")
    return _from_ord(target)

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    m = _RE_EXT_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _dim(y, mo):
            raise ValueError(f"day {d} out of range for {y}-{mo:02d}")
        return (y, mo, d)

    m = _RE_EXT_WK.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        nw = _iso_weeks_raw(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        target = _iso_week_to_ord(y, wk, wd)
        if target < 1 or target > 3652059:
            raise ValueError(f"date out of supported range")
        return _from_ord(target)

    m = _RE_BAS_CAL.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        if mo < 1 or mo > 12:
            raise ValueError(f"month {mo} out of range")
        if d < 1 or d > _dim(y, mo):
            raise ValueError(f"day {d} out of range for {y}-{mo:02d}")
        return (y, mo, d)

    m = _RE_EXT_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _doy_to_ymd(y, doy)

    m = _RE_BAS_WK.match(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        nw = _iso_weeks_raw(y)
        if wk < 1 or wk > nw:
            raise ValueError(f"week {wk} out of range 1..{nw}")
        if wd < 1 or wd > 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        target = _iso_week_to_ord(y, wk, wd)
        if target < 1 or target > 3652059:
            raise ValueError(f"date out of supported range")
        return _from_ord(target)

    m = _RE_BAS_ORD.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y < 1:
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return _doy_to_ymd(y, doy)

    raise ValueError(f"unrecognized date format: {s!r}")

def format_date(date, form):
    _chk_date(date, 'date')
    y, m, d = date
    _chk_range(y, m, d)

    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"form must be 'calendar', 'ordinal', or 'week'")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _to_ord(y, m, d) - _to_ord(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    else:
        iy, iw, id_ = iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{id_:01d}"

def diff(a, b):
    _chk_date(a, 'a')
    _chk_date(b, 'b')
    y1, m1, d1 = a
    y2, m2, d2 = b
    _chk_range(y1, m1, d1)
    _chk_range(y2, m2, d2)

    oa = _to_ord(y1, m1, d1)
    ob = _to_ord(y2, m2, d2)

    if oa <= ob:
        # Largest K such that add_months(a, K) is valid (year <= 9999)
        K_max = (9999 - y1) * 12 + 12 - m1

        # Check if K_max itself satisfies the condition
        if _to_ord(9999, 12, d1 if d1 <= 31 else 31) <= ob:
            K = K_max
        else:
            lo, hi = 0, K_max - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                sy, sm, sd = _add_months_raw(y1, m1, d1, mid)
                if _to_ord(sy, sm, sd) <= ob:
                    lo = mid
                else:
                    hi = mid - 1
            K = lo

        years, months = divmod(K, 12)
        sy, sm, sd = _add_months_raw(y1, m1, d1, K)
        days = ob - _to_ord(sy, sm, sd)
        return (years, months, days)
    else:
        years, months, days = diff(b, a)
        return (-years, -months, -days)