package main

import (
	"testing"
	"time"
)

// feed drives applyData with a synthetic generation-token counter so the rate
// llmpanel computes is deterministic: it is a difference quotient over the poll
// interval, exactly as the live path computes it.
func feed(a *app, model string, genTotal float64, at time.Time) {
	g := genTotal
	a.applyData(AppData{
		Active:    &ActiveModel{ID: model, Port: 9100},
		Metrics:   &VLLMMetrics{GenTotal: &g},
		FetchedAt: at,
	})
}

// The peak must belong to the model that set it. Before this was fixed, peakTokPerS
// was a running max that was never cleared on a model change, so a figure read off
// the panel while watching one profile could have been set by any profile loaded
// earlier in the same llmpanel process. During a benchmark sweep that swaps
// profiles that is exactly what happened, and nothing in the display said so --
// the number was real but its provenance was unattributable.
func TestPeakResetsWhenModelChanges(t *testing.T) {
	a := newApp("http://127.0.0.1:8080", time.Second, "/nonexistent.yaml",
		"/nonexistent.log")
	t0 := time.Date(2026, 10, 19, 12, 0, 0, 0, time.UTC)

	// Fast profile: 1000 tokens in one second, then 1300 in the next.
	feed(a, "fast-profile", 0, t0)
	feed(a, "fast-profile", 1000, t0.Add(time.Second))
	feed(a, "fast-profile", 2300, t0.Add(2*time.Second))
	if a.peakTokPerS < 1299 || a.peakTokPerS > 1301 {
		t.Fatalf("peak after fast profile = %.1f, want ~1300", a.peakTokPerS)
	}

	// Swap to a slower profile and serve 100 tok/s.
	feed(a, "slow-profile", 0, t0.Add(3*time.Second))
	feed(a, "slow-profile", 100, t0.Add(4*time.Second))
	feed(a, "slow-profile", 200, t0.Add(5*time.Second))

	if a.peakTokPerS > 101 {
		t.Fatalf("peak after swap = %.1f: the previous profile's %.0f tok/s"+
			" survived the model change, which is the attribution bug",
			a.peakTokPerS, 1300.0)
	}
	if a.peakTokPerS < 99 {
		t.Fatalf("peak after swap = %.1f, want ~100 from the new profile;"+
			" the reset must not also discard the current rate", a.peakTokPerS)
	}

	// The sparkline history must be cleared too, or the new profile's graph is
	// drawn against the old profile's scale and reads as a collapse.
	d := a.tokHist.ActiveStats()
	if d.Peak > 101 {
		t.Fatalf("history peak after swap = %.1f, want <=100: the old"+
			" profile's samples are still in the ring", d.Peak)
	}
}

// The cursor-snap used to re-test currID != a.prevModelID after that field had
// already been assigned, so it could never fire. This pins that a swap is still
// observable to the rest of applyData after the reset block runs.
func TestModelChangeIsStillObservableAfterReset(t *testing.T) {
	a := newApp("http://127.0.0.1:8080", time.Second, "/nonexistent.yaml",
		"/nonexistent.log")
	t0 := time.Date(2026, 10, 19, 12, 0, 0, 0, time.UTC)
	feed(a, "a-profile", 0, t0)
	if a.prevModelID != "a-profile" {
		t.Fatalf("prevModelID = %q, want a-profile", a.prevModelID)
	}
	// Same model again: no reset, so the peak accumulates.
	feed(a, "a-profile", 500, t0.Add(time.Second))
	if a.peakTokPerS < 499 {
		t.Fatalf("peak = %.1f, want ~500; a same-model tick must not reset",
			a.peakTokPerS)
	}
}
