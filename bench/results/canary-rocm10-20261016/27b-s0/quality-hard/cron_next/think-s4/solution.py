import datetime

MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}

DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6
}

_DIGITS = frozenset('0123456789')
_ALPHA = frozenset(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
)


def _split_fields(expr):
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
    return fields


def _parse_value(token, min_val, max_val, names):
    if not token:
        raise ValueError("Empty value")
    all_digits = all(c in _DIGITS for c in token)
    all_alpha = all(c in _ALPHA for c in token)
    if all_alpha:
        if not names:
            raise ValueError(f"Name not allowed in this field: {token!r}")
        upper = token.upper()
        if upper not in names:
            raise ValueError(f"Unknown name: {token!r}")
        val = names[upper]
        if val < min_val or val > max_val:
            raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
        return val
    elif all_digits:
        val = int(token)
        if val < min_val or val > max_val:
            raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
        return val
    else:
        raise ValueError(f"Invalid value: {token!r}")


def _parse_step(token):
    if not token:
        raise ValueError("Empty step")
    if not all(c in _DIGITS for c in token):
        raise ValueError(f"Invalid step: {token!r}")
    val = int(token)
    if val < 1:
        raise ValueError(f"Step must be >= 1: {val}")
    return val


def _parse_item(item, min_val, max_val, names):
    if not item:
        raise ValueError("Empty item")

    step = 1
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Malformed step in {item!r}")
        base, step_str = parts
        step = _parse_step(step_str)
    else:
        base = item

    if base == '*':
        start, end = min_val, max_val
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"Malformed range in {item!r}")
        a_str, b_str = range_parts
        if not a_str or not b_str:
            raise ValueError(f"Malformed range in {item!r}")
        a = _parse_value(a_str, min_val, max_val, names)
        b = _parse_value(b_str, min_val, max_val, names)
        if a > b:
            raise ValueError(f"Reversed range: {a}-{b}")
        start, end = a, b
    else:
        val = _parse_value(base, min_val, max_val, names)
        if '/' in item:
            start, end = val, max_val
        else:
            return {val}

    return set(range(start, end + 1, step))


def _parse_field(field_str, min_val, max_val, names):
    if not field_str:
        raise ValueError("Empty field")
    is_restricted = not field_str.startswith('*')
    values = set()
    items = field_str.split(',')
    for item in items:
        if not item:
            raise ValueError(f"Empty list element in field: {field_str!r}")
        values.update(_parse_item(item, min_val, max_val, names))
    return values, is_restricted


def _day_matches(day, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
    if day.month not in month_set:
        return False
    dom_ok = day.day in dom_set
    py_dow = day.weekday()
    cron_dow = (py_dow + 1) % 7
    if cron_dow == 0:
        dow_ok = (0 in dow_set) or (7 in dow_set)
    else:
        dow_ok = cron_dow in dow_set
    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def _find_earliest_hm(sorted_hours, sorted_minutes, min_h, min_m):
    for h in sorted_hours:
        if h < min_h:
            continue
        if h == min_h:
            for m in sorted_minutes:
                if m >= min_m:
                    return (h, m)
        else:
            return (h, sorted_minutes[0])
    return None


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    minute_set, _ = _parse_field(fields[0], 0, 59, None)
    hour_set, _ = _parse_field(fields[1], 0, 23, None)
    dom_set, dom_restricted = _parse_field(fields[2], 1, 31, None)
    month_set, _ = _parse_field(fields[3], 1, 12, MONTH_NAMES)
    dow_set, dow_restricted = _parse_field(fields[4], 0, 7, DOW_NAMES)

    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    max_year = after.year + 8

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)
    start_date = start.date()

    current_day = start_date
    one_day = datetime.timedelta(days=1)

    while current_day.year <= max_year:
        if _day_matches(current_day, month_set, dom_set, dow_set,
                        dom_restricted, dow_restricted):
            if current_day == start_date:
                hm = _find_earliest_hm(sorted_hours, sorted_minutes,
                                       start.hour, start.minute)
            else:
                hm = _find_earliest_hm(sorted_hours, sorted_minutes, 0, 0)
            if hm is not None:
                h, m = hm
                return datetime.datetime(current_day.year, current_day.month,
                                         current_day.day, h, m)
        current_day += one_day

    raise LookupError("No firing time found within horizon")
