import datetime
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}

_FIELD_SPECS = [
    (0, 59, None),
    (0, 23, None),
    (1, 31, None),
    (1, 12, _MONTH_NAMES),
    (0, 7, _DOW_NAMES),
]


def _parse_step(s):
    if not s:
        raise ValueError("empty step")
    for c in s:
        if c < '0' or c > '9':
            raise ValueError("invalid step")
    n = int(s)
    if n < 1:
        raise ValueError("step must be >= 1")
    return n


def _parse_value(s, pos, names, fmin, fmax):
    if pos >= len(s):
        raise ValueError("expected value")
    c = s[pos]
    if '0' <= c <= '9':
        end = pos
        while end < len(s) and '0' <= s[end] <= '9':
            end += 1
        num = int(s[pos:end])
        if num < fmin or num > fmax:
            raise ValueError("value out of range")
        return num, end
    if c.isascii() and c.isalpha():
        if names is None:
            raise ValueError("names not allowed in this field")
        end = pos
        while end < len(s) and s[end].isascii() and s[end].isalpha():
            end += 1
        name = s[pos:end].upper()
        if len(name) != 3:
            raise ValueError("name must be exactly 3 letters")
        if name not in names:
            raise ValueError("unknown name")
        return names[name], end
    raise ValueError("invalid character in value")


def _parse_item(item, fmin, fmax, names):
    if not item:
        raise ValueError("empty item")

    if item[0] == '*':
        if item == '*':
            return set(range(fmin, fmax + 1))
        if len(item) > 1 and item[1] == '/':
            step = _parse_step(item[2:])
            return set(range(fmin, fmax + 1, step))
        raise ValueError("invalid wildcard item")

    val1, pos = _parse_value(item, 0, names, fmin, fmax)

    if pos == len(item):
        return {val1}

    if item[pos] == '-':
        pos += 1
        val2, pos = _parse_value(item, pos, names, fmin, fmax)
        if val1 > val2:
            raise ValueError("reversed range")
        if pos == len(item):
            return set(range(val1, val2 + 1))
        if item[pos] == '/':
            step = _parse_step(item[pos + 1:])
            return set(range(val1, val2 + 1, step))
        raise ValueError("invalid item")

    if item[pos] == '/':
        step = _parse_step(item[pos + 1:])
        return set(range(val1, fmax + 1, step))

    raise ValueError("invalid item")


def _parse_field(field_str, fmin, fmax, names):
    if not field_str:
        raise ValueError("empty field")
    items = field_str.split(',')
    result = set()
    for item in items:
        if not item:
            raise ValueError("empty list element")
        result |= _parse_item(item, fmin, fmax, names)
    return result


def _parse_expr(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")
    fields = re.split(r'[ \t]+', stripped)
    if len(fields) != 5:
        raise ValueError("expected 5 fields")

    parsed = []
    for i in range(5):
        fmin, fmax, names = _FIELD_SPECS[i]
        parsed.append(_parse_field(fields[i], fmin, fmax, names))
    return parsed, fields


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    parsed, field_texts = _parse_expr(expr)
    minutes, hours, doms, months, dows = parsed

    # Normalize day-of-week: 7 means Sunday (0)
    if 7 in dows:
        dows = dows | {0}

    # Vixie-cron restriction test (purely textual)
    dom_restricted = not field_texts[2].startswith('*')
    dow_restricted = not field_texts[4].startswith('*')

    # First candidate minute boundary strictly after `after`
    start = after + datetime.timedelta(minutes=1)
    start = start.replace(second=0, microsecond=0)

    year_horizon = after.year + 8

    sorted_hours = sorted(hours)
    sorted_minutes = sorted(minutes)

    current_date = datetime.date(start.year, start.month, start.day)
    first_day = True

    while current_date.year <= year_horizon:
        if current_date.month in months:
            dom_ok = current_date.day in doms
            cron_dow = (current_date.weekday() + 1) % 7
            dow_ok = cron_dow in dows

            if dom_restricted and dow_restricted:
                day_match = dom_ok or dow_ok
            else:
                day_match = dom_ok and dow_ok

            if day_match:
                min_h = start.hour if first_day else 0
                min_m = start.minute if first_day else 0

                found = False
                for h in sorted_hours:
                    if h < min_h:
                        continue
                    for m in sorted_minutes:
                        if h == min_h and m < min_m:
                            continue
                        t = datetime.datetime(
                            current_date.year, current_date.month,
                            current_date.day, h, m
                        )
                        if t > after:
                            if t.year <= year_horizon:
                                return t
                            else:
                                raise LookupError("no firing time within horizon")
                        found = True
                    if found:
                        break

        current_date += datetime.timedelta(days=1)
        first_day = False

    raise LookupError("no firing time within horizon")
