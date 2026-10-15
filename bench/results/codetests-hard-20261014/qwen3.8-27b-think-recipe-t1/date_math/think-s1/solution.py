import re

# ─── type / range check helpers ────────────────────────────────────────────

def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")

def _check_date_tuple(x, name):
    if type(x) is not tuple or len(x) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i in range(3):
        if type(x[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int")

def _check_str(x, name):
    if type(x) is not str:
        raise TypeError(f"{name} must be str")

def _check_year(y):
    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range 1..9999")

def _check_month(m):
    if not 1 <= m <= 12:
        raise ValueError(f"month {m} out of range 1..12")

def _check_date(y, m, d):
    _check_year(y)
    _check_month(m)
    if not 1 <= d <= days_in_month(y, m):
        raise ValueError(f"day {d} out of range for {y}-{m}")

# ─── core calendar arithmetic ──────────────────────────────────────────────

def is_leap(y):
    _check_int(y, 'y')
    _check_year(y)
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_year(y)
    _check_month(m)
    if m == 2:
        return 29 if is_leap(y) else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31

def _year_start(y):
    """Ordinal of (y, 1, 1)."""
    return 365 * (y - 1) + (y - 1) // 4 - (y - 1) // 100 + (y - 1) // 400 + 1

def _day_of_year(y, m, d):
    days = 0
    for i in range(1, m):
        days += days_in_month(y, i)
    return days + d

def _from_day_of_year(y, doy):
    m = 1
    while m <= 12:
        dim = days_in_month(y, m)
        if doy <= dim:
            return (y, m, doy)
        doy -= dim
        m += 1
    raise ValueError("internal: invalid day-of-year")

def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date(y, m, d)
    return _year_start(y) + _day_of_year(y, m, d) - 1

def from_ordinal(n):
    _check_int(n, 'n')
    if not 1 <= n <= 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _year_start(mid) <= n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    doy = n - _year_start(y) + 1
    return _from_day_of_year(y, doy)

def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date(y, m, d)
    return (to_ordinal(y, m, d) - 1) % 7

def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date(y, m, d)
    ord_n = to_ordinal(y, m, d) + n
    if ord_n < 1 or ord_n > 3652059:
        raise OverflowError(f"result out of supported range")
    return from_ordinal(ord_n)

def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_date(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ny = total // 12 + 1
    nm = total % 12 + 1
    if not 1 <= ny <= 9999:
        raise OverflowError(f"result year {ny} out of range")
    nd = min(d, days_in_month(ny, nm))
    return (ny, nm, nd)

# ─── ISO week ──────────────────────────────────────────────────────────────

def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    _check_year(iso_year)
    wd = (to_ordinal(iso_year, 1, 1) - 1) % 7
    if wd == 3 or (is_leap(iso_year) and wd == 2):
        return 53
    return 52

def _iso_week_start(iso_year):
    """Ordinal of the Monday that begins ISO week 1 of *iso_year*."""
    jan4 = to_ordinal(iso_year, 1, 4)
    return jan4 - (jan4 - 1) % 7

def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_date(y, m, d)
    ordinal = to_ordinal(y, m, d)
    wd0 = (ordinal - 1) % 7          # Mon=0
    monday = ordinal - wd0
    thursday = monday + 3
    iso_y = from_ordinal(thursday)[0]
    start_w1 = _iso_week_start(iso_y)
    week = (ordinal - start_w1) // 7 + 1
    return (iso_y, week, wd0 + 1)

def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    _check_year(iso_year)
    max_w = iso_weeks_in_year(iso_year)
    if not 1 <= week <= max_w:
        raise ValueError(f"week {week} out of range 1..{max_w}")
    if not 1 <= weekday <= 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    target = _iso_week_start(iso_year) + (week - 1) * 7 + (weekday - 1)
    if target < 1 or target > 3652059:
        raise OverflowError(f"result out of supported range")
    return from_ordinal(target)

# ─── parse / format ────────────────────────────────────────────────────────

_PARSE_RE = re.compile(
    r'(?:'
    r'([0-9]{4})-([0-9]{2})-([0-9]{2})'   # ext calendar
    r'|([0-9]{4})([0-9]{2})([0-9]{2})'    # basic calendar
    r'|([0-9]{4})-([0-9]{3})'             # ext ordinal
    r'|([0-9]{4})([0-9]{3})'              # basic ordinal
    r'|([0-9]{4})-W([0-9]{2})-([0-9])'    # ext week
    r'|([0-9]{4})W([0-9]{2})([0-9])'      # basic week
    r')\Z'
)

def parse(s):
    _check_str(s, 's')
    m = _PARSE_RE.match(s)
    if m is None:
        raise ValueError(f"invalid date string: {s!r}")
    g = m.groups()

    if g[0] is not None:            # extended calendar
        y, mo, d = int(g[0]), int(g[1]), int(g[2])
    elif g[3] is not None:          # basic calendar
        y, mo, d = int(g[3]), int(g[4]), int(g[5])
    elif g[6] is not None:          # extended ordinal
        y, doy = int(g[6]), int(g[7])
    elif g[8] is not None:          # basic ordinal
        y, doy = int(g[8]), int(g[9])
    elif g[10] is not None:         # extended week
        y, w, wd = int(g[10]), int(g[11]), int(g[12])
    else:                           # basic week
        y, w, wd = int(g[13]), int(g[14]), int(g[15])

    if not 1 <= y <= 9999:
        raise ValueError(f"year {y} out of range")

    if 'mo' in dir() and mo is not None:  # calendar forms
        pass  # handled below by checking which branch we're in

    # Determine form and validate
    if g[0] is not None or g[3] is not None:
        # calendar
        if not 1 <= mo <= 12:
            raise ValueError(f"month {mo} out of range")
        if not 1 <= d <= days_in_month(y, mo):
            raise ValueError(f"day {d} out of range")
        return (y, mo, d)
    elif g[6] is not None or g[8] is not None:
        # ordinal
        max_doy = 366 if is_leap(y) else 365
        if not 1 <= doy <= max_doy:
            raise ValueError(f"day of year {doy} out of range")
        return _from_day_of_year(y, doy)
    else:
        # week
        max_w = iso_weeks_in_year(y)
        if not 1 <= w <= max_w:
            raise ValueError(f"week {w} out of range 1..{max_w}")
        if not 1 <= wd <= 7:
            raise ValueError(f"weekday {wd} out of range 1..7")
        try:
            return from_iso_week(y, w, wd)
        except OverflowError:
            raise ValueError("week date outside supported range")

def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_date(y, m, d)
    if form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")
    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _day_of_year(y, m, d)
        return f"{y:04d}-{doy:03d}"
    else:
        iso_y, iso_w, iso_d = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_d:01d}"

# ─── diff ──────────────────────────────────────────────────────────────────

def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_date(ay, am, ad)
    _check_date(by, bm, bd)

    if a <= b:
        def _shift(k):
            total = (ay - 1) * 12 + (am - 1) + k
            ny = total // 12 + 1
            nm = total % 12 + 1
            if not 1 <= ny <= 9999:
                return None
            nd = min(ad, days_in_month(ny, nm))
            return (ny, nm, nd)

        lo, hi = 0, (by - ay) * 12 + 12
        while lo < hi:
            mid = (lo + hi + 1) // 2
            s = _shift(mid)
            if s is not None and s <= b:
                lo = mid
            else:
                hi = mid - 1
        K = lo
        s = _shift(K)
        years, months = divmod(K, 12)
        days = to_ordinal(by, bm, bd) - to_ordinal(s[0], s[1], s[2])
        return (years, months, days)
    else:
        y, m, d = diff(b, a)
        return (-y, -m, -d)
