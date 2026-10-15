import datetime
import re
import bisect

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

# (min, max) for minute, hour, day-of-month, month, day-of-week
_FIELD_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]

_DIGITS = set('0123456789')


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted = _parse_expr(expr)

    # Next whole minute strictly after `after`
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    year_limit = after.year + 8

    current_date = start.date()
    current_time = start.time()

    while current_date.year <= year_limit:
        if _day_matches(current_date, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
            result = _find_time(current_date, current_time, hour_set, minute_set)
            if result is not None:
                return result
        current_date += datetime.timedelta(days=1)
        current_time = datetime.time(0, 0)

    raise LookupError("No firing time found within the horizon")


def _parse_expr(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")

    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    for i, f in enumerate(fields):
        if not f:
            raise ValueError(f"empty field at position {i}")

    minute_set = _parse_field(fields[0], 0)
    hour_set = _parse_field(fields[1], 1)
    dom_set = _parse_field(fields[2], 2)
    month_set = _parse_field(fields[3], 3)
    dow_set = _parse_field(fields[4], 4)

    # Normalize day-of-week: 7 means Sunday, same as 0
    if 7 in dow_set:
        dow_set.discard(7)
        dow_set.add(0)

    # Vixie-cron restricted test: purely textual
    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def _parse_field(field_text, field_idx):
    items = field_text.split(',')
    result = set()
    for item in items:
        result |= _parse_item(item, field_idx)
    return result


def _parse_item(item, field_idx):
    if not item:
        raise ValueError("empty item")

    parts = item.split('/')
    if len(parts) > 2:
        raise ValueError(f"invalid item (multiple slashes): {item}")

    base = parts[0]
    step = None
    if len(parts) == 2:
        step = _parse_step(parts[1])

    lo, hi = _FIELD_RANGES[field_idx]

    if base == '*':
        pass  # full range
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"invalid range: {base}")
        lo = _parse_value(range_parts[0], field_idx)
        hi = _parse_value(range_parts[1], field_idx)
        if lo > hi:
            raise ValueError(f"reversed range: {base}")
    else:
        val = _parse_value(base, field_idx)
        if step is not None:
            # a/n is shorthand for a-MAX/n
            lo = val
            hi = _FIELD_RANGES[field_idx][1]
        else:
            return {val}

    if step is None:
        step = 1

    return set(range(lo, hi + 1, step))


def _parse_step(s):
    if not s:
        raise ValueError("empty step")
    if not all(c in _DIGITS for c in s):
        raise ValueError(f"invalid step: {s}")
    n = int(s)
    if n < 1:
        raise ValueError(f"step must be >= 1, got {n}")
    return n


def _parse_value(s, field_idx):
    if not s:
        raise ValueError("empty value")

    if all(c in _DIGITS for c in s):
        val = int(s)
    elif field_idx in (3, 4) and s.isalpha() and s.isascii():
        if len(s) != 3:
            raise ValueError(f"name must be exactly 3 letters: {s}")
        name = s.upper()
        if field_idx == 3:
            if name not in _MONTH_NAMES:
                raise ValueError(f"unknown month name: {s}")
            val = _MONTH_NAMES[name]
        else:
            if name not in _DOW_NAMES:
                raise ValueError(f"unknown day-of-week name: {s}")
            val = _DOW_NAMES[name]
    else:
        raise ValueError(f"invalid value: {s}")

    lo, hi = _FIELD_RANGES[field_idx]
    if val < lo or val > hi:
        raise ValueError(f"value {val} out of range [{lo},{hi}]")

    return val


def _day_matches(date, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
    if date.month not in month_set:
        return False

    # Python weekday(): Mon=0 .. Sun=6
    # Cron dow:         Sun=0 .. Sat=6
    dow = (date.weekday() + 1) % 7

    dom_match = date.day in dom_set
    dow_match = dow in dow_set

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match


def _find_time(date, min_time, hour_set, minute_set):
    hours = sorted(hour_set)
    minutes = sorted(minute_set)

    for h in hours:
        if h < min_time.hour:
            continue
        if h == min_time.hour:
            idx = bisect.bisect_left(minutes, min_time.minute)
        else:
            idx = 0
        if idx < len(minutes):
            return datetime.datetime(date.year, date.month, date.day, h, minutes[idx])

    return None
