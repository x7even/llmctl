import datetime
import re

_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_DAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]

# (min, max, name -> value)
_SPECS = [
    (0, 59, {}),
    (0, 23, {}),
    (1, 31, {}),
    (1, 12, {n: i + 1 for i, n in enumerate(_MONTHS)}),
    (0, 7, {n: i for i, n in enumerate(_DAYS)}),
]

_NUM = re.compile(r"[0-9]+")


def _value(tok, lo, hi, names):
    if _NUM.fullmatch(tok):
        v = int(tok)
    elif tok.upper() in names and len(tok) == 3 and tok.isascii():
        v = names[tok.upper()]
    else:
        raise ValueError(f"bad value {tok!r}")
    if not lo <= v <= hi:
        raise ValueError(f"value {v} out of range {lo}-{hi}")
    return v


def _parse_field(text, spec):
    lo, hi, names = spec
    out = set()
    for item in text.split(","):
        if item == "":
            raise ValueError("empty list element")
        base, slash, step_s = item.partition("/")
        if slash:
            if not _NUM.fullmatch(step_s):
                raise ValueError(f"bad step {step_s!r}")
            step = int(step_s)
            if step < 1:
                raise ValueError("zero step")
        else:
            step = 1
        if base == "*":
            a, b = lo, hi
        elif "-" in base:
            left, dash, right = base.partition("-")
            a = _value(left, lo, hi, names)
            b = _value(right, lo, hi, names)
            if a > b:
                raise ValueError("reversed range")
        else:
            a = _value(base, lo, hi, names)
            b = hi if slash else a
        out.update(range(a, b + 1, step))
    return out


def _parse(expr):
    fields = [f for f in re.split(r"[ \t]+", expr.strip(" \t")) if f != ""]
    if len(fields) != 5:
        raise ValueError("expected 5 fields")
    sets = [_parse_field(f, s) for f, s in zip(fields, _SPECS)]
    sets[4] = {0 if v == 7 else v for v in sets[4]}
    dom_star = fields[2].startswith("*")
    dow_star = fields[4].startswith("*")
    return sets, dom_star, dow_star


def next_fire(expr, after):
    (mins, hours, doms, months, dows), dom_star, dow_star = _parse(expr)
    mins_l, hours_l = sorted(mins), sorted(hours)
    start = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    last_year = after.year + 8

    def day_ok(d):
        if d.month not in months:
            return False
        dm = d.day in doms
        dw = ((d.weekday() + 1) % 7) in dows
        if dom_star or dow_star:
            return dm and dw
        return dm or dw

    day = start.date()
    one = datetime.timedelta(days=1)
    while day.year <= last_year:
        if day.month not in months:
            # jump to the first of the next month
            if day.month == 12:
                day = datetime.date(day.year + 1, 1, 1)
            else:
                day = datetime.date(day.year, day.month + 1, 1)
            continue
        if day_ok(day):
            for h in hours_l:
                for mi in mins_l:
                    t = datetime.datetime(day.year, day.month, day.day, h, mi)
                    if t >= start:
                        return t
        day += one
    raise LookupError("no firing time within horizon")
