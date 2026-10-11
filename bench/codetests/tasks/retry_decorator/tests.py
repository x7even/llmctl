"""Hidden tests for retry_decorator. Each test takes the loaded solution module `m`."""


def _raises(exc, fn):
    try:
        fn()
    except exc:
        return
    except Exception as e:
        raise AssertionError(f"raised {type(e).__name__}, expected {exc.__name__}")
    raise AssertionError(f"did not raise {exc.__name__}")


class Flaky:
    """Fails `fails` times with `exc`, then returns 'ok'."""

    def __init__(self, fails, exc=ValueError):
        self.fails, self.exc, self.n = fails, exc, 0

    def __call__(self, *a, **k):
        self.n += 1
        if self.n <= self.fails:
            raise self.exc(f"fail {self.n}")
        return ("ok", a, k)


def test_success_first_try(m):
    sleeps = []
    f = m.retry(sleep=sleeps.append)(Flaky(0))
    assert f(1, x=2) == ("ok", (1,), {"x": 2})
    assert sleeps == []


def test_retries_then_succeeds(m):
    sleeps = []
    fn = Flaky(2)
    f = m.retry(max_attempts=5, delay=1.0, backoff=2.0, sleep=sleeps.append)(fn)
    assert f()[0] == "ok"
    assert fn.n == 3
    assert sleeps == [1.0, 2.0]


def test_exhausts_and_raises_last(m):
    sleeps = []
    fn = Flaky(10)
    f = m.retry(max_attempts=3, delay=0.5, backoff=3.0, sleep=sleeps.append)(fn)
    try:
        f()
    except ValueError as e:
        assert str(e) == "fail 3"
    else:
        raise AssertionError("did not raise")
    assert fn.n == 3
    assert sleeps == [0.5, 1.5]  # no sleep after the last failure


def test_backoff_sequence(m):
    sleeps = []
    f = m.retry(max_attempts=5, delay=2, backoff=2, sleep=sleeps.append)(Flaky(4))
    f()
    assert sleeps == [2, 4, 8, 16]


def test_unlisted_exception_propagates_immediately(m):
    sleeps = []
    fn = Flaky(5, exc=KeyError)
    f = m.retry(max_attempts=4, exceptions=(ValueError,), sleep=sleeps.append)(fn)
    _raises(KeyError, f)
    assert fn.n == 1 and sleeps == []


def test_listed_tuple_of_exceptions(m):
    sleeps = []
    calls = {"n": 0}

    def g():
        calls["n"] += 1
        if calls["n"] == 1:
            raise KeyError("k")
        if calls["n"] == 2:
            raise ValueError("v")
        return 7

    f = m.retry(max_attempts=4, exceptions=(KeyError, ValueError), sleep=sleeps.append)(g)
    assert f() == 7 and len(sleeps) == 2


def test_default_exceptions_cover_exception_subclasses(m):
    sleeps = []
    fn = Flaky(1, exc=OSError)
    f = m.retry(sleep=sleeps.append)(fn)
    assert f()[0] == "ok" and sleeps == [1.0]


def test_max_attempts_one(m):
    sleeps = []
    fn = Flaky(1)
    f = m.retry(max_attempts=1, sleep=sleeps.append)(fn)
    _raises(ValueError, f)
    assert fn.n == 1 and sleeps == []


def test_parameter_validation(m):
    _raises(ValueError, lambda: m.retry(max_attempts=0))
    _raises(ValueError, lambda: m.retry(delay=-1))
    _raises(ValueError, lambda: m.retry(backoff=0.5))
    m.retry(delay=0, backoff=1)  # boundary values are fine


def test_preserves_metadata(m):
    @m.retry(sleep=lambda s: None)
    def documented(a, b=2):
        """Doc string."""
        return a + b

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "Doc string."
    assert documented(1) == 3


def test_calls_counter_accumulates(m):
    fn = Flaky(2)
    f = m.retry(max_attempts=5, sleep=lambda s: None)(fn)
    assert f.calls == 0
    f()
    assert f.calls == 3
    f()
    assert f.calls == 4


def test_independent_decorated_functions(m):
    sleeps = []
    dec = m.retry(max_attempts=2, sleep=sleeps.append)
    a, b = dec(Flaky(1)), dec(Flaky(0))
    a()
    b()
    assert a.calls == 2 and b.calls == 1


TESTS = [test_success_first_try, test_retries_then_succeeds, test_exhausts_and_raises_last,
         test_backoff_sequence, test_unlisted_exception_propagates_immediately,
         test_listed_tuple_of_exceptions, test_default_exceptions_cover_exception_subclasses,
         test_max_attempts_one, test_parameter_validation, test_preserves_metadata,
         test_calls_counter_accumulates, test_independent_decorated_functions]
