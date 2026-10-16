import datetime
import re


MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def _is_ascii_digits(s):
    return len(s) > 0 and all('0' <= c <= '9' for c in s)


def _parse_value(s, field_min, field_max, allow_names, name_map):
    if _is_ascii_digits(s):
        val = int(s)
    elif allow_names:
        upper = s.upper()
        if len(upper) == 3 and upper in name_map:
            val = name_map[upper]
        else:
            raise ValueError(f"invalid name: {s!r}")
    else:
        raise ValueError(f"invalid value: {s!r}")
    if val < field_min or val > field_max:
        raise ValueError(f"value {val} out of range [{field_min}, {field_max}]")
    return val


def _parse_step(s):
    if not _is_ascii_digits(s):
        raise ValueError(f"invalid step: {s!r}")
    val = int(s)
    if val < 1:
        raise ValueError(f"step must be >= 1, got {val}")
    return val


def _parse_item(item_str, field_min, field_max, allow_names, name_map):
    if item_str == '':
        raise ValueError("empty item")

    if item_str.startswith('*'):
        if item_str == '*':
            return set(range(field_min, field_max + 1))
        if item_str.startswith('*/'):
            step = _parse_step(item_str[2:])
            return set(range(field_min, field_max + 1, step))
        raise ValueError(f"invalid item: {item_str!r}")

    # Does not start with '*'
    slash_parts = item_str.split('/')
    if len(slash_parts) > 2:
        raise ValueError(f"invalid item: {item_str!r}")

    if len(slash_parts) == 2:
        base_str, step_str = slash_parts
        if base_str == '':
            raise ValueError(f"invalid item: {item_str!r}")
        step = _parse_step(step_str)
    else:
        base_str = item_str
        step = None

    if '-' in base_str:
        dash_parts = base_str.split('-')
        if len(dash_parts) != 2:
            raise ValueError(f"invalid range: {base_str!r}")
        a_str, b_str = dash_parts
        if a_str == '' or b_str == '':
            raise ValueError(f"invalid range: {base_str!r}")
        a = _parse_value(a_str, field_min, field_max, allow_names, name_map)
        b = _parse_value(b_str, field_min, field_max, allow_names, name_map)
        if a > b:
            raise ValueError(f"reversed range: {a}-{b}")
        if step is not None:
            return set(range(a, b + 1, step))
        return set(range(a, b + 1))
    else:
        a = _parse_value(base_str, field_min, field_max, allow_names, name_map)
        if step is not None:
            return set(range(a, field_max + 1, step))
        return {a}


def _parse_field(field_str, field_min, field_max, allow_names, name_map):
    if field_str == '':
        raise ValueError("empty field")
    items = field_str.split(',')
    for item in items:
        if item == '':
            raise ValueError("empty list element in field")
    result = set()
    for item in items:
        result |= _parse_item(item, field_min, field_max, allow_names, name_map)
    return result


def _parse(expr):
    stripped = expr.strip(' \t')
    if stripped == '':
        raise ValueError("empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    minute_set = _parse_field(fields[0], 0, 59, False, None)
    hour_set = _parse_field(fields[1], 0, 23, False, None)
    dom_set = _parse_field(fields[2], 1, 31, False, None)
    month_set = _parse_field(fields[3], 1, 12, True, MONTH_NAMES)
    dow_set = _parse_field(fields[4], 0, 7, True, DOW_NAMES)

    # Normalise: 7 means Sunday (0)
    if 7 in dow_set:
        dow_set.add(0)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return (minute_set, hour_set, dom_set, month_set, dow_set,
            dom_restricted, dow_restricted)


def _day_matches(d, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
    if d.month not in month_set:
        return False
    dom_ok = d.day in dom_set
    # Python weekday: Mon=0..Sun=6; cron: Sun=0..Sat=6
    dow = (d.weekday() + 1) % 7
    dow_ok = dow in dow_set
    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    (minute_set, hour_set, dom_set, month_set, dow_set,
     dom_restricted, dow_restricted) = _parse(expr)

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)
    min_h = sorted_hours[0]
    min_m = sorted_minutes[0]

    max_year = after.year + 8
    end_date = datetime.date(max_year, 12, 31)

    current_day = after.date()
    after_day = after.date()
    after_h = after.hour
    after_m = after.minute

    while current_day <= end_date:
        if _day_matches(current_day, month_set, dom_set, dow_set,
                        dom_restricted, dow_restricted):
            if current_day > after_day:
                return datetime.datetime(current_day.year, current_day.month,
                                         current_day.day, min_h, min_m)
            else:
                # Same calendar day as 'after': find earliest valid time > after
                found = None
                for h in sorted_hours:
                    if h > after_h:
                        found = datetime.datetime(current_day.year,
                                                  current_day.month,
                                                  current_day.day, h, min_m)
                        break
                    if h == after_h:
                        for m in sorted_minutes:
                            if m > after_m:
                                found = datetime.datetime(current_day.year,
                                                          current_day.month,
                                                          current_day.day, h, m)
                                break
                        if found is not None:
                            break
                if found is not None:
                    return found
        current_day += datetime.timedelta(days=1)

    raise LookupError("no firing time found within search horizon")
