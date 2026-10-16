import datetime


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    """Compute the next firing time of a standard 5-field cron expression."""
    (minute_set, hour_set, dom_set, month_set, dow_set,
     dom_restricted, dow_restricted) = _parse(expr)

    # Normalise day-of-week: 7 means Sunday, treat as 0
    if 7 in dow_set:
        dow_set = dow_set | {0}

    # Earliest candidate: strictly after `after`, rounded up to next whole minute
    candidate = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    # Search horizon
    max_year = after.year + 8
    max_date = datetime.date(max_year, 12, 31)

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    current_date = candidate.date()

    while current_date <= max_date:
        # Month check
        if current_date.month not in month_set:
            current_date += datetime.timedelta(days=1)
            continue

        # Day matching (Vixie-cron rule)
        if not _day_matches(current_date, dom_set, dow_set,
                            dom_restricted, dow_restricted):
            current_date += datetime.timedelta(days=1)
            continue

        # Determine the earliest (hour, minute) to consider on this day
        if current_date == candidate.date():
            min_h, min_m = candidate.hour, candidate.minute
        else:
            min_h, min_m = 0, 0

        result = _find_next_time(sorted_hours, sorted_minutes, min_h, min_m)
        if result is not None:
            h, m = result
            return datetime.datetime(current_date.year, current_date.month,
                                     current_date.day, h, m)

        current_date += datetime.timedelta(days=1)

    raise LookupError("No firing time found within search horizon")


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

_ASCII_DIGITS = frozenset('0123456789')
_ASCII_LETTERS = frozenset(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')


def _split_fields(s: str) -> list:
    """Split *s* on runs of spaces/tabs, discarding leading/trailing delimiters."""
    fields = []
    i = 0
    n = len(s)
    while i < n:
        while i < n and s[i] in ' \t':
            i += 1
        if i >= n:
            break
        start = i
        while i < n and s[i] not in ' \t':
            i += 1
        fields.append(s[start:i])
    return fields


def _parse_value(token: str, fmin: int, fmax: int,
                 allow_names: bool, names_map: dict) -> int:
    if not token:
        raise ValueError("Empty value token")

    if all(c in _ASCII_DIGITS for c in token):
        val = int(token)
    elif allow_names:
        if not all(c in _ASCII_LETTERS for c in token):
            raise ValueError(f"Invalid token: {token!r}")
        upper = token.upper()
        if upper not in names_map:
            raise ValueError(f"Unknown name: {token!r}")
        val = names_map[upper]
    else:
        raise ValueError(f"Invalid token: {token!r}")

    if val < fmin or val > fmax:
        raise ValueError(f"Value {val} out of range [{fmin}, {fmax}]")
    return val


def _parse_item(item: str, fmin: int, fmax: int,
                allow_names: bool, names_map: dict) -> set:
    if not item:
        raise ValueError("Empty item")

    # Split on '/'
    slash_parts = item.split('/')
    if len(slash_parts) > 2:
        raise ValueError(f"Malformed item: {item!r}")

    step = 1
    if len(slash_parts) == 2:
        base, step_str = slash_parts
        if not step_str:
            raise ValueError(f"Empty step in: {item!r}")
        if not all(c in _ASCII_DIGITS for c in step_str):
            raise ValueError(f"Invalid step: {step_str!r}")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"Step must be >= 1, got {step}")
    else:
        base = item

    # Parse the base part
    if base == '*':
        start, end = fmin, fmax
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"Malformed range: {base!r}")
        if not range_parts[0] or not range_parts[1]:
            raise ValueError(f"Malformed range: {base!r}")
        start = _parse_value(range_parts[0], fmin, fmax, allow_names, names_map)
        end = _parse_value(range_parts[1], fmin, fmax, allow_names, names_map)
        if start > end:
            raise ValueError(f"Reversed range: {base!r}")
    else:
        val = _parse_value(base, fmin, fmax, allow_names, names_map)
        if len(slash_parts) == 2:
            # a/n  →  a-MAX/n
            start, end = val, fmax
        else:
            start, end = val, val

    return set(range(start, end + 1, step))


def _parse_field(text: str, fmin: int, fmax: int,
                 allow_names: bool, names_map: dict) -> set:
    if not text:
        raise ValueError("Empty field")

    items = text.split(',')
    for it in items:
        if it == '':
            raise ValueError(f"Empty list element in field: {text!r}")

    result = set()
    for it in items:
        result |= _parse_item(it, fmin, fmax, allow_names, names_map)
    return result


def _parse(expr: str):
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    minute_set = _parse_field(fields[0], 0, 59, False, None)
    hour_set = _parse_field(fields[1], 0, 23, False, None)
    dom_set = _parse_field(fields[2], 1, 31, False, None)
    month_set = _parse_field(fields[3], 1, 12, True, _MONTH_NAMES)
    dow_set = _parse_field(fields[4], 0, 7, True, _DOW_NAMES)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return (minute_set, hour_set, dom_set, month_set, dow_set,
            dom_restricted, dow_restricted)


# ---------------------------------------------------------------------------
# Day / time matching helpers
# ---------------------------------------------------------------------------

def _day_matches(date, dom_set, dow_set, dom_restricted, dow_restricted) -> bool:
    """Apply the Vixie-cron day-of-month / day-of-week rule."""
    # Python weekday(): Mon=0 … Sun=6  →  cron: Sun=0, Mon=1 … Sat=6
    cron_dow = (date.weekday() + 1) % 7

    dom_ok = date.day in dom_set
    dow_ok = cron_dow in dow_set

    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def _find_next_time(sorted_hours, sorted_minutes, min_h, min_m):
    """Return the earliest (h, m) with h in sorted_hours, m in sorted_minutes,
    and (h, m) >= (min_h, min_m), or None if no such pair exists."""
    for h in sorted_hours:
        if h < min_h:
            continue
        if h == min_h:
            for m in sorted_minutes:
                if m >= min_m:
                    return (h, m)
        else:
            # h > min_h: take the smallest valid minute
            if sorted_minutes:
                return (h, sorted_minutes[0])
    return None