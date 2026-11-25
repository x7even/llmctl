import re


# ─── internal helpers (no public exposure) ───────────────────────────────────

def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _dim(y, m):
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if m in (4, 6, 9, 11):
        return 30
    return 29 if _is_leap(y) else 28


def _check_int(x, name):
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")


def _check_date_tuple(date, name):
    if type(date) is not tuple or len(date) != 3:
        raise TypeError(f"{name} must be a tuple of exactly 3 ints")
    for i in range(3):
        if type(date[i]) is not int:
            raise TypeError(f"{name}[{i}] must be int, got {type(date[i]).__name__}")


def _check_range(y, m, d):
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    if d < 1 or d > _dim(y, m):
        raise ValueError(f"day {d} out of range 1..{_dim(y, m)}")


def _days_before_year(y):
    """Days from year 1 through year y-1 (i.e. before Jan 1 of year y)."""
    y -= 1
    return 365 * y + y // 4 - y // 100 + y // 400


# Cumulative days before each month (0-indexed), non-leap year
_CUM = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def _month_offset(y, m):
    """Days from Jan 1 to the 1st of month m (0-based)."""
    off = _CUM[m - 1]
    if m > 2 and _is_leap(y):
        off += 1
    return off


def _to_ord(y, m, d):
    return _days_before_year(y) + _month_offset(y, m) + d


def _from_ord(n):
    """Convert ordinal (1-based) to (y, m, d). Assumes 1 <= n <= 3652059."""
    # Binary search for year
    lo, hi = 1, 9999
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _days_before_year(mid) < n:
            lo = mid
        else:
            hi = mid - 1
    y = lo
    # Day of year (1-based)
    doy = n - _days_before_year(y)
    # Find month
    if _is_leap(y):
        cum = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    else:
        cum = _CUM
    m = 1
    while m < 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (y, m, d)


def _iso_weeks_in_year(iy):
    jan1_wd = (_to_ord(iy, 1, 1) - 1) % 7  # 0=Mon
    if jan1_wd == 3 or (jan1_wd == 2 and _is_leap(iy)):
        return 53
    return 52


def _iso_week(y, m, d):
    ord_ = _to_ord(y, m, d)
    iso_wd = (ord_ - 1) % 7 + 1  # 1=Mon..7=Sun
    # Thursday of this week
    thu_ord = ord_ - iso_wd + 4
    iso_y = _from_ord(thu_ord)[0]
    # Monday of week 1 of iso_y
    jan4 = _to_ord(iso_y, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4_wd
    week = (ord_ - mon_w1) // 7 + 1
    return (iso_y, week, iso_wd)


def _from_iso_week(iy, week, wd):
    """Returns ordinal or raises OverflowError."""
    jan4 = _to_ord(iy, 1, 4)
    jan4_wd = (jan4 - 1) % 7
    mon_w1 = jan4 - jan4_wd
    target = mon_w1 + (week - 1) * 7 + (wd - 1)
    if target < 1 or target > 3652059:
        raise OverflowError("result out of range")
    return target


def _doy_to_md(y, doy):
    """Convert day-of-year (1-based) to (month, day)."""
    if _is_leap(y):
        cum = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    else:
        cum = _CUM
    m = 1
    while m < 12 and doy > cum[m]:
        m += 1
    d = doy - cum[m - 1]
    return (m, d)


def _md_to_doy(y, m, d):
    return _month_offset(y, m) + d


# ─── public API ──────────────────────────────────────────────────────────────

def is_leap(y):
    _check_int(y, 'y')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    return _is_leap(y)


def days_in_month(y, m):
    _check_int(y, 'y')
    _check_int(m, 'm')
    if y < 1 or y > 9999:
        raise ValueError(f"year {y} out of range 1..9999")
    if m < 1 or m > 12:
        raise ValueError(f"month {m} out of range 1..12")
    return _dim(y, m)


def to_ordinal(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_range(y, m, d)
    return _to_ord(y, m, d)


def from_ordinal(n):
    _check_int(n, 'n')
    if n < 1 or n > 3652059:
        raise ValueError(f"ordinal {n} out of range 1..3652059")
    return _from_ord(n)


def weekday(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_range(y, m, d)
    return (_to_ord(y, m, d) - 1) % 7


def add_days(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_range(y, m, d)
    ord_ = _to_ord(y, m, d) + n
    if ord_ < 1 or ord_ > 3652059:
        raise OverflowError("result out of range")
    return _from_ord(ord_)


def add_months(date, n):
    _check_date_tuple(date, 'date')
    _check_int(n, 'n')
    y, m, d = date
    _check_range(y, m, d)
    total = (y - 1) * 12 + (m - 1) + n
    ty = total // 12 + 1
    tm = total % 12 + 1
    if ty < 1 or ty > 9999:
        raise OverflowError("result out of range")
    td = min(d, _dim(ty, tm))
    return (ty, tm, td)


def iso_weeks_in_year(iso_year):
    _check_int(iso_year, 'iso_year')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    return _iso_weeks_in_year(iso_year)


def iso_week(y, m, d):
    _check_int(y, 'y')
    _check_int(m, 'm')
    _check_int(d, 'd')
    _check_range(y, m, d)
    return _iso_week(y, m, d)


def from_iso_week(iso_year, week, weekday):
    _check_int(iso_year, 'iso_year')
    _check_int(week, 'week')
    _check_int(weekday, 'weekday')
    if iso_year < 1 or iso_year > 9999:
        raise ValueError(f"iso_year {iso_year} out of range 1..9999")
    nw = _iso_weeks_in_year(iso_year)
    if week < 1 or week > nw:
        raise ValueError(f"week {week} out of range 1..{nw}")
    if weekday < 1 or weekday > 7:
        raise ValueError(f"weekday {weekday} out of range 1..7")
    target = _from_iso_week(iso_year, week, weekday)
    return _from_ord(target)


def parse(s):
    if type(s) is not str:
        raise TypeError(f"s must be str, got {type(s).__name__}")

    # All digits must be ASCII 0-9; use [0-9] in regex
    # Lengths: 7 (basic ordinal), 8 (ext ordinal / basic cal / basic week), 10 (ext cal / ext week)

    if len(s) == 7:
        # YYYYDDD (basic ordinal)
        mt = re.fullmatch(r'([0-9]{4})([0-9]{3})', s)
        if not mt:
            raise ValueError(f"invalid date string: {s!r}")
        y = int(mt.group(1))
        doy = int(mt.group(2))
        if y < 1 or y > 9999:
            raise ValueError("year out of range")
        max_doy = 366 if _is_leap(y) else 365
        if doy < 1 or doy > max_doy:
            raise ValueError("day of year out of range")
        m, d = _doy_to_md(y, doy)
        return (y, m, d)

    elif len(s) == 8:
        if s[4] == '-':
            # YYYY-DDD (extended ordinal)
            mt = re.fullmatch(r'([0-9]{4})-([0-9]{3})', s)
            if not mt:
                raise ValueError(f"invalid date string: {s!r}")
            y = int(mt.group(1))
            doy = int(mt.group(2))
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            max_doy = 366 if _is_leap(y) else 365
            if doy < 1 or doy > max_doy:
                raise ValueError("day of year out of range")
            m, d = _doy_to_md(y, doy)
            return (y, m, d)
        elif s[4] == 'W':
            # YYYYWwwD (basic week)
            mt = re.fullmatch(r'([0-9]{4})W([0-9]{2})([0-9])', s)
            if not mt:
                raise ValueError(f"invalid date string: {s!r}")
            iy = int(mt.group(1))
            wk = int(mt.group(2))
            wd = int(mt.group(3))
            if iy < 1 or iy > 9999:
                raise ValueError("year out of range")
            nw = _iso_weeks_in_year(iy)
            if wk < 1 or wk > nw:
                raise ValueError("week out of range")
            if wd < 1 or wd > 7:
                raise ValueError("weekday out of range")
            try:
                target = _from_iso_week(iy, wk, wd)
            except OverflowError:
                raise ValueError("date out of range")
            return _from_ord(target)
        else:
            # YYYYMMDD (basic calendar)
            mt = re.fullmatch(r'([0-9]{4})([0-9]{2})([0-9]{2})', s)
            if not mt:
                raise ValueError(f"invalid date string: {s!r}")
            y = int(mt.group(1))
            m = int(mt.group(2))
            d = int(mt.group(3))
            if y < 1 or y > 9999:
                raise ValueError("year out of range")
            if m < 1 or m > 12:
                raise ValueError("month out of range")
            if d < 1 or d > _dim(y, m):
                raise ValueError("day out of range")
            return (y, m, d)

    elif len(s) == 10:
        if s[4] == '-':
            if s[5] == 'W':
                # YYYY-Www-D (extended week)
                mt = re.fullmatch(r'([0-9]{4})-W([0-9]{2})-([0-9])', s)
                if not mt:
                    raise ValueError(f"invalid date string: {s!r}")
                iy = int(mt.group(1))
                wk = int(mt.group(2))
                wd = int(mt.group(3))
                if iy < 1 or iy > 9999:
                    raise ValueError("year out of range")
                nw = _iso_weeks_in_year(iy)
                if wk < 1 or wk > nw:
                    raise ValueError("week out of range")
                if wd < 1 or wd > 7:
                    raise ValueError("weekday out of range")
                try:
                    target = _from_iso_week(iy, wk, wd)
                except OverflowError:
                    raise ValueError("date out of range")
                return _from_ord(target)
            else:
                # YYYY-MM-DD (extended calendar)
                mt = re.fullmatch(r'([0-9]{4})-([0-9]{2})-([0-9]{2})', s)
                if not mt:
                    raise ValueError(f"invalid date string: {s!r}")
                y = int(mt.group(1))
                m = int(mt.group(2))
                d = int(mt.group(3))
                if y < 1 or y > 9999:
                    raise ValueError("year out of range")
                if m < 1 or m > 12:
                    raise ValueError("month out of range")
                if d < 1 or d > _dim(y, m):
                    raise ValueError("day out of range")
                return (y, m, d)
        else:
            raise ValueError(f"invalid date string: {s!r}")

    else:
        raise ValueError(f"invalid date string: {s!r}")


def format_date(date, form):
    _check_date_tuple(date, 'date')
    y, m, d = date
    _check_range(y, m, d)

    if type(form) is not str or form not in ('calendar', 'ordinal', 'week'):
        raise ValueError(f"invalid form: {form!r}")

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        doy = _md_to_doy(y, m, d)
        return f"{y:04d}-{doy:03d}"
    else:  # week
        iy, iw, iwd = _iso_week(y, m, d)
        return f"{iy:04d}-W{iw:02d}-{iwd}"


def diff(a, b):
    _check_date_tuple(a, 'a')
    _check_date_tuple(b, 'b')
    ay, am, ad = a
    by, bm, bd = b
    _check_range(ay, am, ad)
    _check_range(by, bm, bd)

    negate = False
    if (ay, am, ad) > (by, bm, bd):
        ay, am, ad, by, bm, bd = by, bm, bd, ay, am, ad
        negate = True

    # Find largest K >= 0 such that shift(ay,am,ad, K) <= (by,bm,bd)
    def shift(k):
        total = (ay - 1) * 12 + (am - 1) + k
        ty = total // 12 + 1
        tm = total % 12 + 1
        td = min(ad, _dim(ty, tm))
        return (ty, tm, td)

    lo = 0
    hi = (9999 - ay) * 12 + (12 - am) + 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if shift(mid) <= (by, bm, bd):
            lo = mid
        else:
            hi = mid - 1
    K = lo
    years, months = divmod(K, 12)
    days = _to_ord(by, bm, bd) - _to_ord(*shift(K))

    if negate:
        return (-years, -months, -days)
    return (years, months, days)