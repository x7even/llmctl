import datetime


_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

# (min_val, max_val, names_dict_or_None)
_FIELD_SPECS = [
    (0, 59, None),
    (0, 23, None),
    (1, 31, None),
    (1, 12, _MONTH_NAMES),
    (0, 7, _DOW_NAMES),
]


def _is_number(s):
    return len(s) > 0 and all('0' <= c <= '9' for c in s)


def _is_name(s):
    return len(s) == 3 and all(('a' <= c <= 'z') or ('A' <= c <= 'Z') for c in s)


def _parse_value(s, min_val, max_val, names):
    if names is not None and _is_name(s):
        upper = s.upper()
        if upper not in names:
            raise ValueError(f"Unknown name: {s!r}")
        v = names[upper]
    elif _is_number(s):
        v = int(s)
    else:
        raise ValueError(f"Invalid value: {s!r}")
    if v < min_val or v > max_val:
        raise ValueError(f"Value {v} out of range [{min_val}, {max_val}]")
    return v


def _parse_step(s):
    if not _is_number(s):
        raise ValueError(f"Invalid step: {s!r}")
    n = int(s)
    if n < 1:
        raise ValueError(f"Step must be >= 1, got {n}")
    return n


def _parse_item(item, min_val, max_val, names):
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Invalid item: {item!r}")
        range_part, step_str = parts
        step = _parse_step(step_str)
    else:
        range_part = item
        step = None

    if range_part == '*':
        start, end = min_val, max_val
    elif '-' in range_part:
        dash_parts = range_part.split('-')
        if len(dash_parts) != 2:
            raise ValueError(f"Invalid range: {range_part!r}")
        start = _parse_value(dash_parts[0], min_val, max_val, names)
        end = _parse_value(dash_parts[1], min_val, max_val, names)
        if start > end:
            raise ValueError(f"Reversed range: {start}-{end}")
    else:
        start = _parse_value(range_part, min_val, max_val, names)
        if step is not None:
            end = max_val
        else:
            end = start

    if step is None:
        step = 1

    for v in range(start, end + 1, step):
        yield v


def _parse_field(text, min_val, max_val, names):
    values = set()
    items = text.split(',')
    for item in items:
        if item == '':
            raise ValueError("Empty item in field")
        for v in _parse_item(item, min_val, max_val, names):
            values.add(v)
    return values


def _split_fields(expr):
    s = expr.strip(' \t')
    if not s:
        return []
    fields = []
    current = []
    for ch in s:
        if ch in (' ', '\t'):
            if current:
                fields.append(''.join(current))
                current = []
        else:
            current.append(ch)
    if current:
        fields.append(''.join(current))
    return fields


def _parse_expr(expr):
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    parsed = []
    for i in range(5):
        min_val, max_val, names = _FIELD_SPECS[i]
        values = _parse_field(fields[i], min_val, max_val, names)
        parsed.append(values)

    # Determine restricted status (purely textual test on original field text)
    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    # Normalize day-of-week: 7 -> 0 (both mean Sunday)
    parsed[4] = {0 if v == 7 else v for v in parsed[4]}

    return {
        'minute': parsed[0],
        'hour': parsed[1],
        'dom': parsed[2],
        'month': parsed[3],
        'dow': parsed[4],
        'dom_restricted': dom_restricted,
        'dow_restricted': dow_restricted,
    }


def _day_matches(date, fields):
    dom = date.day
    # Python weekday(): Mon=0..Sun=6; Cron DOW: Sun=0..Sat=6
    cron_dow = (date.weekday() + 1) % 7

    dom_match = dom in fields['dom']
    dow_match = cron_dow in fields['dow']

    if fields['dom_restricted'] and fields['dow_restricted']:
        return dom_match or dow_match
    else:
        return dom_match and dow_match


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    fields = _parse_expr(expr)

    # Earliest candidate minute: strictly after `after`, on a whole minute
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    max_year = after.year + 8

    hours = sorted(fields['hour'])
    minutes = sorted(fields['minute'])

    current_date = start.date()
    end_date = datetime.date(max_year, 12, 31)

    while current_date <= end_date:
        if current_date.month in fields['month'] and _day_matches(current_date, fields):
            if current_date == start.date():
                min_h, min_m = start.hour, start.minute
            else:
                min_h, min_m = 0, 0

            for h in hours:
                if h < min_h:
                    continue
                for m in minutes:
                    if h == min_h and m < min_m:
                        continue
                    return datetime.datetime(
                        current_date.year, current_date.month,
                        current_date.day, h, m
                    )

        current_date += datetime.timedelta(days=1)

    raise LookupError("No matching time within horizon")
