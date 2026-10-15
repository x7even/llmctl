import re


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be an int, got {type(x).__name__}")


def _check_date(d, name):
    if type(d) is not tuple or len(d) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i, x in enumerate(d):
        if type(x) is not int:
            raise TypeError(f"{name}[{i}] must be an int, got {type(x).__name__}")


def _check_valid_date(y, m, d):
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    if not (1 <= m <= 12):
        raise ValueError(f"month {m} out of range 1..12")
    dim = _dim(y, m)
    if not (1 <= d <= dim):
        raise ValueError(f"day {d} out of range 1..{dim} for {y}-{m}")


def _dim(y, m):
    """Days in month, assuming y and m are already validated."""
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31


def _days_before_year(y):
    """Number of days in years 1 through y-1."""
    ym1 = y - 1
    return ym1 * 365 + ym1 // 4 - ym1 // 100 + ym1 // 400


def is_leap(y):
    _check_int(y, 'y')
    if not (1 <= y <= 9999):
        raise ValueError(f"year {y} out of range 1..9999")
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


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
    _check_valid_date(y, m, d)
    total = _days_before_year(y)
    if m > 1:
        feb = 29 if is_leap(y) else 28
        cum = (0, 31, 31 + feb, 31 + feb + 31, 31 + feb + 31 + 30,
               31 + feb + 31 + 30 + 31, 31 + feb + 31 + 30 + 31 + 30,
               31 + feb + 31 + 30 + 31 + 30 + 31, 31 + feb + 31 + 30 + 31 + 30 + 31 + 31,
               31 + feb + 31 + 30 + 31 + 30 + 31 + 31 + 30,
               31 + feb + 31 + 30 + 31 + 30 + 31 + 31 + 30 + 31,
               31 + feb + 31 + 30 + 31 + 30 + 31 + 31 + 30 + 31 + 30)
        total += cum[m - 1]
    total += d
    return total


def from_ordinal(n):
    _check_int(n, 'n')
    if not (1 <= n <= 3652059):
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    # Estimate year
    y = (n * 400) // 146097 + 1
    while _days_before_year(y) >= n:
        y -= 1
    while _days_before_year(y + 1) < n:
        y += 1
    # 0-indexed day of year
    doy = n - _days_before_year(y) - 1
    feb = 29 if is_leap(y) else 28
    md = (31, feb, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    for m in range(1, 13):
        if doy < md[m - 1]:
            return (y, m, doy + 1)
        doy -= md[m - 1]
    raise ValueError("internal error in from_ordinal")


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    ord_n = to_ordinal(y, m, d) + n
    if ord_n < 1 or ord_n > 3652059:
        raise OverflowError(f"result ordinal {ord_n} out of range 1..3652059")
    return from_ordinal(ord_n)


def add_months(date, n):
    _check_date(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_valid_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    new_y = total // 12 + 1
    new_m = total % 12 + 1
    if not (1 <= new_y <= 9999):
        raise OverflowError(f"target year {new_y} out of range 1..9999")
    new_d = min(d, _dim(new_y, new_m))
    return (new_y, new_m, new_d)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    jan1_wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if jan1_wd == 3:
        return 53
    if is_leap(iso_year) and jan1_wd == 2:
        return 53
    return 52


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_valid_date(y, m, d)
    ord_val = to_ordinal(y, m, d)
    iso_wd = weekday(y, m, d) + 1  # 1=Mon .. 7=Sun
    thu_ord = ord_val + (4 - iso_wd)
    iso_y, _, _ = from_ordinal(thu_ord)
    jan4_ord = to_ordinal(iso_y, 1, 4)
    jan4_wd = weekday(iso_y, 1, 4)
    week1_monday_ord = jan4_ord - jan4_wd
    week = (ord_val - week1_monday_ord) // 7 + 1
    return (iso_y, week, iso_wd)


def from_iso_week(iso_year, week, weekday_val):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday_val, 'weekday')
    if not (1 <= iso_year <= 9999):
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    max_week = iso_weeks_in_year(iso_year)
    if not (1 <= week <= max_week):
        raise ValueError(f"week {week} out of range 1..{max_week}")
    if not (1 <= weekday_val <= 7):
        raise ValueError(f"weekday {weekday_val} out of range 1..7")
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_wd = weekday(iso_year, 1, 4)
    week1_monday_ord = jan4_ord - jan4_wd
    day_ord = week1_monday_ord + (week - 1) * 7 + (weekday_val - 1)
    if day_ord < 1 or day_ord > 3652059:
        raise OverflowError(f"result ordinal {day_ord} out of range 1..3652059")
    return from_ordinal(day_ord)


_RE_EXT_CAL = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
_RE_BAS_CAL = re.compile(r'([0-9]{4})([0-9]{2})([0-9]{2})')
_RE_EXT_ORD = re.compile(r'([0-9]{4})-([0-9]{3})')
_RE_BAS_ORD = re.compile(r'([0-9]{4})([0-9]{3})')
_RE_EXT_WK = re.compile(r'([0-9]{4})-W([0-9]{2})-([0-9])')
_RE_BAS_WK = re.compile(r'([0-9]{4})W([0-9]{2})([0-9])')


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be a str, got {type(s).__name__}")

    m = _RE_EXT_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_BAS_CAL.fullmatch(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        if not (1 <= mo <= 12):
            raise ValueError(f"month {mo} out of range")
        if not (1 <= d <= _dim(y, mo)):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)

    m = _RE_EXT_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_BAS_ORD.fullmatch(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if not (1 <= y <= 9999):
            raise ValueError(f"year {y} out of range")
        max_doy = 366 if is_leap(y) else 365
        if not (1 <= doy <= max_doy):
            raise ValueError(f"day of year {doy} out of range 1..{max_doy}")
        return from_ordinal(_days_before_year(y) + doy)

    m = _RE_EXT_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"iso_year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date out of supported range")

    m = _RE_BAS_WK.fullmatch(s)
    if m:
        y, wk, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= y <= 9999):
            raise ValueError(f"iso_year {y} out of range")
        max_wk = iso_weeks_in_year(y)
        if not (1 <= wk <= max_wk):
            raise ValueError(f"week {wk} out of range 1..{max_wk}")
        if not (1 <= wd <= 7):
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, wk, wd)
        except OverflowError:
            raise ValueError(f"week date out of supported range")

    raise ValueError(f"unrecognized date format: {s!r}")


def format_date(date, form):
    _check_date(date, 'date')
    y, m, d = date
    _check_valid_date(y, m, d)
    if type(form) is not str:
        raise ValueError(f"form must be a str, got {type(form).__name__}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = to_ordinal(y, m, d) - to_ordinal(y, 1, 1) + 1
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd}"
    else:
        raise ValueError(f"unknown form: {form!r}")


def diff(a, b):
    _check_date(a, 'a')
    _check_date(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_valid_date(ay, am, ad)
    _check_valid_date(by, bm, bd)

    if a <= b:
        K = (by - ay) * 12 + (bm - am)
        if K > 0:
            total_k = (ay - 1) * 12 + (am - 1) + K
            sy = total_k // 12 + 1
            sm = total_k % 12 + 1
            sd = min(ad, _dim(sy, sm))
            if (sy, sm, sd) > (by, bm, bd):
                K -= 1
        total_k = (ay - 1) * 12 + (am - 1) + K
        sy = total_k // 12 + 1
        sm = total_k % 12 + 1
        sd = min(ad, _dim(sy, sm))
        years, months = divmod(K, 12)
        days = to_ordinal(by, bm, bd) - to_ordinal(sy, sm, sd)
        return (years, months, days)
    else:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
