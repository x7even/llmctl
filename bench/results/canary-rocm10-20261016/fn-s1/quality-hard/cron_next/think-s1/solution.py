import datetime
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

# (min, max) for minute, hour, day-of-month, month, day-of-week
_FIELD_RANGE = [
    (0, 59),
    (0, 23),
    (1, 31),
    (1, 12),
    (0, 7),
]


def _is_digits(s):
    return len(s) > 0 and all(c in '0123456789' for c in s)


def _is_ascii_alpha(s):
    return len(s) > 0 and all(c.isalpha() and c.isascii() for c in s)


def _parse_value(s, field_idx):
    if not s:
        raise ValueError(f"empty value in field {field_idx + 1}")
    if _is_digits(s):
        return int(s)
    if field_idx in (3, 4):
        if len(s) == 3 and _is_ascii_alpha(s):
            table = _MONTH_NAMES if field_idx == 3 else _DOW_NAMES
            name = s.upper()
            if name in table:
                return table[name]
            raise ValueError(f"unknown name '{s}' in field {field_idx + 1}")
        raise ValueError(f"invalid name '{s}' in field {field_idx + 1}")
    raise ValueError(f"invalid value '{s}' in field {field_idx + 1}")


def _parse_step(s):
    if not _is_digits(s):
        raise ValueError(f"invalid step '{s}'")
    n = int(s)
    if n < 1:
        raise ValueError(f"step must be >= 1, got {n}")
    return n


def _parse_item(item, field_idx):
    lo, hi = _FIELD_RANGE[field_idx]

    parts = item.split('/')
    if len(parts) > 2:
        raise ValueError(f"malformed item '{item}' in field {field_idx + 1}")

    base = parts[0]
    step = _parse_step(parts[1]) if len(parts) == 2 else 1

    if base == '*':
        start, end = lo, hi
    elif '-' in base:
        rp = base.split('-')
        if len(rp) != 2:
            raise ValueError(f"malformed range '{base}' in field {field_idx + 1}")
        start = _parse_value(rp[0], field_idx)
        end = _parse_value(rp[1], field_idx)
        if start > end:
            raise ValueError(
                f"reversed range {start}-{end} in field {field_idx + 1}"
            )
    else:
        val = _parse_value(base, field_idx)
        if len(parts) == 2:
            start, end = val, hi
        else:
            start, end = val, val

    if start < lo or start > hi:
        raise ValueError(
            f"value {start} out of range [{lo},{hi}] in field {field_idx + 1}"
        )
    if end < lo or end > hi:
        raise ValueError(
            f"value {end} out of range [{lo},{hi}] in field {field_idx + 1}"
        )

    values = set()
    v = start
    while v <= end:
        values.add(v)
        v += step
    return values


def _parse_field(text, field_idx):
    if not text:
        raise ValueError(f"empty field {field_idx + 1}")
    items = text.split(',')
    result = set()
    for item in items:
        if not item:
            raise ValueError(f"empty item in field {field_idx + 1}")
        result |= _parse_item(item, field_idx)
    return result


def _earliest_time(date, min_time, sorted_hours, sorted_minutes):
    for h in sorted_hours:
        if h > min_time.hour:
            return datetime.datetime(
                date.year, date.month, date.day, h, sorted_minutes[0]
            )
        if h == min_time.hour:
            for m in sorted_minutes:
                if m >= min_time.minute:
                    return datetime.datetime(
                        date.year, date.month, date.day, h, m
                    )
    return None


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    # ---- split into exactly 5 whitespace-separated fields ----
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    # ---- restricted-field test (purely textual, before parsing) ----
    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    # ---- parse & validate all five fields ----
    minute_set = _parse_field(fields[0], 0)
    hour_set   = _parse_field(fields[1], 1)
    dom_set    = _parse_field(fields[2], 2)
    month_set  = _parse_field(fields[3], 3)
    dow_set    = _parse_field(fields[4], 4)

    # normalise day-of-week: 7 and 0 both mean Sunday
    if 7 in dow_set:
        dow_set.discard(7)
        dow_set.add(0)

    # ---- earliest candidate whole-minute strictly after `after` ----
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    year_limit = after.year + 8

    sorted_hours   = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    # ---- iterate day-by-day (at most ~2928 iterations) ----
    cur_date = start.date()
    cur_time = start.time()
    end_date = datetime.date(year_limit, 12, 31)

    while cur_date <= end_date:
        if cur_date.month in month_set:
            dom_match = cur_date.day in dom_set
            dow = cur_date.isoweekday() % 7  # Sun=0 … Sat=6
            dow_match = dow in dow_set

            if dom_restricted and dow_restricted:
                day_ok = dom_match or dow_match
            else:
                day_ok = dom_match and dow_match

            if day_ok:
                result = _earliest_time(
                    cur_date, cur_time, sorted_hours, sorted_minutes
                )
                if result is not None:
                    return result

        cur_date += datetime.timedelta(days=1)
        cur_time = datetime.time(0, 0)

    raise LookupError("no next fire time within the horizon")
