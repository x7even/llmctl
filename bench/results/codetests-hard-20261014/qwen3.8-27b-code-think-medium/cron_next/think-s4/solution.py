import datetime

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

# (min_val, max_val, names_dict_or_None)
_FIELD_SPECS = [
    (0, 59, None),
    (0, 23, None),
    (1, 31, None),
    (1, 12, _MONTH_NAMES),
    (0, 7, _DOW_NAMES),
]


def _split_fields(expr):
    """Split expression on spaces/tabs, returning list of non-empty field strings."""
    fields = []
    current = []
    for ch in expr:
        if ch == ' ' or ch == '\t':
            if current:
                fields.append(''.join(current))
                current = []
        else:
            current.append(ch)
    if current:
        fields.append(''.join(current))
    return fields


def _parse_value(token, min_val, max_val, names):
    """Parse a single value token (number or name) and return int."""
    if not token:
        raise ValueError("Empty value token")

    # ASCII digits only
    if all('0' <= c <= '9' for c in token):
        val = int(token)
        if val < min_val or val > max_val:
            raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
        return val

    # ASCII letters only
    if all(('a' <= c <= 'z') or ('A' <= c <= 'Z') for c in token):
        if names is None:
            raise ValueError(f"Name '{token}' not allowed in this field")
        upper = token.upper()
        if len(upper) != 3:
            raise ValueError(f"Name must be exactly 3 letters: '{token}'")
        if upper not in names:
            raise ValueError(f"Unknown name: '{token}'")
        return names[upper]

    raise ValueError(f"Invalid token: '{token}'")


def _parse_item(item, min_val, max_val, names):
    """Parse a single cron item and return a set of ints."""
    if not item:
        raise ValueError("Empty item")

    # Handle step
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Malformed step in: '{item}'")
        base, step_str = parts
        if not step_str:
            raise ValueError(f"Empty step in: '{item}'")
        if not all('0' <= c <= '9' for c in step_str):
            raise ValueError(f"Invalid step: '{step_str}'")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"Step must be >= 1: {step}")
    else:
        base = item
        step = 1

    # Parse base to get start/end
    if base == '*':
        start = min_val
        end = max_val
    elif '-' in base:
        parts = base.split('-')
        if len(parts) != 2:
            raise ValueError(f"Malformed range: '{base}'")
        left_str, right_str = parts
        if not left_str or not right_str:
            raise ValueError(f"Malformed range: '{base}'")
        start = _parse_value(left_str, min_val, max_val, names)
        end = _parse_value(right_str, min_val, max_val, names)
        if start > end:
            raise ValueError(f"Reversed range: {start}-{end}")
    else:
        val = _parse_value(base, min_val, max_val, names)
        if '/' in item:
            # a/n shorthand for a-MAX/n
            start = val
            end = max_val
        else:
            return {val}

    return set(range(start, end + 1, step))


def _parse_field(field_str, min_val, max_val, names):
    """Parse a comma-separated field and return a set of ints."""
    if not field_str:
        raise ValueError("Empty field")
    items = field_str.split(',')
    values = set()
    for item in items:
        if not item:
            raise ValueError("Empty list element in field")
        values |= _parse_item(item, min_val, max_val, names)
    return values


def _parse(expr):
    """Parse and validate the full cron expression. Returns all sets and flags."""
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    minute_set = _parse_field(fields[0], *_FIELD_SPECS[0])
    hour_set = _parse_field(fields[1], *_FIELD_SPECS[1])
    dom_set = _parse_field(fields[2], *_FIELD_SPECS[2])
    month_set = _parse_field(fields[3], *_FIELD_SPECS[3])
    dow_set = _parse_field(fields[4], *_FIELD_SPECS[4])

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return (minute_set, hour_set, dom_set, month_set, dow_set,
            dom_restricted, dow_restricted)


def _day_matches(day, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
    """Check whether a calendar date matches the cron day rules."""
    if day.month not in month_set:
        return False

    # Python weekday(): Mon=0 ... Sun=6
    # Cron dow: Sun=0, Mon=1, ..., Sat=6
    cron_dow = (day.weekday() + 1) % 7

    if cron_dow == 0:
        dow_match = (0 in dow_set) or (7 in dow_set)
    else:
        dow_match = cron_dow in dow_set

    dom_match = day.day in dom_set

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match


def _find_time(day, hour_set, minute_set, min_h, min_m):
    """Find the earliest (h, m) in the sets with (h,m) >= (min_h, min_m)."""
    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    for h in sorted_hours:
        if h < min_h:
            continue
        if h == min_h:
            for m in sorted_minutes:
                if m >= min_m:
                    return datetime.datetime(day.year, day.month, day.day, h, m)
        else:
            return datetime.datetime(day.year, day.month, day.day, h, sorted_minutes[0])
    return None


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    """Compute the next firing time of a 5-field cron expression after `after`."""
    (minute_set, hour_set, dom_set, month_set, dow_set,
     dom_restricted, dow_restricted) = _parse(expr)

    # Next whole minute strictly after `after`
    if after.second > 0 or after.microsecond > 0:
        start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    else:
        start = after + datetime.timedelta(minutes=1)

    max_year = after.year + 8
    end_date = datetime.date(max_year, 12, 31)

    current = start.date()
    while current <= end_date:
        if _day_matches(current, month_set, dom_set, dow_set,
                        dom_restricted, dow_restricted):
            if current == start.date():
                min_h, min_m = start.hour, start.minute
            else:
                min_h, min_m = 0, 0

            result = _find_time(current, hour_set, minute_set, min_h, min_m)
            if result is not None:
                return result

        current += datetime.timedelta(days=1)

    raise LookupError("No firing time found within search horizon")