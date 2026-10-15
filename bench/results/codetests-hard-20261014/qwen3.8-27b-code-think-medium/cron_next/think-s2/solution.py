import datetime


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    """Compute the next firing time of a standard 5-field cron expression."""
    (minutes, hours, doms, months, dows,
     dom_restricted, dow_restricted) = _parse_expr(expr)

    sorted_minutes = sorted(minutes)
    sorted_hours = sorted(hours)

    # First whole-minute strictly after `after`
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    # Search horizon: t.year <= after.year + 8
    end_year = after.year + 8
    end_date = datetime.date(end_year, 12, 31)

    current = start.date()
    start_date = start.date()

    while current <= end_date:
        if _day_matches(current, months, doms, dows, dom_restricted, dow_restricted):
            if current == start_date:
                # Need (h, m) such that resulting datetime >= start
                for h in sorted_hours:
                    if h < start.hour:
                        continue
                    if h > start.hour:
                        return datetime.datetime(
                            current.year, current.month, current.day,
                            h, sorted_minutes[0])
                    # h == start.hour
                    for m in sorted_minutes:
                        if m >= start.minute:
                            return datetime.datetime(
                                current.year, current.month, current.day,
                                h, m)
                # No valid time on this day; continue to next day
            else:
                return datetime.datetime(
                    current.year, current.month, current.day,
                    sorted_hours[0], sorted_minutes[0])
        current += datetime.timedelta(days=1)

    raise LookupError("No matching time found within the 8-year horizon")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

# (min_val, max_val, names_or_None) for minute, hour, dom, month, dow
_FIELD_SPECS = [
    (0, 59, None),
    (0, 23, None),
    (1, 31, None),
    (1, 12, _MONTH_NAMES),
    (0, 7, _DOW_NAMES),
]


def _split_fields(stripped: str) -> list:
    """Split on one or more spaces/tabs (no other whitespace)."""
    fields = []
    current = []
    for c in stripped:
        if c == ' ' or c == '\t':
            if current:
                fields.append(''.join(current))
                current = []
        else:
            current.append(c)
    if current:
        fields.append(''.join(current))
    return fields


def _parse_expr(expr: str):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")
    fields = _split_fields(stripped)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    parsed = []
    for i, (field_text, (lo, hi, names)) in enumerate(zip(fields, _FIELD_SPECS)):
        if not field_text:
            raise ValueError(f"Empty field at position {i + 1}")
        values = _parse_field(field_text, lo, hi, names)
        parsed.append(values)

    minutes, hours, doms, months, dows = parsed
    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return minutes, hours, doms, months, dows, dom_restricted, dow_restricted


def _parse_field(field_text: str, min_val: int, max_val: int, names) -> set:
    values = set()
    items = field_text.split(',')
    for item in items:
        if not item:
            raise ValueError(f"Empty item in field: {field_text!r}")
        values.update(_parse_item(item, min_val, max_val, names))
    return values


def _parse_item(item: str, min_val: int, max_val: int, names) -> set:
    # Handle optional /step
    slash_parts = item.split('/')
    if len(slash_parts) > 2:
        raise ValueError(f"Malformed item: {item!r}")

    if len(slash_parts) == 2:
        base, step_str = slash_parts
        if not step_str or not all(c in '0123456789' for c in step_str):
            raise ValueError(f"Invalid step: {step_str!r}")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"Step must be >= 1, got {step}")
    else:
        base = item
        step = 1

    # Parse the base part
    if base == '*':
        start_val = min_val
        end_val = max_val
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"Malformed range: {base!r}")
        if not range_parts[0] or not range_parts[1]:
            raise ValueError(f"Malformed range: {base!r}")
        start_val = _parse_value(range_parts[0], min_val, max_val, names)
        end_val = _parse_value(range_parts[1], min_val, max_val, names)
        if start_val > end_val:
            raise ValueError(f"Reversed range: {base!r}")
    else:
        start_val = _parse_value(base, min_val, max_val, names)
        if len(slash_parts) == 2:
            end_val = max_val  # a/n is shorthand for a-MAX/n
        else:
            end_val = start_val

    return set(range(start_val, end_val + 1, step))


def _parse_value(token: str, min_val: int, max_val: int, names) -> int:
    if not token:
        raise ValueError("Empty value token")

    # All ASCII digits?
    if all(c in '0123456789' for c in token):
        val = int(token)
        if val < min_val or val > max_val:
            raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
        return val

    # All ASCII letters?
    if all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in token):
        if names is None:
            raise ValueError(f"Names not allowed in this field: {token!r}")
        if len(token) != 3:
            raise ValueError(f"Name must be exactly 3 letters: {token!r}")
        upper = token.upper()
        if upper not in names:
            raise ValueError(f"Unknown name: {token!r}")
        return names[upper]

    raise ValueError(f"Invalid value token: {token!r}")


# ---------------------------------------------------------------------------
# Day matching (Vixie-cron rule)
# ---------------------------------------------------------------------------

def _day_matches(d, months, doms, dows, dom_restricted, dow_restricted) -> bool:
    if d.month not in months:
        return False

    # Cron day-of-week: Sun=0, Mon=1, ..., Sat=6
    cron_dow = (d.weekday() + 1) % 7

    dom_ok = d.day in doms
    dow_ok = cron_dow in dows or (cron_dow == 0 and 7 in dows)

    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok
