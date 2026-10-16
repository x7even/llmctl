import datetime
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

# (min_val, max_val, name_dict_or_None) for each of the five fields
_FIELD_SPECS = [
    (0, 59, None),
    (0, 23, None),
    (1, 31, None),
    (1, 12, _MONTH_NAMES),
    (0, 7, _DOW_NAMES),
]


def _parse_number(s):
    """Parse a non-empty ASCII-digit-only string into an int."""
    if not s:
        raise ValueError("empty number token")
    for c in s:
        if not ('0' <= c <= '9'):
            raise ValueError(f"invalid number token: {s!r}")
    return int(s)


def _parse_value(s, field_idx):
    """Parse a single value token (number or optional name) for *field_idx*."""
    min_val, max_val, names = _FIELD_SPECS[field_idx]

    # Attempt name interpretation only when the field allows names and the
    # token looks like a pure ASCII alpha string.
    if names is not None and s.isalpha() and s.isascii():
        if len(s) != 3:
            raise ValueError(f"invalid name (must be 3 letters): {s!r}")
        upper = s.upper()
        if upper not in names:
            raise ValueError(f"unknown name: {s!r}")
        return names[upper]

    # Otherwise it must be a decimal number.
    val = _parse_number(s)
    if val < min_val or val > max_val:
        raise ValueError(
            f"value {val} out of range [{min_val},{max_val}] for field {field_idx}"
        )
    return val


def _parse_field(field_text, field_idx):
    """Parse one cron field into a set of integers."""
    min_val, max_val, _ = _FIELD_SPECS[field_idx]

    if not field_text:
        raise ValueError("empty field")

    items = field_text.split(',')
    result = set()

    for item in items:
        if not item:
            raise ValueError("empty list element in field")

        # Split off optional /step
        slash_parts = item.split('/')
        if len(slash_parts) > 2:
            raise ValueError(f"malformed item (multiple '/'): {item!r}")

        base = slash_parts[0]
        step = 1
        if len(slash_parts) == 2:
            step_str = slash_parts[1]
            if not step_str:
                raise ValueError(f"empty step in item: {item!r}")
            step = _parse_number(step_str)
            if step < 1:
                raise ValueError(f"step must be >= 1 in item: {item!r}")

        # Determine lo / hi from the base
        if base == '*':
            lo, hi = min_val, max_val
        elif '-' in base:
            range_parts = base.split('-')
            if len(range_parts) != 2:
                raise ValueError(f"malformed range in item: {item!r}")
            lo = _parse_value(range_parts[0], field_idx)
            hi = _parse_value(range_parts[1], field_idx)
            if lo > hi:
                raise ValueError(f"reversed range in item: {item!r}")
        else:
            lo = _parse_value(base, field_idx)
            # a/n means a..MAX/n ; plain a means just {a}
            hi = max_val if len(slash_parts) == 2 else lo

        v = lo
        while v <= hi:
            result.add(v)
            v += step

    return result


def _parse_expr(expr):
    """Validate and parse the full 5-field expression.

    Returns (minute_set, hour_set, dom_set, month_set, dow_set,
             dom_restricted, dow_restricted).
    """
    stripped = expr.strip(' \t')
    if stripped == '':
        raise ValueError("empty expression")

    fields = re.split(r'[ \t]+', stripped)

    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    minute_set = _parse_field(fields[0], 0)
    hour_set   = _parse_field(fields[1], 1)
    dom_set    = _parse_field(fields[2], 2)
    month_set  = _parse_field(fields[3], 3)
    dow_set    = _parse_field(fields[4], 4)

    # Vixie-cron restricted test: purely textual – does the field text start
    # with '*'?
    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def _day_matches(year, month, day, dom_set, dow_set, month_set,
                 dom_restricted, dow_restricted):
    """Return True if the calendar day satisfies the cron day rule."""
    if month not in month_set:
        return False

    # Python date.weekday(): Mon=0 … Sun=6.  Cron: Sun=0 … Sat=6.
    dow = (datetime.date(year, month, day).weekday() + 1) % 7

    dom_match = day in dom_set
    # 7 in the dow set is equivalent to 0 (Sunday)
    dow_match = (dow in dow_set) or (dow == 0 and 7 in dow_set)

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    """Return the earliest firing time strictly after *after*."""

    minute_set, hour_set, dom_set, month_set, dow_set, \
        dom_restricted, dow_restricted = _parse_expr(expr)

    # Earliest candidate: next whole minute strictly greater than *after*.
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    max_year = after.year + 8
    end_date = datetime.date(max_year, 12, 31)

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    current_date = start.date()

    while current_date <= end_date:
        if _day_matches(current_date.year, current_date.month, current_date.day,
                        dom_set, dow_set, month_set,
                        dom_restricted, dow_restricted):
            for h in sorted_hours:
                for m in sorted_minutes:
                    candidate = datetime.datetime(
                        current_date.year, current_date.month,
                        current_date.day, h, m,
                    )
                    if candidate >= start:
                        return candidate

        current_date += datetime.timedelta(days=1)

    raise LookupError("no matching firing time within the 8-year horizon")
