import datetime
import re
import bisect

MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def _is_ascii_digits(s):
    return len(s) > 0 and all(c in '0123456789' for c in s)


def _is_ascii_letters(s):
    return len(s) > 0 and all(
        c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in s
    )


def _parse_value(token, min_val, max_val, names, field_idx):
    if names is not None and len(token) == 3 and _is_ascii_letters(token):
        upper = token.upper()
        if upper in names:
            return names[upper]
        raise ValueError(f"Unknown name '{token}' in field {field_idx + 1}")
    if _is_ascii_digits(token):
        val = int(token)
        if val < min_val or val > max_val:
            raise ValueError(
                f"Value {val} out of range [{min_val},{max_val}] in field {field_idx + 1}"
            )
        return val
    raise ValueError(f"Invalid value '{token}' in field {field_idx + 1}")


def _parse_item(item, min_val, max_val, names, field_idx):
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Malformed item '{item}' in field {field_idx + 1}")
        base, step_str = parts
        if not _is_ascii_digits(step_str):
            raise ValueError(f"Malformed step '{step_str}' in field {field_idx + 1}")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"Step must be >= 1 in field {field_idx + 1}")
    else:
        base = item
        step = 1

    if base == '*':
        start, end = min_val, max_val
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"Malformed range '{base}' in field {field_idx + 1}")
        start = _parse_value(range_parts[0], min_val, max_val, names, field_idx)
        end = _parse_value(range_parts[1], min_val, max_val, names, field_idx)
        if start > end:
            raise ValueError(f"Reversed range in field {field_idx + 1}: '{item}'")
    else:
        val = _parse_value(base, min_val, max_val, names, field_idx)
        if '/' in item:
            start, end = val, max_val
        else:
            return {val}

    return set(range(start, end + 1, step))


def _parse_field(field_str, min_val, max_val, names, field_idx):
    if not field_str:
        raise ValueError(f"Empty field {field_idx + 1}")
    items = field_str.split(',')
    for item in items:
        if not item:
            raise ValueError(f"Empty item in field {field_idx + 1}")
    values = set()
    for item in items:
        values |= _parse_item(item, min_val, max_val, names, field_idx)
    return values


def _parse_expr(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    minute_set = _parse_field(fields[0], 0, 59, None, 0)
    hour_set = _parse_field(fields[1], 0, 23, None, 1)
    dom_set = _parse_field(fields[2], 1, 31, None, 2)
    month_set = _parse_field(fields[3], 1, 12, MONTH_NAMES, 3)
    dow_set = _parse_field(fields[4], 0, 7, DOW_NAMES, 4)

    if 7 in dow_set:
        dow_set.add(0)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return (minute_set, hour_set, dom_set, month_set, dow_set,
            dom_restricted, dow_restricted)


def _find_earliest_time(sorted_hours, sorted_minutes, min_h, min_m):
    best = None

    h_idx = bisect.bisect_left(sorted_hours, min_h)
    if h_idx < len(sorted_hours) and sorted_hours[h_idx] == min_h:
        m_idx = bisect.bisect_left(sorted_minutes, min_m)
        if m_idx < len(sorted_minutes):
            best = (min_h, sorted_minutes[m_idx])

    h_idx2 = bisect.bisect_right(sorted_hours, min_h)
    if h_idx2 < len(sorted_hours):
        candidate = (sorted_hours[h_idx2], sorted_minutes[0])
        if best is None or candidate < best:
            best = candidate

    return best


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    (minute_set, hour_set, dom_set, month_set, dow_set,
     dom_restricted, dow_restricted) = _parse_expr(expr)

    sorted_minutes = sorted(minute_set)
    sorted_hours = sorted(hour_set)

    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    end_year = after.year + 8
    end_day = datetime.date(end_year, 12, 31)

    current = start.date()

    while current <= end_day:
        if current.month not in month_set:
            current += datetime.timedelta(days=1)
            continue

        cron_dow = (current.weekday() + 1) % 7

        if dom_restricted and dow_restricted:
            day_ok = (current.day in dom_set) or (cron_dow in dow_set)
        else:
            day_ok = (current.day in dom_set) and (cron_dow in dow_set)

        if not day_ok:
            current += datetime.timedelta(days=1)
            continue

        if current == start.date():
            t = _find_earliest_time(sorted_hours, sorted_minutes,
                                    start.hour, start.minute)
        else:
            t = _find_earliest_time(sorted_hours, sorted_minutes, 0, 0)

        if t is not None:
            return datetime.datetime(current.year, current.month, current.day,
                                     t[0], t[1])

        current += datetime.timedelta(days=1)

    raise LookupError("No firing time found within search horizon")
