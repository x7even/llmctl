import datetime
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def _is_ascii_digits(s: str) -> bool:
    return len(s) > 0 and all('0' <= c <= '9' for c in s)


def _parse_value(s: str, min_val: int, max_val: int, names) -> int:
    if not s:
        raise ValueError("empty value token")
    if names is not None and len(s) == 3 and s.isascii() and s.isalpha():
        upper = s.upper()
        if upper in names:
            return names[upper]
        raise ValueError(f"unknown name: {s}")
    if _is_ascii_digits(s):
        val = int(s)
        if val < min_val or val > max_val:
            raise ValueError(f"value {val} out of range [{min_val},{max_val}]")
        return val
    raise ValueError(f"invalid value token: {s}")


def _parse_step(s: str) -> int:
    if not _is_ascii_digits(s):
        raise ValueError(f"invalid step: {s}")
    n = int(s)
    if n < 1:
        raise ValueError("step must be >= 1")
    return n


def _parse_item(item: str, min_val: int, max_val: int, names) -> set:
    if not item:
        raise ValueError("empty item")

    # Split on '/'
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"malformed item: {item}")
        range_part, step_part = parts
        step = _parse_step(step_part)
    else:
        range_part = item
        step = None

    # Parse range portion
    if range_part == '*':
        lo, hi = min_val, max_val
    elif '-' in range_part:
        segs = range_part.split('-')
        if len(segs) != 2:
            raise ValueError(f"malformed range: {range_part}")
        lo = _parse_value(segs[0], min_val, max_val, names)
        hi = _parse_value(segs[1], min_val, max_val, names)
        if lo > hi:
            raise ValueError(f"reversed range {lo}-{hi}")
    else:
        lo = _parse_value(range_part, min_val, max_val, names)
        if step is not None:
            hi = max_val
        else:
            hi = lo

    if step is None:
        step = 1

    return set(range(lo, hi + 1, step))


def _parse_field(text: str, min_val: int, max_val: int, names) -> set:
    if not text:
        raise ValueError("empty field")
    items = text.split(',')
    result = set()
    for item in items:
        if not item:
            raise ValueError("empty list element")
        result.update(_parse_item(item, min_val, max_val, names))
    return result


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    # --- Parse and validate expression ---
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError("expression must have exactly 5 fields")

    minute_text, hour_text, dom_text, month_text, dow_text = fields

    minute_set = _parse_field(minute_text, 0, 59, None)
    hour_set = _parse_field(hour_text, 0, 23, None)
    dom_set = _parse_field(dom_text, 1, 31, None)
    month_set = _parse_field(month_text, 1, 12, _MONTH_NAMES)
    dow_set = _parse_field(dow_text, 0, 7, _DOW_NAMES)

    # Normalise day-of-week: 7 -> 0 (both mean Sunday)
    if 7 in dow_set:
        dow_set.discard(7)
        dow_set.add(0)

    # Determine restricted status (purely textual on the raw field text)
    dom_restricted = not dom_text.startswith('*')
    dow_restricted = not dow_text.startswith('*')

    # --- Compute the earliest candidate minute ---
    start = (after + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    end_year = after.year + 8

    # --- Search day-by-day ---
    current_date = start.date()

    while current_date.year <= end_year:
        if current_date.month in month_set:
            # Cron day-of-week: Sunday=0 ... Saturday=6
            cron_dow = (current_date.weekday() + 1) % 7

            dom_match = current_date.day in dom_set
            dow_match = cron_dow in dow_set

            if dom_restricted and dow_restricted:
                day_ok = dom_match or dow_match
            else:
                day_ok = dom_match and dow_match

            if day_ok:
                if current_date == start.date():
                    # Must find time >= start on this day
                    for h in sorted_hours:
                        if h < start.hour:
                            continue
                        for m in sorted_minutes:
                            if h == start.hour and m < start.minute:
                                continue
                            t = datetime.datetime(
                                current_date.year, current_date.month,
                                current_date.day, h, m
                            )
                            if t.year <= end_year:
                                return t
                            raise LookupError("no match within horizon")
                else:
                    h = sorted_hours[0]
                    m = sorted_minutes[0]
                    t = datetime.datetime(
                        current_date.year, current_date.month,
                        current_date.day, h, m
                    )
                    if t.year <= end_year:
                        return t
                    raise LookupError("no match within horizon")

        current_date += datetime.timedelta(days=1)

    raise LookupError("no match within horizon")
