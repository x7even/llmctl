import datetime
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def _is_digits(s):
    return len(s) > 0 and all(c in '0123456789' for c in s)


def _parse_value(s, min_val, max_val, names):
    if not s:
        raise ValueError("Empty value token")
    if names:
        upper = s.upper()
        if upper in names:
            val = names[upper]
            if val < min_val or val > max_val:
                raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
            return val
    if not _is_digits(s):
        raise ValueError(f"Invalid value token '{s}'")
    val = int(s)
    if val < min_val or val > max_val:
        raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
    return val


def _parse_item(item, min_val, max_val, names, values):
    step = 1
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Malformed item '{item}'")
        base, step_str = parts
        if not _is_digits(step_str):
            raise ValueError(f"Invalid step '{step_str}'")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"Step must be >= 1, got {step}")
    else:
        base = item

    if base == '*':
        start, end = min_val, max_val
    elif '-' in base:
        dash_parts = base.split('-')
        if len(dash_parts) != 2:
            raise ValueError(f"Malformed range '{base}'")
        a_str, b_str = dash_parts
        a = _parse_value(a_str, min_val, max_val, names)
        b = _parse_value(b_str, min_val, max_val, names)
        if a > b:
            raise ValueError(f"Reversed range {a}-{b}")
        start, end = a, b
    else:
        a = _parse_value(base, min_val, max_val, names)
        if '/' in item:
            start, end = a, max_val
        else:
            start, end = a, a

    for v in range(start, end + 1, step):
        values.add(v)


def _parse_field(text, min_val, max_val, names):
    if not text:
        raise ValueError("Empty field")
    values = set()
    for item in text.split(','):
        if not item:
            raise ValueError("Empty list element in field")
        _parse_item(item, min_val, max_val, names, values)
    return values


def _split_fields(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")
    return re.split(r'[ \t]+', stripped)


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    minutes = _parse_field(fields[0], 0, 59, {})
    hours = _parse_field(fields[1], 0, 23, {})
    doms = _parse_field(fields[2], 1, 31, {})
    months = _parse_field(fields[3], 1, 12, _MONTH_NAMES)
    dows = _parse_field(fields[4], 0, 7, _DOW_NAMES)

    # Normalize: 7 means Sunday (0)
    if 7 in dows:
        dows.add(0)

    # Vixie-cron restricted test (purely textual)
    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    sorted_hours = sorted(hours)
    sorted_minutes = sorted(minutes)

    # Next whole minute strictly after `after`
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    # Search horizon
    max_year = after.year + 8
    max_dt = datetime.datetime(max_year, 12, 31, 23, 59)
    end_date = max_dt.date()

    current = start.date()

    while current <= end_date:
        if current.month not in months:
            current += datetime.timedelta(days=1)
            continue

        # Python weekday(): Mon=0..Sun=6; we need Sun=0, Mon=1..Sat=6
        dow = (current.weekday() + 1) % 7

        if dom_restricted and dow_restricted:
            day_match = (current.day in doms) or (dow in dows)
        else:
            day_match = (current.day in doms) and (dow in dows)

        if not day_match:
            current += datetime.timedelta(days=1)
            continue

        # Find earliest (hour, minute) on this day that is > after
        for h in sorted_hours:
            for m in sorted_minutes:
                candidate = datetime.datetime(
                    current.year, current.month, current.day, h, m
                )
                if candidate > after:
                    return candidate

        current += datetime.timedelta(days=1)

    raise LookupError("No matching firing time within search horizon")
