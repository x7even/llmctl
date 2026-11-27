import re

# Precomputed days in months (1-indexed, 0 at index 0)
_MONTH_DAYS = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# Cumulative days before month m (1-indexed)
# _MONTH_DAYS_CUM[m] = sum(_MONTH_DAYS[1...m-1])
_MONTH_DAYS_CUM = [0] * 13
_acc = 0
for _i in range(1, 13):
    _MONTH_DAYS_CUM[_i] = _acc
    _acc += _MONTH_DAYS[_i]

# Regex patterns for parse
_RE_CAL_EXT = re.compile(r'^([0-9]{4})-([0-9]{2})-([0-9]{2})$')
_RE_CAL_BAS = re.compile(r'^([0-9]{4})([0-9]{2})([0-9]{2})$')
_RE_ORD_EXT = re.compile(r'^([0-9]{4})-([0-9]{3})$')
_RE_ORD_BAS = re.compile(r'^([0-9]{4})([0-9]{3})$')
_RE_WEEK_EXT = re.compile(r'^([0-9]{4})-W([0-9]{2})-([0-9])$')
_RE_WEEK_BAS = re.compile(r'^([0-9]{4})W([0-9]{2})([0-9])$')

def check_int(x):
    if type(x) is not int:
        raise TypeError

def check_date(t):
    if type(t) is not tuple:
        raise TypeError
    if len(t) != 3:
        raise TypeError
    if type(t[0]) is not int or type(t[1]) is not int or type(t[2]) is not int:
        raise TypeError

def is_leap(y):
    check_int(y)
    if not (1 <= y <= 9999):
        raise ValueError
    return (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)

def days_in_month(y, m):
    check_int(y)
    check_int(m)
    if not (1 <= y <= 9999):
        raise ValueError
    if not (1 <= m <= 12):
        raise ValueError
    if m == 2:
        return 29 if is_leap(y) else 28
    return _MONTH_DAYS[m]

def _days_before_year(y):
    # y is valid int 1..9999
    k = y - 1
    return 365 * k + k // 4 - k // 100 + k // 400

def to_ordinal(y, m, d):
    check_int(y)
    check_int(m)
    check_int(d)
    if not (1 <= y <= 9999):
        raise ValueError
    if not (1 <= m <= 12):
        raise ValueError
    dim = days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError
    
    days = _days_before_year(y)
    days += _MONTH_DAYS_CUM[m]
    if m > 2 and is_leap(y):
        days += 1
    days += d
    return days

def from_ordinal(n):
    check_int(n)
    if not (1 <= n <= 3652059):
        raise ValueError
    
    # Approximate year
    y = (n * 400) // 146097 + 1
    
    # Adjust y if needed
    k = y - 1
    dby = 365 * k + k // 4 - k // 100 + k // 400
    
    if dby >= n:
        # y is too high
        while dby >= n:
            y -= 1
            k -= 1
            dby = 365 * k + k // 4 - k // 100 + k // 400
            
    # Check if y is too low: days_before_year(y+1) < n
    while True:
        # days before year y+1
        k_next = y 
        dby_next = 365 * k_next + k_next // 4 - k_next // 100 + k_next // 400
        if dby_next >= n:
            break
        y += 1
        dby = dby_next 
        
    # Now y is correct year
    day_of_year = n - dby
    
    # Find month
    m = 1
    while m <= 12:
        if m == 2:
            dim = 29 if is_leap(y) else 28
        else:
            dim = _MONTH_DAYS[m]
        
        if day_of_year <= dim:
            break
        day_of_year -= dim
        m += 1
    
    d = day_of_year
    return (y, m, d)

def weekday(y, m, d):
    check_int(y)
    check_int(m)
    check_int(d)
    if not (1 <= y <= 9999):
        raise ValueError
    if not (1 <= m <= 12):
        raise ValueError
    dim = days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError
    
    # (1, 1, 1) is Monday (0)
    # ordinal 1 -> 0
    ord_val = to_ordinal(y, m, d)
    return (ord_val - 1) % 7

def add_days(date, n):
    check_date(date)
    check_int(n)
    y, m, d = date
    
    # Check validity
    try:
        to_ordinal(y, m, d)
    except ValueError:
        raise
    
    ord_val = to_ordinal(y, m, d)
    new_ord = ord_val + n
    
    if new_ord < 1 or new_ord > 3652059:
        raise OverflowError
    
    return from_ordinal(new_ord)

def add_months(date, n):
    check_date(date)
    check_int(n)
    y, m, d = date
    
    # Check validity
    try:
        to_ordinal(y, m, d)
    except ValueError:
        raise

    # Calculate target month index
    M = (y - 1) * 12 + m + n
    
    if M < 1:
        raise OverflowError
    
    y_new = (M - 1) // 12 + 1
    m_new = (M - 1) % 12 + 1
    
    if y_new > 9999:
        raise OverflowError
    
    # Clamp day
    dim = days_in_month(y_new, m_new)
    if d > dim:
        d = dim
    
    return (y_new, m_new, d)

def iso_weeks_in_year(iso_year):
    check_int(iso_year)
    if not (1 <= iso_year <= 9999):
        raise ValueError
    
    w = weekday(iso_year, 1, 1)
    if w == 3 or (is_leap(iso_year) and w == 2):
        return 53
    return 52

def iso_week(y, m, d):
    check_int(y)
    check_int(m)
    check_int(d)
    if not (1 <= y <= 9999):
        raise ValueError
    if not (1 <= m <= 12):
        raise ValueError
    dim = days_in_month(y, m)
    if not (1 <= d <= dim):
        raise ValueError
    
    ord_val = to_ordinal(y, m, d)
    w = (ord_val - 1) % 7
    thursday_ord = ord_val - w + 3
    
    iso_year, _, _ = from_ordinal(thursday_ord)
    
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_w = (jan4_ord - 1) % 7
    first_monday_ord = jan4_ord - jan4_w
    
    monday_ord = ord_val - w
    iso_week_num = 1 + (monday_ord - first_monday_ord) // 7
    
    iso_weekday = w + 1
    return (iso_year, iso_week_num, iso_weekday)

def from_iso_week(iso_year, week, weekday):
    check_int(iso_year)
    check_int(week)
    check_int(weekday)
    
    if not (1 <= iso_year <= 9999):
        raise ValueError
    if not (1 <= week <= iso_weeks_in_year(iso_year)):
        raise ValueError
    if not (1 <= weekday <= 7):
        raise ValueError
    
    jan4_ord = to_ordinal(iso_year, 1, 4)
    jan4_w = (jan4_ord - 1) % 7
    first_monday_ord = jan4_ord - jan4_w
    
    target_monday_ord = first_monday_ord + (week - 1) * 7
    target_ord = target_monday_ord + (weekday - 1)
    
    if target_ord < 1 or target_ord > 3652059:
        raise OverflowError
    
    return from_ordinal(target_ord)

def parse(s):
    if type(s) is not str:
        raise TypeError
    
    m = _RE_CAL_EXT.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y == 0 or not (1 <= y <= 9999): raise ValueError
        if mo == 0 or mo > 12: raise ValueError
        dim = days_in_month(y, mo)
        if d == 0 or d > dim: raise ValueError
        return (y, mo, d)
        
    m = _RE_CAL_BAS.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y == 0 or not (1 <= y <= 9999): raise ValueError
        if mo == 0 or mo > 12: raise ValueError
        dim = days_in_month(y, mo)
        if d == 0 or d > dim: raise ValueError
        return (y, mo, d)
        
    m = _RE_ORD_EXT.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y == 0 or not (1 <= y <= 9999): raise ValueError
        if doy == 0: raise ValueError
        dim_year = 366 if is_leap(y) else 365
        if doy > dim_year: raise ValueError
        k = y - 1
        ord_val = 365 * k + k // 4 - k // 100 + k // 400 + doy
        return from_ordinal(ord_val)
        
    m = _RE_ORD_BAS.match(s)
    if m:
        y, doy = int(m.group(1)), int(m.group(2))
        if y == 0 or not (1 <= y <= 9999): raise ValueError
        if doy == 0: raise ValueError
        dim_year = 366 if is_leap(y) else 365
        if doy > dim_year: raise ValueError
        k = y - 1
        ord_val = 365 * k + k // 4 - k // 100 + k // 400 + doy
        return from_ordinal(ord_val)
        
    m = _RE_WEEK_EXT.match(s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y == 0 or not (1 <= y <= 9999): raise ValueError
        max_w = iso_weeks_in_year(y)
        if w < 1 or w > max_w: raise ValueError
        if wd < 1 or wd > 7: raise ValueError
        
        jan4_ord = to_ordinal(y, 1, 4)
        jan4_w = (jan4_ord - 1) % 7
        first_monday_ord = jan4_ord - jan4_w
        
        target_monday_ord = first_monday_ord + (w - 1) * 7
        target_ord = target_monday_ord + (wd - 1)
        
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError
        
        return from_ordinal(target_ord)
        
    m = _RE_WEEK_BAS.match(s)
    if m:
        y, w, wd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y == 0 or not (1 <= y <= 9999): raise ValueError
        max_w = iso_weeks_in_year(y)
        if w < 1 or w > max_w: raise ValueError
        if wd < 1 or wd > 7: raise ValueError
        
        jan4_ord = to_ordinal(y, 1, 4)
        jan4_w = (jan4_ord - 1) % 7
        first_monday_ord = jan4_ord - jan4_w
        
        target_monday_ord = first_monday_ord + (w - 1) * 7
        target_ord = target_monday_ord + (wd - 1)
        
        if target_ord < 1 or target_ord > 3652059:
            raise ValueError
        
        return from_ordinal(target_ord)
        
    raise ValueError

def format_date(date, form):
    check_date(date)
    y, m, d = date
    
    # Check range
    if not (1 <= y <= 9999): raise ValueError
    if not (1 <= m <= 12): raise ValueError
    dim = days_in_month(y, m)
    if not (1 <= d <= dim): raise ValueError

    if form == 'calendar':
        return f"{y:04d}-{m:02d}-{d:02d}"
    elif form == 'ordinal':
        k = y - 1
        dby = 365 * k + k // 4 - k // 100 + k // 400
        ord_val = to_ordinal(y, m, d)
        doy = ord_val - dby
        return f"{y:04d}-{doy:03d}"
    elif form == 'week':
        iso_y, iso_w, iso_wd = iso_week(y, m, d)
        return f"{iso_y:04d}-W{iso_w:02d}-{iso_wd:01d}"
    else:
        raise ValueError

def diff(a, b):
    check_date(a)
    check_date(b)
    y1, m1, d1 = a
    y2, m2, d2 = b
    
    # Check validity
    try:
        to_ordinal(y1, m1, d1)
        to_ordinal(y2, m2, d2)
    except ValueError:
        raise

    if a == b:
        return (0, 0, 0)
    
    if a > b:
        res = diff(b, a)
        return (-res[0], -res[1], -res[2])
    
    # a < b
    # Find K
    K = 12 * (y2 - y1) + (m2 - m1)
    
    # Check shift(a, K)
    s = add_months(a, K)
    
    if s > b:
        K -= 1
        s = add_months(a, K)
    
    years, months = divmod(K, 12)
    
    ord_b = to_ordinal(y2, m2, d2)
    ord_s = to_ordinal(s[0], s[1], s[2])
    days = ord_b - ord_s
    
    return (years, months, days)
