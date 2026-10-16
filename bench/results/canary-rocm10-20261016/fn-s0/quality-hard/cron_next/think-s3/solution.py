import datetime
import bisect
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def _is_digits(s):
    return bool(s) and all('0' <= c <= '9' for c in s)


def _is_alpha(s):
    return bool(s) and all(('a' <= c <= 'z') or ('A' <= c <= 'Z') for c in s)


def _parse_step(s):
    if not _is_digits(s):
        raise ValueError(f"invalid step: {s!r}")
    n = int(s)
    if n < 1:
        raise ValueError(f"step must be >= 1, got {n}")
    return n


def _parse_value(s, min_val, max_val, names):
    if _is_digits(s):
        v = int(s)
        if v < min_val or v > max_val:
            raise ValueError(f"value {v} out of range [{min_val}, {max_val}]")
        return v
    if names is not None and _is_alpha(s):
        if len(s) != 3:
            raise ValueError(f"invalid name length: {s!r}")
        upper = s.upper()
        if upper not in names:
            raise ValueError(f"unknown name: {s!r}")
        return names[upper]
    raise ValueError(f"invalid value: {s!r}")


def _parse_item(item, min_val, max_val, names):
    parts = item.split('/')
    if len(parts) > 2:
        raise ValueError(f"too many '/' in item: {item!r}")

    if len(parts) == 2:
        left, step_str = parts
        step = _parse_step(step_str)
    else:
        left = parts[0]
        step = 1

    if not left:
        raise ValueError(f"empty left part in item: {item!r}")

    if left == '*':
        lo, hi = min_val, max_val
    elif '-' in left:
        range_parts = left.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"malformed range in item: {item!r}")
        lo = _parse_value(range_parts[0], min_val, max_val, names)
        hi = _parse_value(range_parts[1], min_val, max_val, names)
        if lo > hi:
            raise ValueError(f"reversed range in item: {item!r}")
    else:
        v = _parse_value(left, min_val, max_val, names)
        if len(parts) == 2:
            lo, hi = v, max_val
        else:
            lo, hi = v, v

    values = set()
    cur = lo
    while cur <= hi:
        values.add(cur)
        cur += step
    return values


def _parse_field(text, min_val, max_val, names):
    if not text:
        raise ValueError("empty field")
    items = text.split(',')
    if any(item == '' for item in items):
        raise ValueError("empty item in field")
    values = set()
    for item in items:
        values |= _parse_item(item, min_val, max_val, names)
    return values


def _parse_expr(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    minute_text, hour_text, dom_text, month_text, dow_text = fields

    minutes = _parse_field(minute_text, 0, 59, None)
    hours = _parse_field(hour_text, 0, 23, None)
    doms = _parse_field(dom_text, 1, 31, None)
    months = _parse_field(month_text, 1, 12, _MONTH_NAMES)
    dows = _parse_field(dow_text, 0, 7, _DOW_NAMES)

    # Normalize: 7 means Sunday (0)
    if 7 in dows:
        dows.add(0)

    # Vixie-cron restricted check: purely textual
    dom_restricted = not dom_text.startswith('*')
    dow_restricted = not dow_text.startswith('*')

    return minutes, hours, doms, months, dows, dom_restricted, dow_restricted


def _day_matches(year, month, day, months, doms, dows, dom_restricted, dow_restricted):
    if month not in months:
        return False

    cron_dow = (datetime.date(year, month, day).weekday() + 1) % 7

    dom_match = day in doms
    dow_match = cron_dow in dows

    if dom_restricted and dow_restricted:
        return dom_match or dow_match
    else:
        return dom_match and dow_match


def _find_time_on_day(d, min_hour, min_min, sorted_hours, sorted_minutes):
    """Find earliest valid (hour, minute) on day d that is >= (min_hour, min_min)."""
    idx = bisect.bisect_left(sorted_hours, min_hour)
    if idx >= len(sorted_hours):
        return None

    h = sorted_hours[idx]
    if h == min_hour:
        midx = bisect.bisect_left(sorted_minutes, min_min)
        if midx < len(sorted_minutes):
            return datetime.datetime(d.year, d.month, d.day, h, sorted_minutes[midx])
        # No valid minute in this hour; try next hour
        idx += 1
        if idx >= len(sorted_hours):
            return None
        return datetime.datetime(d.year, d.month, d.day, sorted_hours[idx], sorted_minutes[0])
    else:
        # h > min_hour, any valid minute works
        return datetime.datetime(d.year, d.month, d.day, h, sorted_minutes[0])


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minutes, hours, doms, months, dows, dom_restricted, dow_restricted = _parse_expr(expr)

    # Earliest candidate: next whole minute strictly after `after`
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    max_year = after.year + 8

    sorted_minutes = sorted(minutes)
    sorted_hours = sorted(hours)

    d = start.date()
    cur_hour = start.hour
    cur_min = start.minute
    first_day = True

    while d.year <= max_year:
        if _day_matches(d.year, d.month, d.day, months, doms, dows,
                        dom_restricted, dow_restricted):
            if first_day:
                result = _find_time_on_day(d, cur_hour, cur_min,
                                           sorted_hours, sorted_minutes)
                if result is not None:
                    return result
            else:
                return datetime.datetime(d.year, d.month, d.day,
                                         sorted_hours[0], sorted_minutes[0])

        first_day = False
        d += datetime.timedelta(days=1)

    raise LookupError("no firing time found within horizon")
