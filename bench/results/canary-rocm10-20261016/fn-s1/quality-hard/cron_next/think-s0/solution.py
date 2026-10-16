import datetime

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def _is_valid_number(s):
    if not s:
        return False
    for c in s:
        if c < '0' or c > '9':
            return False
    return True


def _parse_value(s, names):
    if _is_valid_number(s):
        return int(s)
    if names is not None and len(s) == 3 and s.isascii() and s.isalpha():
        upper = s.upper()
        if upper in names:
            return names[upper]
    raise ValueError(f"invalid value token: {s!r}")


def _parse_step(s):
    if not _is_valid_number(s):
        raise ValueError(f"invalid step: {s!r}")
    n = int(s)
    if n < 1:
        raise ValueError(f"step must be >= 1, got {n}")
    return n


def _parse_item(item, min_val, max_val, names):
    if not item:
        raise ValueError("empty item")

    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"malformed step in item: {item!r}")
        base, step_str = parts
        step = _parse_step(step_str)
    else:
        base = item
        step = None

    if base == '*':
        start = min_val
        end = max_val
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"malformed range in item: {item!r}")
        start = _parse_value(range_parts[0], names)
        end = _parse_value(range_parts[1], names)
        if start < min_val or start > max_val:
            raise ValueError(f"value {start} out of range [{min_val},{max_val}]")
        if end < min_val or end > max_val:
            raise ValueError(f"value {end} out of range [{min_val},{max_val}]")
        if start > end:
            raise ValueError(f"reversed range {start}-{end}")
    else:
        val = _parse_value(base, names)
        if val < min_val or val > max_val:
            raise ValueError(f"value {val} out of range [{min_val},{max_val}]")
        if step is None:
            return {val}
        start = val
        end = max_val

    if step is None:
        step = 1

    result = set()
    v = start
    while v <= end:
        result.add(v)
        v += step
    return result


def _parse_field(text, min_val, max_val, names=None):
    items = text.split(',')
    result = set()
    for item in items:
        if not item:
            raise ValueError("empty list element")
        result.update(_parse_item(item, min_val, max_val, names))
    return result


def _split_fields(expr):
    fields = []
    current = []
    for ch in expr:
        if ch == ' ' or ch == '\t':
            if current:
                fields.append(''.join(current))
                current = []
        else:
            current.append(ch)
    if current:
        fields.append(''.join(current))
    return fields


def _validate_and_parse(expr):
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    minute_text, hour_text, dom_text, month_text, dow_text = fields

    for i, f in enumerate(fields):
        if not f:
            raise ValueError(f"empty field at position {i}")

    minute_set = _parse_field(minute_text, 0, 59, None)
    hour_set = _parse_field(hour_text, 0, 23, None)
    dom_set = _parse_field(dom_text, 1, 31, None)
    month_set = _parse_field(month_text, 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(dow_text, 0, 7, _DOW_NAMES)

    # Normalize day-of-week: 7 means Sunday (same as 0)
    if 7 in dow_set:
        dow_set.discard(7)
        dow_set.add(0)

    dom_restricted = not dom_text.startswith('*')
    dow_restricted = not dow_text.startswith('*')

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def _day_matches(date, dom_set, month_set, dow_set, dom_restricted, dow_restricted):
    if date.month not in month_set:
        return False

    # Python weekday(): Mon=0..Sun=6. Cron: Sun=0..Sat=6.
    cron_dow = (date.weekday() + 1) % 7

    dom_match = date.day in dom_set
    dow_match = cron_dow in dow_set

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted = \
        _validate_and_parse(expr)

    # Earliest candidate minute strictly after `after`
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    end_year = after.year + 8
    end_date = datetime.date(end_year, 12, 31)

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    current_date = start.date()

    while current_date <= end_date:
        if _day_matches(current_date, dom_set, month_set, dow_set,
                        dom_restricted, dow_restricted):
            if current_date == start.date():
                min_hour = start.hour
                min_minute = start.minute
            else:
                min_hour = 0
                min_minute = 0

            for h in sorted_hours:
                if h < min_hour:
                    continue
                if h == min_hour:
                    for m in sorted_minutes:
                        if m >= min_minute:
                            return datetime.datetime(
                                current_date.year, current_date.month,
                                current_date.day, h, m, 0)
                else:
                    return datetime.datetime(
                        current_date.year, current_date.month,
                        current_date.day, h, sorted_minutes[0], 0)

        current_date += datetime.timedelta(days=1)

    raise LookupError("no matching time found within the 8-year horizon")
