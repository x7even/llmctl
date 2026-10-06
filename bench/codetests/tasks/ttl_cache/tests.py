"""Hidden tests for ttl_cache. Each test takes the loaded solution module `m`."""


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def mk(m, cap=3, ttl=10.0):
    c = Clock()
    return m.TTLCache(cap, ttl, clock=c), c


def _raises(exc, fn):
    try:
        fn()
    except exc:
        return
    except Exception as e:
        raise AssertionError(f"raised {type(e).__name__}, expected {exc.__name__}")
    raise AssertionError(f"did not raise {exc.__name__}")


def test_basic_put_get(m):
    c, _ = mk(m)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1 and c.get("b") == 2
    assert c.get("zz") is None and c.get("zz", 5) == 5
    assert len(c) == 2 and "a" in c and "zz" not in c


def test_validation(m):
    c = Clock()
    for bad_cap in (0, -1):
        _raises(ValueError, lambda: m.TTLCache(bad_cap, 1.0, clock=c))
    for bad_ttl in (0, -5, 0.0):
        _raises(ValueError, lambda: m.TTLCache(2, bad_ttl, clock=c))
    cache = m.TTLCache(2, 5.0, clock=c)
    cache.put("k", "v")
    _raises(ValueError, lambda: cache.put("k", "new", ttl=0))
    _raises(ValueError, lambda: cache.put("j", "x", ttl=-1))
    assert cache.get("k") == "v" and "j" not in cache and len(cache) == 1  # unchanged


def test_expiry_boundary_inclusive(m):
    c, clk = mk(m, ttl=10.0)
    c.put("a", 1)
    clk.advance(9.999)
    assert c.get("a") == 1
    clk.advance(0.001)  # now exactly t0 + 10 (float: 1000.0+9.999+0.001 may be 1010.0000000000001 or 1009.9999999999999)
    clk.t = 1010.0
    assert c.get("a") is None
    assert "a" not in c and len(c) == 0


def test_per_entry_ttl(m):
    c, clk = mk(m, ttl=10.0)
    c.put("short", 1, ttl=2.0)
    c.put("long", 2, ttl=50.0)
    c.put("default", 3)
    clk.advance(2.0)
    assert c.get("short") is None and c.get("long") == 2 and c.get("default") == 3
    clk.advance(8.0)
    assert c.get("default") is None and c.get("long") == 2
    clk.advance(40.0)
    assert c.get("long") is None


def test_infinite_ttl(m):
    c, clk = mk(m, ttl=1.0)
    c.put("forever", 1, ttl=float("inf"))
    clk.advance(1e12)
    assert c.get("forever") == 1


def test_get_does_not_extend_ttl(m):
    c, clk = mk(m, ttl=10.0)
    c.put("a", 1)
    clk.advance(6)
    assert c.get("a") == 1
    clk.advance(4)  # t0+10 -> expired despite the get at t0+6
    assert c.get("a") is None


def test_overwrite_resets_ttl_and_value(m):
    c, clk = mk(m, ttl=10.0)
    c.put("a", 1)
    clk.advance(8)
    c.put("a", 2)
    clk.advance(8)  # 16s after first put, 8 after second
    assert c.get("a") == 2
    clk.advance(2)  # 10 after second put
    assert c.get("a") is None


def test_overwrite_uses_new_ttl_or_default(m):
    c, clk = mk(m, ttl=10.0)
    c.put("a", 1, ttl=100.0)
    clk.advance(1)
    c.put("a", 2)  # ttl=None -> default 10, not the old 100
    clk.advance(10)
    assert c.get("a") is None


def test_lru_eviction_order(m):
    c, _ = mk(m, cap=3)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)
    c.put("d", 4)  # evicts a
    assert c.keys() == ["b", "c", "d"]
    assert "a" not in c


def test_get_refreshes_recency(m):
    c, _ = mk(m, cap=3)
    for k in "abc":
        c.put(k, k)
    assert c.get("a") == "a"  # a becomes MRU
    c.put("d", "d")  # evicts b
    assert c.keys() == ["c", "a", "d"]


def test_peek_does_not_refresh(m):
    c, _ = mk(m, cap=3)
    for k in "abc":
        c.put(k, k)
    assert c.peek("a") == "a"
    c.put("d", "d")  # evicts a (peek did not refresh)
    assert c.keys() == ["b", "c", "d"]
    assert c.peek("nope") is None and c.peek("nope", 9) == 9


def test_contains_does_not_refresh(m):
    c, _ = mk(m, cap=2)
    c.put("a", 1)
    c.put("b", 2)
    assert "a" in c
    c.put("c", 3)  # evicts a
    assert c.keys() == ["b", "c"]


def test_overwrite_refreshes_and_never_evicts(m):
    c, _ = mk(m, cap=3)
    for k in "abc":
        c.put(k, 1)
    c.put("a", 99)  # full cache, existing key: no eviction, a -> MRU
    assert len(c) == 3 and c.keys() == ["b", "c", "a"]
    c.put("d", 4)  # evicts b
    assert c.keys() == ["c", "a", "d"]


def test_expired_purged_before_lru_eviction(m):
    c, clk = mk(m, cap=3, ttl=100.0)
    c.put("old", 1, ttl=5.0)  # LRU slot... but will be expired
    c.put("b", 2)
    c.put("c", 3)
    c.get("old")  # old becomes MRU, so plain LRU would evict b
    clk.advance(5.0)  # old expires
    c.put("d", 4)  # must drop expired "old", NOT evict live b
    assert c.keys() == ["b", "c", "d"]


def test_expired_slot_reclaimed_prefers_expired_over_lru(m):
    c, clk = mk(m, cap=2, ttl=100.0)
    c.put("a", 1)  # LRU, live
    c.put("b", 2, ttl=1.0)  # MRU, will expire
    clk.advance(1.0)
    c.put("c", 3)  # purge b first -> no eviction of a
    assert c.keys() == ["a", "c"]


def test_len_excludes_expired(m):
    c, clk = mk(m, cap=5, ttl=10.0)
    c.put("a", 1, ttl=1.0)
    c.put("b", 2, ttl=2.0)
    c.put("c", 3, ttl=30.0)
    assert len(c) == 3
    clk.advance(2.0)
    assert len(c) == 1 and c.keys() == ["c"]


def test_delete_semantics(m):
    c, clk = mk(m, cap=3, ttl=10.0)
    c.put("a", 1)
    c.put("b", 2, ttl=1.0)
    assert c.delete("a") is True
    assert c.delete("a") is False
    assert c.delete("never") is False
    clk.advance(1.0)
    assert c.delete("b") is False  # expired -> False
    assert len(c) == 0


def test_overwrite_expired_key_counts_as_new_insert(m):
    c, clk = mk(m, cap=2, ttl=100.0)
    c.put("a", 1)
    c.put("x", 9, ttl=1.0)
    clk.advance(1.0)  # x expired but still physically present
    c.put("x", 10)  # new insert; purge expired first (x itself), nothing else evicted
    assert c.keys() == ["a", "x"] and c.get("x") == 10


def test_none_value_is_a_hit(m):
    c, _ = mk(m, cap=2)
    c.put("a", None)
    c.put("b", 2)
    sentinel = object()
    assert c.get("a", sentinel) is None  # hit, not the default
    assert "a" in c
    c.put("c", 3)  # a was refreshed by get -> evicts b
    assert c.keys() == ["a", "c"]


def test_hashable_keys(m):
    c, _ = mk(m, cap=4)
    ks = [(1, 2), "s", 3.5, frozenset([1])]
    for i, k in enumerate(ks):
        c.put(k, i)
    assert [c.get(k) for k in ks] == [0, 1, 2, 3]


def test_capacity_one(m):
    c, _ = mk(m, cap=1)
    c.put("a", 1)
    c.put("b", 2)
    assert c.keys() == ["b"] and c.get("a") is None
    c.put("b", 3)
    assert c.get("b") == 3 and len(c) == 1


def test_model_based_random(m):
    """Random op sequences vs an independent simple model (list-based)."""
    import random
    rnd = random.Random(99)
    for trial in range(60):
        cap = rnd.randint(1, 4)
        clk = Clock(0.0)
        c = m.TTLCache(cap, 7.0, clock=clk)
        model = []  # [(key, value, expires)] LRU -> MRU

        def live():
            return [e for e in model if clk.t < e[2]]

        for _ in range(80):
            op = rnd.choice(["put", "put", "get", "peek", "del", "adv", "len", "keys", "has"])
            k = rnd.choice("abcde")
            if op == "put":
                ttl = rnd.choice([None, 1.0, 3.0, 20.0])
                v = rnd.randint(0, 99)
                exp = clk.t + (7.0 if ttl is None else ttl)
                model[:] = live()
                idx = next((i for i, e in enumerate(model) if e[0] == k), None)
                if idx is not None:
                    model.pop(idx)
                elif len(model) >= cap:
                    model.pop(0)
                model.append((k, v, exp))
                c.put(k, v, ttl)
            elif op == "get":
                model[:] = live()
                idx = next((i for i, e in enumerate(model) if e[0] == k), None)
                want = None
                if idx is not None:
                    e = model.pop(idx)
                    model.append(e)
                    want = e[1]
                assert c.get(k) == want, f"get {k}"
            elif op == "peek":
                model[:] = live()
                want = next((e[1] for e in model if e[0] == k), None)
                assert c.peek(k) == want, f"peek {k}"
            elif op == "del":
                model[:] = live()
                idx = next((i for i, e in enumerate(model) if e[0] == k), None)
                if idx is not None:
                    model.pop(idx)
                assert c.delete(k) is (idx is not None), f"delete {k}"
            elif op == "adv":
                dt = rnd.choice([0.5, 1.0, 2.0, 3.0, 8.0])
                clk.advance(dt)
            elif op == "len":
                assert len(c) == len(live()), "len"
            elif op == "keys":
                model[:] = live()
                assert c.keys() == [e[0] for e in model], "keys"
            elif op == "has":
                assert (k in c) == any(e[0] == k for e in live()), f"contains {k}"


TESTS = [
    test_basic_put_get, test_validation, test_expiry_boundary_inclusive, test_per_entry_ttl,
    test_infinite_ttl, test_get_does_not_extend_ttl, test_overwrite_resets_ttl_and_value,
    test_overwrite_uses_new_ttl_or_default, test_lru_eviction_order, test_get_refreshes_recency,
    test_peek_does_not_refresh, test_contains_does_not_refresh, test_overwrite_refreshes_and_never_evicts,
    test_expired_purged_before_lru_eviction, test_expired_slot_reclaimed_prefers_expired_over_lru,
    test_len_excludes_expired, test_delete_semantics, test_overwrite_expired_key_counts_as_new_insert,
    test_none_value_is_a_hit, test_hashable_keys, test_capacity_one, test_model_based_random,
]
