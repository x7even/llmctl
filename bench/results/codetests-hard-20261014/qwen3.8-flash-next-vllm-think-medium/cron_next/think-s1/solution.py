import datetime
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

# (min_val, max_val, allows_names, name_dict)
_FIELD_DEFS = [
    (0, 59, False, None),
    (0, 23, False, None),
    (1, 31, False, None),
    (1, 12, True, _MONTH_NAMES),
    (0, 7, True, _DOW_NAMES),
]


def _is_number(s: str) -> bool:
    return len(s) > 0 and all('0' <= c <= '9' for c in s)


def _is_name(s: str) -> bool:
    return len(s) == 3 and all(c.isascii() and c.isalpha() for c in s)


def _parse_value(s: str, field_idx: int) -> int:
    if _is_number(s):
        return int(s)
    if _FIELD_DEFS[field_idx][2]:
        if _is_name(s):
            name_dict = _FIELD_DEFS[field_idx][3]
            upper = s.upper()
            if upper in name_dict:
                return name_dict[upper]
            raise ValueError(f"Unknown name: {s!r}")
    raise ValueError(f"Invalid value token: {s!r}")


def _parse_field(text: str, field_idx: int) -> set:
    min_val, max_val, _, _ = _FIELD_DEFS[field_idx]

    if not text:
        raise ValueError("Empty field")

    items = text.split(',')
    result = set()

    for item in items:
        if not item:
            raise ValueError("Empty list element")

        parts = item.split('/')
        if len(parts) > 2:
            raise ValueError(f"Malformed step in {item!r}")

        base = parts[0]
        step = 1
        if len(parts) == 2:
            step_str = parts[1]
            if not _is_number(step_str):
                raise ValueError(f"Malformed step in {item!r}")
            step = int(step_str)
            if step < 1:
                raise ValueError(f"Step must be >= 1 in {item!r}")

        if base == '*':
            start = min_val
            end = max_val
        elif '-' in base:
            range_parts = base.split('-')
            if len(range_parts) != 2:
                raise ValueError(f"Malformed range in {item!r}")
            start = _parse_value(range_parts[0], field_idx)
            end = _parse_value(range_parts[1], field_idx)
            if start < min_val or start > max_val:
                raise ValueError(f"Out of range in {item!r}")
            if end < min_val or end > max_val:
                raise ValueError(f"Out of range in {item!r}")
            if start > end:
                raise ValueError(f"Reversed range in {item!r}")
        else:
            start = _parse_value(base, field_idx)
            if start < min_val or start > max_val:
                raise ValueError(f"Out of range in {item!r}")
            if len(parts) == 2:
                end = max_val
            else:
                end = start

        v = start
        while v <= end:
            result.add(v)
            v += step

    return result


def _day_matches(date, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
    if date.month not in month_set:
        return False

    dom = date.day
    # Python weekday(): Mon=0..Sun=6; cron DOW: Sun=0..Sat=6
    cron_dow = (date.weekday() + 1) % 7

    dom_match = dom in dom_set
    dow_match = cron_dow in dow_set

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    # --- Parse and validate expression ---
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError("Expected exactly 5 fields")

    minute_set = _parse_field(fields[0], 0)
    hour_set = _parse_field(fields[1], 1)
    dom_set = _parse_field(fields[2], 2)
    month_set = _parse_field(fields[3], 3)
    dow_set_raw = _parse_field(fields[4], 4)

    # Normalize DOW: 7 -> 0 (both mean Sunday)
    dow_set = set()
    for d in dow_set_raw:
        dow_set.add(0 if d == 7 else d)

    # Vixie-cron restricted check (purely textual)
    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    # --- Determine search start ---
    start_minute = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    year_limit = after.year + 8

    # --- Search day by day ---
    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    current_date = start_minute.date()

    while current_date.year <= year_limit:
        if _day_matches(current_date, month_set, dom_set, dow_set,
                        dom_restricted, dow_restricted):
            if current_date == start_minute.date():
                min_h = start_minute.hour
                min_m = start_minute.minute
            else:
                min_h = 0
                min_m = 0

            result = _find_first_time(sorted_hours, sorted_minutes,
                                      min_h, min_m, current_date)
            if result is not None:
                return result

        current_date += datetime.timedelta(days=1)

    raise LookupError("No firing time found within the search horizon")


def _find_first_time(sorted_hours, sorted_minutes, min_h, min_m, date):
    for h in sorted_hours:
        if h < min_h:
            continue
        if h == min_h:
            for m in sorted_minutes:
                if m >= min_m:
                    return datetime.datetime(date.year, date.month, date.day, h, m)
        else:
            return datetime.datetime(date.year, date.month, date.day, h, sorted_minutes[0])
    return None
