package main

// OverDrive: GFX voltage offset, core clock offset and memory max clock on RDNA3/RDNA4, through
// pp_od_clk_voltage. Needs amdgpu.ppfeaturemask with the OverDrive bit (0x4000) set; otherwise the
// file does not exist and every setting is reported as unavailable.
//
// Commands as the SMU13/SMU14 driver code parses them (see smu_v14_0_2_od_edit_dpm_table):
//
//	vo <mV>        voltage offset, applied to the whole V/F curve
//	s <MHz>        core clock offset (a single value, no index)
//	m 1 <MHz>      memory max clock (index 0 would be the minimum)
//	r              restore the boot table (all OverDrive settings)
//	c              commit what was staged
//
// The driver range-checks every value and rejects bad ones with EINVAL.

import (
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
)

const odFile = "/pp_od_clk_voltage"

// odTable is the parsed contents of pp_od_clk_voltage. hasX is false when the card does not list that setting.
type odTable struct {
	hasV, hasS, hasM bool
	vo, voLo, voHi   int // voltage offset and its range, mV
	sclk, sLo, sHi   int // core clock offset and its range, MHz
	mMin, mMax       int // current memory min/max clock, MHz
	mLo, mHi         int // allowed memory clock range, MHz
}

// odSettings is what gpucap wants the card to be set to, plus its own safety limits.
type odSettings struct {
	uv, sclk, mclk int // mV offset (<=0), MHz offset, memory max MHz (0 = leave at stock)
	uvLimit        int // deepest undervolt allowed, mV magnitude
	sclkLimit      int // largest core clock offset allowed, MHz
	mclkLimit      int // highest memory max clock allowed, MHz
}

func (c conf) od() odSettings {
	return odSettings{c.uvMV, c.sclkMHz, c.mclkMHz, c.uvLimit, c.sclkLimit, c.mclkLimit}
}

var (
	reVO     = regexp.MustCompile(`(?mi)^OD_VDDGFX_OFFSET:\s*\n\s*(-?\d+)\s*mV`)
	reVORng  = regexp.MustCompile(`(?mi)^VDDGFX_OFFSET:\s*(-?\d+)\s*mV\s+(-?\d+)\s*mV`)
	reS      = regexp.MustCompile(`(?mi)^OD_SCLK_OFFSET:\s*\n\s*(-?\d+)\s*MHz`)
	reSRng   = regexp.MustCompile(`(?mi)^SCLK_OFFSET:\s*(-?\d+)\s*MHz\s+(-?\d+)\s*MHz`)
	reM      = regexp.MustCompile(`(?mi)^OD_MCLK:\s*\n\s*0:\s*(\d+)\s*MHz\s*\n\s*1:\s*(\d+)\s*MHz`)
	reMRange = regexp.MustCompile(`(?mi)^MCLK:\s*(\d+)\s*MHz\s+(\d+)\s*MHz`)
)

func atoi(s string) int { n, _ := strconv.Atoi(s); return n }

// parseOD parses the contents of pp_od_clk_voltage. A setting whose allowed range line is
// missing gets an empty range (nothing but its current value is accepted), which is the safe default.
func parseOD(table string) odTable {
	table = strings.ReplaceAll(table, "\x00", "") // the driver pads sections with NUL bytes
	var t odTable
	if m := reVO.FindStringSubmatch(table); m != nil {
		t.hasV, t.vo = true, atoi(m[1])
		t.voLo, t.voHi = t.vo, t.vo
		if r := reVORng.FindStringSubmatch(table); r != nil {
			t.voLo, t.voHi = atoi(r[1]), atoi(r[2])
		}
	}
	if m := reS.FindStringSubmatch(table); m != nil {
		t.hasS, t.sclk = true, atoi(m[1])
		t.sLo, t.sHi = t.sclk, t.sclk
		if r := reSRng.FindStringSubmatch(table); r != nil {
			t.sLo, t.sHi = atoi(r[1]), atoi(r[2])
		}
	}
	if m := reM.FindStringSubmatch(table); m != nil {
		t.hasM, t.mMin, t.mMax = true, atoi(m[1]), atoi(m[2])
		t.mLo, t.mHi = t.mMin, t.mMax
		if r := reMRange.FindStringSubmatch(table); r != nil {
			t.mLo, t.mHi = atoi(r[1]), atoi(r[2])
		}
	}
	return t
}

func readOD(c card) (odTable, bool) {
	b, err := os.ReadFile(c.dev + odFile)
	if err != nil {
		return odTable{}, false
	}
	t := parseOD(string(b))
	return t, t.hasV || t.hasS || t.hasM
}

// planOD validates s against what the card reports and gpucap's own limits and returns the lines to
// write to pp_od_clk_voltage, ending in the commit. reset restores the boot table first, which is the
// only way back to the stock memory clock. Nothing is written if it returns an error.
func planOD(t odTable, avail bool, s odSettings, reset bool) ([]string, error) {
	if !avail {
		if s.uv == 0 && s.sclk == 0 && s.mclk == 0 && !reset {
			return nil, nil // nothing asked for, nothing to do
		}
		return nil, fmt.Errorf("voltage/clock tuning unavailable (is amdgpu.ppfeaturemask OverDrive bit 0x4000 set?)")
	}
	var cmds []string
	if reset {
		cmds = append(cmds, "r")
	}
	switch {
	case t.hasV:
		lo := max(t.voLo, -s.uvLimit)
		if s.uv < lo || s.uv > t.voHi {
			return nil, fmt.Errorf("voltage offset %dmV outside allowed %d..%dmV (raise UV_LIMIT_MV in %s to go deeper)", s.uv, lo, t.voHi, confPath)
		}
		cmds = append(cmds, fmt.Sprintf("vo %d", s.uv))
	case s.uv != 0:
		return nil, fmt.Errorf("voltage offset not supported by this card")
	}
	switch {
	case t.hasS:
		hi := min(t.sHi, s.sclkLimit)
		if s.sclk < t.sLo || s.sclk > hi {
			return nil, fmt.Errorf("core clock offset %+dMHz outside allowed %d..%dMHz (raise SCLK_LIMIT_MHZ in %s to go higher)", s.sclk, t.sLo, hi, confPath)
		}
		cmds = append(cmds, fmt.Sprintf("s %d", s.sclk))
	case s.sclk != 0:
		return nil, fmt.Errorf("core clock offset not supported by this card")
	}
	if s.mclk != 0 {
		if !t.hasM {
			return nil, fmt.Errorf("memory clock not supported by this card")
		}
		lo, hi := max(t.mLo, t.mMin), min(t.mHi, s.mclkLimit)
		if s.mclk < lo || s.mclk > hi {
			return nil, fmt.Errorf("memory clock %dMHz outside allowed %d..%dMHz (raise MCLK_LIMIT_MHZ in %s to go higher)", s.mclk, lo, hi, confPath)
		}
		cmds = append(cmds, fmt.Sprintf("m 1 %d", s.mclk))
	}
	return append(cmds, "c"), nil
}

// applyOD plans, writes and verifies s on every card. Cards are planned before anything is written,
// so a bad value is rejected everywhere rather than applied to the first few cards only.
func applyOD(cards []card, s odSettings, reset bool) error {
	plans := make([][]string, len(cards))
	var failed int
	for i, c := range cards {
		t, ok := readOD(c)
		plan, err := planOD(t, ok, s, reset)
		if err != nil {
			fmt.Fprintf(os.Stderr, "%s: %v\n", c.name, err)
			failed++
		}
		plans[i] = plan
	}
	if failed > 0 {
		return fmt.Errorf("%d card(s) rejected the settings; nothing applied", failed)
	}
	for i, c := range cards {
		if len(plans[i]) == 0 {
			continue
		}
		var err error
		for _, cmd := range plans[i] {
			if err = os.WriteFile(c.dev+odFile, []byte(cmd+"\n"), 0); err != nil {
				err = fmt.Errorf("%q: %w", cmd, err)
				break
			}
		}
		if err == nil {
			err = verifyOD(c, s)
		}
		if err != nil {
			fmt.Fprintf(os.Stderr, "%s: %v\n", c.name, err)
			failed++
			continue
		}
		t, _ := readOD(c)
		fmt.Printf("%s %s\n", c.name, t.summary())
	}
	if failed > 0 {
		return fmt.Errorf("%d card(s) failed", failed)
	}
	return nil
}

// verifyOD re-reads the table and checks the values stuck.
func verifyOD(c card, s odSettings) error {
	t, _ := readOD(c)
	if t.hasV && t.vo != s.uv {
		return fmt.Errorf("wrote %dmV voltage offset but read back %dmV", s.uv, t.vo)
	}
	if t.hasS && t.sclk != s.sclk {
		return fmt.Errorf("wrote %+dMHz core offset but read back %+dMHz", s.sclk, t.sclk)
	}
	if s.mclk != 0 && t.mMax != s.mclk {
		return fmt.Errorf("wrote %dMHz memory max but read back %dMHz", s.mclk, t.mMax)
	}
	return nil
}

func (t odTable) summary() string {
	var p []string
	if t.hasV {
		p = append(p, fmt.Sprintf("voltage=%dmV", t.vo))
	}
	if t.hasS {
		p = append(p, fmt.Sprintf("sclk=%+dMHz", t.sclk))
	}
	if t.hasM {
		p = append(p, fmt.Sprintf("mclk-max=%dMHz", t.mMax))
	}
	return strings.Join(p, " ")
}
