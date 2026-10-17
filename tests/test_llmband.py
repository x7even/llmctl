#!/usr/bin/env python3
"""
Unit tests for scripts/llmband (slow-decode-band detector for gfx1201 vLLM servers):
the band decision from mem_busy, the gpu_busy guard, the tok/s cross-check and what happens
when the two signals disagree, dropping idle samples, card discovery, and that errors come
back as "undecided" with exit status 2 rather than as a crash.

No GPU and no server are needed: the sysfs tree is a temp directory and the counters are
supplied directly.

Run:  python3 tests/test_llmband.py        (also pytest-compatible)
"""
import importlib.machinery
import importlib.util
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "llmband"

_loader = importlib.machinery.SourceFileLoader("llmband", str(SCRIPT))
_spec = importlib.util.spec_from_loader("llmband", _loader)
band = importlib.util.module_from_spec(_spec)
_loader.exec_module(band)


def _sysfs(root, spec):
    """spec: {"card0": (gpu_busy, mem_busy) or None to omit the counters}"""
    for name, vals in spec.items():
        d = Path(root) / name / "device"
        d.mkdir(parents=True, exist_ok=True)
        if vals is None:
            continue
        g, m = vals
        (d / "gpu_busy_percent").write_text(f"{g}\n")
        (d / "mem_busy_percent").write_text(f"{m}\n")


# ─── classify ────────────────────────────────────────────────────────────────────────

def test_fast_band_from_mem_busy():
    verdict, reasons = band.classify(mem_busy=64.0, gpu_busy=100.0)
    assert verdict == "fast", reasons
    assert any("mem_busy 64%" in r for r in reasons)


def test_slow_band_from_mem_busy():
    verdict, reasons = band.classify(mem_busy=26.0, gpu_busy=100.0)
    assert verdict == "slow", reasons


def test_threshold_is_inclusive_at_the_boundary():
    assert band.classify(mem_busy=45.0, gpu_busy=100.0)[0] == "fast"
    assert band.classify(mem_busy=44.9, gpu_busy=100.0)[0] == "slow"


def test_idle_gpus_are_undecided_not_slow():
    """mem_busy is meaningless when the GPUs were not decoding; must not report "slow"."""
    verdict, reasons = band.classify(mem_busy=5.0, gpu_busy=3.0)
    assert verdict == "undecided", reasons
    assert any("not decoding" in r for r in reasons)


def test_missing_samples_are_undecided():
    assert band.classify(mem_busy=None, gpu_busy=None)[0] == "undecided"
    assert band.classify(mem_busy=60.0, gpu_busy=None)[0] == "undecided"


def test_tps_crosscheck_agrees():
    verdict, reasons = band.classify(mem_busy=64.0, gpu_busy=100.0, tps=63.0, expect_tps=66.0)
    assert verdict == "fast", reasons
    assert any("tok/s" in r for r in reasons)


def test_tps_crosscheck_agrees_on_slow():
    assert band.classify(mem_busy=25.0, gpu_busy=100.0, tps=30.0, expect_tps=66.0)[0] == "slow"


def test_disagreement_is_undecided():
    """A fast mem_busy with a slow tok/s (or the reverse) must not be resolved by guessing."""
    verdict, reasons = band.classify(mem_busy=64.0, gpu_busy=100.0, tps=30.0, expect_tps=66.0)
    assert verdict == "undecided", reasons
    assert "signals disagree" in reasons

    verdict, _ = band.classify(mem_busy=25.0, gpu_busy=100.0, tps=65.0, expect_tps=66.0)
    assert verdict == "undecided"


def test_tolerance_band_is_generous_enough_for_normal_variance():
    # 25% below the baseline is still "fast": the bands are >=1.2x apart, and run-to-run
    # variance from prompt and acceptance-rate differences is a few percent.
    assert band.classify(mem_busy=64.0, gpu_busy=100.0, tps=50.0, expect_tps=66.0)[0] == "fast"
    assert band.classify(mem_busy=25.0, gpu_busy=100.0, tps=49.0, expect_tps=66.0)[0] == "slow"


def test_expect_tps_absent_leaves_mem_busy_in_charge():
    verdict, reasons = band.classify(mem_busy=64.0, gpu_busy=100.0, tps=30.0, expect_tps=None)
    assert verdict == "fast"
    assert not any("tok/s" in r for r in reasons)


# ─── busy_under_load ─────────────────────────────────────────────────────────────────

def test_busy_under_load_drops_idle_samples():
    rows = [(2.0, 1.0), (100.0, 64.0), (100.0, 66.0), (0.0, 0.0)]
    gpu, mem, n = band.busy_under_load(rows)
    assert n == 2
    assert gpu == 100.0
    assert mem == 65.0


def test_busy_under_load_with_no_loaded_samples():
    assert band.busy_under_load([(1.0, 1.0), (2.0, 0.0)]) == (None, None, 0)


def test_busy_under_load_on_empty_input():
    assert band.busy_under_load([]) == (None, None, 0)


# ─── sysfs reading ───────────────────────────────────────────────────────────────────

def test_cards_finds_and_orders_numerically():
    with tempfile.TemporaryDirectory() as d:
        _sysfs(d, {"card0": (100, 60), "card1": (100, 60), "card2": (100, 60),
                   "card10": (100, 60)})
        names = [c.name for c in band.cards(Path(d))]
        assert names == ["card0", "card1", "card2", "card10"]


def test_cards_skips_devices_without_the_counters():
    with tempfile.TemporaryDirectory() as d:
        _sysfs(d, {"card0": (100, 60), "card1": None})
        assert [c.name for c in band.cards(Path(d))] == ["card0"]


def test_read_percent_parses_and_tolerates_garbage():
    with tempfile.TemporaryDirectory() as d:
        _sysfs(d, {"card0": (100, 64)})
        c = Path(d) / "card0"
        assert band.read_percent(c, "gpu") == 100.0
        assert band.read_percent(c, "mem") == 64.0
        (c / "device" / "mem_busy_percent").write_text("not-a-number\n")
        assert band.read_percent(c, "mem") is None
        assert band.read_percent(Path(d) / "card9", "gpu") is None


def test_sample_busy_stops_when_asked_and_averages_cards():
    with tempfile.TemporaryDirectory() as d:
        _sysfs(d, {"card0": (100, 60), "card1": (100, 70)})
        cl = band.cards(Path(d))
        stop = threading.Event()
        rows = []

        def run():
            rows.extend(band.sample_busy(cl, stop, interval=0.0))

        t = threading.Thread(target=run)
        t.start()
        stop.set()
        t.join(timeout=5)
        assert not t.is_alive()
        for gpu, mem in rows:
            assert gpu == 100.0
            assert mem == 65.0     # mean across the two cards


# ─── CLI ─────────────────────────────────────────────────────────────────────────────

def _run(args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=120)


def test_cli_reports_undecided_and_exits_2_when_it_cannot_measure():
    """An unreachable server is an error, and an error must be "undecided" (2), never "slow" (1)."""
    r = _run(["--model", "nope", "--base", "http://127.0.0.1:1", "--json", "--timeout", "3"])
    assert r.returncode == 2, r.stderr
    assert '"verdict": "undecided"' in r.stdout


def test_cli_help_works_without_requests_installed():
    r = _run(["--help"])
    assert r.returncode == 0
    assert "slow decode band" in r.stdout


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
