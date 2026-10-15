import datetime
import re

_MONTH_NAMES = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}

_DOW_NAMES = {
    'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6,
}


def _is_valid_number(s: str) -> bool:
    return bool(s) and all(c in '0123456789' for c in s)


def _parse_value(s: str, min_val: int, max_val: int, names) -> int:
    if names is not None:
        low = s.lower()
        if low in names:
            val = names[low]
            if val < min_val or val > max_val:
                raise ValueError(f"Value {val} out of range [{min_val},{max_val}]")
            return val
    if not _is_valid_number(s):
        raise ValueError(f"Invalid token: {s!r}")
    val = int(s)
    if val < min_val or val > max_val:
        raise ValueError(f"Value {val} out of range [{min_val},{max_val}]")
    return val


def _parse_step(s: str) -> int:
    if not _is_valid_number(s):
        raise ValueError(f"Invalid step: {s!r}")
    n = int(s)
    if n < 1:
        raise ValueError(f"Step must be >= 1, got {n}")
    return n


def _parse_item(item: str, min_val: int, max_val: int, names) -> set:
    if not item:
        raise ValueError("Empty item")

    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Invalid item with step: {item!r}")
        base_str, step_str = parts
        step = _parse_step(step_str)
        has_step = True
    else:
        base_str = item
        step = 1
        has_step = False

    if base_str == '*':
        start, end = min_val, max_val
    elif '-' in base_str:
        rp = base_str.split('-')
        if len(rp) != 2:
            raise ValueError(f"Invalid range: {base_str!r}")
        start = _parse_value(rp[0], min_val, max_val, names)
        end = _parse_value(rp[1], min_val, max_val, names)
        if start > end:
            raise ValueError(f"Reversed range: {start}-{end}")
    else:
        start = _parse_value(base_str, min_val, max_val, names)
        end = max_val if has_step else start

    return set(range(start, end + 1, step))


def _parse_field(text: str, min_val: int, max_val: int, names) -> set:
    if not text:
        raise ValueError("Empty field")
    items = text.split(',')
    result: set = set()
    for item in items:
        if not item:
            raise ValueError(f"Empty element in field: {text!r}")
        result |= _parse_item(item, min_val, max_val, names)
    return result


def _parse_expr(expr: str):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    minute_set = _parse_field(fields[0], 0, 59, None)
    hour_set = _parse_field(fields[1], 0, 23, None)
    dom_set = _parse_field(fields[2], 1, 31, None)
    month_set = _parse_field(fields[3], 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(fields[4], 0, 7, _DOW_NAMES)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def _day_matches(d: datetime.date, dom_set: set, dow_set: set,
                 dom_restricted: bool, dow_restricted: bool) -> bool:
    dom_match = d.day in dom_set
    # Python weekday(): Mon=0..Sun=6; cron DOW: Sun=0, Mon=1..Sat=6
    cron_dow = (d.weekday() + 1) % 7
    dow_match = (cron_dow in dow_set) or (cron_dow == 0 and 7 in dow_set)

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted = _parse_expr(expr)

    # Earliest candidate: next whole minute strictly after `after`
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    horizon_year = after.year + 8

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    current_date = start.date()
    horizon_end = datetime.date(horizon_year, 12, 31)

    while current_date <= horizon_end:
        if current_date.month in month_set and _day_matches(
                current_date, dom_set, dow_set, dom_restricted, dow_restricted):
            if current_date == start.date():
                min_hour = start.hour
                min_minute = start.minute
            else:
                min_hour = 0
                min_minute = 0

            for h in sorted_hours:
                if h < min_hour:
                    continue
                for m in sorted_minutes:
                    if h == min_hour and m < min_minute:
                        continue
                    return datetime.datetime(
                        current_date.year, current_date.month, current_date.day, h, m)

        current_date += datetime.timedelta(days=1)

    raise LookupError("No matching firing time within the search horizon")
