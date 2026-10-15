import datetime
import re

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_DOW_NAMES = {
    'SUN': 0, 'MON': 1, 'TUE': 2, 'WED': 3, 'THU': 4, 'FRI': 5, 'SAT': 6,
}


def _is_digits(s):
    return len(s) > 0 and all('0' <= c <= '9' for c in s)


def _parse_value(s, lo, hi, names):
    if names is not None:
        u = s.upper()
        if u in names:
            v = names[u]
        elif _is_digits(s):
            v = int(s)
        else:
            raise ValueError(f"invalid value {s!r}")
    else:
        if not _is_digits(s):
            raise ValueError(f"invalid value {s!r}")
        v = int(s)
    if v < lo or v > hi:
        raise ValueError(f"value {v} out of range [{lo}, {hi}]")
    return v


def _parse_item(item, lo, hi, names):
    if item.count('/') > 1:
        raise ValueError(f"malformed item {item!r}")

    if '/' in item:
        left, step_s = item.split('/')
        if not _is_digits(step_s):
            raise ValueError(f"invalid step {step_s!r}")
        step = int(step_s)
        if step < 1:
            raise ValueError(f"step must be >= 1")

        if left == '*':
            return set(range(lo, hi + 1, step))
        if '-' in left:
            parts = left.split('-')
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(f"malformed range {left!r}")
            a = _parse_value(parts[0], lo, hi, names)
            b = _parse_value(parts[1], lo, hi, names)
            if a > b:
                raise ValueError(f"reversed range {a}-{b}")
            return set(range(a, b + 1, step))
        a = _parse_value(left, lo, hi, names)
        return set(range(a, hi + 1, step))

    if item == '*':
        return set(range(lo, hi + 1))
    if '-' in item:
        parts = item.split('-')
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"malformed range {item!r}")
        a = _parse_value(parts[0], lo, hi, names)
        b = _parse_value(parts[1], lo, hi, names)
        if a > b:
            raise ValueError(f"reversed range {a}-{b}")
        return set(range(a, b + 1))
    v = _parse_value(item, lo, hi, names)
    return {v}


def _parse_field(text, lo, hi, names):
    if not text:
        raise ValueError("empty field")
    result = set()
    for item in text.split(','):
        if not item:
            raise ValueError(f"empty element in field {text!r}")
        result |= _parse_item(item, lo, hi, names)
    return result


def _parse_expr(expr):
    s = expr.strip(' \t')
    if not s:
        raise ValueError("empty expression")
    fields = re.split(r'[ \t]+', s)
    if len(fields) != 5:
        raise ValueError(f"expected 5 fields, got {len(fields)}")

    m_t, h_t, dom_t, mon_t, dow_t = fields

    minutes = _parse_field(m_t, 0, 59, None)
    hours = _parse_field(h_t, 0, 23, None)
    doms = _parse_field(dom_t, 1, 31, None)
    months = _parse_field(mon_t, 1, 12, _MONTH_NAMES)
    dows = _parse_field(dow_t, 0, 7, _DOW_NAMES)
    if 7 in dows:
        dows.add(0)

    dom_r = not dom_t.startswith('*')
    dow_r = not dow_t.startswith('*')

    return minutes, hours, doms, months, dows, dom_r, dow_r


def _day_ok(d, months, doms, dows, dom_r, dow_r):
    if d.month not in months:
        return False
    cdow = d.isoweekday() % 7  # Sun=0, Mon=1, …, Sat=6
    dm = d.day in doms
    dw = cdow in dows
    if dom_r and dow_r:
        return dm or dw
    return dm and dw


def next_fire(expr: str, after: datetime.datetime) -> datetime.datetime:
    minutes, hours, doms, months, dows, dom_r, dow_r = _parse_expr(expr)

    hm = sorted((h, m) for h in hours for m in minutes)
    if not hm:
        raise LookupError("no valid firing time")

    start = after.date()
    end = datetime.date(after.year + 8, 12, 31)

    d = start
    while d <= end:
        if _day_ok(d, months, doms, dows, dom_r, dow_r):
            if d == start:
                ah, am = after.hour, after.minute
                for h, m in hm:
                    if h > ah or (h == ah and m > am):
                        return datetime.datetime(d.year, d.month, d.day, h, m)
            else:
                h, m = hm[0]
                return datetime.datetime(d.year, d.month, d.day, h, m)
        d += datetime.timedelta(days=1)

    raise LookupError("no firing time within horizon")
