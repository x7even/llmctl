import datetime
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def _is_number(s):
    return len(s) > 0 and all(c in '0123456789' for c in s)


def _is_name(s):
    return len(s) == 3 and all(
        c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in s
    )


def _parse_value(s, name_map):
    if _is_number(s):
        return int(s)
    if name_map is not None and _is_name(s):
        upper = s.upper()
        if upper in name_map:
            return name_map[upper]
        raise ValueError(f"Unknown name: {s}")
    raise ValueError(f"Invalid value token: {s!r}")


def _parse_item(item, field_min, field_max, name_map):
    if not item:
        raise ValueError("Empty item in field")

    # Split off step if present
    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Malformed item (multiple /): {item!r}")
        base_str, step_str = parts
        if not _is_number(step_str):
            raise ValueError(f"Invalid step: {step_str!r}")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"Step must be >= 1, got {step}")
    else:
        base_str = item
        step = None

    # Parse the base portion
    if base_str == '*':
        if step is not None:
            return set(range(field_min, field_max + 1, step))
        return set(range(field_min, field_max + 1))

    if '-' in base_str:
        parts = base_str.split('-')
        if len(parts) != 2:
            raise ValueError(f"Malformed range: {base_str!r}")
        a = _parse_value(parts[0], name_map)
        b = _parse_value(parts[1], name_map)
        if a < field_min or a > field_max:
            raise ValueError(f"Range start {a} out of [{field_min},{field_max}]")
        if b < field_min or b > field_max:
            raise ValueError(f"Range end {b} out of [{field_min},{field_max}]")
        if a > b:
            raise ValueError(f"Reversed range {a}-{b}")
        if step is not None:
            return set(range(a, b + 1, step))
        return set(range(a, b + 1))

    # Single value (possibly with /step meaning a-MAX/step)
    a = _parse_value(base_str, name_map)
    if a < field_min or a > field_max:
        raise ValueError(f"Value {a} out of [{field_min},{field_max}]")
    if step is not None:
        return set(range(a, field_max + 1, step))
    return {a}


def _parse_field(field_str, field_min, field_max, name_map):
    if not field_str:
        raise ValueError("Empty field")
    result = set()
    for item in field_str.split(','):
        result |= _parse_item(item, field_min, field_max, name_map)
    return result


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    # --- Split into 5 fields (only spaces and tabs are separators) ---
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    # --- Parse and validate all five fields before searching ---
    minute_set = _parse_field(fields[0], 0, 59, None)
    hour_set   = _parse_field(fields[1], 0, 23, None)
    dom_set    = _parse_field(fields[2], 1, 31, None)
    month_set  = _parse_field(fields[3], 1, 12, _MONTH_NAMES)
    dow_set    = _parse_field(fields[4], 0, 7,  _DOW_NAMES)

    # --- Restricted flags (purely textual: starts with '*'?) ---
    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    # --- Normalize day-of-week: 7 means Sunday (same as 0) ---
    dow_set = {0 if v == 7 else v for v in dow_set}

    # --- Precompute sorted lists for fast lookup ---
    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    horizon_year = after.year + 8

    # --- Search day by day (at most ~2920 iterations over 8 years) ---
    current_date = after.date()

    while current_date.year <= horizon_year:
        # Skip months not in the set
        if current_date.month not in month_set:
            if current_date.month == 12:
                current_date = datetime.date(current_date.year + 1, 1, 1)
            else:
                current_date = datetime.date(current_date.year, current_date.month + 1, 1)
            continue

        # Day matching (Vixie-cron rule)
        dom_in = current_date.day in dom_set
        # Python weekday: Mon=0..Sun=6  ->  cron: Sun=0..Sat=6
        cron_dow = (current_date.weekday() + 1) % 7
        dow_in = cron_dow in dow_set

        if dom_restricted and dow_restricted:
            day_ok = dom_in or dow_in
        else:
            day_ok = dom_in and dow_in

        if day_ok:
            if current_date == after.date():
                # Must find a time strictly greater than `after`
                min_hour = after.hour
                min_minute = after.minute + 1
                if min_minute >= 60:
                    min_minute = 0
                    min_hour += 1
                if min_hour < 24:
                    for h in sorted_hours:
                        if h < min_hour:
                            continue
                        for m in sorted_minutes:
                            if h == min_hour and m < min_minute:
                                continue
                            result = datetime.datetime(
                                current_date.year, current_date.month,
                                current_date.day, h, m
                            )
                            if result.year <= horizon_year:
                                return result
                            # result is on the same day, year check always passes here
                            # but keep it for safety
                            break
                        else:
                            continue
                        break
            else:
                # Earliest valid time on this day
                h = sorted_hours[0]
                m = sorted_minutes[0]
                result = datetime.datetime(
                    current_date.year, current_date.month,
                    current_date.day, h, m
                )
                if result.year <= horizon_year:
                    return result

        current_date += datetime.timedelta(days=1)

    raise LookupError("No firing time found within the search horizon")
