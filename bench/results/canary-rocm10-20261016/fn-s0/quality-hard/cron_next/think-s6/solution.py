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

    minute_set = _parse_field(fields[0], 0, 59, None)
    hour_set = _parse_field(fields[1], 0, 23, None)
    dom_set = _parse_field(fields[2], 1, 31, None)
    month_set = _parse_field(fields[3], 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(fields[4], 0, 7, _DOW_NAMES)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    # Normalize day-of-week: 7 means Sunday (0)
    dow_set = {0 if v == 7 else v for v in dow_set}

    # Compute the earliest candidate time (strictly after 'after', whole minute)
    start = after + datetime.timedelta(minutes=1)
    start = start.replace(second=0, microsecond=0)

    horizon_year = after.year + 8

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    current_date = start.date()
    horizon_end = datetime.date(horizon_year, 12, 31)

    while current_date <= horizon_end:
        if current_date.month in month_set:
            if _day_matches(current_date, dom_set, dow_set, dom_restricted, dow_restricted):
                if current_date == start.date():
                    result = _find_in_day(
                        current_date, sorted_hours, sorted_minutes,
                        start.hour, start.minute
                    )
                else:
                    result = _find_in_day(
                        current_date, sorted_hours, sorted_minutes, 0, 0
                    )
                if result is not None:
                    return result
        current_date += datetime.timedelta(days=1)

    raise LookupError("No matching time found within the search horizon")


def _split_fields(expr):
    i, j = 0, len(expr)
    while i < j and expr[i] in ' \t':
        i += 1
    while j > i and expr[j - 1] in ' \t':
        j -= 1
    if i == j:
        raise ValueError("Empty expression")

    fields = []
    current = []
    for ch in expr[i:j]:
        if ch in ' \t':
            if current:
                fields.append(''.join(current))
                current = []
        else:
            current.append(ch)
    if current:
        fields.append(''.join(current))

    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")
    return fields


def _parse_field(field_text, min_val, max_val, names):
    if not field_text:
        raise ValueError("Empty field")

    items = field_text.split(',')
    result = set()

    for item in items:
        if not item:
            raise ValueError("Empty list element")
        values = _parse_item(item, min_val, max_val, names)
        result.update(values)

    return result


def _parse_item(item, min_val, max_val, names):
    parts = item.split('/')
    if len(parts) > 2:
        raise ValueError("Multiple slashes in item")

    base = parts[0]
    step = None
    if len(parts) == 2:
        step = _parse_step(parts[1])

    if base == '*':
        start, end = min_val, max_val
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError("Invalid range")
        a = _parse_value(range_parts[0], names)
        b = _parse_value(range_parts[1], names)
        a = _check_range(a, min_val, max_val)
        b = _check_range(b, min_val, max_val)
        if a > b:
            raise ValueError("Reversed range")
        start, end = a, b
    else:
        val = _parse_value(base, names)
        val = _check_range(val, min_val, max_val)
        if step is not None:
            start, end = val, max_val
        else:
            return {val}

    if step is not None:
        result = set()
        v = start
        while v <= end:
            result.add(v)
            v += step
        return result
    else:
        return set(range(start, end + 1))


def _parse_value(token, names):
    if not token:
        raise ValueError("Empty value")

    # Check for a 3-letter ASCII name (only when names dict is provided)
    if names is not None and len(token) == 3:
        if all(('a' <= c <= 'z') or ('A' <= c <= 'Z') for c in token):
            upper = token.upper()
            if upper in names:
                return names[upper]
            else:
                raise ValueError(f"Unknown name: {token}")

    # Must be non-empty string of ASCII digits
    for c in token:
        if c < '0' or c > '9':
            raise ValueError(f"Invalid value token: {token}")

    return int(token)


def _parse_step(token):
    if not token:
        raise ValueError("Empty step")
    for c in token:
        if c < '0' or c > '9':
            raise ValueError(f"Invalid step token: {token}")
    val = int(token)
    if val < 1:
        raise ValueError("Step must be >= 1")
    return val


def _check_range(val, min_val, max_val):
    if val < min_val or val > max_val:
        raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
    return val


def _day_matches(date, dom_set, dow_set, dom_restricted, dow_restricted):
    dom = date.day
    # Python weekday(): Mon=0..Sun=6; Cron DOW: Sun=0..Sat=6
    dow = (date.weekday() + 1) % 7

    dom_match = dom in dom_set
    dow_match = dow in dow_set

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match


def _find_in_day(date, sorted_hours, sorted_minutes, min_hour, min_minute):
    for h in sorted_hours:
        if h < min_hour:
            continue
        if h > min_hour:
            return datetime.datetime(date.year, date.month, date.day, h, sorted_minutes[0])
        # h == min_hour: find first minute >= min_minute
        for m in sorted_minutes:
            if m >= min_minute:
                return datetime.datetime(date.year, date.month, date.day, h, m)
    return None
