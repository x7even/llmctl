import datetime
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    fields = _split_fields(expr)

    minute_set = _parse_field(fields[0], 0, 59, False, None)
    hour_set = _parse_field(fields[1], 0, 23, False, None)
    dom_set = _parse_field(fields[2], 1, 31, False, None)
    month_set = _parse_field(fields[3], 1, 12, True, _MONTH_NAMES)
    dow_set = _parse_field(fields[4], 0, 7, True, _DOW_NAMES)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return _search(minute_set, hour_set, dom_set, month_set, dow_set,
                   dom_restricted, dow_restricted, after)


def _split_fields(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")
    parts = re.split(r'[ \t]+', stripped)
    if len(parts) != 5:
        raise ValueError(f"expected 5 fields, got {len(parts)}")
    return parts


def _parse_field(field_str, min_val, max_val, allow_names, name_map):
    items = field_str.split(',')
    result = set()
    for item in items:
        if item == '':
            raise ValueError("empty item in field")
        result.update(_parse_item(item, min_val, max_val, allow_names, name_map))
    return result


def _parse_item(item, min_val, max_val, allow_names, name_map):
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError("malformed step expression")
        range_part, step_str = parts
        step = _parse_step(step_str)
        if range_part == '*':
            start, end = min_val, max_val
        elif '-' in range_part:
            start, end = _parse_range(range_part, min_val, max_val,
                                      allow_names, name_map)
        else:
            start = _parse_value(range_part, min_val, max_val,
                                 allow_names, name_map)
            end = max_val
        return set(range(start, end + 1, step))
    else:
        if item == '*':
            return set(range(min_val, max_val + 1))
        elif '-' in item:
            start, end = _parse_range(item, min_val, max_val,
                                      allow_names, name_map)
            return set(range(start, end + 1))
        else:
            val = _parse_value(item, min_val, max_val, allow_names, name_map)
            return {val}


def _parse_range(s, min_val, max_val, allow_names, name_map):
    parts = s.split('-')
    if len(parts) != 2:
        raise ValueError("malformed range")
    start = _parse_value(parts[0], min_val, max_val, allow_names, name_map)
    end = _parse_value(parts[1], min_val, max_val, allow_names, name_map)
    if start > end:
        raise ValueError("reversed range")
    return start, end


def _parse_value(s, min_val, max_val, allow_names, name_map):
    if not s:
        raise ValueError("empty value")
    if _is_ascii_alpha(s):
        if not allow_names:
            raise ValueError("names not allowed in this field")
        if len(s) != 3:
            raise ValueError("name must be exactly 3 letters")
        upper = s.upper()
        if upper not in name_map:
            raise ValueError(f"unknown name: {s}")
        val = name_map[upper]
    elif _is_ascii_digits(s):
        val = int(s)
    else:
        raise ValueError(f"invalid value token: {s}")
    if val < min_val or val > max_val:
        raise ValueError(f"value {val} out of range [{min_val},{max_val}]")
    return val


def _parse_step(s):
    if not s:
        raise ValueError("empty step")
    if not _is_ascii_digits(s):
        raise ValueError("invalid step")
    n = int(s)
    if n < 1:
        raise ValueError("step must be >= 1")
    return n


def _is_ascii_digits(s):
    return len(s) > 0 and all(c in '0123456789' for c in s)


def _is_ascii_alpha(s):
    return len(s) > 0 and all(
        c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in s
    )


def _search(minute_set, hour_set, dom_set, month_set, dow_set,
            dom_restricted, dow_restricted, after):
    start = after + datetime.timedelta(minutes=1)
    start = start.replace(second=0, microsecond=0)

    max_year = after.year + 8
    end_date = datetime.date(max_year, 12, 31)

    sorted_minutes = sorted(minute_set)
    sorted_hours = sorted(hour_set)

    current_date = start.date()

    while current_date <= end_date:
        if _day_matches(current_date, dom_set, month_set, dow_set,
                        dom_restricted, dow_restricted):
            for h in sorted_hours:
                for m in sorted_minutes:
                    t = datetime.datetime(current_date.year, current_date.month,
                                          current_date.day, h, m)
                    if t >= start:
                        return t
        current_date += datetime.timedelta(days=1)

    raise LookupError("no firing time found within the horizon")


def _day_matches(date, dom_set, month_set, dow_set,
                 dom_restricted, dow_restricted):
    if date.month not in month_set:
        return False

    # Python weekday(): Mon=0 .. Sun=6
    # Our convention:   Sun=0, Mon=1 .. Sat=6
    python_dow = date.weekday()
    our_dow = (python_dow + 1) % 7

    dow_match = our_dow in dow_set or (our_dow == 0 and 7 in dow_set)
    dom_match = date.day in dom_set

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match
