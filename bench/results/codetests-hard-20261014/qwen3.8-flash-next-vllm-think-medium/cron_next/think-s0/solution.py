import datetime


_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

_ASCII_DIGITS = frozenset('0123456789')
_ASCII_ALPHA = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')


def _is_ascii_digits(s):
    return len(s) > 0 and all(c in _ASCII_DIGITS for c in s)


def _is_ascii_alpha(s):
    return len(s) > 0 and all(c in _ASCII_ALPHA for c in s)


def _parse_value(s, min_val, max_val, names):
    if not s:
        raise ValueError("empty value")
    if names is not None and len(s) == 3 and _is_ascii_alpha(s):
        upper = s.upper()
        if upper in names:
            val = names[upper]
        else:
            raise ValueError("unknown name: " + s)
    elif _is_ascii_digits(s):
        val = int(s)
    else:
        raise ValueError("invalid value: " + repr(s))
    if val < min_val or val > max_val:
        raise ValueError("value out of range")
    return val


def _parse_item(item_str, min_val, max_val, names):
    if not item_str:
        raise ValueError("empty item")

    if '/' in item_str:
        slash_parts = item_str.split('/')
        if len(slash_parts) != 2:
            raise ValueError("malformed step in: " + repr(item_str))
        range_part, step_str = slash_parts
        if not _is_ascii_digits(step_str):
            raise ValueError("invalid step: " + repr(step_str))
        step = int(step_str)
        if step < 1:
            raise ValueError("step must be >= 1")
    else:
        range_part = item_str
        step = 1

    if range_part == '*':
        start, end = min_val, max_val
    elif range_part.startswith('*'):
        raise ValueError("invalid range: " + repr(range_part))
    elif '-' in range_part:
        dash_parts = range_part.split('-')
        if len(dash_parts) != 2:
            raise ValueError("malformed range: " + repr(range_part))
        start = _parse_value(dash_parts[0], min_val, max_val, names)
        end = _parse_value(dash_parts[1], min_val, max_val, names)
        if start > end:
            raise ValueError("reversed range")
    else:
        start = _parse_value(range_part, min_val, max_val, names)
        if step > 1:
            end = max_val
        else:
            end = start

    values = set()
    v = start
    while v <= end:
        values.add(v)
        v += step
    return values


def _parse_field(field_str, min_val, max_val, names):
    if not field_str:
        raise ValueError("empty field")
    items = field_str.split(',')
    values = set()
    for item in items:
        if not item:
            raise ValueError("empty list element")
        values |= _parse_item(item, min_val, max_val, names)
    return values


def _split_fields(expr):
    result = []
    i = 0
    n = len(expr)
    while i < n and expr[i] in ' \t':
        i += 1
    while i < n:
        j = i
        while j < n and expr[j] not in ' \t':
            j += 1
        result.append(expr[i:j])
        i = j
        while i < n and expr[i] in ' \t':
            i += 1
    return result


def _parse_expr(expr):
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError("expected 5 fields, got " + str(len(fields)))

    minute_str, hour_str, dom_str, month_str, dow_str = fields

    minute_set = _parse_field(minute_str, 0, 59, None)
    hour_set = _parse_field(hour_str, 0, 23, None)
    dom_set = _parse_field(dom_str, 1, 31, None)
    month_set = _parse_field(month_str, 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(dow_str, 0, 7, _DOW_NAMES)

    dom_restricted = not dom_str.startswith('*')
    dow_restricted = not dow_str.startswith('*')

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted = _parse_expr(expr)

    # Compute the earliest candidate minute strictly after `after`
    start = after + datetime.timedelta(minutes=1)
    start = start.replace(second=0, microsecond=0)

    year_limit = after.year + 8

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    current_date = start.date()
    current_hour = start.hour
    current_minute = start.minute

    while current_date.year <= year_limit:
        if current_date.month in month_set:
            dom = current_date.day
            # Python weekday: Mon=0..Sun=6; cron: Sun=0..Sat=6
            cron_dow = (current_date.weekday() + 1) % 7

            dom_match = dom in dom_set
            dow_match = (cron_dow in dow_set) or (cron_dow == 0 and 7 in dow_set)

            if dom_restricted and dow_restricted:
                day_ok = dom_match or dow_match
            else:
                day_ok = dom_match and dow_match

            if day_ok:
                # Find earliest (hour, minute) >= (current_hour, current_minute)
                found = False
                h_result = None
                m_result = None
                for h in sorted_hours:
                    if h < current_hour:
                        continue
                    if h > current_hour:
                        h_result = h
                        m_result = sorted_minutes[0]
                        found = True
                        break
                    # h == current_hour
                    for m in sorted_minutes:
                        if m >= current_minute:
                            h_result = h
                            m_result = m
                            found = True
                            break
                    if found:
                        break

                if found:
                    return datetime.datetime(
                        current_date.year, current_date.month, current_date.day,
                        h_result, m_result
                    )

        # Advance to next day
        current_date += datetime.timedelta(days=1)
        current_hour = 0
        current_minute = 0

    raise LookupError("no matching time found within the horizon")
