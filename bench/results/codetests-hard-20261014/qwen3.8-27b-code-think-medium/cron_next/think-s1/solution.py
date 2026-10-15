import datetime


_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}
_DIGITS = frozenset('0123456789')
_ASCII_LETTERS = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
)


def _parse_value(token, min_val, max_val, names):
    """Parse a single value token (number or name) and range-check it."""
    if not token:
        raise ValueError("Empty value token")
    if all(c in _DIGITS for c in token):
        val = int(token)
    elif names is not None and len(token) == 3 and all(c in _ASCII_LETTERS for c in token):
        upper = token.upper()
        if upper in names:
            val = names[upper]
        else:
            raise ValueError(f"Unknown name: {token}")
    else:
        raise ValueError(f"Invalid token: {token!r}")
    if val < min_val or val > max_val:
        raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
    return val


def _parse_step(token):
    """Parse a step value (positive integer)."""
    if not token:
        raise ValueError("Empty step")
    if not all(c in _DIGITS for c in token):
        raise ValueError(f"Invalid step: {token!r}")
    val = int(token)
    if val < 1:
        raise ValueError("Step must be >= 1")
    return val


def _parse_item(item, min_val, max_val, names):
    """Parse a single item (e.g. '*', '5', '1-10', '*/5', '3-20/4', '5/10')."""
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Malformed item: {item!r}")
        base_str, step_str = parts
        step = _parse_step(step_str)
    else:
        base_str = item
        step = 1

    if base_str == '*':
        start, end = min_val, max_val
    elif '-' in base_str:
        range_parts = base_str.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"Malformed range: {base_str!r}")
        start = _parse_value(range_parts[0], min_val, max_val, names)
        end = _parse_value(range_parts[1], min_val, max_val, names)
        if start > end:
            raise ValueError(f"Reversed range: {start}-{end}")
    else:
        val = _parse_value(base_str, min_val, max_val, names)
        if '/' in item:
            # a/n shorthand for a-MAX/n
            return set(range(val, max_val + 1, step))
        else:
            return {val}

    return set(range(start, end + 1, step))


def _parse_field(field_text, min_val, max_val, names=None):
    """Parse a full field (comma-separated list of items) into a set of ints."""
    if not field_text:
        raise ValueError("Empty field")
    result = set()
    for item in field_text.split(','):
        if not item:
            raise ValueError("Empty list element in field")
        result |= _parse_item(item, min_val, max_val, names)
    return result


def _days_in_month(year, month):
    """Return the number of days in the given month/year (proleptic Gregorian)."""
    if month == 12:
        return (datetime.datetime(year + 1, 1, 1) - datetime.datetime(year, 12, 1)).days
    return (datetime.datetime(year, month + 1, 1) - datetime.datetime(year, month, 1)).days


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    """Compute the next firing time of a standard 5-field cron expression."""
    # --- Split expression into exactly 5 fields (separated by spaces/tabs) ---
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")

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

    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    # --- Parse and validate all five fields ---
    minute_set = _parse_field(fields[0], 0, 59, None)
    hour_set = _parse_field(fields[1], 0, 23, None)
    dom_set = _parse_field(fields[2], 1, 31, None)
    month_set = _parse_field(fields[3], 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(fields[4], 0, 7, _DOW_NAMES)

    # Normalise day-of-week: 7 means Sunday (0)
    if 7 in dow_set:
        dow_set.add(0)

    # Vixie-cron restricted test (purely textual)
    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    # --- Determine the search start (strictly after `after`, whole minutes) ---
    t = after.replace(second=0, microsecond=0)
    if t <= after:
        t = t + datetime.timedelta(minutes=1)

    # --- Search within the horizon ---
    max_year = after.year + 8
    sorted_minutes = sorted(minute_set)
    sorted_hours = sorted(hour_set)
    sorted_months = sorted(month_set)

    for year in range(t.year, max_year + 1):
        for month in sorted_months:
            if year == t.year and month < t.month:
                continue
            dim = _days_in_month(year, month)
            for day in range(1, dim + 1):
                if year == t.year and month == t.month and day < t.day:
                    continue
                # Day of week: Sun=0, Mon=1, ..., Sat=6
                dow = (datetime.datetime(year, month, day).weekday() + 1) % 7
                dom_ok = day in dom_set
                dow_ok = dow in dow_set
                if dom_restricted and dow_restricted:
                    if not (dom_ok or dow_ok):
                        continue
                else:
                    if not (dom_ok and dow_ok):
                        continue
                for hour in sorted_hours:
                    if year == t.year and month == t.month and day == t.day and hour < t.hour:
                        continue
                    for minute in sorted_minutes:
                        if (year == t.year and month == t.month and day == t.day
                                and hour == t.hour and minute < t.minute):
                            continue
                        return datetime.datetime(year, month, day, hour, minute)

    raise LookupError("No matching time found within the 8-year horizon")
