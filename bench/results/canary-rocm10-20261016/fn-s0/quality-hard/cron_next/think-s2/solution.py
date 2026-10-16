import datetime
from datetime import timedelta


_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

_ASCII_LETTERS = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
)


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted = _parse_expr(expr)

    start = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    horizon_year = after.year + 8

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    current_date = start.date()
    current_hour = start.hour
    current_minute = start.minute

    while current_date.year <= horizon_year:
        if _day_matches(current_date, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
            result = _find_time(current_hour, current_minute, sorted_hours, sorted_minutes)
            if result is not None:
                h, m = result
                return datetime.datetime(current_date.year, current_date.month, current_date.day, h, m)

        current_date += timedelta(days=1)
        current_hour = 0
        current_minute = 0

    raise LookupError("no matching time found within horizon")


def _find_time(hour, minute, sorted_hours, sorted_minutes):
    for h in sorted_hours:
        if h < hour:
            continue
        if h == hour:
            for m in sorted_minutes:
                if m >= minute:
                    return (h, m)
        else:
            return (h, sorted_minutes[0])
    return None


def _day_matches(date, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
    if date.month not in month_set:
        return False

    # Python weekday(): 0=Mon .. 6=Sun;  Cron DOW: 0=Sun, 1=Mon .. 6=Sat
    cron_dow = (date.weekday() + 1) % 7

    dow_match = (cron_dow in dow_set) or (cron_dow == 0 and 7 in dow_set)
    dom_match = date.day in dom_set

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match


def _parse_expr(expr):
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    minute_set = _parse_field(fields[0], 0, 59, {})
    hour_set = _parse_field(fields[1], 0, 23, {})
    dom_set = _parse_field(fields[2], 1, 31, {})
    month_set = _parse_field(fields[3], 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(fields[4], 0, 7, _DOW_NAMES)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def _split_fields(expr):
    i = 0
    n = len(expr)
    while i < n and expr[i] in ' \t':
        i += 1
    if i >= n:
        return []
    fields = []
    while i < n:
        j = i
        while j < n and expr[j] not in ' \t':
            j += 1
        fields.append(expr[i:j])
        while j < n and expr[j] in ' \t':
            j += 1
        i = j
    return fields


def _parse_field(text, min_val, max_val, names):
    items = text.split(',')
    values = set()
    for item in items:
        if not item:
            raise ValueError("empty item in field")
        values.update(_parse_item(item, min_val, max_val, names))
    return values


def _parse_item(item, min_val, max_val, names):
    slash_count = item.count('/')
    if slash_count > 1:
        raise ValueError("multiple slashes in item")

    if slash_count == 1:
        base, step_str = item.split('/', 1)
        step = _parse_step(step_str)
    else:
        base = item
        step = None

    if base == '*':
        start = min_val
        end = max_val
    elif '-' in base:
        parts = base.split('-')
        if len(parts) != 2:
            raise ValueError("invalid range")
        start = _parse_value(parts[0], min_val, max_val, names)
        end = _parse_value(parts[1], min_val, max_val, names)
        if start > end:
            raise ValueError("reversed range")
    else:
        val = _parse_value(base, min_val, max_val, names)
        if step is not None:
            start = val
            end = max_val
        else:
            return {val}

    if step is None:
        step = 1

    values = set()
    v = start
    while v <= end:
        values.add(v)
        v += step
    return values


def _parse_step(s):
    if not _is_number(s):
        raise ValueError("invalid step")
    n = int(s)
    if n < 1:
        raise ValueError("step must be >= 1")
    return n


def _parse_value(token, min_val, max_val, names):
    if _is_number(token):
        val = int(token)
        if val < min_val or val > max_val:
            raise ValueError(f"value {val} out of range [{min_val}, {max_val}]")
        return val
    if names and len(token) == 3 and all(c in _ASCII_LETTERS for c in token):
        upper = token.upper()
        if upper in names:
            return names[upper]
    raise ValueError(f"invalid value: {token!r}")


def _is_number(s):
    return len(s) > 0 and all(c in '0123456789' for c in s)
