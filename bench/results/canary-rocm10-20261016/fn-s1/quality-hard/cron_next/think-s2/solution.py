import datetime
import calendar

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    fields = _split_fields(expr)

    minute_set = _parse_field(fields[0], 0, 59, None)
    hour_set = _parse_field(fields[1], 0, 23, None)
    dom_set = _parse_field(fields[2], 1, 31, None)
    month_set = _parse_field(fields[3], 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(fields[4], 0, 7, _DOW_NAMES)

    # Normalize day-of-week: 7 means Sunday (same as 0)
    dow_set = {0 if v == 7 else v for v in dow_set}

    # Vixie-cron restricted test: purely textual on the raw field string
    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    sorted_minutes = sorted(minute_set)
    sorted_hours = sorted(hour_set)
    sorted_months = sorted(month_set)

    # Earliest whole-minute datetime strictly greater than `after`
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    max_year = after.year + 8

    for year in range(start.year, max_year + 1):
        for month in sorted_months:
            if year == start.year and month < start.month:
                continue
            num_days = calendar.monthrange(year, month)[1]
            for day in range(1, num_days + 1):
                if year == start.year and month == start.month and day < start.day:
                    continue
                if not _day_matches(year, month, day, dom_set, month_set,
                                    dow_set, dom_restricted, dow_restricted):
                    continue
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

    raise LookupError("no firing time found within horizon")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split_fields(expr: str) -> list:
    """Split on space/tab only; reject anything that isn't exactly 5 fields."""
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")
    fields = []
    current = []
    for ch in stripped:
        if ch in (' ', '\t'):
            if current:
                fields.append(''.join(current))
                current = []
        else:
            current.append(ch)
    if current:
        fields.append(''.join(current))
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")
    return fields


def _parse_field(text: str, min_val: int, max_val: int, names) -> set:
    items = text.split(',')
    result = set()
    for item in items:
        result |= _parse_item(item, min_val, max_val, names)
    return result


def _parse_item(item: str, min_val: int, max_val: int, names) -> set:
    if not item:
        raise ValueError("empty item")

    slash_parts = item.split('/')
    if len(slash_parts) > 2:
        raise ValueError("malformed step")

    base = slash_parts[0]
    has_step = len(slash_parts) == 2

    if has_step:
        step = _parse_number(slash_parts[1])
        if step < 1:
            raise ValueError("step must be >= 1")
    else:
        step = 1

    if base == '*':
        start, end = min_val, max_val
    elif '-' in base:
        parts = base.split('-')
        if len(parts) != 2:
            raise ValueError("malformed range")
        start = _parse_value(parts[0], min_val, max_val, names)
        end = _parse_value(parts[1], min_val, max_val, names)
        if start > end:
            raise ValueError("reversed range")
    else:
        val = _parse_value(base, min_val, max_val, names)
        if has_step:
            # a/n is shorthand for a-MAX/n
            start, end = val, max_val
        else:
            start, end = val, val

    result = set()
    v = start
    while v <= end:
        result.add(v)
        v += step
    return result


def _parse_value(token: str, min_val: int, max_val: int, names) -> int:
    if not token:
        raise ValueError("empty value")

    # Number: non-empty string of ASCII digits only
    if all('0' <= c <= '9' for c in token):
        val = int(token)
    # Name (only where allowed): exactly 3 ASCII letters, known name
    elif (names is not None
          and len(token) == 3
          and all(('a' <= c <= 'z') or ('A' <= c <= 'Z') for c in token)):
        upper = token.upper()
        if upper not in names:
            raise ValueError(f"unknown name: {token!r}")
        val = names[upper]
    else:
        raise ValueError(f"invalid token: {token!r}")

    if val < min_val or val > max_val:
        raise ValueError(f"value {val} out of range [{min_val},{max_val}]")
    return val


def _parse_number(token: str) -> int:
    if not token:
        raise ValueError("empty number")
    if not all('0' <= c <= '9' for c in token):
        raise ValueError(f"invalid number: {token!r}")
    return int(token)


def _day_matches(year, month, day, dom_set, month_set, dow_set,
                 dom_restricted, dow_restricted) -> bool:
    if month not in month_set:
        return False

    # Python weekday(): Mon=0 .. Sun=6
    # Cron dow:         Sun=0 .. Sat=6
    py_wd = datetime.date(year, month, day).weekday()
    dow = (py_wd + 1) % 7

    dom_match = day in dom_set
    dow_match = dow in dow_set

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match
