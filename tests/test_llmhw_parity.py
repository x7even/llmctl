#!/usr/bin/env python3
"""
Parity test for the hardware-requirement rules.

tests/fixtures/llmhw_cases.json is shared with the Go implementation
(tui/hw_test.go, TestSupportsParity). Both sides must satisfy every case, so
scripts/llmhw.py and tui/hw.go cannot drift apart. When you change a rule,
add or adjust a case in the fixture and update BOTH implementations.

Case shape: {name, requires, hw: {gpu_count, host_ram_gib}, expect: {ok, use,
reasons[, estimate]}}. null gpu_count / host_ram_gib = unknown; use null = no
TP/split size. `estimate` is only checked by the Go side (supports() here does
not return it); this test just verifies the fixture's flag mirrors requires.

Run:  python3 tests/test_llmhw_parity.py        (also pytest-compatible)
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import llmhw  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "llmhw_cases.json"


def _cases():
    return json.loads(FIXTURE.read_text())


def test_fixture_is_well_formed_and_broad():
    cases = _cases()
    assert len(cases) >= 30
    names = [c["name"] for c in cases]
    assert len(names) == len(set(names)), "duplicate case names"
    for c in cases:
        assert set(c) == {"name", "requires", "hw", "expect"}, c["name"]
        assert set(c["hw"]) == {"gpu_count", "host_ram_gib"}, c["name"]
        assert {"ok", "use", "reasons"} <= set(c["expect"]), c["name"]
    # the edge classes the Go port must cover
    reqs = [c["requires"] for c in cases]
    assert any(r is None for r in reqs) and any(r == {} for r in reqs)
    assert any(r and "gpus" in r for r in reqs) and any(r and "min_gpus" in r for r in reqs)
    assert any(r and "host_ram_gib" in r for r in reqs)
    assert any(r and r.get("estimate") for r in reqs)
    assert any(c["hw"]["gpu_count"] is None for c in cases)
    assert any(c["hw"]["host_ram_gib"] is None for c in cases)


def test_supports_matches_shared_fixture():
    for c in _cases():
        hw = {"gpu_count": c["hw"]["gpu_count"], "vram_gib_per_gpu": [],
              "host_ram_gib": c["hw"]["host_ram_gib"], "source": "test", "ignored_devices": 0}
        ok, use, reasons = llmhw.supports(c["requires"], hw)
        exp = c["expect"]
        assert ok == exp["ok"], f"{c['name']}: ok {ok} != {exp['ok']}"
        assert use == exp["use"], f"{c['name']}: use {use} != {exp['use']}"
        assert reasons == exp["reasons"], f"{c['name']}: reasons {reasons} != {exp['reasons']}"


def test_fixture_estimate_flag_mirrors_requires():
    for c in _cases():
        want = bool((c["requires"] or {}).get("estimate"))
        assert c["expect"].get("estimate", False) == want, c["name"]


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
