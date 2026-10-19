package main

import (
	"fmt"
	"math"
	"sort"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

const maxHistory = 512

// braille encodes two vertical bar levels (0-4) per cell: braille[left*5+right]
const braille = " ⢀⢠⢰⢸⡀⣀⣠⣰⣸⡄⣄⣤⣴⣼⡆⣆⣦⣶⣾⡇⣇⣧⣷⣿"

type RingBuffer struct {
	data  [maxHistory]float64
	index int
	count int
}

func (r *RingBuffer) Push(v float64) {
	r.data[r.index] = v
	r.index = (r.index + 1) % maxHistory
	if r.count < maxHistory {
		r.count++
	}
}

func (r *RingBuffer) Values() []float64 {
	if r.count == 0 {
		return nil
	}
	out := make([]float64, r.count)
	start := (r.index - r.count + maxHistory) % maxHistory
	for i := 0; i < r.count; i++ {
		out[i] = r.data[(start+i)%maxHistory]
	}
	return out
}

type colorStop struct {
	pos     float64
	r, g, b uint8
}

type gradient [101][3]uint8

func buildGradient(stops []colorStop) gradient {
	var g gradient
	for i := 0; i <= 100; i++ {
		v := float64(i)
		for j := 0; j < len(stops)-1; j++ {
			s0, s1 := stops[j], stops[j+1]
			if v <= s1.pos {
				t := (v - s0.pos) / (s1.pos - s0.pos)
				g[i][0] = uint8(float64(s0.r) + float64(int(s1.r)-int(s0.r))*t)
				g[i][1] = uint8(float64(s0.g) + float64(int(s1.g)-int(s0.g))*t)
				g[i][2] = uint8(float64(s0.b) + float64(int(s1.b)-int(s0.b))*t)
				break
			}
		}
	}
	last := stops[len(stops)-1]
	g[100] = [3]uint8{last.r, last.g, last.b}
	return g
}

// tokGradient: cyan (idle/low) → green → yellow → orange → red (peak)
var tokGradient = buildGradient([]colorStop{
	{0, 0, 180, 220},
	{40, 0, 215, 100},
	{70, 180, 215, 0},
	{88, 255, 130, 0},
	{100, 255, 30, 0},
})

func clampIdx(v float64) int {
	if v < 0 {
		return 0
	}
	if v > 100 {
		return 100
	}
	return int(v)
}

func rgbStyle(r, g, b uint8) lipgloss.Style {
	return lipgloss.NewStyle().Foreground(lipgloss.Color(fmt.Sprintf("#%02x%02x%02x", r, g, b)))
}

func normalizeToLevels(value, vmin, vmax float64, total int) int {
	if vmax <= vmin || value <= vmin {
		return 0
	}
	if value >= vmax {
		return total
	}
	t := (value - vmin) / (vmax - vmin)
	level := int(t * float64(total))
	if level < 1 {
		level = 1
	}
	if level > total {
		level = total
	}
	return level
}

func renderMultilineSparkline(history []float64, width, rows int, vmin, vmax float64, grad gradient, gradScale float64) []string {
	result := make([]string, rows)
	if width <= 0 {
		return result
	}

	needed := width * 2
	samples := make([]float64, needed)
	if len(history) >= needed {
		copy(samples, history[len(history)-needed:])
	} else {
		copy(samples[needed-len(history):], history)
	}

	totalLevels := rows * 4
	brailleRunes := []rune(braille)
	emptyStyle := rgbStyle(35, 35, 35)

	rowBuilders := make([]strings.Builder, rows)

	for i := 0; i < width; i++ {
		vl := samples[i*2]
		vr := samples[i*2+1]

		fillL := normalizeToLevels(vl, vmin, vmax, totalLevels)
		fillR := normalizeToLevels(vr, vmin, vmax, totalLevels)
		isEmpty := fillL == 0 && fillR == 0

		avg := (vl + vr) / 2
		pct := 0.0
		if gradScale > 0 {
			pct = avg / gradScale * 100
		}
		c := grad[clampIdx(pct)]
		colStyle := rgbStyle(c[0], c[1], c[2])

		for r := 0; r < rows; r++ {
			levelsBelow := (rows - 1 - r) * 4
			ll := fillL - levelsBelow
			rl := fillR - levelsBelow
			if ll < 0 {
				ll = 0
			}
			if ll > 4 {
				ll = 4
			}
			if rl < 0 {
				rl = 0
			}
			if rl > 4 {
				rl = 4
			}

			if isEmpty || (ll == 0 && rl == 0) {
				rowBuilders[r].WriteString(emptyStyle.Render(string(brailleRunes[0])))
			} else {
				rowBuilders[r].WriteString(colStyle.Render(string(brailleRunes[ll*5+rl])))
			}
		}
	}

	for i := range result {
		result[i] = rowBuilders[i].String()
	}
	return result
}

// Distribution summarises a rolling window of sampled rates.
//
// It exists because "cur" and "peak" alone are misleading. A peak is the maximum
// of a few hundred difference quotients, so it is biased upward by sampling noise
// even when the underlying rate is flat, and it says nothing about what a client
// typically got. The median and the p10 do.
type Distribution struct {
	N    int
	Low  float64
	P10  float64
	P50  float64
	P90  float64
	Peak float64
}

// pctRank is nearest-rank with round-half-up, deliberately identical to pct() in
// bench/depth_bench.py so a panel reading and a saved benchmark row are computed
// the same way and can be compared. Not math.Round: Go's Round is half-away-from-
// zero and Python's round() is banker's rounding, so neither matches the other by
// accident -- floor(x+0.5) matches on both.
func pctRank(sorted []float64, q float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	i := int(math.Floor(q*float64(len(sorted)-1) + 0.5))
	if i < 0 {
		i = 0
	}
	if i > len(sorted)-1 {
		i = len(sorted) - 1
	}
	return sorted[i]
}

// ActiveStats summarises only the ticks in which the server produced tokens.
//
// Idle ticks are excluded on purpose: a stack that has been sitting unused would
// otherwise report a median of zero, which describes the operator's afternoon
// rather than the hardware. N is reported so a distribution computed from a
// handful of active ticks can be recognised as one.
func (r *RingBuffer) ActiveStats() Distribution {
	vals := r.Values()
	act := make([]float64, 0, len(vals))
	for _, v := range vals {
		if v > 0 {
			act = append(act, v)
		}
	}
	if len(act) == 0 {
		return Distribution{}
	}
	sort.Float64s(act)
	return Distribution{
		N:    len(act),
		Low:  act[0],
		P10:  pctRank(act, 0.10),
		P50:  pctRank(act, 0.50),
		P90:  pctRank(act, 0.90),
		Peak: act[len(act)-1],
	}
}

// distLine renders a Distribution as one line, dropping fields from the right as
// the width shrinks. It reports n because a distribution over a handful of active
// ticks is not a distribution; the reader should be able to see that without
// opening the code.
//
// The order of what survives a narrow pane is deliberate: median first, because it
// is the figure a client actually experiences; then p10, because the floor is what
// a slow request feels; then p90 and the extremes, which are the least robust.
func distLine(d Distribution, w int) string {
	if d.N == 0 {
		return stDim.Render("   (no activity sampled yet)")
	}
	full := fmt.Sprintf("   low %s  p10 %s  med %s  p90 %s  peak %s  n=%d",
		fmtRate(d.Low), fmtRate(d.P10), fmtRate(d.P50),
		fmtRate(d.P90), fmtRate(d.Peak), d.N)
	mid := fmt.Sprintf("   p10 %s  med %s  p90 %s  n=%d",
		fmtRate(d.P10), fmtRate(d.P50), fmtRate(d.P90), d.N)
	narrow := fmt.Sprintf("   med %s  n=%d", fmtRate(d.P50), d.N)
	for _, s := range []string{full, mid, narrow} {
		if len(s) <= w {
			return stDim.Render(s)
		}
	}
	return stDim.Render(narrow)
}

func fmtRate(v float64) string {
	if v >= 100 {
		return fmt.Sprintf("%.0f", v)
	}
	return fmt.Sprintf("%.1f", v)
}
