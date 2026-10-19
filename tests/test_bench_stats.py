#!/usr/bin/env python3
"""
Unit tests for the statistics helpers in bench/depth_bench.py: pct(), dist() and
MetricsSampler.summary(). No GPU and no server -- the sampler's sample list is
populated directly.

These exist because a throughput figure without a distribution behind it is not a
measurement. Two specific traps are pinned here:

  1. pct() must be nearest-rank with ROUND-HALF-UP, and must agree exactly with
     pctRank() in tui/sparkline.go. Python's round() is banker's rounding
     (round(4.5) == 4) and Go's math.Round is half-away-from-zero, so neither
     language's built-in matches the other by accident. floor(x + 0.5) matches on
     both, so a figure read off llmpanel and a figure read out of a saved baseline
     mean the same thing.

  2. The saturated subset must be a HIGH-WATER band, not the modal running-count.
     The mode picks the wrong samples in exactly the regime that matters most: at
     deep prompts and high concurrency the ramp-in is LONGER than the plateau, so
     the mode selects the ramp and reports it as steady state -- precisely
     backwards. This was a real bug in the first implementation, caught by the
     synthetic series below.

Run:  python3 tests/test_bench_stats.py        (also pytest-compatible)
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "depth_bench_under_test", REPO / "bench" / "depth_bench.py")
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)


def _ramp_then_plateau():
    """A series shaped like a real deep-and-wide cell.

    The ramp is deliberately LONGER than the plateau (12 samples against 10),
    because that is what actually happens: at 32 streams and a deep prompt most of
    the wall clock is spent with only a few streams decoding while the rest queue
    for prefill. Any rule that picks the most common running-count will pick this
    ramp.
    """
    ramp = [{"dt": 1, "gen_tok_s": r, "prompt_tok_s": 0, "running": 4,
             "waiting": 28}
            for r in (0, 0, 50, 60, 90, 120, 150, 180, 200, 240, 260, 300)]
    plateau = [{"dt": 1, "gen_tok_s": r, "prompt_tok_s": 0, "running": 32,
                "waiting": 0}
               for r in (900, 950, 1000, 1050, 1100, 980, 1020, 1010, 990, 1303)]
    return ramp + plateau


def test_pct_is_nearest_rank_never_interpolated():
    v = sorted([10, 20, 30, 40])
    for q in (0, 0.1, 0.25, 0.5, 0.75, 0.9, 1):
        got = db.pct(v, q)
        assert got in v, (
            "pct(%r, %r) = %r is not an observed value; the cells are measured "
            "at a handful of concurrency levels and interpolating between four "
            "observations invents precision" % (v, q, got))


def test_pct_rounds_half_up_not_bankers():
    # n=4, q=0.5 -> floor(0.5*3 + 0.5) = 2, the upper-middle value. Python's
    # round() would give 1 here (banker's rounding on 1.5), silently picking the
    # lower-middle value and disagreeing with the Go implementation.
    assert db.pct([10, 20, 30, 40], 0.5) == 30
    assert db.pct([10, 20, 30, 40], 0.0) == 10
    assert db.pct([10, 20, 30, 40], 1.0) == 40


def test_pct_degenerate_inputs():
    assert db.pct([], 0.9) is None
    assert db.pct([42.0], 0.9) == 42.0
    # Out-of-range quantiles clamp rather than raising an IndexError.
    assert db.pct([1, 2, 3], 5) == 3
    assert db.pct([1, 2, 3], -1) == 1


def test_dist_flags_degenerate_sample_sizes():
    d = db.dist([10, 20, 30, 40])
    assert d["n"] == 4
    assert d["percentiles_meaningful"] is False, (
        "below n=10 a 'p10' and a 'p90' are just the min and the max; publishing "
        "them as percentiles overstates what was measured")
    assert d["p10"] == d["min"] and d["p90"] == d["max"]

    d20 = db.dist(list(range(1, 21)))
    assert d20["percentiles_meaningful"] is True
    assert d20["min"] == 1 and d20["max"] == 20
    assert d20["p50"] == 11  # floor(0.5*19 + 0.5) = 10 -> the 11th value


def test_dist_empty_and_all_none():
    assert db.dist([]) is None
    assert db.dist([None]) is None
    assert db.dist([None, None]) is None
    # A single real value among Nones is still a distribution of one.
    d = db.dist([None, 7.5, None])
    assert d["n"] == 1 and d["p50"] == 7.5 and d["stdev"] == 0.0


def test_saturation_is_high_water_not_the_mode():
    s = db.MetricsSampler("http://unused", 1.0)
    s.samples = _ramp_then_plateau()
    summ = s.summary()

    assert summ["max_running_requests"] == 32
    assert summ["modal_running_requests"] == 4, (
        "the mode IS the ramp in this series -- that is the trap the high-water "
        "rule avoids, and it is still reported so a reader can see it")
    assert summ["saturation_threshold_requests"] == 0.9 * 32

    sat = summ["decode_tok_s_saturated"]
    assert sat["n"] == 10, (
        "the saturated subset must be the plateau (10 samples), not the ramp (12)")
    assert sat["max"] == 1303
    assert sat["min"] == 900


def test_zero_decode_ticks_are_excluded_but_counted():
    """A tick inside the band that emitted no tokens is not a slow decode.

    It is a second the engine spent on a prefill chunk. Measured on a real
    2048 x conc=32 cell, 9 of 39 ticks inside the saturated band emitted nothing,
    which made the reported floor and p10 read 0.0 tok/s -- a figure no client ever
    experienced as a decode rate. They are dropped from the distribution and
    counted, because the count is what explains why these percentiles sit above
    the run average.
    """
    s = db.MetricsSampler("http://unused", 1.0)
    s.samples = [{"dt": 1, "gen_tok_s": r, "prompt_tok_s": 0, "running": 32,
                  "waiting": 0}
                 for r in (0, 1000, 0, 1100, 900, 0, 1050)]
    summ = s.summary()
    sat = summ["decode_tok_s_saturated"]
    assert sat["n"] == 4, "zero ticks must not be in the decode distribution"
    assert sat["min"] == 900, (
        "the floor must be the slowest decoding second (900), not 0.0")
    assert summ["n_samples_in_band"] == 7
    assert summ["n_zero_decode_ticks_in_band"] == 3
    assert abs(summ["zero_decode_tick_fraction_in_band"] - 3 / 7) < 1e-9
    # decode_tok_s_all must filter them too, or the two distributions in one
    # summary would use different rules.
    assert summ["decode_tok_s_all"]["n"] == 4


def test_ramp_dilution_is_visible_in_the_two_medians():
    s = db.MetricsSampler("http://unused", 1.0)
    s.samples = _ramp_then_plateau()
    summ = s.summary()
    alls = summ["decode_tok_s_all"]
    sat = summ["decode_tok_s_saturated"]
    assert sat["p50"] > alls["p50"], (
        "excluding the ramp must raise the median, otherwise the subset logic is "
        "inert and the reported steady-state rate is diluted by the ramp-in")
    # peak_over_median is the figure that explains why a live panel's peak and a
    # benchmark's run average disagree: the peak is a max over noisy one-second
    # difference quotients.
    assert 1.2 < summ["peak_over_median"] < 1.4


def test_summary_on_an_empty_or_idle_series():
    s = db.MetricsSampler("http://unused", 1.0)
    s.samples = []
    assert s.summary() is None, (
        "nothing sampled must store an honest null, not a distribution over an "
        "empty window")

    # All-idle: running is 0 everywhere, so there is no high-water band to take.
    s.samples = [{"dt": 1, "gen_tok_s": 0, "prompt_tok_s": 0, "running": 0,
                  "waiting": 0} for _ in range(5)]
    summ = s.summary()
    assert summ["max_running_requests"] is None
    assert summ["decode_tok_s_all"] is None, (
        "an all-zero window has no decoding seconds in it at all")
    assert summ["decode_tok_s_saturated"] is None, (
        "an idle window is no distribution; reporting one would describe the "
        "operator's afternoon rather than the hardware")


def test_prefill_series_excludes_zero_ticks():
    s = db.MetricsSampler("http://unused", 1.0)
    s.samples = [
        {"dt": 1, "gen_tok_s": 100, "prompt_tok_s": 0, "running": 8, "waiting": 0},
        {"dt": 1, "gen_tok_s": 100, "prompt_tok_s": 4000, "running": 8,
         "waiting": 0},
        {"dt": 1, "gen_tok_s": 100, "prompt_tok_s": 4400, "running": 8,
         "waiting": 0},
    ]
    pf = s.summary()["prefill_tok_s_nonzero"]
    assert pf["n"] == 2, (
        "prefill happens in bursts, so the zero ticks between them are not slow "
        "prefill -- averaging them in would understate the rate by the duty cycle")
    assert pf["min"] == 4000 and pf["max"] == 4400


def test_pct_matches_the_go_implementation_index_rule():
    """Guard the cross-language contract explicitly.

    tui/sparkline.go computes int(math.Floor(q*float64(len-1) + 0.5)). If either
    side ever switches to an interpolating percentile or to a language built-in,
    this is the test that fails.
    """
    import math
    for n in range(1, 40):
        v = list(range(n))
        for q in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
            want = min(max(int(math.floor(q * (n - 1) + 0.5)), 0), n - 1)
            assert db.pct(v, q) == v[want], (n, q)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok   %s" % name)
            except AssertionError as e:
                failed += 1
                print("FAIL %s: %s" % (name, e))
    print("\n%d failed" % failed)
    sys.exit(1 if failed else 0)
