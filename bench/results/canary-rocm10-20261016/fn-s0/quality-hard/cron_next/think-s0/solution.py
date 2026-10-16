import datetime

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

_DIGITS = frozenset('0123456789')
_LETTERS = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')


def _split_fields(expr):
    fields = []
    i = 0
    n = len(expr)
    while i < n:
        while i < n and expr[i] in ' \t':
            i += 1
        if i >= n:
            break
        j = i
        while j < n and expr[j] not in ' \t':
            j += 1
        fields.append(expr[i:j])
        i = j
    return fields


def _is_number(token):
    return len(token) > 0 and all(c in _DIGITS for c in token)


def _is_name(token):
    return len(token) == 3 and all(c in _LETTERS for c in token)


def _parse_value(token, min_val, max_val, allow_names, names):
    if not token:
        raise ValueError("Empty value token")
    if _is_number(token):
        val = int(token)
        if val < min_val or val > max_val:
            raise ValueError("Value out of range")
        return val
    if allow_names and _is_name(token):
        upper = token.upper()
        if upper in names:
            val = names[upper]
            if val < min_val or val > max_val:
                raise ValueError("Name value out of range")
            return val
        raise ValueError("Unknown name")
    raise ValueError("Invalid token")


def _parse_step(token):
    if not token:
        raise ValueError("Empty step")
    if not _is_number(token):
        raise ValueError("Invalid step")
    n = int(token)
    if n < 1:
        raise ValueError("Step must be >= 1")
    return n


def _parse_item(item, min_val, max_val, allow_names, names):
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError("Malformed step")
        base, step_str = parts
        step = _parse_step(step_str)
    else:
        base = item
        step = None

    if base == '*':
        start, end = min_val, max_val
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError("Malformed range")
        start = _parse_value(range_parts[0], min_val, max_val, allow_names, names)
        end = _parse_value(range_parts[1], min_val, max_val, allow_names, names)
        if start > end:
            raise ValueError("Reversed range")
    else:
        start = _parse_value(base, min_val, max_val, allow_names, names)
        if step is not None:
            end = max_val
        else:
            end = start

    if step is not None:
        return set(range(start, end + 1, step))
    return set(range(start, end + 1))


def _parse_field(field_str, min_val, max_val, allow_names=False, names=None):
    if not field_str:
        raise ValueError("Empty field")
    items = field_str.split(',')
    result = set()
    for item in items:
        if not item:
            raise ValueError("Empty list element")
        result |= _parse_item(item, min_val, max_val, allow_names, names)
    return result


def _day_matches(date, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
    if date.month not in month_set:
        return False
    cron_dow = (date.weekday() + 1) % 7
    dom_match = date.day in dom_set
    dow_match = cron_dow in dow_set
    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    return dom_match and dow_match


def _find_time(sorted_hours, sorted_minutes, min_hour, min_minute):
    for h in sorted_hours:
        if h > min_hour:
            return h, sorted_minutes[0]
        if h == min_hour:
            for m in sorted_minutes:
                if m >= min_minute:
                    return h, m
    return None, None


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError("Expected 5 fields")

    minute_set = _parse_field(fields[0], 0, 59)
    hour_set = _parse_field(fields[1], 0, 23)
    dom_set = _parse_field(fields[2], 1, 31)
    month_set = _parse_field(fields[3], 1, 12, allow_names=True, names=_MONTH_NAMES)
    dow_set = _parse_field(fields[4], 0, 7, allow_names=True, names=_DOW_NAMES)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    # Normalize day-of-week: 7 means Sunday (0)
    dow_set = set(0 if v == 7 else v for v in dow_set)

    # First candidate minute (strictly after `after`)
    start = after + datetime.timedelta(minutes=1)
    start = start.replace(second=0, microsecond=0)

    max_year = after.year + 8
    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    current_date = start.date()
    start_date = current_date
    end_date = datetime.date(max_year, 12, 31)

    while current_date <= end_date:
        if _day_matches(current_date, month_set, dom_set, dow_set,
                        dom_restricted, dow_restricted):
            if current_date == start_date:
                h, m = _find_time(sorted_hours, sorted_minutes,
                                  start.hour, start.minute)
            else:
                h, m = sorted_hours[0], sorted_minutes[0]

            if h is not None:
                result = datetime.datetime(
                    current_date.year, current_date.month,
                    current_date.day, h, m)
                if result > after:
                    return result

        current_date += datetime.timedelta(days=1)

    raise LookupError("No firing time found within horizon")
