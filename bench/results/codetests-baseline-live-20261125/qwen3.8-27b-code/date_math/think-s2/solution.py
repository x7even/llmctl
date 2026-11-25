import re

# ─── internal helpers (no validation) ───────────────────────────────────────────

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def _dim(y, m):
    if m == 2:
        return 29 if _is_leap(y) else 28
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    return 30

def _days_before_year(y):
    n = y - 1
    return n * 365 + n // 4 - n // 100 + n // 400

def _days_before_month(y, m):
    total = 0
    for i in range(1, m):
        total += _dim(y, i)
    return total

def _ordinal(y, m, d):
    return _days_before_year(y) + _days_before_month(y, m) + d

def _from_ordinal(n):
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _days_before_year(y)
    m = 1
    while True:
        dm = _dim(y, m)
        if doy <= dm:
            break
        doy -= dm
        m += 1
    return (y, m, doy)

def _ordinal_to_year(ord_val):
    lo, hi = 1, 10000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < ord_val:
            lo = mid
        else:
            hi = mid - 1
    return lo

def _iso_weeks_in_year(y):
    wd = _days_before_year(y) % 7
    if wd == 3:
        return 53
    if _is_leap(y) and wd == 2:
        return 53
    return 52

def _add_months_internal(date, n):
    y, m, d = date
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    new_d = min(d, _dim(new_y, new_m))
    return (new_y, new_m, new_d)

# ─── validation helpers ─────────────────────────────────────────────────────────

def _check_int(x, name="value"):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")

def _check_date_tuple(date, name="date"):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i, v in enumerate(date):
        if type(v) is not int:
            raise TypeError(f"{name}[{i}] must be an int")

def _check_date_valid(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dm = _dim(y, m)
    if not (1 <= d <= dm):
        raise ValueError(f"day {d} out of range 1..{dm}")

# ─── public API ─────────────────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y, "y")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)

def days_in_month(y, m):
    _check_int(y, "y")
    _check_int(m, "m")
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)

def to_ordinal(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_valid(y, m, d)
    return _ordinal(y, m, d)

def from_ordinal(n):
    _check_int(n, "n")
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ordinal(n)

def weekday(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_valid(y, m, d)
    return (_ordinal(y, m, d) - 1) % 7

def add_days(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_valid(y, m, d)
    result_ord = _ordinal(y, m, d) + n
    if result_ord < 1 or result_ord > 3652059:
        raise OverflowError(f"result ordinal {result_ord} out of range 1..3652059")
    return _from_ordinal(result_ord)

def add_months(date, n):
    _check_date_tuple(date, "date")
    _check_int(n, "n")
    y, m, d = date
    _check_date_valid(y, m, d)
    result = _add_months_internal(date, n)
    new_y = result[0]
    if not (1 <= new_y <= 9999):
        raise OverflowError(f"result year {new_y} out of range 1..9999")
    return result

def iso_weeks_in_year(iso_year):
    _check_int(iso_year, "iso_year")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)

def iso_week(y, m, d):
    _check_int(y, "y")
    _check_int(m, "m")
    _check_int(d, "d")
    _check_date_valid(y, m, d)
    ord_val = _ordinal(y, m, d)
    wd = (ord_val - 1) % 7  # 0=Mon .. 6=Sun
    week_monday = ord_val - wd
    thursday = week_monday + 3
    iso_y = _ordinal_to_year(thursday)
    jan4_ord = _days_before_year(iso_y) + 4
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    week_num = (week_monday - week1_monday) // 7 + 1
    iso_wd = wd + 1
    return (iso_y, week_num, iso_wd)

def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, "iso_year")
    _check_int(week, "week")
    _check_int(weekday, "weekday")
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = _iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday <= 7):
        raise ValueError(f"weekday {weekday} out of range 1..7")
    jan4_ord = _days_before_year(iso_year) + 4
    jan4_wd = (jan4_ord - 1) % 7
    week1_monday = jan4_ord - jan4_wd
    target_ord = week1_monday + (week - 1) * 7 + (weekday - 1)
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError(f"result ordinal {target_ord} out of range 1..3652059")
    return _from_ordinal(target_ord)

def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    if len(s) == 10:
        # YYYY-MM-DD
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', s):
            raise ValueError(f"invalid date string: {s!r}")
        y = int(s[0:4])
        m = int(s[5:7])
        d = int(s[8:10])
        if y < 1:
            raise ValueError(f"year {y} out of range 1..9999")
        _check_date_valid(y, m, d)
        return (y, m, d)

    elif len(s) == 8:
        if s[4] == 'W':
            # YYYYWwwD
            if not re.fullmatch(r'[0-9]{4}W[0-9]{2}[0-9]', s):
                raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            w = int(s[5:7])
            wd = int(s[7])
            if y < 1:
                raise ValueError(f"year {y} out of range 1..9999")
            max_week = _iso_weeks_in_year(y)
            if not (1 <= w <= max_week):
                raise ValueError(f"week {w} out of range 1..{max_week}")
            if not (1 <= wd <= 7):
                raise ValueError(f"weekday {wd} out of range 1..7")
            jan4_ord = _days_before_year(y) + 4
            jan4_wd = (jan4_ord - 1) % 7
            week1_monday = jan4_ord - jan4_wd
            target_ord = week1_monday + (w - 1) * 7 + (wd - 1)
            if target_ord < 1 or target_ord > 3652059:
                raise ValueError(f"date out of range")
            return _from_ordinal(target_ord)

        elif s[4] == '-':
            # YYYY-DDD
            if not re.fullmatch(r'[0-9]{4}-[0-9]{3}', s):
                raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            doy = int(s[5:8])
            if y < 1:
                raise ValueError(f"year {y} out of range 1..9999")
            max_doy = 366 if _is_leap(y) else 365
            if not (1 <= doy <= max_doy):
                raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
            return _from_ordinal(_days_before_year(y) + doy)

        else:
            # All digits: try YYYYMMDD, then YYYYDDD
            if not re.fullmatch(r'[0-9]{8}', s):
                raise ValueError(f"invalid date string: {s!r}")
            y = int(s[0:4])
            if y < 1:
                raise ValueError(f"year {y} out of range 1..9999")
            m = int(s[4:6])
            d = int(s[6:8])
            if 1 <= m <= 12 and 1 <= d <= _dim(y, m):
                return (y, m, d)
            doy = int(s[4:8])
            max_doy = 366 if _is_leap(y) else 365
            if 1 <= doy <= max_doy:
                return _from_ordinal(_days_before_year(y) + doy)
            raise ValueError(f"invalid date string: {s!r}")

    elif len(s) == 11:
        # YYYY-Www-D
        if not re.fullmatch(r'[0-9]{4}-W[0-9]{2}-[0-9]', s):
            raise ValueError(f"invalid date string: {s!r}")
        y = int(s[0:4])
        w = int(s[6:8])
        wd = int(s[9])
        if y < 1:
            raise ValueError(f"year {y} out of range 1..9999")
        max_week = _iso_weeks_in_year(y)
        if not (1 <= w <= max_week):
            raise ValueError(f"week {w} out of range 1..{max_week}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        jan4_ord = _days_before_year(y) + 4
        jan4_wd = (jan4_ord - 1) % 7
        week1_monday = jan4_ord - jan4_wd
        target_ord = week1_monday + (w - 1) * 7 + (wd - 1)
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError(f"date out of range")
        return _from_ordinal(target_ord)

    else:
        raise ValueError(f"invalid date string: {s!r}")

def format_date(date, form):
    _check_date_tuple(date, "date")
    y, m, d = date
    _check_date_valid(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a string, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _days_before_month(y, m) + d
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"
    else:
        raise ValueError(f"invalid form: {form!r}")

def diff(a, b):
    _check_date_tuple(a, "a")
    _check_date_tuple(b, "b")
    ay, am, ad = a
    by, bm, bd = b
    _check_date_valid(ay, am, ad)
    _check_date_valid(by, bm, bd)

    if a <= b:
        # Binary search for largest K >= 0 with add_months(a, K) <= b
        lo, hi = 0, (by - ay) * 12 + 12
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _add_months_internal(a, mid) <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        years, months = divmod(K, 12)
        shifted = _add_months_internal(a, K)
        days = _ordinal(by, bm, bd) - _ordinal(shifted[0], shifted[1], shifted[2])
        return (years, months, days)
    else:
        years, months, days = diff(b, a)
        return (-years, -months, -days)