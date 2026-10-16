import datetime
import calendar

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

_FIELD_MIN = [0, 0, 1, 1, 0]
_FIELD_MAX = [59, 23, 31, 12, 7]
_NAME_FIELDS = {3, 4}


def _is_ascii_digits(s):
    if not s:
        return False
    for c in s:
        if c < '0' or c > '9':
            return False
    return True


def _is_ascii_alpha(s):
    if not s:
        return False
    for c in s:
        if not ('a' <= c <= 'z' or 'A' <= c <= 'Z'):
            return False
    return True


def _parse_number(s):
    if not _is_ascii_digits(s):
        raise ValueError(f"invalid number token: {s!r}")
    return int(s)


def _parse_value(s, field_idx):
    if _is_ascii_digits(s):
        val = int(s)
        if val < _FIELD_MIN[field_idx] or val > _FIELD_MAX[field_idx]:
            raise ValueError(
                f"value {val} out of range [{_FIELD_MIN[field_idx]}-"
                f"{_FIELD_MAX[field_idx]}] for field {field_idx}"
            )
        return val
    if _is_ascii_alpha(s):
        if field_idx not in _NAME_FIELDS:
            raise ValueError(f"names not allowed in field {field_idx}")
        if len(s) != 3:
            raise ValueError(f"name must be exactly 3 letters: {s!r}")
        upper = s.upper()
        if field_idx == 3:
            if upper not in _MONTH_NAMES:
                raise ValueError(f"unknown month name: {s!r}")
            return _MONTH_NAMES[upper]
        else:
            if upper not in _DOW_NAMES:
                raise ValueError(f"unknown day-of-week name: {s!r}")
            return _DOW_NAMES[upper]
    raise ValueError(f"invalid token: {s!r}")


def _parse_item(item_text, field_idx):
    min_val = _FIELD_MIN[field_idx]
    max_val = _FIELD_MAX[field_idx]

    parts = item_text.split('/')
    if len(parts) > 2:
        raise ValueError(f"malformed item: {item_text!r}")

    base = parts[0]
    step = 1
    if len(parts) == 2:
        step_text = parts[1]
        if not _is_ascii_digits(step_text):
            raise ValueError(f"invalid step: {step_text!r}")
        step = int(step_text)
        if step < 1:
            raise ValueError(f"step must be >= 1, got {step}")

    if base == '*':
        lo, hi = min_val, max_val
    elif '-' in base:
        range_parts = base.split('-')
        if len(range_parts) != 2:
            raise ValueError(f"malformed range: {base!r}")
        start_s, end_s = range_parts
        if not start_s or not end_s:
            raise ValueError(f"malformed range: {base!r}")
        lo = _parse_value(start_s, field_idx)
        hi = _parse_value(end_s, field_idx)
        if lo > hi:
            raise ValueError(f"reversed range: {lo}-{hi}")
    else:
        if not base:
            raise ValueError("empty item")
        val = _parse_value(base, field_idx)
        if len(parts) == 2:
            lo, hi = val, max_val
        else:
            lo, hi = val, val

    result = set()
    v = lo
    while v <= hi:
        result.add(v)
        v += step
    return result


def _parse_field(text, field_idx):
    if not text:
        raise ValueError("empty field")
    items = text.split(',')
    result = set()
    for item in items:
        if not item:
            raise ValueError(f"empty list element in field: {text!r}")
        result |= _parse_item(item, field_idx)
    return result


def _split_fields(expr):
    fields = []
    i = 0
    n = len(expr)
    while i < n:
        while i < n and expr[i] in (' ', '\t'):
            i += 1
        if i >= n:
            break
        j = i
        while j < n and expr[j] not in (' ', '\t'):
            j += 1
        fields.append(expr[i:j])
        i = j
    return fields


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    dom_text = fields[2]
    dow_text = fields[4]

    minute_set = _parse_field(fields[0], 0)
    hour_set = _parse_field(fields[1], 1)
    dom_set = _parse_field(fields[2], 2)
    month_set = _parse_field(fields[3], 3)
    dow_set = _parse_field(fields[4], 4)

    # Normalize day-of-week: 7 means Sunday (same as 0)
    if 7 in dow_set:
        dow_set.add(0)

    # Vixie-cron restrictedness: purely textual test on field text
    dom_restricted = not dom_text.startswith('*')
    dow_restricted = not dow_text.startswith('*')

    # First candidate minute (strictly after `after`)
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    horizon_year = after.year + 8

    sorted_minutes = sorted(minute_set)
    sorted_hours = sorted(hour_set)
    sorted_months = sorted(m for m in month_set if 1 <= m <= 12)

    for year in range(start.year, horizon_year + 1):
        for month in sorted_months:
            if year == start.year and month < start.month:
                continue
            days_in_month = calendar.monthrange(year, month)[1]
            for day in range(1, days_in_month + 1):
                if year == start.year and month == start.month and day < start.day:
                    continue

                # Day matching (Vixie-cron rule)
                cron_dow = datetime.date(year, month, day).isoweekday() % 7
                dom_match = day in dom_set
                dow_match = cron_dow in dow_set

                if dom_restricted and dow_restricted:
                    if not (dom_match or dow_match):
                        continue
                else:
                    if not (dom_match and dow_match):
                        continue

                for hour in sorted_hours:
                    if (year == start.year and month == start.month
                            and day == start.day and hour < start.hour):
                        continue
                    for minute in sorted_minutes:
                        if (year == start.year and month == start.month
                                and day == start.day and hour == start.hour
                                and minute < start.minute):
                            continue
                        return datetime.datetime(year, month, day, hour, minute)

    raise LookupError("no matching firing time within the horizon")
