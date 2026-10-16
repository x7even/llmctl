import datetime


_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    minute_set = _parse_field(fields[0], 0, 59, None)
    hour_set = _parse_field(fields[1], 0, 23, None)
    dom_set = _parse_field(fields[2], 1, 31, None)
    month_set = _parse_field(fields[3], 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(fields[4], 0, 7, _DOW_NAMES)

    # Normalize DOW: 7 means Sunday (0)
    if 7 in dow_set:
        dow_set.add(0)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    # Compute start: strictly after `after`, whole minutes
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    max_year = after.year + 8
    sorted_minutes = sorted(minute_set)
    sorted_hours = sorted(hour_set)

    year = start.year
    while year <= max_year:
        for month in range(1, 13):
            if month not in month_set:
                continue
            if year == start.year and month < start.month:
                continue
            dim = _days_in_month(year, month)
            for day in range(1, dim + 1):
                if year == start.year and month == start.month and day < start.day:
                    continue
                if not _is_valid_day(year, month, day, dom_set, dow_set,
                                     dom_restricted, dow_restricted):
                    continue
                if year == start.year and month == start.month and day == start.day:
                    t = _first_valid_time(sorted_hours, sorted_minutes,
                                          start.hour, start.minute)
                else:
                    t = _first_valid_time(sorted_hours, sorted_minutes, 0, 0)
                if t is not None:
                    return datetime.datetime(year, month, day, t[0], t[1])
        year += 1

    raise LookupError("no firing time found within horizon")


def _split_fields(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        return []
    fields = []
    current = []
    for ch in stripped:
        if ch == ' ' or ch == '\t':
            if current:
                fields.append(''.join(current))
                current = []
        else:
            current.append(ch)
    if current:
        fields.append(''.join(current))
    return fields


def _parse_field(field_text, min_val, max_val, names):
    if not field_text:
        raise ValueError("empty field")
    items = field_text.split(',')
    for item in items:
        if item == '':
            raise ValueError("empty item in field")
    result = set()
    for item in items:
        result |= _parse_item(item, min_val, max_val, names)
    return result


def _parse_item(item, min_val, max_val, names):
    if not item:
        raise ValueError("empty item")

    step = None
    base = item

    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"malformed step in: {item}")
        base, step_str = parts
        if not step_str:
            raise ValueError("empty step")
        if not all(c in '0123456789' for c in step_str):
            raise ValueError(f"invalid step: {step_str}")
        step = int(step_str)
        if step < 1:
            raise ValueError("step must be >= 1")

    if base == '*':
        if step is None:
            return set(range(min_val, max_val + 1))
        else:
            return set(range(min_val, max_val + 1, step))

    if '-' in base:
        parts = base.split('-')
        if len(parts) != 2:
            raise ValueError(f"malformed range: {base}")
        a = _parse_value(parts[0], min_val, max_val, names)
        b = _parse_value(parts[1], min_val, max_val, names)
        if a > b:
            raise ValueError(f"reversed range: {a}-{b}")
        if step is None:
            return set(range(a, b + 1))
        else:
            return set(range(a, b + 1, step))

    # Single value (with optional step meaning a-MAX/n)
    a = _parse_value(base, min_val, max_val, names)
    if step is None:
        return {a}
    else:
        return set(range(a, max_val + 1, step))


def _parse_value(token, min_val, max_val, names):
    if not token:
        raise ValueError("empty value")

    if names is not None:
        upper = token.upper()
        if upper in names:
            return names[upper]

    # Must be ASCII digits only
    if not all(c in '0123456789' for c in token):
        raise ValueError(f"invalid value token: {token!r}")

    val = int(token)
    if val < min_val or val > max_val:
        raise ValueError(f"value {val} out of range [{min_val}, {max_val}]")
    return val


def _days_in_month(year, month):
    if month in (1, 3, 5, 7, 8, 10, 12):
        return 31
    elif month in (4, 6, 9, 11):
        return 30
    else:
        if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
            return 29
        return 28


def _is_valid_day(year, month, day, dom_set, dow_set, dom_restricted, dow_restricted):
    dt = datetime.datetime(year, month, day)
    # weekday(): Monday=0 ... Sunday=6; convert to Sunday=0 ... Saturday=6
    dow = (dt.weekday() + 1) % 7

    dom_ok = day in dom_set
    dow_ok = dow in dow_set

    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    else:
        return dom_ok and dow_ok


def _first_valid_time(sorted_hours, sorted_minutes, min_hour, min_minute):
    for h in sorted_hours:
        if h < min_hour:
            continue
        if h == min_hour:
            for m in sorted_minutes:
                if m >= min_minute:
                    return (h, m)
        else:
            if sorted_minutes:
                return (h, sorted_minutes[0])
    return None