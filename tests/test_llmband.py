#!/usr/bin/env python3
"""
Unit tests for scripts/llmband (slow-decode-band detector for gfx1201 vLLM servers):
the band decision from step rate against a stored baseline, the refusal to decide without one,
the gpu_busy guard, mem_busy's corroborating-only role, dropping idle cards and idle samples,
card discovery, baseline round-tripping, that the warmup decode runs before the measured one,
and that errors come back as "undecided" with exit status 2 rather than as a crash.

No GPU and no server are needed: the sysfs tree is a temp directory and the counters and
baselines are supplied directly.

Run:  python3 tests/test_llmband.py        (also pytest-compatible)
"""
import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "llmband"

_loader = importlib.machinery.SourceFileLoader("llmband", str(SCRIPT))
_spec = importlib.util.spec_from_loader("llmband", _loader)
band = importlib.util.module_from_spec(_spec)
_loader.exec_module(band)

FAST = {"steps_s": 30.0, "tok_s": 70.0, "mem_busy": 37.0, "accepted_per_step": 2.33}


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


# ─── classify: the baseline is mandatory ─────────────────────────────────────────────

def test_no_baseline_is_undecided_not_a_guess():
    """Without a baseline there is nothing to compare against, and no universal threshold."""
    for b in (None, {}, {"steps_s": None}):
        verdict, reasons = band.classify(30.0, b)
        assert verdict == "undecided", (b, reasons)
        assert any("calibrate" in r for r in reasons)


def test_fast_when_step_rate_matches_baseline():
    verdict, reasons = band.classify(29.5, FAST, mem_busy=37.0, gpu_busy=100.0)
    assert verdict == "fast", reasons


def test_slow_when_step_rate_is_far_below_baseline():
    verdict, reasons = band.classify(15.0, FAST, mem_busy=25.0, gpu_busy=100.0)
    assert verdict == "slow", reasons


def test_tolerance_separates_the_narrowest_band_gap_from_noise():
    """The narrowest reported gap is 1.21x: the slow band is 17.4% down. Noise is a few percent."""
    assert band.classify(30.0 * 0.95, FAST, gpu_busy=100.0)[0] == "fast"   # noise
    assert band.classify(30.0 / 1.21, FAST, gpu_busy=100.0)[0] == "slow"   # dense band gap
    assert band.classify(30.0 / 2.0, FAST, gpu_busy=100.0)[0] == "slow"    # hybrid band gap


def test_tolerance_boundary_is_inclusive():
    floor = 30.0 * (1 - band.STEP_TOLERANCE)
    assert band.classify(floor, FAST, gpu_busy=100.0)[0] == "fast"
    assert band.classify(floor - 0.01, FAST, gpu_busy=100.0)[0] == "slow"


def test_missing_step_rate_is_undecided():
    assert band.classify(None, FAST, gpu_busy=100.0)[0] == "undecided"


def test_idle_gpus_are_undecided_not_slow():
    """If the GPUs were not decoding, the whole measurement is void - don't report a band."""
    verdict, reasons = band.classify(2.0, FAST, mem_busy=5.0, gpu_busy=3.0)
    assert verdict == "undecided", reasons
    assert any("not decoding" in r for r in reasons)


# ─── classify: mem_busy corroborates, it never decides ───────────────────────────────

def test_mem_busy_cannot_by_itself_call_a_server_slow():
    """The upstream 24-27%/62-67% clusters do not transfer to this rig.

    A healthy server here sampled 36.7-37.5%. A mem_busy far from any upstream cluster must
    not override a step rate that matches the baseline.
    """
    verdict, _ = band.classify(29.5, FAST, mem_busy=26.0, gpu_busy=100.0)
    assert verdict == "fast"


def test_mem_busy_matching_fast_baseline_downgrades_a_slow_call_to_undecided():
    """Split signal: don't tell someone to restart a server on a contradiction."""
    verdict, reasons = band.classify(15.0, FAST, mem_busy=37.0, gpu_busy=100.0)
    assert verdict == "undecided", reasons
    assert any("split signal" in r for r in reasons)


def test_mem_busy_disagreement_does_not_block_a_fast_verdict():
    """"Carry on" is the safe outcome, so it does not need both signals to agree."""
    assert band.classify(29.5, FAST, mem_busy=5.0, gpu_busy=100.0)[0] == "fast"


def test_baseline_without_mem_busy_still_decides_on_steps():
    b = {"steps_s": 30.0}
    assert band.classify(15.0, b, mem_busy=37.0, gpu_busy=100.0)[0] == "slow"


# ─── busy_under_load ─────────────────────────────────────────────────────────────────

def test_busy_under_load_drops_idle_samples():
    rows = [(2.0, 1.0), (100.0, 36.0), (100.0, 38.0), (0.0, 0.0)]
    gpu, mem, n = band.busy_under_load(rows)
    assert (gpu, mem, n) == (100.0, 37.0, 2)


def test_busy_under_load_drops_unused_cards_on_a_partial_tp_spawn():
    """A TP2 spawn in a 4-card box: the two idle cards must be dropped, not averaged in.

    Averaged across cards the mean gpu_busy would be ~50%, below the floor, and the whole
    run would come back "undecided" on a healthy server.
    """
    rows = [(100.0, 36.0), (1.0, 0.0), (100.0, 38.0), (2.0, 1.0)] * 3
    gpu, mem, n = band.busy_under_load(rows)
    assert (gpu, mem, n) == (100.0, 37.0, 6)


def test_busy_under_load_with_no_loaded_samples():
    assert band.busy_under_load([(1.0, 1.0), (2.0, 0.0)]) == (None, None, 0)


def test_busy_under_load_on_empty_input():
    assert band.busy_under_load([]) == (None, None, 0)


# ─── sysfs reading ───────────────────────────────────────────────────────────────────

def test_cards_finds_and_orders_numerically():
    with tempfile.TemporaryDirectory() as d:
        _sysfs(d, {"card0": (100, 37), "card1": (100, 37), "card2": (100, 37),
                   "card10": (100, 37)})
        assert [c.name for c in band.cards(Path(d))] == ["card0", "card1", "card2", "card10"]


def test_cards_ignores_drm_connector_directories():
    """/sys/class/drm has a directory per connector too: card0-DP-1, card1-Writeback-2, ...

    A card[0-9]* glob matches those and then dies parsing "0-DP-1" as an int, which is exactly
    what happened on the first live run against a real server. The earlier fixture only ever
    created card<N> directories, so it could not catch it.
    """
    with tempfile.TemporaryDirectory() as d:
        _sysfs(d, {"card0": (100, 37), "card1": (100, 37),
                   "card0-DP-1": (100, 37), "card1-Writeback-2": (100, 37),
                   "renderD128": (100, 37)})
        assert [c.name for c in band.cards(Path(d))] == ["card0", "card1"]


def test_cards_skips_devices_without_the_counters():
    with tempfile.TemporaryDirectory() as d:
        _sysfs(d, {"card0": (100, 37), "card1": None})
        assert [c.name for c in band.cards(Path(d))] == ["card0"]


def test_read_percent_parses_and_tolerates_garbage():
    with tempfile.TemporaryDirectory() as d:
        _sysfs(d, {"card0": (100, 37)})
        c = Path(d) / "card0"
        assert band.read_percent(c, "gpu") == 100.0
        assert band.read_percent(c, "mem") == 37.0
        (c / "device" / "mem_busy_percent").write_text("not-a-number\n")
        assert band.read_percent(c, "mem") is None
        assert band.read_percent(Path(d) / "card9", "gpu") is None


def test_sample_busy_keeps_cards_separate_and_stops_when_asked():
    with tempfile.TemporaryDirectory() as d:
        _sysfs(d, {"card0": (100, 36), "card1": (100, 38)})
        cl = band.cards(Path(d))
        stop = threading.Event()
        rows = []

        def run():
            rows.extend(band.sample_busy(cl, stop, interval=0.0))

        t = threading.Thread(target=run)
        t.start()
        time.sleep(0.2)            # let it actually sample before asking it to stop
        stop.set()
        t.join(timeout=5)
        assert not t.is_alive()
        assert rows, "sampler returned nothing; the rest of this test would pass vacuously"
        assert {m for _, m in rows} == {36.0, 38.0}, "cards were averaged together"
        assert all(g == 100.0 for g, _ in rows)


# ─── baselines ───────────────────────────────────────────────────────────────────────

def test_baseline_round_trips_and_is_used_by_classify():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sub" / "band-baselines.json"
        m = {"steps_s": 30.0, "tok_s": 70.0, "mem_busy": 37.0, "accepted_per_step": 2.33}
        rec = band.save_baseline("prof", m, p, now="2026-10-17T00:00:00Z")
        assert rec["steps_s"] == 30.0
        assert rec["calibrated"] == "2026-10-17T00:00:00Z"
        loaded = band.load_baselines(p)["prof"]
        assert band.classify(29.5, loaded, gpu_busy=100.0)[0] == "fast"
        assert band.classify(15.0, loaded, gpu_busy=100.0)[0] == "slow"


def test_save_baseline_keeps_other_profiles():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.json"
        band.save_baseline("a", {"steps_s": 1.0, "tok_s": 1.0, "mem_busy": 1.0,
                                 "accepted_per_step": 1.0}, p)
        band.save_baseline("b", {"steps_s": 2.0, "tok_s": 2.0, "mem_busy": 2.0,
                                 "accepted_per_step": 2.0}, p)
        data = json.loads(p.read_text())
        assert set(data) == {"a", "b"}
        assert data["a"]["steps_s"] == 1.0


def test_load_baselines_tolerates_missing_and_corrupt_files():
    with tempfile.TemporaryDirectory() as d:
        assert band.load_baselines(Path(d) / "nope.json") == {}
        bad = Path(d) / "bad.json"
        bad.write_text("{not json")
        assert band.load_baselines(bad) == {}


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


# ─── warmup ──────────────────────────────────────────────────────────────────────────

MEASURED = {"steps_s": 36.0, "mem_busy": 46.0, "gpu_busy": 100.0,
            "tok_s": 81.0, "accepted_per_step": 2.25}


def _main_with_stubs(extra_args, warmup, measure):
    """Run main() with warmup/measure replaced, restoring them afterwards."""
    real_w, real_m = band.warmup, band.measure
    band.warmup, band.measure = warmup, measure
    try:
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "b.json"
            base.write_text(json.dumps({"x": {"steps_s": 36.0, "mem_busy": 46.0}}))
            return band.main(["--model", "x", "--baselines", str(base), "--json", *extra_args])
    finally:
        band.warmup, band.measure = real_w, real_m


def test_warmup_runs_before_the_measured_decode_by_default():
    """The measured run must not be the server's first decode.

    A server's first decode after startup runs ~12% below steady state, which is the same
    order as the slow-band tolerance, so an unwarmed probe of a healthy cold spawn reads
    `undecided`. The ordering is the whole point: warm first, then measure.
    """
    calls = []
    rc = _main_with_stubs(
        [],
        lambda base, model, tok, timeout: calls.append(("warmup", tok)),
        lambda *a, **k: (calls.append(("measure", None)), MEASURED)[1])
    assert rc == 0
    assert calls == [("warmup", 128), ("measure", None)], calls


def test_warmup_tokens_zero_skips_it():
    """Needed to diagnose the warmup effect itself; nothing else should use it."""
    calls = []
    rc = _main_with_stubs(
        ["--warmup-tokens", "0"],
        lambda *a, **k: calls.append("warmup"),
        lambda *a, **k: MEASURED)
    assert rc == 0
    assert calls == [], calls


def test_a_failing_warmup_does_not_become_a_band_verdict():
    """A warmup that cannot reach the server must not be reported as slow, or at all.

    The real request is what surfaces an unreachable server, as "undecided"/2.
    """
    r = _run(["--model", "nope", "--base", "http://127.0.0.1:1", "--json", "--timeout", "3"])
    assert r.returncode == 2, r.stderr
    assert '"verdict": "undecided"' in r.stdout


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
