"""Hidden tests for cron_next. Each test takes the loaded solution module `m`.

Ground truth is NOT the reference solution:
  * `_oracle` is a brute-force stepper written in this file: it walks real `datetime`
    values one minute at a time (optionally fast-forwarding over whole non-matching days)
    and decides matches with `_field_has`, an independent matcher that interprets the
    field text directly with arithmetic ((v - start) % step == 0), never expanding value sets.
  * `_valid_field` is an independent regex-based validity checker used to fuzz ValueError.
  * Handwritten expectations were derived by hand from the calendar.
"""
import datetime
import random
import re

D = datetime.datetime
MIN = datetime.timedelta(minutes=1)
DAY = datetime.timedelta(days=1)

_MON = {n: i + 1 for i, n in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_DOW = {n: i for i, n in enumerate("sun mon tue wed thu fri sat".split())}


# ---------------------------------------------------------------- oracle

def _conv(tok, names):
    return names[tok.lower()] if tok.lower() in names else int(tok)


def _item_has(item, v, lo, hi, names):
    base, _, stp = item.partition("/")
    step = int(stp) if stp else 1
    if base == "*":
        a, b = lo, hi
    elif "-" in base:
        left, right = base.split("-")
        a, b = _conv(left, names), _conv(right, names)
    else:
        a = _conv(base, names)
        b = hi if stp else a
    return a <= v <= b and (v - a) % step == 0


def _field_has(text, v, lo, hi, names):
    return any(_item_has(it, v, lo, hi, names) for it in text.split(","))


def _day_match(fields, d):
    _mi, _hr, dom, mon, dow = fields
    if not _field_has(mon, d.month, 1, 12, _MON):
        return False
    wd = (d.weekday() + 1) % 7  # python Monday=0 -> cron Sunday=0
    in_dom = _field_has(dom, d.day, 1, 31, {})
    in_dow = _field_has(dow, wd, 0, 7, _DOW) or (wd == 0 and _field_has(dow, 7, 0, 7, _DOW))
    if dom[0] != "*" and dow[0] != "*":
        return in_dom or in_dow
    return in_dom and in_dow


def _hm_match(fields, t):
    return _field_has(fields[0], t.minute, 0, 59, {}) and _field_has(fields[1], t.hour, 0, 23, {})


def _oracle(expr, after, fast=True, limit_days=None):
    """First matching minute strictly after `after` with year <= after.year+8, or None.
    fast=True skips whole non-matching days; fast=False is a pure minute-by-minute stepper
    that gives up after `limit_days` days (returns None)."""
    fields = expr.split()
    t = after.replace(second=0, microsecond=0) + MIN
    end_year = after.year + 8
    if fast:
        while t.year <= end_year:
            day = t.date()
            if not _day_match(fields, day):
                t = D.combine(day + DAY, datetime.time())
                continue
            while t.date() == day:
                if _hm_match(fields, t):
                    return t
                t += MIN
        return None
    cap = t + datetime.timedelta(days=limit_days)
    cache = {}
    while t < cap and t.year <= end_year:
        if _hm_match(fields, t):
            day = t.date()
            if day not in cache:
                cache[day] = _day_match(fields, day)
            if cache[day]:
                return t
        t += MIN
    return None


def _got(m, expr, after):
    try:
        return m.next_fire(expr, after)
    except LookupError:
        return None


def _chain(m, expr, start, n):
    out, cur = [], start
    for _ in range(n):
        cur = m.next_fire(expr, cur)
        out.append(cur)
    return out


def _dts(*tuples):
    return [D(*t) for t in tuples]


# ------------------------------------------------------- random expressions

def _num(rnd, v):
    s = str(v)
    if rnd.random() < 0.1:
        s = s.zfill(rnd.choice([2, 3]))
    return s


def _atom(rnd, v, names_list):
    if names_list and rnd.random() < 0.4 and not (names_list is _DOW_LIST and v == 7):
        n = names_list[v] if names_list is _DOW_LIST else names_list[v - 1]
        return rnd.choice([n.lower(), n.upper(), n.capitalize()])
    return _num(rnd, v)


_MON_LIST = list(_MON)
_DOW_LIST = list(_DOW)
_FIELD_SPECS = [(0, 59, None), (0, 23, None), (1, 31, None), (1, 12, _MON_LIST), (0, 7, _DOW_LIST)]


def _rand_item(rnd, spec, p_star):
    lo, hi, names = spec
    kind = rnd.random()
    if kind < p_star:
        return "*"
    kind = rnd.choice(["a", "a", "a-b", "a-b/n", "*/n", "a/n"])
    if kind == "*/n":
        return "*/" + _num(rnd, rnd.choice([1, 2, 3, 4, 5, 7, 10, 15, 100]))
    a = rnd.randint(lo, hi)
    if kind == "a":
        return _atom(rnd, a, names)
    if kind == "a/n":
        return _atom(rnd, a, names) + "/" + _num(rnd, rnd.choice([1, 2, 3, 5, 7, 20]))
    b = rnd.randint(a, hi)
    s = _atom(rnd, a, names) + "-" + _atom(rnd, b, names)
    if kind == "a-b/n":
        s += "/" + _num(rnd, rnd.choice([1, 2, 3, 4, 7, 50]))
    return s


def _rand_field(rnd, spec, p_star, p_multi=0.3):
    n = 1 if rnd.random() > p_multi else rnd.choice([2, 3])
    items = [_rand_item(rnd, spec, p_star) for _ in range(n)]
    return ",".join(items)


def _ws(rnd):
    return "".join(rnd.choice(" \t") for _ in range(rnd.choice([1, 1, 1, 2, 3])))


def _join(rnd, fields):
    s = _ws(rnd).join(fields)
    if rnd.random() < 0.15:
        s = _ws(rnd) + s
    if rnd.random() < 0.15:
        s = s + _ws(rnd)
    return s


def _rand_after(rnd, y0, y1):
    t = D(rnd.randint(y0, y1), rnd.randint(1, 12), rnd.randint(1, 28),
          rnd.randint(0, 23), rnd.randint(0, 59), rnd.choice([0, 0, 0, rnd.randint(0, 59)]),
          rnd.choice([0, 0, 0, rnd.randint(0, 999999)]))
    return t


def _rand_expr(rnd, p_star=(0.5, 0.4, 0.5, 0.5, 0.5)):
    fields = [_rand_field(rnd, spec, ps) for spec, ps in zip(_FIELD_SPECS, p_star)]
    return _join(rnd, fields)


# ------------------------------------------------------------------ tests

def test_basic_rollovers_and_strictness(m):
    cases = [
        ("* * * * *", D(2024, 1, 1, 12, 0, 0), D(2024, 1, 1, 12, 1)),
        ("* * * * *", D(2024, 1, 1, 12, 0, 59, 999999), D(2024, 1, 1, 12, 1)),
        ("* * * * *", D(2024, 1, 1, 12, 0, 0, 1), D(2024, 1, 1, 12, 1)),
        ("*/15 * * * *", D(2024, 1, 1, 12, 0, 0), D(2024, 1, 1, 12, 15)),
        ("*/15 * * * *", D(2024, 1, 1, 12, 44, 59), D(2024, 1, 1, 12, 45)),
        ("*/15 * * * *", D(2024, 1, 1, 12, 45, 0), D(2024, 1, 1, 13, 0)),
        ("0 12 * * *", D(2024, 1, 1, 12, 0, 0), D(2024, 1, 2, 12, 0)),          # on a fire time
        ("0 12 * * *", D(2024, 1, 1, 11, 59, 59, 999999), D(2024, 1, 1, 12, 0)),
        ("0 12 * * *", D(2024, 1, 1, 12, 0, 0, 1), D(2024, 1, 2, 12, 0)),
        ("0 12 * * *", D(2024, 1, 1, 12, 0, 30), D(2024, 1, 2, 12, 0)),         # seconds past a fire
        ("0 * * * *", D(2024, 1, 1, 23, 30, 0), D(2024, 1, 2, 0, 0)),
        ("0 0 * * *", D(2024, 12, 31, 23, 59, 59), D(2025, 1, 1, 0, 0)),
        ("59 23 31 12 *", D(2024, 12, 31, 23, 59, 0), D(2025, 12, 31, 23, 59)),
        ("0 0 1 1 *", D(2024, 1, 1, 0, 0, 0), D(2025, 1, 1, 0, 0)),
        ("0 0 1 1 *", D(2023, 12, 31, 23, 59, 59, 500000), D(2024, 1, 1, 0, 0)),
        ("5 4 * * *", D(2024, 2, 28, 4, 5, 1), D(2024, 2, 29, 4, 5)),
        ("5 4 * * *", D(2023, 2, 28, 4, 5, 1), D(2023, 3, 1, 4, 5)),
        ("30 2 15 * *", D(2024, 11, 15, 2, 30, 0), D(2024, 12, 15, 2, 30)),
        ("0 0 1 * *", D(2024, 12, 15, 8, 0, 0), D(2025, 1, 1, 0, 0)),
        ("15 10 * * *", D(1999, 12, 31, 23, 59, 59), D(2000, 1, 1, 10, 15)),
        ("*/20 */8 * * *", D(2024, 6, 1, 16, 40, 1), D(2024, 6, 2, 0, 0)),
    ]
    for expr, after, want in cases:
        got = m.next_fire(expr, after)
        assert got == want, f"{expr!r} after {after!r}: got {got!r}, want {want!r}"
    r = m.next_fire("7 7 * * *", D(2024, 5, 5, 5, 5, 5, 5))
    assert type(r) is D and r.tzinfo is None and r.second == 0 and r.microsecond == 0
    assert r == D(2024, 5, 5, 7, 7)
    # argument not modified / repeatable
    a = D(2024, 5, 5, 5, 5, 5, 5)
    assert m.next_fire("7 7 * * *", a) == m.next_fire("7 7 * * *", a)
    assert a == D(2024, 5, 5, 5, 5, 5, 5)


def test_field_syntax_steps_and_lists(m):
    cases = [
        # minute: list mixing *, ranges, steps, a/n
        ("5,10-20/5,*/30,45/7 0 1 1 *", D(2023, 12, 31, 23, 59, 59), 10,
         _dts((2024, 1, 1, 0, 0), (2024, 1, 1, 0, 5), (2024, 1, 1, 0, 10), (2024, 1, 1, 0, 15), (2024, 1, 1, 0, 20),
              (2024, 1, 1, 0, 30), (2024, 1, 1, 0, 45), (2024, 1, 1, 0, 52), (2024, 1, 1, 0, 59), (2025, 1, 1, 0, 0))),
        ("50/5 20/2 * * *", D(2024, 1, 1, 0, 0), 5,
         _dts((2024, 1, 1, 20, 50), (2024, 1, 1, 20, 55), (2024, 1, 1, 22, 50), (2024, 1, 1, 22, 55),
              (2024, 1, 2, 20, 50))),
        ("5/20 10-20/4,23 * * *", D(2024, 3, 10, 0, 0), 13,
         [D(2024, 3, 10, h, mi) for h in (10, 14, 18, 23) for mi in (5, 25, 45)] + [D(2024, 3, 11, 10, 5)]),
        ("0-59/59 12 * * *", D(2024, 3, 10, 12, 0), 3, _dts((2024, 3, 10, 12, 59), (2024, 3, 11, 12, 0), (2024, 3, 11, 12, 59))),
        ("*/100 * * * *", D(2024, 3, 10, 12, 0), 2, _dts((2024, 3, 10, 13, 0), (2024, 3, 10, 14, 0))),
        ("0 0 */10 1 *", D(2023, 12, 31, 23, 59, 59), 5,
         _dts((2024, 1, 1), (2024, 1, 11), (2024, 1, 21), (2024, 1, 31), (2025, 1, 1))),
        ("0 0 29/2 * *", D(2024, 1, 1, 0, 0), 6,
         _dts((2024, 1, 29), (2024, 1, 31), (2024, 2, 29), (2024, 3, 29), (2024, 3, 31), (2024, 4, 29))),
        ("0 0 1 */5 *", D(2024, 1, 1, 0, 0), 3, _dts((2024, 6, 1), (2024, 11, 1), (2025, 1, 1))),
        ("0 0 1 2-4/2,12 *", D(2024, 1, 1, 0, 0), 4, _dts((2024, 2, 1), (2024, 4, 1), (2024, 12, 1), (2025, 2, 1))),
        ("0 0 1 jan-dec/3 *", D(2024, 1, 1, 0, 0), 4, _dts((2024, 4, 1), (2024, 7, 1), (2024, 10, 1), (2025, 1, 1))),
        ("7-7 7-7 7-7 7-7 *", D(2024, 7, 7, 7, 7, 0), 2, _dts((2025, 7, 7, 7, 7), (2026, 7, 7, 7, 7))),
        ("1,1,1,1-3,2 0 1 1 *", D(2023, 12, 31, 0, 0), 4, _dts((2024, 1, 1, 0, 1), (2024, 1, 1, 0, 2), (2024, 1, 1, 0, 3), (2025, 1, 1, 0, 1))),
        ("  */20\t\t3 \t 1   * *  ", D(2024, 1, 1, 0, 0), 4,
         _dts((2024, 1, 1, 3, 0), (2024, 1, 1, 3, 20), (2024, 1, 1, 3, 40), (2024, 2, 1, 3, 0))),
        ("\t0\t0 \t\t1 1\t*\t", D(2024, 1, 1, 0, 0), 1, _dts((2025, 1, 1))),
    ]
    for expr, start, n, want in cases:
        got = _chain(m, expr, start, n)
        assert got == want, f"{expr!r} from {start!r}: got {got!r}, want {want!r}"
    _check_unusual_valid_forms(m)


def _check_unusual_valid_forms(m):
    base = D(2024, 3, 10, 12, 0)
    cases = [
        ("00 00 01 01 *", D(2024, 1, 1, 0, 0), D(2025, 1, 1)),
        ("007 * * * *", base, D(2024, 3, 10, 12, 7)),
        ("0007 * * * *", base, D(2024, 3, 10, 12, 7)),
        ("0 0 001 JAN 000", D(2024, 1, 1, 0, 0), D(2024, 1, 7)),
        ("*/100 * * * *", base, D(2024, 3, 10, 13, 0)),
        ("0-0 * * * *", base, D(2024, 3, 10, 13, 0)),
        ("59-59 * * * *", base, D(2024, 3, 10, 12, 59)),
        ("0,0,0 * * * *", base, D(2024, 3, 10, 13, 0)),
        ("*,5 * * * *", base, D(2024, 3, 10, 12, 1)),
        ("*/2,3 * * * *", base, D(2024, 3, 10, 12, 2)),
        ("30,* * * * *", base, D(2024, 3, 10, 12, 1)),
        ("*/1 */1 */1 */1 */1", base, D(2024, 3, 10, 12, 1)),
        ("  \t 15 \t\t 12 \t * \t * \t * \t  ", base, D(2024, 3, 10, 12, 15)),
        ("30\t13\t*\t*\t*", base, D(2024, 3, 10, 13, 30)),
        ("30 13 * * sUn-SaT", D(2024, 3, 10, 13, 30, 0), D(2024, 3, 11, 13, 30)),
        ("0 0 31 12 7", D(2024, 1, 1), D(2024, 12, 1)),  # both restricted: OR
        ("0 0 1 JAN-DEC *", D(2024, 1, 1), D(2024, 2, 1)),
        ("0 0 1 Jan-Dec/12 *", D(2024, 1, 1), D(2025, 1, 1)),
        ("59 23 * * 0-7/7", D(2024, 3, 10, 23, 59), D(2024, 3, 17, 23, 59)),  # {0,7} = Sunday
        ("0 0 * * 1-7", D(2024, 3, 10, 0, 0), D(2024, 3, 11)),
    ]
    for expr, after, want in cases:
        got = m.next_fire(expr, after)
        assert got == want, f"{expr!r} after {after!r}: got {got!r}, want {want!r}"



def test_names_case_insensitive_and_mixed(m):
    cases = [
        ("0 0 1 JAN,mar,Dec *", D(2024, 1, 1, 0, 0), 3, _dts((2024, 3, 1), (2024, 12, 1), (2025, 1, 1))),
        ("0 0 1 oct-DEC *", D(2024, 1, 1, 0, 0), 4, _dts((2024, 10, 1), (2024, 11, 1), (2024, 12, 1), (2025, 10, 1))),
        ("0 0 1 2-mar *", D(2024, 1, 1, 0, 0), 3, _dts((2024, 2, 1), (2024, 3, 1), (2025, 2, 1))),
        ("0 0 * jun-AUG/2 *", D(2024, 6, 30, 0, 0), 2, _dts((2024, 8, 1), (2024, 8, 2))),
        ("0 9 * * Mon-Fri", D(2024, 1, 5, 9, 0, 0), 2, _dts((2024, 1, 8, 9), (2024, 1, 9, 9))),
        ("0 0 * * 1-fri", D(2024, 1, 1, 0, 0), 5, _dts((2024, 1, 2), (2024, 1, 3), (2024, 1, 4), (2024, 1, 5), (2024, 1, 8))),
        ("0 0 * * sat,SuN", D(2024, 1, 1, 0, 0), 4, _dts((2024, 1, 6), (2024, 1, 7), (2024, 1, 13), (2024, 1, 14))),
        ("0 0 * * tUe-tHu", D(2024, 1, 1, 0, 0), 4, _dts((2024, 1, 2), (2024, 1, 3), (2024, 1, 4), (2024, 1, 9))),
        ("0 0 * * MON-FRI/2", D(2024, 1, 1, 0, 0), 4, _dts((2024, 1, 3), (2024, 1, 5), (2024, 1, 8), (2024, 1, 10))),
        ("0 0 * * fri-7", D(2024, 1, 1, 0, 0), 4, _dts((2024, 1, 5), (2024, 1, 6), (2024, 1, 7), (2024, 1, 12))),
        ("0 0 * * sun-sat", D(2024, 1, 1, 0, 0), 2, _dts((2024, 1, 2), (2024, 1, 3))),
        ("0 0 * * SUN", D(2024, 1, 1, 0, 0), 2, _dts((2024, 1, 7), (2024, 1, 14))),
    ]
    for expr, start, n, want in cases:
        got = _chain(m, expr, start, n)
        assert got == want, f"{expr!r} from {start!r}: got {got!r}, want {want!r}"


def test_day_of_week_zero_and_seven_are_sunday(m):
    start = D(2024, 1, 1, 0, 0)  # a Monday
    cases = [
        ("0 0 * * 0", 3, _dts((2024, 1, 7), (2024, 1, 14), (2024, 1, 21))),
        ("0 0 * * 7", 3, _dts((2024, 1, 7), (2024, 1, 14), (2024, 1, 21))),
        ("0 0 * * 0,7", 2, _dts((2024, 1, 7), (2024, 1, 14))),
        ("0 0 * * 7-7", 2, _dts((2024, 1, 7), (2024, 1, 14))),
        ("0 0 * * 5-7", 4, _dts((2024, 1, 5), (2024, 1, 6), (2024, 1, 7), (2024, 1, 12))),
        ("0 0 * * 6-7", 3, _dts((2024, 1, 6), (2024, 1, 7), (2024, 1, 13))),
        ("0 0 * * 0-7", 3, _dts((2024, 1, 2), (2024, 1, 3), (2024, 1, 4))),
        ("0 0 * * */2", 5, _dts((2024, 1, 2), (2024, 1, 4), (2024, 1, 6), (2024, 1, 7), (2024, 1, 9))),
        ("0 0 * * 1/2", 5, _dts((2024, 1, 3), (2024, 1, 5), (2024, 1, 7), (2024, 1, 8), (2024, 1, 10))),
        ("0 0 * * 2-7/5", 4, _dts((2024, 1, 2), (2024, 1, 7), (2024, 1, 9), (2024, 1, 14))),
        ("0 0 * * 4/3", 4, _dts((2024, 1, 4), (2024, 1, 7), (2024, 1, 11), (2024, 1, 14))),
        ("0 0 * * 6/2", 2, _dts((2024, 1, 6), (2024, 1, 13))),
        ("0 0 * * 7/3", 2, _dts((2024, 1, 7), (2024, 1, 14))),
        ("0 0 * * */7", 2, _dts((2024, 1, 7), (2024, 1, 14))),
        ("0 0 * * 1,7", 4, _dts((2024, 1, 7), (2024, 1, 8), (2024, 1, 14), (2024, 1, 15))),
    ]
    for expr, n, want in cases:
        got = _chain(m, expr, start, n)
        assert got == want, f"{expr!r}: got {got!r}, want {want!r}"
    # Sunday as 7 combined with the OR rule (both fields restricted)
    got = _chain(m, "0 0 3 * 7", start, 3)
    assert got == _dts((2024, 1, 3), (2024, 1, 7), (2024, 1, 14)), got


def test_dom_dow_or_vs_and_rule(m):
    start = D(2024, 1, 1, 0, 0)  # Monday
    cases = [
        # both restricted -> OR
        ("0 12 13 * fri", 6, _dts((2024, 1, 5, 12), (2024, 1, 12, 12), (2024, 1, 13, 12), (2024, 1, 19, 12),
                                  (2024, 1, 26, 12), (2024, 2, 2, 12))),
        ("0 0 31 * mon", 6, _dts((2024, 1, 8), (2024, 1, 15), (2024, 1, 22), (2024, 1, 29), (2024, 1, 31), (2024, 2, 5))),
        ("0 0 15 2 mon", 6, _dts((2024, 2, 5), (2024, 2, 12), (2024, 2, 15), (2024, 2, 19), (2024, 2, 26), (2025, 2, 3))),
        ("0 0 30 2 sun", 5, _dts((2024, 2, 4), (2024, 2, 11), (2024, 2, 18), (2024, 2, 25), (2025, 2, 2))),
        ("0 0 1,15 * 0", 4, _dts((2024, 1, 7), (2024, 1, 14), (2024, 1, 15), (2024, 1, 21))),
        # restriction is textual: these cover every day but are still "restricted" -> OR -> every day
        ("0 0 1-31 * mon", 3, _dts((2024, 1, 2), (2024, 1, 3), (2024, 1, 4))),
        ("0 0 13 * 0-6", 3, _dts((2024, 1, 2), (2024, 1, 3), (2024, 1, 4))),
        ("0 0 13 * 0-7", 3, _dts((2024, 1, 2), (2024, 1, 3), (2024, 1, 4))),
        ("0 0 1,* * mon", 3, _dts((2024, 1, 2), (2024, 1, 3), (2024, 1, 4))),
        ("0 0 7 * mon-sat", 7, _dts((2024, 1, 2), (2024, 1, 3), (2024, 1, 4), (2024, 1, 5), (2024, 1, 6), (2024, 1, 7), (2024, 1, 8))),
        ("0 0 5 * sun-sat", 3, _dts((2024, 1, 2), (2024, 1, 3), (2024, 1, 4))),
        # a '*'-prefixed field is unrestricted even with a step or a list -> AND
        ("0 12 */2 * sat", 4, _dts((2024, 1, 13, 12), (2024, 1, 27, 12), (2024, 2, 3, 12), (2024, 2, 17, 12))),
        ("0 12 1 * */2", 3, _dts((2024, 2, 1, 12), (2024, 6, 1, 12), (2024, 8, 1, 12))),
        ("0 0 */1 * mon", 3, _dts((2024, 1, 8), (2024, 1, 15), (2024, 1, 22))),
        ("0 0 * * mon", 2, _dts((2024, 1, 8), (2024, 1, 15))),
        ("0 0 13 * *", 3, _dts((2024, 1, 13), (2024, 2, 13), (2024, 3, 13))),
        ("0 0 *,13 * mon", 2, _dts((2024, 1, 8), (2024, 1, 15))),
        ("0 0 * * *,3", 2, _dts((2024, 1, 2), (2024, 1, 3))),
        ("0 0 13 * */1", 3, _dts((2024, 1, 13), (2024, 2, 13), (2024, 3, 13))),
        ("0 0 1 * */1", 3, _dts((2024, 2, 1), (2024, 3, 1), (2024, 4, 1))),
    ]
    for expr, n, want in cases:
        got = _chain(m, expr, start, n)
        assert got == want, f"{expr!r}: got {got!r}, want {want!r}"


def test_month_lengths_and_leap_years(m):
    cases = [
        ("0 0 31 * *", D(2024, 1, 1, 0, 0), 9,
         _dts((2024, 1, 31), (2024, 3, 31), (2024, 5, 31), (2024, 7, 31), (2024, 8, 31), (2024, 10, 31), (2024, 12, 31),
              (2025, 1, 31), (2025, 3, 31))),
        ("0 0 30 * *", D(2023, 1, 1, 0, 0), 5,
         _dts((2023, 1, 30), (2023, 3, 30), (2023, 4, 30), (2023, 5, 30), (2023, 6, 30))),
        ("0 0 29 * *", D(2023, 1, 1, 0, 0), 3, _dts((2023, 1, 29), (2023, 3, 29), (2023, 4, 29))),
        ("0 0 29 * *", D(2100, 1, 30, 0, 0), 2, _dts((2100, 3, 29), (2100, 4, 29))),
        ("0 0 29 * *", D(2024, 1, 30, 0, 0), 2, _dts((2024, 2, 29), (2024, 3, 29))),
        ("0 0 29 2 *", D(2024, 3, 1, 0, 0), 1, _dts((2028, 2, 29))),
        ("0 0 29 2 *", D(2024, 2, 29, 0, 0, 0), 1, _dts((2028, 2, 29))),
        ("0 0 29 2 *", D(2096, 3, 1, 0, 0), 1, _dts((2104, 2, 29))),
        ("0 0 29 2 *", D(2096, 2, 29, 0, 0, 0), 1, _dts((2104, 2, 29))),
        ("0 0 29 2 *", D(2099, 1, 1, 0, 0), 2, _dts((2104, 2, 29), (2108, 2, 29))),
        ("0 0 29 2 *", D(1896, 3, 1, 0, 0), 1, _dts((1904, 2, 29))),
        ("0 0 29 2 *", D(1999, 3, 1, 0, 0), 2, _dts((2000, 2, 29), (2004, 2, 29))),
        ("0 0 29 2 *", D(2000, 3, 1, 0, 0), 1, _dts((2004, 2, 29))),
        ("0 0 29 2 *", D(2197, 1, 1, 0, 0), 1, _dts((2204, 2, 29))),
        ("59 23 28-31 2 *", D(2100, 2, 1, 0, 0), 2, _dts((2100, 2, 28, 23, 59), (2101, 2, 28, 23, 59))),
        ("59 23 28-31 2 *", D(2104, 2, 1, 0, 0), 3, _dts((2104, 2, 28, 23, 59), (2104, 2, 29, 23, 59), (2105, 2, 28, 23, 59))),
        ("0 0 * * *", D(2024, 2, 29, 0, 0, 0), 1, _dts((2024, 3, 1))),
        ("0 0 * * *", D(2100, 2, 28, 12, 0), 1, _dts((2100, 3, 1))),
        ("0 0 * * *", D(2000, 2, 28, 12, 0), 2, _dts((2000, 2, 29), (2000, 3, 1))),
        ("0 0 * * *", D(1900, 2, 28, 12, 0), 1, _dts((1900, 3, 1))),
        ("30 6 31 1,3 *", D(2024, 3, 31, 6, 30, 1), 2, _dts((2025, 1, 31, 6, 30), (2025, 3, 31, 6, 30))),
        ("0 0 * 2 *", D(2023, 2, 27, 12, 0), 3, _dts((2023, 2, 28), (2024, 2, 1), (2024, 2, 2))),
    ]
    for expr, start, n, want in cases:
        got = _chain(m, expr, start, n)
        assert got == want, f"{expr!r} from {start!r}: got {got!r}, want {want!r}"


def test_search_horizon_and_lookup_error(m):
    def raises_lookup(expr, after):
        try:
            r = m.next_fire(expr, after)
        except LookupError:
            return
        except Exception as e:
            raise AssertionError(f"{expr!r} after {after!r}: raised {type(e).__name__}, expected LookupError")
        raise AssertionError(f"{expr!r} after {after!r}: returned {r!r}, expected LookupError")

    for expr in ["0 0 30 2 *", "59 23 31 2 *", "0 0 31 4 *", "0 0 31 4,6,9,11 *", "* * 30-31 2 *", "0 0 31 feb,apr,jun,sep,nov *"]:
        for after in [D(2096, 3, 1, 5, 5, 5), D(2999, 12, 31, 23, 59, 59)]:
            raises_lookup(expr, after)
    # dom 30 in February is fine when the OR rule rescues it through day-of-week
    assert m.next_fire("0 0 30 2 sun", D(2024, 1, 1)) == D(2024, 2, 4)
    # but not when day-of-week is unrestricted (AND): Feb 29 on a Sunday: 2004, 2032, 2060
    assert m.next_fire("0 0 29 2 */7", D(2025, 1, 1)) == D(2032, 2, 29)
    raises_lookup("0 0 29 2 */7", D(2020, 1, 1))
    # Jan 1 on a Sunday: 2023 and 2034 (gap of 11 years).  Horizon is a calendar-year bound.
    assert m.next_fire("0 0 1 1 */7", D(2026, 1, 1, 0, 0, 0)) == D(2034, 1, 1)
    assert m.next_fire("0 0 1 1 */7", D(2026, 12, 31, 23, 59, 59)) == D(2034, 1, 1)
    raises_lookup("0 0 1 1 */7", D(2025, 12, 31, 23, 59, 59))
    raises_lookup("0 0 1 1 */7", D(2025, 6, 1))
    raises_lookup("0 0 1 1 */7", D(2023, 1, 1, 0, 0, 0))   # on the fire time itself: next is 2034
    # invalid expressions win over LookupError and are detected even when the search is trivial
    for bad in ["0 0 32 2 *", "60 0 30 2 *", "0 0 30 13 *", "0 0 30 2 8", "0 0 30 2 * *"]:
        try:
            m.next_fire(bad, D(2024, 1, 1))
        except ValueError:
            pass
        except Exception as e:
            raise AssertionError(f"{bad!r}: raised {type(e).__name__}, expected ValueError")
        else:
            raise AssertionError(f"{bad!r}: did not raise")


def _expect_value_error(m, exprs):
    bad = []
    for e in exprs:
        try:
            r = m.next_fire(e, D(2024, 1, 1))
            bad.append(f"{e!r} -> returned {r!r}")
        except ValueError:
            pass
        except Exception as ex:
            bad.append(f"{e!r} -> {type(ex).__name__}")
    assert not bad, "expected ValueError: " + "; ".join(bad[:6])


def test_invalid_structure_ranges_and_steps(m):
    _expect_value_error(m, [
        "", "   ", "\t", "* * * *", "* * * * * *", "* * * * * * *", "@daily", "@hourly", "@yearly", "reboot",
        "*", "0 0 * *",
        "* * * * *\n", "\n* * * * *", "* * * * *\r", "*\t* * * *\r", "* * * * *\x0b", "* * * * *\x0c",
        "* * * * *", "* * * * * *", "* * * * * ", "* *\n* * *",
        "1,,2 * * * *", "1, * * * *", ",1 * * * *", "* * * * 1,", ",", "* * * * ,*", "* 1,,2 * * *", "* * 1,,2 * *",
        "* * * 1,,2 *", ",* * * * *", "*,,* * * * *",
        "60 * * * *", "* 24 * * *", "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *", "* * * * 8",
        "0-60 * * * *", "* 5-24 * * *", "* * 0-5 * *", "* * 5-32 * *", "* * * 1-13 *", "* * * 0-5 *", "* * * * 0-8",
        "60/5 * * * *", "* 24/2 * * *", "* * 0/2 * *", "* * 32/2 * *", "* * * 13/2 *", "* * * 0/2 *", "* * * * 8/2",
        "100000000000000000000 * * * *", "* * * * 99", "99 * * * *", "* 60 * * *",
        "5-3 * * * *", "* 23-0 * * *", "* * 31-1 * *", "* * * 12-1 *", "* * * * 6-0", "* * * * 7-0", "* * * * 7-6",
        "* * * * sat-sun", "* * * * FRI-SUN", "* * * * mon-sun", "* * * dec-jan *", "* * * * 5-mon", "* * * mar-feb *",
        "*/0 * * * *", "1-5/0 * * * *", "5/0 * * * *", "* */0 * * *", "* * */0 * *", "* * * */0 *", "* * * * */0",
        "* * * jan-dec/0 *", "* * * * mon-fri/0", "*/00 * * * *",
        "*/ * * * *", "*/-1 * * * *", "*/+2 * * * *", "*/1.5 * * * *", "1/2/3 * * * *", "*/2/3 * * * *",
        "* * * * */mon", "* * * */jan *", "5/ * * * *", "1-5/ * * * *", "*/2- * * * *", "*/*", "*/* * * * *",
        "1-2-3 * * * *", "-5 * * * *", "5- * * * *", "*-5 * * * *", "5-* * * * *", "*5 * * * *", "5* * * * *",
        "/5 * * * *", "** * * * *", "1--3 * * * *", "1-/2 * * * *", "- * * * *", "-/2 * * * *", "* * * * mon-",
        "*/2-3 * * * *", "1/2-3 * * * *", "1-3-5/2 * * * *", "*,*/ * * * *", "*/2,/3 * * * *",
    ])


def test_invalid_number_tokens_names_and_chars(m):
    _expect_value_error(m, [
        "1_0 * * * *", "* 1_0 * * *", "* * 1_5 * *", "* * * 1_0 *", "5_ * * * *", "_5 * * * *", "*/1_0 * * * *",
        "+5 * * * *", "* +5 * * *", "* * +5 * *", "* * * +5 *", "* * * * +5", "-0 * * * *", "1-+2 * * * *",
        "٣ * * * *", "* * * * ٣", "* ٥ * * *", "５ * * * *", "* １２ * * *",
        "*/１ * * * *", "1-٣ * * * *", "০ * * * *", "² * * * *", "* * ١ * *", "* * * ١ *",
        "5.0 * * * *", "5. * * * *", ".5 * * * *", "1e1 * * * *", "0x10 * * * *", "0b1 * * * *", "1.0-2 * * * *",
        "* * * * monday", "* * * * mo", "* * * * MONDAY", "* * * * sunday", "* * * * s", "* * * jan1 *", "* * * * mon1",
        "* * * * 1mon", "* * * foo *", "* * * * foo", "* * * janu *", "* * * ja *", "* * * january *", "* * * * m-f",
        "* * * * mon-fr", "* * * * mon,tues", "* * * sept *", "* * * * thur", "* * * * thurs",
        "mon * * * *", "* jan * * *", "* * jan * *", "* * mon * *", "* * * mon *", "* * * * jan", "* * * sun *",
        "* * * * dec", "jan-mar * * * *", "* mon-fri * * *", "* * mon-fri * *", "* * * mon-fri *", "* * * * jan-mar",
        "* * * * mon/2/1", "* * * * mon-fri/mon",
        "* * * * frı", "* * * * ſun", "* * * ſep *", "* * * * ＭＯＮ",
        "? * * * *", "* ? * * *", "* * ? * *", "* * * ? *", "* * * * ?", "* * L * *", "* * 1W * *", "* * L-3 * *",
        "* * * * 1#2", "* * * * 5L", "* * * * L", "H * * * *", "%5 * * * *", "(1) * * * *", "1;2 * * * *",
        "1.2.3 * * * *", "$ * * * *", "* * * * mon.", "'5' * * * *", "5– * * * *", "1–5 * * * *",
        "1:2 * * * *", "1 2 * * * *,",
    ])


# --- validity fuzz against an independent regex checker -------------------

def _valid_field(text, lo, hi, names):
    atom = "[0-9]+" + ("|" + "|".join(names) if names else "")
    item = rf"(?:\*|(?:{atom})(?:-(?:{atom}))?)(?:/[0-9]+)?"
    if not re.fullmatch(rf"{item}(?:,{item})*", text, re.I | re.A):
        return False
    table = {n: (i + 1 if names is _MON_LIST else i) for i, n in enumerate(names or [])}

    def val(tok):
        return int(tok) if tok[0].isdigit() else table[tok.lower()]

    for it in text.split(","):
        base, slash, stp = it.partition("/")
        if slash and int(stp) < 1:
            return False
        if base == "*":
            continue
        parts = base.split("-")
        vals = [val(p) for p in parts]
        if any(not lo <= v <= hi for v in vals):
            return False
        if len(vals) == 2 and vals[0] > vals[1]:
            return False
    return True


def test_validation_fuzz_against_independent_checker(m):
    rnd = random.Random(20260714)
    pieces = ["*", "*", "/", "-", ",", "0", "1", "5", "7", "12", "23", "31", "59", "60", "24", "32", "13", "8", "00",
              "mon", "Fri", "JAN", "dec", "sun", "x", "_", "+", ".", "?", "L", "٣", "mo", "monday"]
    nums = [0, 1, 2, 5, 7, 8, 12, 13, 23, 24, 31, 32, 59, 60]
    wordy = ["mon", "FRI", "Sun", "sat", "jan", "Dec", "Mar"]

    def tok():
        return rnd.choice([str(rnd.choice(nums)), str(rnd.choice(nums)), rnd.choice(wordy)])

    def structured():
        t = rnd.choice(["{a}", "{a}-{b}", "*/{a}", "{a}/{b}", "{a}-{b}/{c}", "*", "*/{a}"])
        return t.format(a=tok(), b=tok(), c=str(rnd.choice([0, 1, 2, 3, 7, 60])))

    def candidate():
        r = rnd.random()
        if r < 0.35:
            return "".join(rnd.choice(pieces) for _ in range(rnd.randint(1, 5)))
        s = ",".join(structured() for _ in range(rnd.choice([1, 1, 2, 3])))
        if r > 0.85 and s:
            i = rnd.randrange(len(s))
            s = rnd.choice([s[:i] + s[i + 1:], s[:i] + rnd.choice(",-/*x") + s[i:]])
        return s

    n_valid = n_invalid = 0
    for k, spec in enumerate(_FIELD_SPECS):
        for _ in range(260):
            text = candidate()
            ok = _valid_field(text, *spec)
            fields = ["*"] * 5
            fields[k] = text
            expr = " ".join(fields)
            try:
                got = m.next_fire(expr, D(2024, 1, 1, 0, 0, 30))
            except ValueError:
                got = "VE"
            if ok:
                n_valid += 1
                want = _oracle(expr, D(2024, 1, 1, 0, 0, 30))
                assert got == want, f"field {k} {text!r}: got {got!r}, want {want!r}"
            else:
                n_invalid += 1
                assert got == "VE", f"field {k} {text!r} should be invalid but got {got!r}"
    assert n_valid > 150 and n_invalid > 150, (n_valid, n_invalid)


# --- randomized differential tests against the brute-force oracle ---------

def _random_expressions_vs_oracle(m):
    rnd = random.Random(1234567)
    for i in range(350):
        expr = _rand_expr(rnd)
        after = _rand_after(rnd, 1990, 2150)
        want = _oracle(expr, after)
        got = _got(m, expr, after)
        assert got == want, f"case {i}: {expr!r} after {after!r}: got {got!r}, want {want!r}"


def test_random_day_logic_across_centuries_vs_oracle(m):
    rnd = random.Random(98765)
    bases = [(1895, 1905), (1995, 2005), (2095, 2105), (2395, 2405)]
    for i in range(300):
        y0, y1 = rnd.choice(bases)
        fields = [
            rnd.choice(["0", "30", "*/20", "15,45"]),
            rnd.choice(["0", "12", "23", "*/6"]),
            _rand_field(rnd, _FIELD_SPECS[2], 0.3, 0.5),
            _rand_field(rnd, _FIELD_SPECS[3], 0.5, 0.3),
            _rand_field(rnd, _FIELD_SPECS[4], 0.3, 0.4),
        ]
        expr = _join(rnd, fields)
        after = _rand_after(rnd, y0, y1)
        want = _oracle(expr, after)
        got = _got(m, expr, after)
        assert got == want, f"case {i}: {expr!r} after {after!r}: got {got!r}, want {want!r}"


def _pure_minute_stepper_dense_expressions(m):
    rnd = random.Random(555)
    limit_days = 2
    checked = 0
    for i in range(70):
        fields = [
            _rand_field(rnd, _FIELD_SPECS[0], 0.3, 0.5),
            _rand_field(rnd, _FIELD_SPECS[1], 0.4, 0.4),
            rnd.choice(["*", "*", "*/2", "1-20", "15", "*"]),
            rnd.choice(["*", "*", "*", "1-6", "jan-dec/2", "*/3"]),
            rnd.choice(["*", "*", "mon-fri", "*/2", "0", "6,7", "3"]),
        ]
        expr = _join(rnd, fields)
        after = _rand_after(rnd, 2020, 2030)
        want = _oracle(expr, after, fast=False, limit_days=limit_days)
        got = _got(m, expr, after)
        if want is not None:
            assert got == want, f"case {i}: {expr!r} after {after!r}: got {got!r}, want {want!r}"
            checked += 1
        else:
            cap = after.replace(second=0, microsecond=0) + MIN + datetime.timedelta(days=limit_days)
            assert got is None or got >= cap, f"case {i}: {expr!r} after {after!r}: got {got!r} before {cap!r}"
    assert checked > 25, checked


def _consecutive_fire_chains_match_oracle(m):
    exprs = [
        ("*/7 */5 * * *", D(2024, 2, 27, 3, 3, 3)),
        ("13,47 6-8 * * mon-fri", D(2024, 12, 25, 0, 0, 0)),
        ("0 0 31 * *", D(2023, 6, 1)),
        ("30 4 1,15 * fri", D(2024, 1, 1)),
        ("0 12 */3 */4 sun,wed", D(2099, 1, 1)),
        ("59 23 * 2 *", D(2099, 12, 31, 12, 0)),
        ("1 1 29-31 * 1-5", D(2023, 12, 1)),
    ]
    for expr, start in exprs:
        cur = start
        for i in range(160):
            want = _oracle(expr, cur)
            got = m.next_fire(expr, cur)
            assert got == want, f"{expr!r} step {i} after {cur!r}: got {got!r}, want {want!r}"
            assert got > cur
            cur = got


def test_random_expressions_and_chains_vs_oracle(m):
    _random_expressions_vs_oracle(m)
    _pure_minute_stepper_dense_expressions(m)
    _consecutive_fire_chains_match_oracle(m)


def test_performance_sparse_expressions(m):
    # Each query below needs the search to look 4-8 years ahead.  A per-minute stepper costs
    # roughly 2-4 million iterations per query (> 20 s for the whole test on this machine);
    # a field-skipping solution answers all ~120 queries in well under a second.
    import calendar
    assert m.next_fire("0 0 29 2 *", D(2096, 3, 1)) == D(2104, 2, 29)
    assert m.next_fire("30 3 29 2 *", D(2096, 2, 29, 3, 30, 0)) == D(2104, 2, 29, 3, 30)
    assert m.next_fire("59 23 1 1 */7", D(2026, 1, 1, 0, 0, 0)) == D(2034, 1, 1, 23, 59)
    rnd = random.Random(31337)
    for _ in range(60):  # Feb 29 every 4 (or 8) years
        y = rnd.choice([yy for yy in range(1904, 2100) if calendar.isleap(yy)])
        hh, mm = rnd.randint(0, 23), rnd.randint(0, 59)
        expr = f"{mm} {hh} 29 2 *"
        ny = y + 4
        while not calendar.isleap(ny):
            ny += 1
        after = rnd.choice([D(y, 3, 1), D(y, 2, 29, hh, mm, 0), D(y, 2, 29, hh, mm, 59), D(y, 2, 29, 23, 59, 59, 999999)])
        got = m.next_fire(expr, after)
        assert got == D(ny, 2, 29, hh, mm), f"{expr!r} after {after!r}: got {got!r}"
    never = ["{m} {h} 30 2 *", "{m} {h} 31 4,6,9,11 *", "{m} {h} 30-31 feb *", "{m} {h} 31 2,4 */1"]
    for _ in range(60):  # LookupError only after scanning the whole horizon
        expr = rnd.choice(never).format(m=rnd.randint(0, 59), h=rnd.randint(0, 23))
        after = D(rnd.randint(1950, 2200), rnd.randint(1, 12), rnd.randint(1, 28), rnd.randint(0, 23), rnd.randint(0, 59))
        try:
            r = m.next_fire(expr, after)
        except LookupError:
            continue
        raise AssertionError(f"{expr!r} after {after!r}: expected LookupError, got {r!r}")
    # and many ordinary queries stay cheap
    cur = D(2024, 1, 1)
    for _ in range(3000):
        cur = m.next_fire("*/13 */5 * * 1-5", cur)
    assert cur.year >= 2024


TESTS = [
    test_basic_rollovers_and_strictness, test_field_syntax_steps_and_lists, test_names_case_insensitive_and_mixed,
    test_day_of_week_zero_and_seven_are_sunday, test_dom_dow_or_vs_and_rule, test_month_lengths_and_leap_years,
    test_search_horizon_and_lookup_error, test_invalid_structure_ranges_and_steps,
    test_invalid_number_tokens_names_and_chars, test_validation_fuzz_against_independent_checker,
    test_random_expressions_and_chains_vs_oracle, test_random_day_logic_across_centuries_vs_oracle,
    test_performance_sparse_expressions,
]
