import datetime
import bisect


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    (minute_set, hour_set, dom_set, month_set, dow_set,
     dom_restricted, dow_restricted) = _parse_expr(expr)

    sorted_hours = sorted(hour_set)
    sorted_minutes = sorted(minute_set)

    # First candidate minute (strictly after `after`, whole minute)
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    # Horizon
    horizon_year = after.year + 8
    horizon = datetime.datetime(horizon_year, 12, 31, 23, 59)

    current_day = start.date()
    end_day = horizon.date()

    while current_day <= end_day:
        if _day_matches(current_day, month_set, dom_set, dow_set,
                        dom_restricted, dow_restricted):
            if current_day == start.date():
                sh, sm = start.hour, start.minute
            else:
                sh, sm = 0, 0

            t = _find_earliest_time(sorted_hours, sorted_minutes, sh, sm)
            if t is not None:
                h, m = t
                result = datetime.datetime(
                    current_day.year, current_day.month, current_day.day, h, m)
                if result <= horizon:
                    return result

        current_day += datetime.timedelta(days=1)

    raise LookupError("No matching time found within the 8-year horizon")


def _parse_expr(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("Empty expression")

    fields = _split_fields(stripped)
    if len(fields) != 5:
        raise ValueError(f"Expected 5 fields, got {len(fields)}")

    month_names = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }
    dow_names = {
        'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6
    }

    minute_set = _parse_field(fields[0], 0, 59, None, "minute")
    hour_set = _parse_field(fields[1], 0, 23, None, "hour")
    dom_set = _parse_field(fields[2], 1, 31, None, "day-of-month")
    month_set = _parse_field(fields[3], 1, 12, month_names, "month")
    dow_set = _parse_field(fields[4], 0, 7, dow_names, "day-of-week")

    dom_restricted = not fields[2].startswith('*')
    dow_restricted = not fields[4].startswith('*')

    return minute_set, hour_set, dom_set, month_set, dow_set, dom_restricted, dow_restricted


def _split_fields(s):
    fields = []
    current = []
    for c in s:
        if c == ' ' or c == '\t':
            if current:
                fields.append(''.join(current))
                current = []
        else:
            current.append(c)
    if current:
        fields.append(''.join(current))
    return fields


def _parse_field(text, min_val, max_val, names, field_name):
    if not text:
        raise ValueError(f"Empty field: {field_name}")

    values = set()
    items = text.split(',')

    for item in items:
        if not item:
            raise ValueError(f"Empty item in {field_name} field")
        _parse_item(item, min_val, max_val, names, values, field_name)

    return values


def _parse_item(item, min_val, max_val, names, values, field_name):
    step = 1
    has_step = False

    if '/' in item:
        parts = item.split('/')
        if len(parts) != 2:
            raise ValueError(f"Malformed step in {field_name}: {item}")
        base, step_str = parts
        if not _is_valid_number(step_str):
            raise ValueError(f"Invalid step in {field_name}: {item}")
        step = int(step_str)
        if step < 1:
            raise ValueError(f"Step must be >= 1 in {field_name}: {item}")
        has_step = True
    else:
        base = item

    if not base:
        raise ValueError(f"Empty base in {field_name}: {item}")

    if base == '*':
        values.update(range(min_val, max_val + 1, step))
    elif '-' in base:
        parts = base.split('-')
        if len(parts) != 2:
            raise ValueError(f"Malformed range in {field_name}: {item}")
        a_str, b_str = parts
        a = _parse_value(a_str, min_val, max_val, names, field_name)
        b = _parse_value(b_str, min_val, max_val, names, field_name)
        if a > b:
            raise ValueError(f"Reversed range in {field_name}: {item}")
        values.update(range(a, b + 1, step))
    else:
        a = _parse_value(base, min_val, max_val, names, field_name)
        if has_step:
            values.update(range(a, max_val + 1, step))
        else:
            values.add(a)


def _is_valid_number(s):
    if not s:
        return False
    return all(c in '0123456789' for c in s)


def _parse_value(s, min_val, max_val, names, field_name):
    if not s:
        raise ValueError(f"Empty value in {field_name}")

    # All ASCII digits → number
    if all(c in '0123456789' for c in s):
        val = int(s)
        if val < min_val or val > max_val:
            raise ValueError(
                f"Value {val} out of range [{min_val},{max_val}] in {field_name}")
        return val

    # All ASCII letters → name
    if all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in s):
        if names is None:
            raise ValueError(f"Name not allowed in {field_name}: {s}")
        if len(s) != 3:
            raise ValueError(f"Name must be exactly 3 letters in {field_name}: {s}")
        upper = s.upper()
        if upper not in names:
            raise ValueError(f"Unknown name in {field_name}: {s}")
        val = names[upper]
        if val < min_val or val > max_val:
            raise ValueError(
                f"Value {val} out of range [{min_val},{max_val}] in {field_name}")
        return val

    # Mixed or other characters
    raise ValueError(f"Invalid value in {field_name}: {s}")


def _day_matches(d, month_set, dom_set, dow_set, dom_restricted, dow_restricted):
    if d.month not in month_set:
        return False

    # Convert Python weekday (Mon=0..Sun=6) to cron (Sun=0..Sat=6)
    cron_dow = (d.weekday() + 1) % 7
    dom_ok = d.day in dom_set
    dow_ok = cron_dow in dow_set or (7 in dow_set and cron_dow == 0)

    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    else:
        return dom_ok and dow_ok


def _find_earliest_time(sorted_hours, sorted_minutes, start_h, start_m):
    if not sorted_hours or not sorted_minutes:
        return None

    idx = bisect.bisect_left(sorted_hours, start_h)

    if idx < len(sorted_hours):
        h = sorted_hours[idx]
        m_idx = bisect.bisect_left(sorted_minutes, start_m)
        if m_idx < len(sorted_minutes):
            return (h, sorted_minutes[m_idx])

    for i in range(idx + 1, len(sorted_hours)):
        return (sorted_hours[i], sorted_minutes[0])

    return None
