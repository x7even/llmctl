import datetime
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def _is_valid_number(s):
    if not s:
        return False
    for c in s:
        if c < '0' or c > '9':
            return False
    return True


def _is_ascii_letter(c):
    return ('A' <= c <= 'Z') or ('a' <= c <= 'z')


def _parse_value(s, names):
    if names is not None and len(s) == 3 and all(_is_ascii_letter(c) for c in s):
        upper = s.upper()
        if upper in names:
            return names[upper]
        raise ValueError("Unknown name: " + s)
    if not _is_valid_number(s):
        raise ValueError("Invalid value: " + repr(s))
    return int(s)


def _parse_step(s):
    if not _is_valid_number(s):
        raise ValueError("Invalid step: " + repr(s))
    n = int(s)
    if n < 1:
        raise ValueError("Step must be >= 1")
    return n


def _parse_item(item, min_val, max_val, names):
    if not item:
        raise ValueError("Empty item")

    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError("Invalid item: " + repr(item))
        base, step_str = parts
        step = _parse_step(step_str)
    else:
        base = item
        step = None

    if base == '*':
        start, end = min_val, max_val
    elif '-' in base:
        rp = base.split('-')
        if len(rp) != 2:
            raise ValueError("Invalid range: " + repr(base))
        a = _parse_value(rp[0], names)
        b = _parse_value(rp[1], names)
        if a > b:
            raise ValueError("Reversed range")
        start, end = a, b
    else:
        val = _parse_value(base, names)
        if step is not None:
            start, end = val, max_val
        else:
            start, end = val, val

    if start < min_val or start > max_val:
        raise ValueError("Value out of range")
    if end < min_val or end > max_val:
        raise ValueError("Value out of range")

    if step is None:
        step = 1

    values = set()
    v = start
    while v <= end:
        values.add(v)
        v += step
    return values


def _parse_field(text, min_val, max_val, names=None):
    if not text:
        raise ValueError("Empty field")
    items = text.split(',')
    values = set()
    for item in items:
        if not item:
            raise ValueError("Empty list element")
        values.update(_parse_item(item, min_val, max_val, names))
    return values


def _days_in_month(year, month):
    if month in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if month in (4, 6, 9, 11):
        return 30
    # February
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return 29
    return 28


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")

    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError("Expected 5 fields, got " + str(len(fields)))

    minutes = _parse_field(fields[0], 0, 59)
    hours = _parse_field(fields[1], 0, 23)
    dom_text = fields[2]
    dom = _parse_field(fields[2], 1, 31)
    months = _parse_field(fields[3], 1, 12, _MONTH_NAMES)
    dow_text = fields[4]
    dow = _parse_field(fields[4], 0, 7, _DOW_NAMES)

    # Normalize day-of-week: 7 is Sunday, same as 0
    if 7 in dow:
        dow.add(0)

    # Vixie-cron restricted check (purely textual on original field text)
    dom_restricted = not dom_text.startswith('*')
    dow_restricted = not dow_text.startswith('*')

    sorted_minutes = sorted(minutes)
    sorted_hours = sorted(hours)
    sorted_months = sorted(months)

    # Earliest candidate minute strictly after 'after'
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    end_year = after.year + 8

    for year in range(start.year, end_year + 1):
        for month in sorted_months:
            if year == start.year and month < start.month:
                continue
            dim = _days_in_month(year, month)
            for day in range(1, dim + 1):
                if year == start.year and month == start.month and day < start.day:
                    continue

                # Compute cron day-of-week (Sun=0 .. Sat=6)
                # Python weekday(): Mon=0 .. Sun=6
                cron_dow = (datetime.date(year, month, day).weekday() + 1) % 7

                # Day matching (Vixie-cron rule)
                if dom_restricted and dow_restricted:
                    day_ok = (day in dom) or (cron_dow in dow)
                else:
                    day_ok = (day in dom) and (cron_dow in dow)

                if not day_ok:
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

    raise LookupError("No firing time found within the horizon")
