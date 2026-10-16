import datetime

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
    'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
    'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3,
    'THU': 4, 'FRI': 5, 'SAT': 6,
}

_FIELD_MIN = (0, 0, 1, 1, 0)
_FIELD_MAX = (59, 23, 31, 12, 7)


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


def _is_number(s):
    if not s:
        return False
    for c in s:
        if c < '0' or c > '9':
            return False
    return True


def _parse_value(s, field_index):
    if _is_number(s):
        val = int(s)
    elif field_index in (3, 4) and len(s) == 3 and s.isascii() and s.isalpha():
        upper = s.upper()
        if field_index == 3:
            val = _MONTH_NAMES.get(upper)
        else:
            val = _DOW_NAMES.get(upper)
        if val is None:
            raise ValueError(f"unknown name: {s}")
    else:
        raise ValueError(f"invalid value: {s}")

    fmin = _FIELD_MIN[field_index]
    fmax = _FIELD_MAX[field_index]
    if val < fmin or val > fmax:
        raise ValueError(f"value {val} out of range [{fmin},{fmax}]")
    return val


def _parse_step(s):
    if not _is_number(s):
        raise ValueError(f"invalid step: {s}")
    val = int(s)
    if val < 1:
        raise ValueError("step must be >= 1")
    return val


def _parse_item(item, field_index):
    if not item:
        raise ValueError("empty item")

    fmin = _FIELD_MIN[field_index]
    fmax = _FIELD_MAX[field_index]

    if item[0] == '*':
        if item == '*':
            return set(range(fmin, fmax + 1))
        if len(item) > 1 and item[1] == '/':
            step = _parse_step(item[2:])
            return set(range(fmin, fmax + 1, step))
        raise ValueError(f"invalid item: {item}")

    parts = item.split('/')
    if len(parts) > 2:
        raise ValueError(f"too many / in item: {item}")

    range_part = parts[0]
    step = _parse_step(parts[1]) if len(parts) == 2 else 1

    if not range_part:
        raise ValueError(f"empty range part: {item}")

    if '-' in range_part:
        rp = range_part.split('-')
        if len(rp) != 2:
            raise ValueError(f"invalid range: {range_part}")
        a_str, b_str = rp
        if not a_str or not b_str:
            raise ValueError(f"empty range endpoint: {range_part}")
        a = _parse_value(a_str, field_index)
        b = _parse_value(b_str, field_index)
        if a > b:
            raise ValueError(f"reversed range: {a}-{b}")
        start, end = a, b
    else:
        a = _parse_value(range_part, field_index)
        if len(parts) == 2:
            start, end = a, fmax
        else:
            return {a}

    return set(range(start, end + 1, step))


def _parse_field(field_text, field_index):
    items = field_text.split(',')
    if any(item == '' for item in items):
        raise ValueError("empty element in comma-separated list")
    result = set()
    for item in items:
        result.update(_parse_item(item, field_index))
    return result


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    minutes_set = _parse_field(fields[0], 0)
    hours_set = _parse_field(fields[1], 1)
    dom_set = _parse_field(fields[2], 2)
    month_set = _parse_field(fields[3], 3)
    dow_set = _parse_field(fields[4], 4)

    dom_restricted = fields[2][0] != '*'
    dow_restricted = fields[4][0] != '*'

    dow_normalized = set()
    for v in dow_set:
        dow_normalized.add(0 if v == 7 else v)

    sorted_minutes = sorted(minutes_set)
    sorted_hours = sorted(hours_set)

    start = (after + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    horizon_year = after.year + 8

    current_date = start.date()
    start_hour = start.hour
    start_minute = start.minute

    while current_date.year <= horizon_year:
        if current_date.month in month_set:
            cron_dow = (current_date.weekday() + 1) % 7
            dom_match = current_date.day in dom_set
            dow_match = cron_dow in dow_normalized

            if dom_restricted and dow_restricted:
                day_ok = dom_match or dow_match
            else:
                day_ok = dom_match and dow_match

            if day_ok:
                if current_date == start.date():
                    found = False
                    for h in sorted_hours:
                        if h < start_hour:
                            continue
                        if h == start_hour:
                            for m in sorted_minutes:
                                if m >= start_minute:
                                    return datetime.datetime(
                                        current_date.year, current_date.month,
                                        current_date.day, h, m)
                        else:
                            return datetime.datetime(
                                current_date.year, current_date.month,
                                current_date.day, h, sorted_minutes[0])
                else:
                    return datetime.datetime(
                        current_date.year, current_date.month,
                        current_date.day, sorted_hours[0], sorted_minutes[0])

        current_date += datetime.timedelta(days=1)

    raise LookupError("no firing time found within horizon")
