import datetime


_MONTH_NAMES = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}
_DOW_NAMES = {
    'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3, 'thu': 4, 'fri': 5, 'sat': 6,
}


def _split_fields(expr):
    i, j = 0, len(expr)
    while i < j and expr[i] in ' \t':
        i += 1
    while j > i and expr[j - 1] in ' \t':
        j -= 1
    stripped = expr[i:j]
    if not stripped:
        return ['']
    fields = []
    cur = []
    for c in stripped:
        if c in ' \t':
            if cur:
                fields.append(''.join(cur))
                cur = []
        else:
            cur.append(c)
    if cur:
        fields.append(''.join(cur))
    return fields


def _is_ascii_digits(s):
    if not s:
        return False
    for c in s:
        if c < '0' or c > '9':
            return False
    return True


def _is_ascii_letters(s):
    if not s:
        return False
    for c in s:
        if not (('a' <= c <= 'z') or ('A' <= c <= 'Z')):
            return False
    return True


def _parse_value(s, allow_month, allow_dow, lo, hi):
    if not s:
        raise ValueError("empty value")
    if _is_ascii_digits(s):
        val = int(s)
        if val < lo or val > hi:
            raise ValueError("value out of range")
        return val
    if (allow_month or allow_dow) and len(s) == 3 and _is_ascii_letters(s):
        low = s.lower()
        if allow_month and low in _MONTH_NAMES:
            val = _MONTH_NAMES[low]
        elif allow_dow and low in _DOW_NAMES:
            val = _DOW_NAMES[low]
        else:
            raise ValueError("unknown name")
        if val < lo or val > hi:
            raise ValueError("value out of range")
        return val
    raise ValueError("invalid value")


def _parse_step(s):
    if not _is_ascii_digits(s):
        raise ValueError("invalid step")
    n = int(s)
    if n < 1:
        raise ValueError("step must be >= 1")
    return n


def _parse_item(item, lo, hi, allow_month, allow_dow):
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError("malformed step")
        base, step_s = parts
        step = _parse_step(step_s)
    else:
        base = item
        step = None

    if base == '*':
        if step is not None:
            return set(range(lo, hi + 1, step))
        return set(range(lo, hi + 1))

    if '-' in base:
        rp = base.split('-')
        if len(rp) != 2:
            raise ValueError("malformed range")
        a = _parse_value(rp[0], allow_month, allow_dow, lo, hi)
        b = _parse_value(rp[1], allow_month, allow_dow, lo, hi)
        if a > b:
            raise ValueError("reversed range")
        if step is not None:
            return set(range(a, b + 1, step))
        return set(range(a, b + 1))

    a = _parse_value(base, allow_month, allow_dow, lo, hi)
    if step is not None:
        return set(range(a, hi + 1, step))
    return {a}


def _parse_field(field_str, lo, hi, allow_month, allow_dow):
    if not field_str:
        raise ValueError("empty field")
    result = set()
    for item in field_str.split(','):
        if not item:
            raise ValueError("empty list element")
        result.update(_parse_item(item, lo, hi, allow_month, allow_dow))
    return result


def _parse(expr):
    fields = _split_fields(expr)
    if len(fields) != 5:
        raise ValueError("expected 5 fields")

    minute_set = _parse_field(fields[0], 0, 59, False, False)
    hour_set = _parse_field(fields[1], 0, 23, False, False)
    dom_set = _parse_field(fields[2], 1, 31, False, False)
    month_set = _parse_field(fields[3], 1, 12, True, False)
    dow_set = _parse_field(fields[4], 0, 7, False, True)

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    # Normalize day-of-week: 7 means Sunday (0)
    if 7 in dow_set:
        dow_set.discard(7)
        dow_set.add(0)

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted = _parse(expr)

    # Start from the next whole minute strictly after `after`
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    max_year = after.year + 8
    end_date = datetime.date(max_year, 12, 31)

    sorted_hours = sorted(hour_set)
    min_minute = min(minute_set)
    sorted_minutes = sorted(minute_set)

    current_date = start.date()
    start_hour = start.hour
    start_minute = start.minute

    while current_date <= end_date:
        # Check month
        if current_date.month in month_set:
            dom_val = current_date.day
            dow_val = (current_date.weekday() + 1) % 7  # Sun=0 .. Sat=6

            dom_match = dom_val in dom_set
            dow_match = dow_val in dow_set

            if dom_restricted and dow_restricted:
                day_match = dom_match or dow_match
            else:
                day_match = dom_match and dow_match

            if day_match:
                # Determine earliest acceptable hour/minute for this day
                if current_date == start.date():
                    earliest_h = start_hour
                    earliest_m = start_minute
                else:
                    earliest_h = 0
                    earliest_m = 0

                found = False
                for h in sorted_hours:
                    if h < earliest_h:
                        continue
                    if h == earliest_h:
                        for m in sorted_minutes:
                            if m >= earliest_m:
                                return datetime.datetime(
                                    current_date.year, current_date.month,
                                    current_date.day, h, m)
                        # No minute in this hour works, try next hour
                        # (use earliest minute)
                        return datetime.datetime(
                            current_date.year, current_date.month,
                            current_date.day, h, min_minute)
                    else:
                        # h > earliest_h, use earliest minute
                        return datetime.datetime(
                            current_date.year, current_date.month,
                            current_date.day, h, min_minute)

        current_date += datetime.timedelta(days=1)

    raise LookupError("no firing time found within horizon")
