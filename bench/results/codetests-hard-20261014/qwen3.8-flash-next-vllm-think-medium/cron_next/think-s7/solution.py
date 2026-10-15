"""Cron expression next-fire-time calculator (5-field, Vixie-cron day rule)."""

import datetime
import calendar
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def _is_valid_number(s: str) -> bool:
    return len(s) > 0 and all(c in '0123456789' for c in s)


def _is_valid_name(s: str) -> bool:
    return len(s) == 3 and all(c.isalpha() and c.isascii() for c in s)


def _parse_value(token: str, min_val: int, max_val: int, names) -> int:
    if names is not None and _is_valid_name(token):
        upper = token.upper()
        if upper in names:
            val = names[upper]
        else:
            raise ValueError(f"Unknown name: {token!r}")
    elif _is_valid_number(token):
        val = int(token)
    else:
        raise ValueError(f"Invalid value: {token!r}")
    if val < min_val or val > max_val:
        raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
    return val


def _parse_step(token: str) -> int:
    if not _is_valid_number(token):
        raise ValueError(f"Invalid step: {token!r}")
    val = int(token)
    if val < 1:
        raise ValueError(f"Step must be >= 1, got {val}")
    return val


def _parse_item(item: str, min_val: int, max_val: int, names) -> set:
    if not item:
        raise ValueError("Empty item")

    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Malformed item: {item!r}")
        base_str, step_str = parts
        step = _parse_step(step_str)
    else:
        base_str = item
        step = None

    if base_str == '*':
        start, end = min_val, max_val
    elif '-' in base_str:
        range_parts = base_str.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"Malformed range: {base_str!r}")
        a = _parse_value(range_parts[0], min_val, max_val, names)
        b = _parse_value(range_parts[1], min_val, max_val, names)
        if a > b:
            raise ValueError(f"Reversed range: {a}-{b}")
        start, end = a, b
    else:
        val = _parse_value(base_str, min_val, max_val, names)
        if step is not None:
            start, end = val, max_val
        else:
            return {val}

    if step is None:
        return set(range(start, end + 1))
    else:
        return set(range(start, end + 1, step))


def _parse_field(field_text: str, min_val: int, max_val: int, names) -> set:
    if not field_text:
        raise ValueError("Empty field")
    items = field_text.split(',')
    if any(item == '' for item in items):
        raise ValueError("Empty list element")
    result = set()
    for item in items:
        result.update(_parse_item(item, min_val, max_val, names))
    return result


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    # --- Parse the expression ---
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    minute_text, hour_text, dom_text, month_text, dow_text = fields

    minute_set = _parse_field(minute_text, 0, 59, None)
    hour_set = _parse_field(hour_text, 0, 23, None)
    dom_set = _parse_field(dom_text, 1, 31, None)
    month_set = _parse_field(month_text, 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(dow_text, 0, 7, _DOW_NAMES)

    # Normalize day-of-week: 7 -> 0 (both mean Sunday)
    if 7 in dow_set:
        dow_set.discard(7)
        dow_set.add(0)

    # Restricted check: purely textual (does the raw field start with '*')
    dom_restricted = not dom_text.startswith('*')
    dow_restricted = not dow_text.startswith('*')

    # --- Compute the earliest candidate minute ---
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    max_year = after.year + 8

    # Pre-sorted iteration lists
    sorted_minutes = sorted(minute_set)
    sorted_hours = sorted(hour_set)
    sorted_months = sorted(month_set)

    # --- Search day-by-day (efficient: no minute-by-minute iteration) ---
    for year in range(start.year, max_year + 1):
        for month in sorted_months:
            if year == start.year and month < start.month:
                continue
            days_in_month = calendar.monthrange(year, month)[1]
            for day in range(1, days_in_month + 1):
                if year == start.year and month == start.month and day < start.day:
                    continue

                # Day-of-week: 0=Sun, 1=Mon, ..., 6=Sat
                d = datetime.date(year, month, day)
                dow = (d.weekday() + 1) % 7

                dom_match = day in dom_set
                dow_match = dow in dow_set

                if dom_restricted and dow_restricted:
                    day_match = dom_match or dow_match
                else:
                    day_match = dom_match and dow_match

                if not day_match:
                    continue

                # Find first valid (hour, minute) on this matching day
                for hour in sorted_hours:
                    if (year == start.year and month == start.month
                            and day == start.day and hour < start.hour):
                        continue
                    for minute in sorted_minutes:
                        if (year == start.year and month == start.month
                                and day == start.day and hour == start.hour
                                and minute < start.minute):
                            continue
                        return datetime.datetime(year, month, day, hour, minute)

    raise LookupError("No firing time found within the horizon")
