import datetime
import re
from bisect import bisect_left

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

_FIELD_RANGE = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day-of-month
    (1, 12),   # month
    (0, 7),    # day-of-week
]

_ASCII_DIGITS = '0123456789'
_ASCII_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted = _parse_expr(expr)

    # Normalize day-of-week: 7 means Sunday (0)
    if 7 in dow_set:
        dow_set = (dow_set - {7}) | {0}

    # Earliest whole minute strictly after 'after'
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    year_limit = after.year + 8

    minutes = sorted(minute_set)
    hours = sorted(hour_set)

    current_date = start.date()
    current_time = start.time()

    while current_date.year <= year_limit:
        if current_date.month in month_set:
            # Sunday=0, Monday=1, ..., Saturday=6
            dow = current_date.isoweekday() % 7

            if dom_restricted and dow_restricted:
                day_match = (current_date.day in dom_set) or (dow in dow_set)
            else:
                day_match = (current_date.day in dom_set) and (dow in dow_set)

            if day_match:
                result = _find_time(current_date, current_time, hours, minutes)
                if result is not None:
                    return result

        current_date += datetime.timedelta(days=1)
        current_time = datetime.time(0, 0)

    raise LookupError("no firing time found within the search horizon")


def _find_time(date, time, hours, minutes):
    idx = bisect_left(hours, time.hour)

    if idx < len(hours) and hours[idx] == time.hour:
        midx = bisect_left(minutes, time.minute)
        if midx < len(minutes):
            return datetime.datetime(date.year, date.month, date.day, hours[idx], minutes[midx])
        idx += 1

    if idx < len(hours):
        return datetime.datetime(date.year, date.month, date.day, hours[idx], minutes[0])

    return None


def _parse_expr(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")

    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError("expected exactly 5 fields")

    minute_set, _ = _parse_field(fields[0], 0, False)
    hour_set, _ = _parse_field(fields[1], 1, False)
    dom_set, dom_restricted = _parse_field(fields[2], 2, False)
    month_set, _ = _parse_field(fields[3], 3, True)
    dow_set, dow_restricted = _parse_field(fields[4], 4, True)

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def _parse_field(field_text, field_idx, allow_names):
    if not field_text:
        raise ValueError("empty field")

    items = field_text.split(',')
    values = set()

    for item in items:
        if not item:
            raise ValueError("empty list element")
        vals = _parse_item(item, field_idx, allow_names)
        values.update(vals)

    restricted = not field_text.startswith('*')
    return values, restricted


def _parse_item(item, field_idx, allow_names):
    parts = item.split('/')
    if len(parts) == 1:
        base = parts[0]
        step = 1
    elif len(parts) == 2:
        base = parts[0]
        step = _parse_step(parts[1])
    else:
        raise ValueError("malformed step")

    lo, hi = _FIELD_RANGE[field_idx]

    if base == '*':
        return set(range(lo, hi + 1, step))

    range_parts = base.split('-')
    if len(range_parts) == 1:
        val = _parse_value(range_parts[0], field_idx, allow_names)
        if step == 1:
            return {val}
        return set(range(val, hi + 1, step))
    elif len(range_parts) == 2:
        a = _parse_value(range_parts[0], field_idx, allow_names)
        b = _parse_value(range_parts[1], field_idx, allow_names)
        if a > b:
            raise ValueError("reversed range")
        return set(range(a, b + 1, step))
    else:
        raise ValueError("malformed range")


def _parse_step(s):
    if not s:
        raise ValueError("empty step")
    if not all(c in _ASCII_DIGITS for c in s):
        raise ValueError("invalid step")
    n = int(s)
    if n < 1:
        raise ValueError("step must be >= 1")
    return n


def _parse_value(s, field_idx, allow_names):
    lo, hi = _FIELD_RANGE[field_idx]

    # Try name (only for month and day-of-week fields)
    if allow_names and len(s) == 3 and all(c in _ASCII_LETTERS for c in s):
        name = s.upper()
        if field_idx == 3:
            if name in _MONTH_NAMES:
                return _MONTH_NAMES[name]
            raise ValueError("unknown month name: " + s)
        elif field_idx == 4:
            if name in _DOW_NAMES:
                return _DOW_NAMES[name]
            raise ValueError("unknown day-of-week name: " + s)

    # Try number
    if s and all(c in _ASCII_DIGITS for c in s):
        val = int(s)
        if val < lo or val > hi:
            raise ValueError("value out of range")
        return val

    raise ValueError("invalid value: " + s)
