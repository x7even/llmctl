"""Hidden tests for date_math. Each test takes the loaded solution module `m`.

Oracles (none of them is the reference solution):
  * datetime.date (toordinal / fromordinal / weekday / isocalendar / fromisocalendar /
    isoformat / timetuple().tm_yday) for is_leap, days_in_month, ordinals, weekdays, ISO weeks,
    add_days and the accepted/printed ISO 8601 string forms.
  * a brute-force month-stepping oracle written below (step one month at a time from the
    ORIGINAL day, clamp with datetime by decrementing the day until valid) for add_months,
    and for diff (largest K with shift(a,K) <= b found by scanning the stepped series).
  * hand-written literal expectations for the rules that have no stdlib equivalent.
"""
import ast
import bisect
import datetime
import random

D = datetime.date
MAXORD = 3652059
BAD_MODULES = {"datetime", "calendar", "time", "dateutil", "email"}


def _raises(exc, fn):
    try:
        fn()
    except exc:
        return
    except Exception as e:
        raise AssertionError(f"raised {type(e).__name__}: {e}; expected {exc.__name__}")
    raise AssertionError(f"did not raise {exc.__name__}")


def _is_date(t):
    return type(t) is tuple and len(t) == 3 and all(type(v) is int for v in t)


def _tup(d):
    return (d.year, d.month, d.day)


# ---------------------------------------------------------------- brute-force oracle
def month_series(date, kmin, kmax):
    """{k: shifted date or None if year out of range}, by stepping one month at a time from the
    original day and clamping (decrement the day until datetime accepts it)."""
    y0, m0, d0 = date
    out = {}
    for sign, rng in ((1, range(0, kmax + 1)), (-1, range(0, -kmin + 1))):
        y, m = y0, m0
        for i in rng:
            if i:
                m += sign
                if m == 13:
                    y, m = y + 1, 1
                elif m == 0:
                    y, m = y - 1, 12
            k = sign * i
            if not 1 <= y <= 9999:
                out[k] = None
                continue
            dd = d0
            while True:
                try:
                    out[k] = D(y, m, dd)
                    break
                except ValueError:
                    dd -= 1
    return out


def oracle_diff(a, b):
    """a <= b (tuples). Returns (years, months, days) by scanning the stepped series."""
    da, db = D(*a), D(*b)
    kmax = (b[0] - a[0]) * 12 + (b[1] - a[1]) + 2
    ser = month_series(a, 0, kmax)
    seq = [ser[k] for k in range(kmax + 1)]
    assert all(x is not None for x in seq)
    K = bisect.bisect_right(seq, db) - 1
    return (K // 12, K % 12, (db - seq[K]).days)


# ---------------------------------------------------------------- tests
def test_no_forbidden_imports(m):
    for name in ("is_leap", "days_in_month", "to_ordinal", "from_ordinal", "weekday", "add_days", "add_months",
                 "iso_weeks_in_year", "iso_week", "from_iso_week", "parse", "format_date", "diff"):
        assert callable(getattr(m, name, None)), f"missing public function {name}"
    src = open(m.__file__).read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in BAD_MODULES, f"imports {a.name}"
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in BAD_MODULES, f"imports from {node.module}"
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in ("datetime", "dateutil", "email.utils", "importlib", "__import__"), \
                f"dynamic import string {node.value!r}"
    for name in BAD_MODULES:
        assert not hasattr(m, name), f"module exposes {name}"


def test_leap_and_month_lengths(m):
    for y in range(1, 10000):
        try:
            D(y, 2, 29)
            want = True
        except ValueError:
            want = False
        got = m.is_leap(y)
        assert got is want, f"is_leap({y}) = {got!r}"
    for y in (1700, 1800, 1900, 2100, 2200, 2300):
        assert m.is_leap(y) is False and m.days_in_month(y, 2) == 28
    for y in (1600, 2000, 2400, 4, 8, 2024):
        assert m.is_leap(y) is True and m.days_in_month(y, 2) == 29
    for y in range(1, 10000, 1):
        for mo in range(1, 13):
            nxt = D(y + 1, 1, 1) if mo == 12 and y < 9999 else (D(y, mo + 1, 1) if mo < 12 else None)
            want = (nxt - D(y, mo, 1)).days if nxt else 31
            got = m.days_in_month(y, mo)
            assert got == want and type(got) is int, f"days_in_month({y},{mo}) = {got!r}, want {want}"


def test_ordinal_weekday(m):
    lo, hi = D(1600, 1, 1).toordinal(), D(2101, 1, 1).toordinal()
    for o in range(lo, hi):
        dt = D.fromordinal(o)
        t = (dt.year, dt.month, dt.day)
        assert m.to_ordinal(*t) == o, f"to_ordinal{t}"
        assert m.from_ordinal(o) == t, f"from_ordinal({o})"
        assert m.weekday(*t) == dt.weekday(), f"weekday{t}"
    rnd = random.Random(1234)
    for _ in range(20000):
        o = rnd.randint(1, MAXORD)
        dt = D.fromordinal(o)
        t = (dt.year, dt.month, dt.day)
        r = m.from_ordinal(o)
        assert r == t and _is_date(r), f"from_ordinal({o}) = {r}"
        assert m.to_ordinal(*t) == o and m.weekday(*t) == dt.weekday(), f"mismatch at {t}"
    assert m.to_ordinal(1, 1, 1) == 1 and m.to_ordinal(9999, 12, 31) == MAXORD
    assert m.from_ordinal(1) == (1, 1, 1) and m.from_ordinal(MAXORD) == (9999, 12, 31)
    assert m.weekday(1, 1, 1) == 0 and m.weekday(9999, 12, 31) == D(9999, 12, 31).weekday() == 4
    # century / cycle edges
    for y in (1, 4, 100, 399, 400, 401, 1600, 1700, 1800, 1900, 2000, 2100, 2400, 9996, 9999):
        for mo, d in ((1, 1), (2, 28), (3, 1), (12, 31)):
            dt = D(y, mo, d)
            assert m.to_ordinal(y, mo, d) == dt.toordinal() and m.from_ordinal(dt.toordinal()) == (y, mo, d)
    assert m.from_ordinal(m.to_ordinal(2000, 2, 29)) == (2000, 2, 29)
    assert m.from_ordinal(m.to_ordinal(1900, 2, 28) + 1) == (1900, 3, 1)


def test_iso_week_vs_stdlib(m):
    def check(dt):
        iy, w, wd = dt.isocalendar()
        got = m.iso_week(dt.year, dt.month, dt.day)
        assert got == (iy, w, wd) and _is_date(got), f"iso_week{_tup(dt)} = {got}, want {(iy, w, wd)}"
        assert m.from_iso_week(iy, w, wd) == _tup(dt), f"from_iso_week{(iy, w, wd)}"

    lo, hi = D(1950, 1, 1).toordinal(), D(2051, 1, 1).toordinal()
    for o in range(lo, hi):
        check(D.fromordinal(o))
    for y in (2004, 2009, 2015, 2020, 2026, 2032, 1998, 1992, 2015, 2021, 2027):  # 53-week and neighbours
        for o in range(D(y, 12, 20).toordinal(), D(y + 1, 1, 12).toordinal()):
            check(D.fromordinal(o))
    rnd = random.Random(99)
    for _ in range(300):
        y = rnd.randint(1, 9998)
        for o in range(D(y, 12, 24).toordinal(), D(y + 1, 1, 9).toordinal()):
            check(D.fromordinal(o))
    for _ in range(5000):
        check(D.fromordinal(rnd.randint(1, MAXORD)))
    # first / last days of the supported range and the year-boundary examples in the spec
    assert m.iso_week(1, 1, 1) == (1, 1, 1)
    assert m.iso_week(9999, 12, 31) == (9999, 52, 5)
    assert m.iso_week(2024, 12, 30) == (2025, 1, 1)
    assert m.iso_week(2021, 1, 3) == (2020, 53, 7)
    assert m.iso_week(2027, 1, 1) == (2026, 53, 5)
    assert m.iso_week(2020, 12, 31) == (2020, 53, 4)
    assert m.iso_week(2012, 1, 1) == (2011, 52, 7)
    assert m.iso_week(2008, 12, 29) == (2009, 1, 1)


def test_from_iso_week_rules(m):
    w53 = []
    for y in range(1, 10000):
        want = D(y, 12, 28).isocalendar()[1]
        assert want in (52, 53)
        got = m.iso_weeks_in_year(y)
        assert got == want and type(got) is int, f"iso_weeks_in_year({y}) = {got}"
        if want == 53:
            w53.append(y)
        # stdlib agrees about validity of week 53
        if want == 52:
            _raises(ValueError, lambda: m.from_iso_week(y, 53, 1))
            _raises(ValueError, lambda: D.fromisocalendar(y, 53, 1))
        elif y < 9999:
            assert m.from_iso_week(y, 53, 7) == _tup(D.fromisocalendar(y, 53, 7))
    for y in (2004, 2009, 2015, 2020, 2026, 1981, 1987, 1992, 1998, 2032, 2037, 2043):
        assert y in w53, y
    assert 2024 not in w53 and 2025 not in w53 and 2000 not in w53 and 1900 not in w53
    rnd = random.Random(7)
    for _ in range(4000):
        y = rnd.randint(1, 9998)
        w = rnd.randint(1, m.iso_weeks_in_year(y))
        wd = rnd.randint(1, 7)
        got = m.from_iso_week(y, w, wd)
        assert got == _tup(D.fromisocalendar(y, w, wd)) and _is_date(got), f"from_iso_week{(y, w, wd)} = {got}"
    assert m.from_iso_week(1, 1, 1) == (1, 1, 1)
    assert m.from_iso_week(9999, 52, 5) == (9999, 12, 31)
    assert m.from_iso_week(2025, 1, 1) == (2024, 12, 30)
    assert m.from_iso_week(2026, 53, 5) == (2027, 1, 1)
    assert m.from_iso_week(2020, 53, 7) == (2021, 1, 3)
    for y in (0, -1, 10000, 12345):
        _raises(ValueError, lambda: m.from_iso_week(y, 1, 1))
        _raises(ValueError, lambda: m.iso_weeks_in_year(y))
    for w in (0, -1, 54, 99):
        _raises(ValueError, lambda: m.from_iso_week(2020, w, 1))
    for wd in (0, 8, -1, 100):
        _raises(ValueError, lambda: m.from_iso_week(2020, 10, wd))
    _raises(ValueError, lambda: m.from_iso_week(2024, 53, 1))  # 52-week year
    _raises(ValueError, lambda: m.from_iso_week(9999, 53, 1))  # 52-week year, ValueError wins over range
    _raises(OverflowError, lambda: m.from_iso_week(9999, 52, 6))
    _raises(OverflowError, lambda: m.from_iso_week(9999, 52, 7))


def test_add_days(m):
    rnd = random.Random(2024)
    for _ in range(20000):
        o = rnd.randint(1, MAXORD)
        mag = rnd.choice((10, 400, 40000, 4000000))
        n = rnd.randint(-mag, mag)
        dt = D.fromordinal(o)
        got_in = _tup(dt)
        if 1 <= o + n <= MAXORD:
            want = _tup(D.fromordinal(o + n))
            got = m.add_days(got_in, n)
            assert got == want and _is_date(got), f"add_days({got_in},{n}) = {got}, want {want}"
        else:
            _raises(OverflowError, lambda: m.add_days(got_in, n))
    assert m.add_days((2024, 2, 28), 1) == (2024, 2, 29)
    assert m.add_days((2023, 2, 28), 1) == (2023, 3, 1)
    assert m.add_days((1900, 2, 28), 1) == (1900, 3, 1)
    assert m.add_days((2000, 2, 28), 2) == (2000, 3, 1)
    assert m.add_days((2024, 12, 31), 1) == (2025, 1, 1)
    assert m.add_days((2024, 3, 1), -1) == (2024, 2, 29)
    assert m.add_days((2024, 5, 17), 0) == (2024, 5, 17)
    assert m.add_days((1, 1, 1), MAXORD - 1) == (9999, 12, 31)
    assert m.add_days((9999, 12, 31), -(MAXORD - 1)) == (1, 1, 1)
    assert m.add_days((9999, 12, 31), 0) == (9999, 12, 31)
    assert m.add_days((1, 1, 1), 0) == (1, 1, 1)
    _raises(OverflowError, lambda: m.add_days((9999, 12, 31), 1))
    _raises(OverflowError, lambda: m.add_days((1, 1, 1), -1))
    _raises(OverflowError, lambda: m.add_days((1, 1, 1), MAXORD))
    _raises(OverflowError, lambda: m.add_days((2000, 1, 1), 10 ** 15))
    _raises(OverflowError, lambda: m.add_days((2000, 1, 1), -10 ** 15))
    _raises(OverflowError, lambda: m.add_days((2000, 1, 1), 10 ** 40))


def test_add_months_oracle(m):
    # every start day in a window that crosses Jan 31 / Feb 29 / Mar 31 / Dec 31 boundaries
    for o in range(D(2023, 12, 20).toordinal(), D(2024, 3, 8).toordinal()):
        a = _tup(D.fromordinal(o))
        ser = month_series(a, -300, 300)
        for n in range(-300, 301):
            want = ser[n]
            if want is None:
                _raises(OverflowError, lambda: m.add_months(a, n))
            else:
                got = m.add_months(a, n)
                assert got == _tup(want) and _is_date(got), f"add_months({a},{n}) = {got}, want {_tup(want)}"
    rnd = random.Random(5150)
    for _ in range(80):
        a = _tup(D.fromordinal(rnd.randint(1, MAXORD)))
        n = rnd.randint(-1500, 1500)
        want = month_series(a, min(n, 0), max(n, 0))[n]
        if want is None:
            _raises(OverflowError, lambda: m.add_months(a, n))
        else:
            assert m.add_months(a, n) == _tup(want), f"add_months({a},{n})"
    # range edges: every month-end start next to year 1 and year 9999
    for a in ((1, 1, 31), (1, 3, 31), (9999, 12, 31), (9999, 10, 31), (9999, 1, 31), (1, 1, 1), (9999, 12, 1)):
        ser = month_series(a, -30, 30)
        for n in range(-30, 31):
            if ser[n] is None:
                _raises(OverflowError, lambda: m.add_months(a, n))
            else:
                assert m.add_months(a, n) == _tup(ser[n]), f"add_months({a},{n})"
    # the clamp is applied once: two single steps differ from one double step
    assert m.add_months((2024, 1, 31), 1) == (2024, 2, 29)
    assert m.add_months((2024, 1, 31), 2) == (2024, 3, 31)
    assert m.add_months(m.add_months((2023, 1, 31), 1), 1) == (2023, 3, 28)
    assert m.add_months((2023, 1, 31), 2) == (2023, 3, 31)
    assert m.add_months((2023, 1, 31), 13) == (2024, 2, 29)
    assert m.add_months((2024, 3, 31), -1) == (2024, 2, 29)
    assert m.add_months((2024, 3, 31), -13) == (2023, 2, 28)
    assert m.add_months((2024, 2, 29), 12) == (2025, 2, 28)
    assert m.add_months((2024, 2, 29), 48) == (2028, 2, 29)
    assert m.add_months((2024, 2, 29), -12) == (2023, 2, 28)
    assert m.add_months((2024, 5, 31), 0) == (2024, 5, 31)
    assert m.add_months((2024, 11, 30), 3) == (2025, 2, 28)
    assert m.add_months((2024, 12, 15), 1) == (2025, 1, 15)
    assert m.add_months((2024, 1, 15), -1) == (2023, 12, 15)
    assert m.add_months((2024, 1, 15), -13) == (2022, 12, 15)
    assert m.add_months((9999, 11, 30), 1) == (9999, 12, 30)
    assert m.add_months((9999, 1, 31), 11) == (9999, 12, 31)
    assert m.add_months((1, 2, 28), -1) == (1, 1, 28)
    _raises(OverflowError, lambda: m.add_months((9999, 12, 1), 1))
    _raises(OverflowError, lambda: m.add_months((1, 1, 31), -1))
    _raises(OverflowError, lambda: m.add_months((2000, 1, 1), 10 ** 12))
    _raises(OverflowError, lambda: m.add_months((2000, 1, 1), -10 ** 12))
    _raises(OverflowError, lambda: m.add_months((2000, 1, 1), 12 * 8000))


def _all_forms(dt):
    y = dt.year
    yday = dt.timetuple().tm_yday
    iy, w, wd = dt.isocalendar()
    return [
        f"{y:04d}-{dt.month:02d}-{dt.day:02d}", f"{y:04d}{dt.month:02d}{dt.day:02d}",
        f"{y:04d}-{yday:03d}", f"{y:04d}{yday:03d}",
        f"{iy:04d}-W{w:02d}-{wd}", f"{iy:04d}W{w:02d}{wd}",
    ]


def test_parse_accepts(m):
    for o in range(D(1996, 1, 1).toordinal(), D(2031, 1, 1).toordinal()):
        dt = D.fromordinal(o)
        t = _tup(dt)
        for s in _all_forms(dt):
            got = m.parse(s)
            assert got == t and _is_date(got), f"parse({s!r}) = {got}, want {t}"
    rnd = random.Random(31337)
    for _ in range(3000):
        dt = D.fromordinal(rnd.randint(1, MAXORD))
        for s in _all_forms(dt):
            assert m.parse(s) == _tup(dt), f"parse({s!r})"
    for y in (2004, 2009, 2015, 2020, 2026):  # 53-week years: week 53 days
        for wd in range(1, 8):
            dt = D.fromisocalendar(y, 53, wd)
            assert m.parse(f"{y}-W53-{wd}") == _tup(dt) and m.parse(f"{y}W53{wd}") == _tup(dt)
    assert m.parse("0001-01-01") == (1, 1, 1) and m.parse("00010101") == (1, 1, 1)
    assert m.parse("0001-001") == (1, 1, 1) and m.parse("0001001") == (1, 1, 1)
    assert m.parse("0001-W01-1") == (1, 1, 1) and m.parse("0001W011") == (1, 1, 1)
    assert m.parse("9999-12-31") == (9999, 12, 31) and m.parse("9999-365") == (9999, 12, 31)
    assert m.parse("9999-W52-5") == (9999, 12, 31) and m.parse("9999W525") == (9999, 12, 31)
    assert m.parse("2024-366") == (2024, 12, 31) and m.parse("2024366") == (2024, 12, 31)
    assert m.parse("2000-366") == (2000, 12, 31) and m.parse("2400-366") == (2400, 12, 31)
    assert m.parse("2024060") == (2024, 2, 29) and m.parse("2023-060") == (2023, 3, 1)
    assert m.parse("2024010") == (2024, 1, 10) and m.parse("2024-010") == (2024, 1, 10)
    assert m.parse("20240110") == (2024, 1, 10) and m.parse("2024-01-10") == (2024, 1, 10)
    assert m.parse("2026-W53-5") == (2027, 1, 1) and m.parse("20201228") == (2020, 12, 28)
    assert m.parse("2025W011") == (2024, 12, 30) and m.parse("2025-W01-1") == (2024, 12, 30)
    assert m.parse("1900-02-28") == (1900, 2, 28) and m.parse("2000-02-29") == (2000, 2, 29)


REJECTS = [
    # whitespace / trailing newline
    "", " ", "\n", " 2024-01-01", "2024-01-01 ", "2024-01-01\n", "20240101\n", "2024-001\n", "2024001\n",
    "2024-W10-1\n", "2024W101\n", "\t2024-01-01", "2024-01-01\r\n", "2024 -01-01", "2024-01 -01",
    # lengths / missing zeros / extra digits / wrong years
    "2024-1-1", "2024-01-1", "2024-1-01", "24-01-01", "024-01-01", "02024-01-01", "10000-01-01", "20240-01-01",
    "2024", "2024-", "202401", "2024-01", "2024-12", "2024-1", "20240", "202401011", "2024-01-011", "2024-0123",
    "2024-01-01-", "-2024-01-01", "+2024-01-01", "2024--01-01", "2024-01--01", "2024-01-", "2024-01-01Z",
    "0000-01-01", "00000101", "0000-001", "0000001", "0000-W01-1", "0000W011",
    # separators and other formats
    "2024/01/01", "2024.01.01", "2024_01_01", "01-01-2024", "01/01/2024", "2024-01-01T00:00:00", "20240101T0000",
    "2024-01-01 12:00", "YYYY-MM-DD", "abcd-ef-gh", "abcdefgh", "2024-W10-1x", "x2024-W10-1",
    # month/day ranges
    "2024-13-01", "2024-00-01", "2024-01-00", "2024-01-32", "2024-04-31", "2024-06-31", "2024-02-30",
    "2023-02-29", "1900-02-29", "2100-02-29", "20230229", "20240230", "20241301", "20240001", "20240100", "20240431",
    # ordinal ranges
    "2023-366", "2023366", "1900-366", "2100-366", "2024-000", "2024000", "2024-367", "2024367", "2024-999", "2024999",
    # week ranges
    "2024-W00-1", "2024W001", "2024-W54-1", "2024W541", "2024-W99-1", "2024-W53-1", "2024W531", "2023-W53-1",
    "2025-W53-1", "2025W537", "2000-W53-3", "1900-W53-1",
    "2024-W10-0", "2024W100", "2024-W10-8", "2024W108", "2024-W10-9", "2024W109",
    # week syntax
    "2024-w10-1", "2024w101", "2024-W10", "2024W10", "2024-W1-1", "2024W11", "2024-W10-", "2024-W-10-1", "W10", "2024-WXX-1",
    "2024-W101", "2024W10-1", "2024-W10-11", "2024W1011", "2024-W010-1",
    # mixed basic / extended
    "2024-0101", "202401-01", "2024-01-0101", "2024W10-1", "2024-W101", "2024-01101",
    # characters that int() / isdigit() would swallow
    "2024-+1-01", "2024-1_-01", "2024-01- 1", "2024-W 1-1", "2024W+11", "2024-W1_-1", "202+0101", "2024-0 1-01", "2024-٠١-٠١",
    "２０２４-01-01", "٢٠٢٤-01-01", "٢٠٢٤٠١٠١",
    "2024-01-0²", "2024-0¹-01", "2024٣-01-01", "2024-W1٠-1", "2024-W10-١", "2024-٠١٠",
    # week dates beyond 9999-12-31 are ValueError in parse
    "9999-W52-6", "9999W526", "9999-W52-7", "9999W527", "9999-W53-1",
]


def test_parse_rejects(m):
    for s in REJECTS:
        try:
            got = m.parse(s)
        except ValueError:
            continue
        except Exception as e:
            raise AssertionError(f"parse({s!r}) raised {type(e).__name__}, expected ValueError")
        raise AssertionError(f"parse({s!r}) returned {got}, expected ValueError")
    # near-misses that must still be accepted (guards against over-rejecting)
    for s, want in (("2024-W10-7", (2024, 3, 10)), ("2024W107", (2024, 3, 10)), ("2024-12-31", (2024, 12, 31)),
                    ("2023-365", (2023, 12, 31)), ("2023365", (2023, 12, 31)), ("2024-W52-7", (2024, 12, 29)),
                    ("2020-W53-1", (2020, 12, 28)), ("2400-02-29", (2400, 2, 29)), ("0004-02-29", (4, 2, 29))):
        assert m.parse(s) == want, f"parse({s!r})"


def test_format_date(m):
    def forms(dt):
        iy, w, wd = dt.isocalendar()
        return (dt.isoformat(), f"{dt.year:04d}-{dt.timetuple().tm_yday:03d}", f"{iy:04d}-W{w:02d}-{wd}")

    def check(dt):
        t = _tup(dt)
        for form, want in zip(("calendar", "ordinal", "week"), forms(dt)):
            got = m.format_date(t, form)
            assert got == want and type(got) is str, f"format_date({t}, {form!r}) = {got!r}, want {want!r}"
            assert m.parse(got) == t, f"parse(format_date({t}, {form!r})) round trip"

    for o in range(D(1999, 1, 1).toordinal(), D(2002, 1, 1).toordinal()):
        check(D.fromordinal(o))
    for o in range(D(2026, 12, 15).toordinal(), D(2027, 1, 10).toordinal()):
        check(D.fromordinal(o))
    rnd = random.Random(4)
    for _ in range(3000):
        check(D.fromordinal(rnd.randint(1, MAXORD)))
    for t in ((1, 1, 1), (9999, 12, 31), (4, 2, 29), (100, 12, 31), (999, 1, 1), (1000, 1, 1)):
        check(D(*t))
    assert m.format_date((1, 1, 1), "calendar") == "0001-01-01"
    assert m.format_date((1, 1, 1), "ordinal") == "0001-001"
    assert m.format_date((1, 1, 1), "week") == "0001-W01-1"
    assert m.format_date((9999, 12, 31), "calendar") == "9999-12-31"
    assert m.format_date((9999, 12, 31), "ordinal") == "9999-365"
    assert m.format_date((9999, 12, 31), "week") == "9999-W52-5"
    assert m.format_date((2024, 12, 31), "ordinal") == "2024-366"
    assert m.format_date((2023, 12, 31), "ordinal") == "2023-365"
    assert m.format_date((2024, 12, 30), "week") == "2025-W01-1"
    assert m.format_date((2021, 1, 3), "week") == "2020-W53-7"
    assert m.format_date((2027, 1, 1), "week") == "2026-W53-5"
    assert m.format_date((2024, 3, 5), "calendar") == "2024-03-05"
    assert m.format_date((2024, 3, 5), "ordinal") == "2024-065"
    assert m.format_date((2024, 3, 5), "week") == "2024-W10-2"
    for bad in ("Calendar", "CALENDAR", "iso", "week ", " week", "", "basic", "cal", None, 1, b"week", ("week",), ["week"]):
        _raises(ValueError, lambda: m.format_date((2024, 3, 5), bad))
    _raises(ValueError, lambda: m.format_date((2024, 2, 30), "calendar"))
    _raises(ValueError, lambda: m.format_date((2024, 2, 30), "nonsense"))


def test_diff_rule(m):
    cases = [
        ((2023, 1, 31), (2023, 2, 28), (0, 1, 0)),
        ((2023, 1, 31), (2023, 2, 27), (0, 0, 27)),
        ((2023, 1, 31), (2023, 3, 1), (0, 1, 1)),
        ((2023, 1, 31), (2023, 3, 30), (0, 1, 30)),
        ((2023, 1, 31), (2023, 3, 31), (0, 2, 0)),
        ((2023, 1, 30), (2023, 3, 1), (0, 1, 1)),
        ((2024, 1, 31), (2024, 2, 29), (0, 1, 0)),
        ((2024, 1, 31), (2024, 3, 1), (0, 1, 1)),
        ((2024, 1, 30), (2024, 2, 29), (0, 1, 0)),
        ((2024, 2, 29), (2025, 2, 28), (1, 0, 0)),
        ((2024, 2, 29), (2025, 3, 1), (1, 0, 1)),
        ((2024, 2, 29), (2025, 2, 27), (0, 11, 29)),
        ((2024, 2, 29), (2028, 2, 29), (4, 0, 0)),
        ((2024, 2, 29), (2028, 2, 28), (3, 11, 30)),
        ((2024, 5, 31), (2024, 6, 30), (0, 1, 0)),
        ((2024, 5, 31), (2024, 6, 29), (0, 0, 29)),
        ((2023, 12, 31), (2024, 2, 29), (0, 2, 0)),
        ((2023, 12, 31), (2024, 2, 28), (0, 1, 28)),
        ((2000, 1, 1), (2000, 1, 1), (0, 0, 0)),
        ((2000, 1, 1), (2000, 1, 2), (0, 0, 1)),
        ((2000, 1, 15), (2000, 2, 14), (0, 0, 30)),
        ((2000, 1, 15), (2000, 2, 15), (0, 1, 0)),
        ((2000, 1, 15), (2001, 1, 14), (0, 11, 30)),
        ((1999, 12, 31), (2000, 1, 1), (0, 0, 1)),
        ((2020, 2, 29), (2021, 2, 28), (1, 0, 0)),
        ((2020, 2, 29), (2021, 2, 27), (0, 11, 29)),
        ((1, 1, 1), (9999, 12, 31), (9998, 11, 30)),
        ((1, 1, 31), (1, 3, 1), (0, 1, 1)),
        ((9998, 12, 31), (9999, 12, 31), (1, 0, 0)),
        ((9999, 1, 31), (9999, 2, 28), (0, 1, 0)),
    ]
    for a, b, want in cases:
        got = m.diff(a, b)
        assert got == want and _is_date(got), f"diff({a},{b}) = {got}, want {want}"
        # reversed: component-wise negation, months measured from the earlier date
        neg = m.diff(b, a)
        assert neg == tuple(-v for v in want), f"diff({b},{a}) = {neg}, want {tuple(-v for v in want)}"
        # identity
        y, mo, d = got
        assert m.add_days(m.add_months(a, 12 * y + mo), d) == b
    assert m.diff((2023, 3, 1), (2023, 1, 31)) == (0, -1, -1)
    assert m.diff((2023, 3, 30), (2023, 1, 31)) == (0, -1, -30)
    assert m.diff((2025, 3, 1), (2024, 2, 29)) == (-1, 0, -1)
    assert m.diff((9999, 12, 31), (1, 1, 1)) == (-9998, -11, -30)


def test_diff_oracle_and_identity(m):
    # exhaustive-ish against the brute-force scan: month-end heavy starts x every end day in a 3-year window
    starts = []
    for yy in (2023, 2024):
        for mo in range(1, 13):
            for dd in (1, 15, 28, 29, 30, 31):
                try:
                    D(yy, mo, dd)
                except ValueError:
                    continue
                starts.append((yy, mo, dd))
    ends = [_tup(D.fromordinal(o)) for o in range(D(2023, 1, 1).toordinal(), D(2025, 4, 1).toordinal())]
    count = 0
    for a in starts:
        ser = month_series(a, 0, 40)
        seq = [ser[k] for k in range(41)]
        da = D(*a)
        for b in ends:
            db = D(*b)
            if db < da:
                continue
            K = bisect.bisect_right(seq, db) - 1
            want = (K // 12, K % 12, (db - seq[K]).days)
            got = m.diff(a, b)
            assert got == want, f"diff({a},{b}) = {got}, want {want}"
            count += 1
            if count % 11 == 0:
                assert m.diff(b, a) == (-want[0], -want[1], -want[2]) if a != b else m.diff(b, a) == (0, 0, 0)
                assert m.add_days(m.add_months(a, 12 * got[0] + got[1]), got[2]) == b
    assert count > 40000
    rnd = random.Random(808)
    # random pairs within ~30 years: oracle scan
    for _ in range(250):
        o1 = rnd.randint(1, MAXORD - 12000)
        o2 = o1 + rnd.randint(0, 11000)
        a, b = _tup(D.fromordinal(o1)), _tup(D.fromordinal(o2))
        assert m.diff(a, b) == oracle_diff(a, b), f"diff({a},{b})"
        assert m.diff(b, a) == tuple(-v for v in oracle_diff(a, b)) or a == b
    # random pairs over the full range: structural properties (identity + maximality + uniqueness)
    for _ in range(4000):
        o1, o2 = rnd.randint(1, MAXORD), rnd.randint(1, MAXORD)
        a, b = _tup(D.fromordinal(o1)), _tup(D.fromordinal(o2))
        got = m.diff(a, b)
        assert _is_date(got)
        if a > b:
            assert got == tuple(-v for v in m.diff(b, a))
            a, b = b, a
            got = m.diff(a, b)
        yy, mo, dd = got
        assert yy >= 0 and 0 <= mo <= 11 and dd >= 0, f"diff({a},{b}) = {got}"
        K = 12 * yy + mo
        s = m.add_months(a, K)
        assert s <= b and m.add_days(s, dd) == b, f"identity broken for diff({a},{b}) = {got}"
        try:
            nxt = m.add_months(a, K + 1)
        except OverflowError:
            nxt = None
        assert nxt is None or nxt > b, f"diff({a},{b}) = {got} not maximal in months"


def test_validation_and_types(m):
    bad_dates = [(2024, 2, 30), (2023, 2, 29), (1900, 2, 29), (2100, 2, 29), (2024, 13, 1), (2024, 0, 1),
                 (2024, 1, 0), (2024, 1, 32), (2024, 4, 31), (0, 1, 1), (10000, 1, 1), (-1, 1, 1),
                 (2024, -1, 1), (2024, 1, -5), (0, 0, 0), (9999, 12, 32), (10000, 12, 31)]
    ok = (2024, 1, 1)
    for t in bad_dates:
        _raises(ValueError, lambda: m.to_ordinal(*t))
        _raises(ValueError, lambda: m.weekday(*t))
        _raises(ValueError, lambda: m.iso_week(*t))
        _raises(ValueError, lambda: m.add_days(t, 1))
        _raises(ValueError, lambda: m.add_days(t, 0))
        _raises(ValueError, lambda: m.add_months(t, 1))
        _raises(ValueError, lambda: m.add_months(t, 0))
        _raises(ValueError, lambda: m.format_date(t, "calendar"))
        _raises(ValueError, lambda: m.format_date(t, "week"))
        _raises(ValueError, lambda: m.diff(t, ok))
        _raises(ValueError, lambda: m.diff(ok, t))
        _raises(ValueError, lambda: m.diff(t, t))
    for t in ((2000, 2, 29), (2400, 2, 29), (1600, 2, 29), (1, 1, 1), (9999, 12, 31), (4, 2, 29)):
        m.to_ordinal(*t), m.weekday(*t), m.iso_week(*t), m.add_days(t, 0), m.add_months(t, 0)
        m.format_date(t, "calendar"), m.diff(t, t)
    for y in (0, -4, 10000, 20000):
        _raises(ValueError, lambda: m.is_leap(y))
        _raises(ValueError, lambda: m.days_in_month(y, 1))
    for mo in (0, 13, -1, 100):
        _raises(ValueError, lambda: m.days_in_month(2024, mo))
    for n in (0, -1, -100, MAXORD + 1, 10 ** 12):
        _raises(ValueError, lambda: m.from_ordinal(n))
    assert m.days_in_month(2000, 2) == 29 and m.days_in_month(1900, 2) == 28 and m.days_in_month(2024, 12) == 31
    # types
    class MyInt(int):
        pass

    wrong = [2024.0, "2024", None, True, False, MyInt(2024), [2024], 2024.5]
    for w in wrong:
        _raises(TypeError, lambda: m.is_leap(w))
        _raises(TypeError, lambda: m.days_in_month(w, 1))
        _raises(TypeError, lambda: m.days_in_month(2024, w))
        _raises(TypeError, lambda: m.to_ordinal(w, 1, 1))
        _raises(TypeError, lambda: m.to_ordinal(2024, w, 1))
        _raises(TypeError, lambda: m.to_ordinal(2024, 1, w))
        _raises(TypeError, lambda: m.from_ordinal(w))
        _raises(TypeError, lambda: m.weekday(2024, w, 1))
        _raises(TypeError, lambda: m.iso_week(2024, 1, w))
        _raises(TypeError, lambda: m.add_days(ok, w))
        _raises(TypeError, lambda: m.add_months(ok, w))
        _raises(TypeError, lambda: m.iso_weeks_in_year(w))
        _raises(TypeError, lambda: m.from_iso_week(w, 1, 1))
        _raises(TypeError, lambda: m.from_iso_week(2024, w, 1))
        _raises(TypeError, lambda: m.from_iso_week(2024, 1, w))
    for w in (2024, 20240101, 2024.0, None, b"2024-01-01", ["2024-01-01"], True):
        _raises(TypeError, lambda: m.parse(w))
    for w in ([2024, 1, 1], (2024, 1), (2024, 1, 1, 1), (2024.0, 1, 1), (2024, 1, "1"), (2024, 1, True), None,
              "2024-01-01", D(2024, 1, 1), 20240101, (), (2024, 1, None)):
        _raises(TypeError, lambda: m.add_days(w, 1))
        _raises(TypeError, lambda: m.add_months(w, 1))
        _raises(TypeError, lambda: m.format_date(w, "calendar"))
        _raises(TypeError, lambda: m.diff(w, ok))
        _raises(TypeError, lambda: m.diff(ok, w))
    # all arguments are type-checked before any range check
    _raises(TypeError, lambda: m.to_ordinal(2024.5, 13, 40))
    _raises(TypeError, lambda: m.to_ordinal(2024, 13, 40.0))
    _raises(TypeError, lambda: m.add_days((2024, 2, 30), 1.5))
    _raises(TypeError, lambda: m.add_days((2024, 2, 30), "1"))
    _raises(TypeError, lambda: m.add_days((2024.0, 2, 30), 1))
    _raises(TypeError, lambda: m.add_months((2024, 13, 1), None))
    _raises(TypeError, lambda: m.diff((2024, 2, 30), (2024.0, 1, 1)))
    _raises(TypeError, lambda: m.diff((2024.0, 1, 1), (2024, 2, 30)))
    _raises(TypeError, lambda: m.from_iso_week(0, "1", 1))
    _raises(TypeError, lambda: m.from_iso_week(2024, 99, 1.0))
    _raises(TypeError, lambda: m.days_in_month(0, 1.0))
    _raises(TypeError, lambda: m.format_date((2024.0, 1, 1), "zzz"))
    # valid-but-unusual inputs are still fine
    assert m.add_days((2024, 1, 31), 10 ** 3) == _tup(D(2024, 1, 31) + datetime.timedelta(days=1000))
    r = m.add_months((2024, 1, 31), 1)
    assert type(r) is tuple and all(type(v) is int for v in r)


def test_scale(m):
    rnd = random.Random(2718)
    ords = [rnd.randint(1, MAXORD) for _ in range(50000)]
    for o in ords:
        t = m.from_ordinal(o)
        assert m.to_ordinal(*t) == o
    ds = [m.from_ordinal(o) for o in ords[:20000]]
    for t in ds:
        iy, w, wd = m.iso_week(*t)
        assert m.from_iso_week(iy, w, wd) == t
    for t, o in zip(ds[:10000], ords[10000:20000]):
        a, b = (t, ds[o % len(ds)]) if t <= ds[o % len(ds)] else (ds[o % len(ds)], t)
        y, mo, d = m.diff(a, b)
        assert m.add_days(m.add_months(a, 12 * y + mo), d) == b
    for t in ds[:10000]:
        n = rnd.randint(-5000, 5000)
        try:
            m.add_months(t, n)
        except OverflowError:
            pass
    for i in range(2000):
        _raises(OverflowError, lambda: m.add_days((2000, 1, 1), 10 ** 15 + i))
        _raises(OverflowError, lambda: m.add_months((2000, 1, 1), -10 ** 15 - i))
    assert m.diff((1, 1, 1), (9999, 12, 31)) == (9998, 11, 30)


TESTS = [test_no_forbidden_imports, test_leap_and_month_lengths, test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_add_months_oracle, test_parse_accepts, test_parse_rejects, test_format_date, test_diff_rule, test_diff_oracle_and_identity, test_validation_and_types, test_scale]
