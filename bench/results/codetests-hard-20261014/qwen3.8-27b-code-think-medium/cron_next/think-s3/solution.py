import datetime


_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

_FIELD_MIN = [0, 0, 1, 1, 0]
_FIELD_MAX = [59, 23, 31, 12, 7]
_FIELD_NAMES = [None, None, None, _MONTH_NAMES, _DOW_NAMES]


def _is_ascii_digits(s):
    return len(s) > 0 and all('0' <= c <= '9' for c in s)


def _is_ascii_alpha(s):
    return len(s) > 0 and all(('a' <= c <= 'z') or ('A' <= c <= 'Z') for c in s)


def _parse_value(token, field_idx):
    names = _FIELD_NAMES[field_idx]
    if names is not None and _is_ascii_alpha(token):
        upper = token.upper()
        if len(upper) != 3:
            raise ValueError(f"Invalid name (must be 3 letters): {token!r}")
        if upper not in names:
            raise ValueError(f"Unknown name: {token!r}")
        return names[upper]
    if _is_ascii_digits(token):
        return int(token)
    raise ValueError(f"Invalid value token: {token!r}")


def _parse_item(item, field_idx):
    fmin = _FIELD_MIN[field_idx]
    fmax = _FIELD_MAX[field_idx]

    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Malformed step in: {item!r}")
        base, step_str = parts
        if not base:
            raise ValueError(f"Empty base in: {item!r}")
        if not _is_ascii_digits(step_str):
            raise ValueError(f"Invalid step: {step_str!r}")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"Step must be >= 1: {item!r}")
    else:
        base = item
        step = 1

    if base == '*':
        start_val = fmin
        end_val = fmax
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"Malformed range: {base!r}")
        a_str, b_str = range_parts
        if not a_str or not b_str:
            raise ValueError(f"Malformed range: {base!r}")
        start_val = _parse_value(a_str, field_idx)
        end_val = _parse_value(b_str, field_idx)
        if start_val > end_val:
            raise ValueError(f"Reversed range: {base!r}")
    else:
        start_val = _parse_value(base, field_idx)
        if '/' in item:
            end_val = fmax
        else:
            end_val = start_val

    if start_val < fmin or start_val > fmax:
        raise ValueError(f"Value {start_val} out of range [{fmin}, {fmax}]")
    if end_val < fmin or end_val > fmax:
        raise ValueError(f"Value {end_val} out of range [{fmin}, {fmax}]")

    return set(range(start_val, end_val + 1, step))


def _parse_field(field_str, field_idx):
    if not field_str:
        raise ValueError("Empty field")
    items = field_str.split(',')
    result = set()
    for item in items:
        if not item:
            raise ValueError("Empty list element in field")
        result |= _parse_item(item, field_idx)
    return result


def _split_fields(expr):
    fields = []
    current = []
    for c in expr:
        if c == ' ' or c == '\t':
            if current:
                fields.append(''.join(current))
                current = []
        else:
            current.append(c)
    if current:
        fields.append(''.join(current))
    return fields


def _parse(expr):
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    minute_set = _parse_field(fields[0], 0)
    hour_set = _parse_field(fields[1], 1)
    dom_set = _parse_field(fields[2], 2)
    month_set = _parse_field(fields[3], 3)
    dow_set = _parse_field(fields[4], 4)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def _day_matches(day, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
    if day.month not in month_set:
        return False
    dom = day.day
    # Python weekday(): Mon=0..Sun=6; Cron: Sun=0..Sat=6
    cron_dow = (day.weekday() + 1) % 7
    if dom_restricted and dow_restricted:
        return dom in dom_set or cron_dow in dow_set
    else:
        return dom in dom_set and cron_dow in dow_set


def _find_earliest_time(date, sorted_hours, sorted_minutes, min_hour, min_minute):
    for h in sorted_hours:
        if h > min_hour:
            return datetime.datetime(date.year, date.month, date.day, h, sorted_minutes[0])
        elif h == min_hour:
            for m in sorted_minutes:
                if m >= min_minute:
                    return datetime.datetime(date.year, date.month, date.day, h, m)
    return None


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted = _parse(expr)

    # Normalise DOW: 7 means Sunday, so add 0 if 7 is present
    if 7 in dow_set:
        dow_set = dow_set | {0}

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    if not sorted_hours or not sorted_minutes:
        raise LookupError("No matching time within horizon")

    # Earliest candidate minute (strictly after `after`)
    start_dt = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    max_year = after.year + 8
    end_dt = datetime.datetime(max_year, 12, 31, 23, 59)

    current = start_dt.date()
    end_date = end_dt.date()
    start_date = start_dt.date()

    while current <= end_date:
        if _day_matches(current, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
            if current == start_date:
                t = _find_earliest_time(current, sorted_hours, sorted_minutes,
                                        start_dt.hour, start_dt.minute)
            else:
                t = datetime.datetime(current.year, current.month, current.day,
                                      sorted_hours[0], sorted_minutes[0])
            if t is not None and t > after and t <= end_dt:
                return t
        current += datetime.timedelta(days=1)

    raise LookupError("No matching time within horizon")
