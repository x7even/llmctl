import datetime


_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6
}


def _parse_value(token, min_val, max_val, names):
    """Parse a single value token (number or name). Returns int or raises ValueError."""
    if not token:
        raise ValueError("empty value token")
    if names:
        upper = token.upper()
        if upper in names:
            return names[upper]
    if all(c in '0123456789' for c in token):
        val = int(token)
        if val < min_val or val > max_val:
            raise ValueError(f"value {val} out of range [{min_val}, {max_val}]")
        return val
    if all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in token):
        raise ValueError(f"invalid name: {token!r}")
    raise ValueError(f"invalid value: {token!r}")


def _parse_item(item, min_val, max_val, names):
    """Parse a single cron item (e.g. '*', '5', '1-10', '*/15', '3-20/5', '5/10')."""
    if not item:
        raise ValueError("empty item")

    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"malformed step expression: {item!r}")
        base, step_str = parts
        if not step_str or not all(c in '0123456789' for c in step_str):
            raise ValueError(f"invalid step: {step_str!r}")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"step must be >= 1, got {step}")

        if base == '*':
            start, end = min_val, max_val
        elif '-' in base:
            rp = base.split('-')
            if len(rp) != 2:
                raise ValueError(f"malformed range: {base!r}")
            start = _parse_value(rp[0], min_val, max_val, names)
            end = _parse_value(rp[1], min_val, max_val, names)
            if start > end:
                raise ValueError(f"reversed range: {start}-{end}")
        else:
            start = _parse_value(base, min_val, max_val, names)
            end = max_val
            if start > end:
                raise ValueError(f"reversed range: {start}-{end}")
        return set(range(start, end + 1, step))

    if '-' in item:
        rp = item.split('-')
        if len(rp) != 2:
            raise ValueError(f"malformed range: {item!r}")
        start = _parse_value(rp[0], min_val, max_val, names)
        end = _parse_value(rp[1], min_val, max_val, names)
        if start > end:
            raise ValueError(f"reversed range: {start}-{end}")
        return set(range(start, end + 1))

    if item == '*':
        return set(range(min_val, max_val + 1))

    val = _parse_value(item, min_val, max_val, names)
    return {val}


def _parse_field(text, min_val, max_val, names):
    """Parse a full cron field (comma-separated list of items). Returns a set of ints."""
    if not text:
        raise ValueError("empty field")
    items = text.split(',')
    result = set()
    for item in items:
        if not item:
            raise ValueError(f"empty list element in field: {text!r}")
        result |= _parse_item(item, min_val, max_val, names)
    return result


def _split_fields(expr):
    """Split expression into exactly 5 fields separated by spaces/tabs. Raises ValueError."""
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")
    parts = []
    current = []
    for ch in stripped:
        if ch == ' ' or ch == '\t':
            if current:
                parts.append(''.join(current))
                current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current))
    if len(parts) != 5:
        raise ValueError(f"expected 5 fields, got {len(parts)}")
    return parts


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    """Compute the next firing time of a 5-field cron expression after the given datetime."""
    parts = _split_fields(expr)

    minute_set = _parse_field(parts[0], 0, 59, None)
    hour_set = _parse_field(parts[1], 0, 23, None)
    dom_set = _parse_field(parts[2], 1, 31, None)
    month_set = _parse_field(parts[3], 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(parts[4], 0, 7, _DOW_NAMES)

    # Vixie-cron restricted test (purely textual)
    dom_restricted = not parts[2].startswith('*')
    dow_restricted = not parts[4].startswith('*')

    # Normalize dow for matching: 7 means Sunday (0)
    dow_match = set(dow_set)
    if 7 in dow_set:
        dow_match.add(0)

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    # Earliest candidate: next whole minute strictly after `after`
    candidate = after.replace(second=0, microsecond=0)
    if candidate <= after:
        candidate += datetime.timedelta(minutes=1)

    horizon_year = after.year + 8
    horizon = datetime.datetime(horizon_year, 12, 31, 23, 59)

    current_date = candidate.date()
    start_hour = candidate.hour
    start_minute = candidate.minute
    first_day = True

    while True:
        if current_date.year > horizon_year:
            raise LookupError("no firing time found within horizon")

        if current_date.month in month_set:
            # Sunday=0, Monday=1, ..., Saturday=6
            dow = (current_date.weekday() + 1) % 7
            dom = current_date.day

            if dom_restricted and dow_restricted:
                day_ok = (dom in dom_set) or (dow in dow_match)
            else:
                day_ok = (dom in dom_set) and (dow in dow_match)

            if day_ok:
                if first_day:
                    for h in sorted_hours:
                        if h < start_hour:
                            continue
                        if h == start_hour:
                            for m in sorted_minutes:
                                if m >= start_minute:
                                    result = datetime.datetime(
                                        current_date.year, current_date.month,
                                        current_date.day, h, m)
                                    if result <= horizon:
                                        return result
                                    raise LookupError("no firing time found within horizon")
                        else:
                            m = sorted_minutes[0]
                            result = datetime.datetime(
                                current_date.year, current_date.month,
                                current_date.day, h, m)
                            if result <= horizon:
                                return result
                            raise LookupError("no firing time found within horizon")
                else:
                    h = sorted_hours[0]
                    m = sorted_minutes[0]
                    result = datetime.datetime(
                        current_date.year, current_date.month,
                        current_date.day, h, m)
                    if result <= horizon:
                        return result
                    raise LookupError("no firing time found within horizon")

        current_date += datetime.timedelta(days=1)
        first_day = False

    raise LookupError("no firing time found within horizon")
