import datetime
import bisect
import re

MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

_DIGITS = frozenset('0123456789')
_LETTERS = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')


def _is_digits(s):
    return len(s) > 0 and all(c in _DIGITS for c in s)


def _parse_value(token, min_val, max_val, names):
    if not token:
        raise ValueError("Empty value token")
    if _is_digits(token):
        val = int(token)
    elif names is not None and len(token) == 3 and all(c in _LETTERS for c in token):
        upper = token.upper()
        if upper not in names:
            raise ValueError(f"Unknown name: {token!r}")
        val = names[upper]
    else:
        raise ValueError(f"Invalid value token: {token!r}")
    if val < min_val or val > max_val:
        raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
    return val


def _parse_item(item, min_val, max_val, names, values):
    if not item:
        raise ValueError("Empty item")
    slash_parts = item.split('/')
    if len(slash_parts) > 2:
        raise ValueError(f"Malformed item: {item!r}")
    base = slash_parts[0]
    step = None
    if len(slash_parts) == 2:
        step_str = slash_parts[1]
        if not _is_digits(step_str):
            raise ValueError(f"Malformed step: {step_str!r}")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"Step must be >= 1: {step}")
    if base == '*':
        start, end = min_val, max_val
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"Malformed range: {base!r}")
        if not range_parts[0] or not range_parts[1]:
            raise ValueError(f"Malformed range: {base!r}")
        start = _parse_value(range_parts[0], min_val, max_val, names)
        end = _parse_value(range_parts[1], min_val, max_val, names)
        if start > end:
            raise ValueError(f"Reversed range: {base!r}")
    else:
        val = _parse_value(base, min_val, max_val, names)
        if step is not None:
            start, end = val, max_val
        else:
            values.add(val)
            return
    s = step if step is not None else 1
    for v in range(start, end + 1, s):
        values.add(v)


def _parse_field(text, min_val, max_val, names=None):
    if not text:
        raise ValueError("Empty field")
    values = set()
    items = text.split(',')
    for item in items:
        if not item:
            raise ValueError(f"Empty list element in field: {text!r}")
        _parse_item(item, min_val, max_val, names, values)
    return values


def _parse_expr(expr):
    stripped = expr.strip(' \t')
    parts = re.split(r'[ \t]+', stripped)
    if len(parts) != 5:
        raise ValueError(f"Expected 5 fields, got {len(parts)}")
    minute_text, hour_text, dom_text, month_text, dow_text = parts
    minutes = _parse_field(minute_text, 0, 59)
    hours = _parse_field(hour_text, 0, 23)
    doms = _parse_field(dom_text, 1, 31)
    months = _parse_field(month_text, 1, 12, MONTH_NAMES)
    dows = _parse_field(dow_text, 0, 7, DOW_NAMES)
    if 7 in dows:
        dows.add(0)
    dom_restricted = not dom_text.startswith('*')
    dow_restricted = not dow_text.startswith('*')
    return minutes, hours, doms, months, dows, dom_restricted, dow_restricted


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minutes, hours, doms, months, dows, dom_restricted, dow_restricted = _parse_expr(expr)

    start = (after + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    end_date = datetime.date(after.year + 8, 12, 31)

    valid_times = sorted((h, m) for h in hours for m in minutes)

    current_date = start.date()
    start_hour = start.hour
    start_minute = start.minute
    first_day = True

    while current_date <= end_date:
        month = current_date.month
        if month in months:
            dom = current_date.day
            dow = (current_date.weekday() + 1) % 7
            if dom_restricted and dow_restricted:
                day_match = (dom in doms) or (dow in dows)
            else:
                day_match = (dom in doms) and (dow in dows)
            if day_match:
                if first_day:
                    idx = bisect.bisect_left(valid_times, (start_hour, start_minute))
                    if idx < len(valid_times):
                        h, m = valid_times[idx]
                        return datetime.datetime(current_date.year, month, dom, h, m)
                else:
                    h, m = valid_times[0]
                    return datetime.datetime(current_date.year, month, dom, h, m)
        current_date += datetime.timedelta(days=1)
        first_day = False

    raise LookupError("No firing time found within the 8-year horizon")
