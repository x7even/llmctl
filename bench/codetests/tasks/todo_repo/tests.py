"""Hidden tests for todo_repo. Each test takes the loaded solution module `m`."""
import os
import tempfile


def _raises(exc, fn):
    try:
        fn()
    except exc:
        return
    except Exception as e:
        raise AssertionError(f"raised {type(e).__name__}, expected {exc.__name__}")
    raise AssertionError(f"did not raise {exc.__name__}")


def test_add_and_get(m):
    r = m.TodoRepo()
    a = r.add("write tests")
    b = r.add("ship it", priority=1)
    assert (a, b) == (1, 2)
    assert r.get(a) == {"id": 1, "title": "write tests", "priority": 3, "done": False}
    assert r.get(b)["priority"] == 1
    assert r.get(99) is None


def test_title_stripped_and_validated(m):
    r = m.TodoRepo()
    i = r.add("   padded  \n")
    assert r.get(i)["title"] == "padded"
    _raises(ValueError, lambda: r.add(""))
    _raises(ValueError, lambda: r.add("   \t "))
    assert r.count() == 1


def test_priority_validation(m):
    r = m.TodoRepo()
    for bad in (0, 6, -1):
        _raises(ValueError, lambda: r.add("x", priority=bad))
    r.add("lo", priority=5)
    r.add("hi", priority=1)
    assert r.count() == 2


def test_special_characters_roundtrip(m):
    r = m.TodoRepo()
    titles = ["it's \"quoted\"", "'; DROP TABLE todos; --", "unicode: café ✓ \U0001f600", "a;b,c|d"]
    ids = [r.add(t) for t in titles]
    assert [r.get(i)["title"] for i in ids] == titles
    assert r.count() == len(titles)


def test_list_order_by_priority_then_id(m):
    r = m.TodoRepo()
    r.add("c", 3)
    r.add("a", 1)
    r.add("b", 3)
    r.add("d", 1)
    assert [t["title"] for t in r.list()] == ["a", "d", "c", "b"]


def test_list_filter_by_done(m):
    r = m.TodoRepo()
    a, b, c = r.add("a"), r.add("b"), r.add("c")
    r.mark_done(b)
    assert [t["title"] for t in r.list(done=True)] == ["b"]
    assert [t["title"] for t in r.list(done=False)] == ["a", "c"]
    assert len(r.list()) == 3
    assert r.get(b)["done"] is True and r.get(a)["done"] is False


def test_mark_done(m):
    r = m.TodoRepo()
    i = r.add("a")
    assert r.mark_done(i) is True
    assert r.mark_done(i) is True  # already done
    assert r.mark_done(42) is False


def test_delete_and_no_id_reuse(m):
    r = m.TodoRepo()
    a, b = r.add("a"), r.add("b")
    assert r.delete(b) is True
    assert r.delete(b) is False
    assert r.get(b) is None
    c = r.add("c")
    assert c == 3 and c != b


def test_count(m):
    r = m.TodoRepo()
    ids = [r.add(str(i)) for i in range(5)]
    r.mark_done(ids[0])
    r.mark_done(ids[1])
    assert r.count() == 5 and r.count(done=True) == 2 and r.count(done=False) == 3
    r.delete(ids[0])
    assert r.count(done=True) == 1 and r.count() == 4


def test_persistence_across_instances(m):
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "todo.db")
        r = m.TodoRepo(path)
        a = r.add("persist me", priority=2)
        r.mark_done(a)
        r.close()
        r2 = m.TodoRepo(path)
        assert r2.get(a) == {"id": a, "title": "persist me", "priority": 2, "done": True}
        b = r2.add("second")
        assert b == a + 1
        r2.close()


def test_empty_repo(m):
    r = m.TodoRepo()
    assert r.list() == [] and r.count() == 0 and r.count(done=True) == 0
    assert r.mark_done(1) is False and r.delete(1) is False


TESTS = [test_add_and_get, test_title_stripped_and_validated, test_priority_validation,
         test_special_characters_roundtrip, test_list_order_by_priority_then_id, test_list_filter_by_done,
         test_mark_done, test_delete_and_no_id_reuse, test_count, test_persistence_across_instances,
         test_empty_repo]
