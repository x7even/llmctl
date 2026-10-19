package main

import (
	"math"
	"testing"
)

// pctRank must agree with pct() in bench/depth_bench.py so that a figure read off
// the panel and a figure read out of a saved baseline mean the same thing. The
// convention is nearest-rank with round-half-up and NO interpolation: the cells
// are measured at a handful of concurrency levels, and interpolating between four
// observations invents precision that was never measured.
func TestPctRankIsNearestRankNotInterpolated(t *testing.T) {
	v := []float64{10, 20, 30, 40}
	for _, q := range []float64{0, 0.1, 0.25, 0.5, 0.75, 0.9, 1} {
		got := pctRank(v, q)
		found := false
		for _, x := range v {
			if got == x {
				found = true
			}
		}
		if !found {
			t.Fatalf("pctRank(%v, %v) = %v, which is not an observed value;"+
				" nearest-rank must never interpolate", v, q, got)
		}
	}
	// Round-half-up, not banker's rounding and not half-away-from-zero: q=0.5 on
	// n=4 is index floor(0.5*3+0.5) = 2, i.e. the upper-middle value.
	if got := pctRank(v, 0.5); got != 30 {
		t.Fatalf("p50 of %v = %v, want 30 (round-half-up index 2)", v, got)
	}
	if got := pctRank(v, 0); got != 10 {
		t.Fatalf("p0 = %v, want min 10", got)
	}
	if got := pctRank(v, 1); got != 40 {
		t.Fatalf("p100 = %v, want max 40", got)
	}
}

func TestPctRankDegenerateInputs(t *testing.T) {
	if got := pctRank(nil, 0.9); got != 0 {
		t.Fatalf("pctRank(nil) = %v, want 0", got)
	}
	if got := pctRank([]float64{42}, 0.9); got != 42 {
		t.Fatalf("pctRank(single) = %v, want 42", got)
	}
	// Out-of-range quantiles must clamp rather than panic on an index.
	if got := pctRank([]float64{1, 2, 3}, 5); got != 3 {
		t.Fatalf("pctRank(q=5) = %v, want clamped max 3", got)
	}
	if got := pctRank([]float64{1, 2, 3}, -1); got != 1 {
		t.Fatalf("pctRank(q=-1) = %v, want clamped min 1", got)
	}
}

// ActiveStats must ignore idle ticks. A stack that has been sitting unused would
// otherwise report a median of zero, which describes the operator's afternoon
// rather than the hardware.
func TestActiveStatsExcludesIdleTicks(t *testing.T) {
	var r RingBuffer
	for i := 0; i < 50; i++ {
		r.Push(0) // fifty seconds of nobody using the stack
	}
	for _, v := range []float64{300, 320, 340, 360, 380} {
		r.Push(v)
	}
	d := r.ActiveStats()
	if d.N != 5 {
		t.Fatalf("N = %d, want 5 active ticks (idle ticks must not count)", d.N)
	}
	if d.Low != 300 || d.Peak != 380 {
		t.Fatalf("low/peak = %v/%v, want 300/380", d.Low, d.Peak)
	}
	if d.P50 != 340 {
		t.Fatalf("median = %v, want 340; a zero here means idle ticks leaked in",
			d.P50)
	}
}

func TestActiveStatsEmptyAndAllIdle(t *testing.T) {
	var empty RingBuffer
	if d := empty.ActiveStats(); d.N != 0 {
		t.Fatalf("empty ring: N = %d, want 0", d.N)
	}
	var idle RingBuffer
	for i := 0; i < 10; i++ {
		idle.Push(0)
	}
	if d := idle.ActiveStats(); d.N != 0 {
		t.Fatalf("all-idle ring: N = %d, want 0 -- an all-zero window is no"+
			" distribution at all and must be reported as such", d.N)
	}
}

// The peak is the statistic most often quoted off this panel, and it is a running
// max over 1 s difference quotients, so it is biased upward by sampling noise even
// when the underlying rate is flat. ActiveStats exists so the median is available
// next to it; this test pins the relationship so a future change cannot quietly
// make the two disagree about the same window.
func TestPeakExceedsMedianOnNoisySeries(t *testing.T) {
	var r RingBuffer
	for _, v := range []float64{900, 950, 1000, 1050, 1100, 980, 1020, 1010, 990, 1303} {
		r.Push(v)
	}
	d := r.ActiveStats()
	if d.Peak != 1303 {
		t.Fatalf("peak = %v, want 1303", d.Peak)
	}
	if d.Peak <= d.P50 {
		t.Fatalf("peak %v must exceed median %v on this series", d.Peak, d.P50)
	}
	if infl := d.Peak / d.P50; math.Abs(infl-1.29) > 0.02 {
		t.Fatalf("peak/median = %.3f, want ~1.29 -- the inflation this panel"+
			" is meant to expose", infl)
	}
	if d.N != 10 {
		t.Fatalf("N = %d, want 10", d.N)
	}
}

// distLine must degrade by dropping fields, never by overflowing the pane. An
// overflowing line wraps and silently pushes a row off the bottom of the panel.
func TestDistLineFitsWidth(t *testing.T) {
	var r RingBuffer
	for _, v := range []float64{900, 950, 1000, 1050, 1100, 980, 1020, 1010, 990, 1303} {
		r.Push(v)
	}
	d := r.ActiveStats()
	for _, w := range []int{20, 30, 40, 50, 60, 80, 120, 200} {
		got := distLine(d, w)
		if len([]rune(stripANSI(got))) > w && w >= 24 {
			t.Fatalf("distLine at w=%d produced %d visible chars: %q",
				w, len([]rune(stripANSI(got))), got)
		}
	}
	// With nothing sampled it must say so rather than print zeros, which would
	// read as "the hardware did 0 tok/s".
	if got := distLine(Distribution{}, 80); got == "" {
		t.Fatal("distLine on an empty Distribution returned nothing")
	}
}

// stripANSI removes the style escapes lipgloss may add, so the width assertion
// measures what the terminal shows rather than what the string contains.
func stripANSI(s string) string {
	out := make([]rune, 0, len(s))
	inEsc := false
	for _, c := range s {
		switch {
		case c == 0x1b:
			inEsc = true
		case inEsc && (c == 'm' || c == 'K'):
			inEsc = false
		case !inEsc:
			out = append(out, c)
		}
	}
	return string(out)
}
