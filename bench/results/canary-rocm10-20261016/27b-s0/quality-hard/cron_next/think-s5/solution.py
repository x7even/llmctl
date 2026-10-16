import datetime
import re

MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

_DIGITS = frozenset('0123456789')
_LETTERS = frozenset(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
)


def _parse_value(token, min_val, max_val, names, field_name):
    if not token:
        raise ValueError(f"Empty value in {field_name} field")
    if all(c in _DIGITS for c in token):
        val = int(token)
    elif names is not None and all(c in _LETTERS for c in token):
        upper = token.upper()
        if len(upper) != 3:
            raise ValueError(f"Name must be exactly 3 letters: {token!r}")
        if upper not in names:
            raise ValueError(f"Unknown name: {token!r}")
        val = names[upper]
    else:
        raise ValueError(f"Invalid value token: {token!r}")
    if val < min_val or val > max_val:
        raise ValueError(
            f"Value {val} out of range [{min_val}, {max_val}] in {field_name} field"
        )
    return val


def _parse_item(item, min_val, max_val, names, field_name):
    parts = item.split('/')
    if len(parts) > 2:
        raise ValueError(f"Malformed item: {item!r}")

    if len(parts) == 2:
        base_str, step_str = parts
        if not step_str or not all(c in _DIGITS for c in step_str):
            raise ValueError(f"Invalid step: {step_str!r}")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"Step must be >= 1, got {step}")
    else:
        base_str = item
        step = None

    if base_str == '*':
        start, end = min_val, max_val
    elif '-' in base_str:
        range_parts = base_str.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"Malformed range: {base_str!r}")
        start = _parse_value(range_parts[0], min_val, max_val, names, field_name)
        end = _parse_value(range_parts[1], min_val, max_val, names, field_name)
        if start > end:
            raise ValueError(f"Reversed range: {start}-{end}")
    else:
        val = _parse_value(base_str, min_val, max_val, names, field_name)
        if step is not None:
            start, end = val, max_val
        else:
            return {val}

    if step is not None:
        return set(range(start, end + 1, step))
    return set(range(start, end + 1))


def _parse_field(field_str, min_val, max_val, names, field_name):
    if not field_str:
        raise ValueError(f"Empty {field_name} field")
    items = field_str.split(',')
    result = set()
    for item in items:
        if not item:
            raise ValueError(f"Empty item in {field_name} field")
        result |= _parse_item(item, min_val, max_val, names, field_name)
    return result


def _parse_expr(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    minute_set = _parse_field(fields[0], 0, 59, None, 'minute')
    hour_set = _parse_field(fields[1], 0, 23, None, 'hour')
    dom_set = _parse_field(fields[2], 1, 31, None, 'day-of-month')
    month_set = _parse_field(fields[3], 1, 12, MONTH_NAMES, 'month')
    dow_set = _parse_field(fields[4], 0, 7, DOW_NAMES, 'day-of-week')

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def _date_matches(date, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
    if date.month not in month_set:
        return False
    dom_ok = date.day in dom_set
    # Python weekday(): Mon=0 .. Sun=6; we need Sun=0 .. Sat=6
    dow = (date.weekday() + 1) % 7
    dow_ok = (dow in dow_set) or (dow == 0 and 7 in dow_set)

    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    (minute_set, hour_set, dom_set,
     month_set, dow_set, dom_restricted, dow_restricted) = _parse_expr(expr)

    # First candidate: the next whole minute strictly after `after`
    first = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    # Search horizon
    max_year = after.year + 8
    horizon = datetime.datetime(max_year, 12, 31, 23, 59)

    if first > horizon:
        raise LookupError("No firing time within horizon")

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    current_date = first.date()
    end_date = horizon.date()

    while current_date <= end_date:
        if _date_matches(
            current_date, month_set, dom_set, dow_set,
            dom_restricted, dow_restricted,
        ):
            if current_date == first.date():
                sh, sm = first.hour, first.minute
            else:
                sh, sm = 0, 0

            for h in sorted_hours:
                if h < sh:
                    continue
                if h == sh:
                    for m in sorted_minutes:
                        if m >= sm:
                            return datetime.datetime(
                                current_date.year, current_date.month,
                                current_date.day, h, m,
                            )
                else:
                    return datetime.datetime(
                        current_date.year, current_date.month,
                        current_date.day, h, sorted_minutes[0],
                    )

        current_date += datetime.timedelta(days=1)

    raise LookupError("No firing time within horizon")
