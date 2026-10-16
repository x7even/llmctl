import datetime
import calendar
import re

MONTH_NAMES = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
               'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
DOW_NAMES = {'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6}

_DIGITS = frozenset('0123456789')
_ASCII_LETTERS = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')


def _parse_value(token, min_val, max_val, names):
    if not token:
        raise ValueError("empty value token")
    if all(c in _DIGITS for c in token):
        val = int(token)
        if val < min_val or val > max_val:
            raise ValueError(f"value {val} out of range [{min_val}, {max_val}]")
        return val
    if names is not None and len(token) == 3 and all(c in _ASCII_LETTERS for c in token):
        upper = token.upper()
        if upper in names:
            val = names[upper]
            if val < min_val or val > max_val:
                raise ValueError(f"value {val} out of range [{min_val}, {max_val}]")
            return val
    raise ValueError(f"invalid value token: {token!r}")


def _parse_item(item, min_val, max_val, names):
    if not item:
        raise ValueError("empty item")

    step = None
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"malformed item: {item!r}")
        item, step_str = parts
        if not step_str or not all(c in _DIGITS for c in step_str):
            raise ValueError(f"invalid step: {step_str!r}")
        step = int(step_str)
        if step < 1:
            raise ValueError("step must be >= 1")

    if item == '*':
        start, end = min_val, max_val
    elif '-' in item:
        parts = item.split('-')
        if len(parts) != 2:
            raise ValueError(f"malformed range: {item!r}")
        start = _parse_value(parts[0], min_val, max_val, names)
        end = _parse_value(parts[1], min_val, max_val, names)
        if start > end:
            raise ValueError(f"reversed range: {start}-{end}")
    else:
        val = _parse_value(item, min_val, max_val, names)
        if step is not None:
            start, end = val, max_val
        else:
            start = end = val

    return set(range(start, end + 1, step if step is not None else 1))


def _parse_field(text, min_val, max_val, names=None):
    if not text:
        raise ValueError("empty field")
    items = text.split(',')
    for item in items:
        if item == '':
            raise ValueError("empty list element")
    values = set()
    for item in items:
        values |= _parse_item(item, min_val, max_val, names)
    return values


def _parse_expr(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")
    parts = re.split(r'[ \t]+', stripped)
    if len(parts) != 5:
        raise ValueError(f"expected 5 fields, got {len(parts)}")

    minute_set = _parse_field(parts[0], 0, 59)
    hour_set = _parse_field(parts[1], 0, 23)
    dom_set = _parse_field(parts[2], 1, 31)
    month_set = _parse_field(parts[3], 1, 12, MONTH_NAMES)
    dow_set = _parse_field(parts[4], 0, 7, DOW_NAMES)

    dom_restricted = not parts[2].startswith('*')
    dow_restricted = not parts[4].startswith('*')

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def _day_matches(d, month, year, dom_set, dow_set, dom_restricted, dow_restricted):
    dom_ok = d in dom_set
    py_dow = calendar.weekday(year, month, d)  # Mon=0, ..., Sun=6
    our_dow = (py_dow + 1) % 7  # Sun=0, Mon=1, ..., Sat=6
    dow_ok = our_dow in dow_set
    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def _find_next_hm(sh, sm, hours, minutes):
    for h in hours:
        if h < sh:
            continue
        if h > sh:
            return (h, minutes[0])
        for m in minutes:
            if m >= sm:
                return (h, m)
    return None


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted = _parse_expr(expr)

    if 7 in dow_set:
        dow_set = dow_set | {0}

    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    max_year = after.year + 8

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    year = start.year
    month = start.month
    first = True

    while year <= max_year:
        if month in month_set:
            days_in_month = calendar.monthrange(year, month)[1]
            d_start = start.day if first else 1
            for d in range(d_start, days_in_month + 1):
                if not _day_matches(d, month, year, dom_set, dow_set, dom_restricted, dow_restricted):
                    continue
                if first and d == start.day:
                    found = _find_next_hm(start.hour, start.minute, sorted_hours, sorted_minutes)
                else:
                    found = (sorted_hours[0], sorted_minutes[0])
                if found:
                    h, m = found
                    return datetime.datetime(year, month, d, h, m)
        first = False
        month += 1
        if month > 12:
            month = 1
            year += 1

    raise LookupError("no firing time found within horizon")
