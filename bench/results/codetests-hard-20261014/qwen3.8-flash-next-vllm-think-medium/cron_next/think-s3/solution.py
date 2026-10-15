import datetime

_MONTH_NAMES = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
_DOW_NAMES = {'SUN':0,'MON':1,'TUE':2,'WED':3,'THU':4,'FRI':5,'SAT':6}
_FIELD_RANGES = [(0,59),(0,23),(1,31),(1,12),(0,7)]


def _is_ascii_digit(c):
    return '0' <= c <= '9'


def _is_ascii_alpha(c):
    return ('a' <= c <= 'z') or ('A' <= c <= 'Z')


def _parse_step(s):
    if not s:
        raise ValueError("empty step")
    if not all(_is_ascii_digit(c) for c in s):
        raise ValueError(f"invalid step: {s}")
    n = int(s)
    if n < 1:
        raise ValueError("step must be >= 1")
    return n


def _parse_value_at(item, pos, field_idx):
    if pos >= len(item):
        raise ValueError("unexpected end of value")
    c = item[pos]
    if _is_ascii_digit(c):
        end = pos
        while end < len(item) and _is_ascii_digit(item[end]):
            end += 1
        return int(item[pos:end]), end
    if _is_ascii_alpha(c):
        if field_idx not in (3, 4):
            raise ValueError(f"names not allowed in field {field_idx}")
        end = pos
        while end < len(item) and _is_ascii_alpha(item[end]):
            end += 1
        token = item[pos:end]
        if len(token) != 3:
            raise ValueError(f"invalid name: {token}")
        upper = token.upper()
        if field_idx == 3:
            if upper not in _MONTH_NAMES:
                raise ValueError(f"unknown month name: {token}")
            return _MONTH_NAMES[upper], end
        else:
            if upper not in _DOW_NAMES:
                raise ValueError(f"unknown day name: {token}")
            return _DOW_NAMES[upper], end
    raise ValueError(f"invalid character: {c!r}")


def _parse_item(item, field_idx):
    lo, hi = _FIELD_RANGES[field_idx]
    if not item:
        raise ValueError("empty item")
    if item[0] == '*':
        if len(item) == 1:
            return set(range(lo, hi + 1))
        if item[1] == '/':
            step = _parse_step(item[2:])
            return set(range(lo, hi + 1, step))
        raise ValueError(f"invalid item: {item}")
    val1, pos = _parse_value_at(item, 0, field_idx)
    if pos == len(item):
        return {val1}
    if item[pos] == '-':
        val2, pos = _parse_value_at(item, pos + 1, field_idx)
        step = 1
        if pos < len(item):
            if item[pos] == '/':
                step = _parse_step(item[pos + 1:])
                pos = len(item)
            else:
                raise ValueError(f"invalid item: {item}")
        if val1 > val2:
            raise ValueError("reversed range")
        return set(range(val1, val2 + 1, step))
    if item[pos] == '/':
        step = _parse_step(item[pos + 1:])
        return set(range(val1, hi + 1, step))
    raise ValueError(f"invalid item: {item}")


def _parse_field(text, field_idx):
    lo, hi = _FIELD_RANGES[field_idx]
    is_restricted = not text.startswith('*')
    if not text:
        raise ValueError("empty field")
    items = text.split(',')
    result = set()
    for item in items:
        if not item:
            raise ValueError("empty list element")
        result.update(_parse_item(item, field_idx))
    for v in result:
        if v < lo or v > hi:
            raise ValueError(f"value {v} out of range [{lo},{hi}]")
    if field_idx == 4:
        if 7 in result:
            result.discard(7)
            result.add(0)
    return result, is_restricted


def _parse_expr(expr):
    stripped = expr.strip(' \t')
    if not stripped:
        raise ValueError("empty expression")
    fields = []
    i = 0
    n = len(stripped)
    while i < n:
        if stripped[i] in (' ', '\t'):
            i += 1
            continue
        j = i
        while j < n and stripped[j] not in (' ', '\t'):
            j += 1
        fields.append(stripped[i:j])
        i = j
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")
    parsed = []
    for idx in range(5):
        parsed.append(_parse_field(fields[idx], idx))
    return parsed


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minute_set, _ = _parse_expr(expr)[0]
    hour_set, _ = _parse_expr(expr)[1]
    dom_set, dom_restricted = _parse_expr(expr)[2]
    month_set, _ = _parse_expr(expr)[3]
    dow_set, dow_restricted = _parse_expr(expr)[4]

    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    end_year = after.year + 8
    end_date = datetime.date(end_year, 12, 31)

    hours = sorted(hour_set)
    minutes = sorted(minute_set)

    current_date = start.date()

    while current_date <= end_date:
        if current_date.month not in month_set:
            current_date += datetime.timedelta(days=1)
            continue

        dow = current_date.isoweekday() % 7  # Sun=0 .. Sat=6

        if dom_restricted and dow_restricted:
            day_ok = (current_date.day in dom_set) or (dow in dow_set)
        else:
            day_ok = (current_date.day in dom_set) and (dow in dow_set)

        if not day_ok:
            current_date += datetime.timedelta(days=1)
            continue

        if current_date == start.date():
            sh, sm = start.hour, start.minute
            for h in hours:
                if h < sh:
                    continue
                for m in minutes:
                    if h == sh and m < sm:
                        continue
                    return datetime.datetime(
                        current_date.year, current_date.month,
                        current_date.day, h, m)
        else:
            return datetime.datetime(
                current_date.year, current_date.month,
                current_date.day, hours[0], minutes[0])

        current_date += datetime.timedelta(days=1)

    raise LookupError("No next fire time found within the horizon")
