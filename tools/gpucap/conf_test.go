package main

import (
	"strings"
	"testing"
)

// TestParseConfNoDefaults is the install-time contract: nothing configured must mean nothing
// asked for. A missing, empty or malformed config must not produce a cap or any tuning, because
// `gpucap apply` runs at every boot and after every resume on machines that want neither.
func TestParseConfNoDefaults(t *testing.T) {
	for _, tc := range []struct {
		name string
		in   string
	}{
		{"missing file", ""},
		{"blank lines", "\n\n  \n"},
		{"garbage", "this is not a config\nCAP_W=abc\nUV_MV=lots\n"},
		{"zeros only", "UV_MV=0\nSCLK_MHZ=0\nMCLK_MHZ=0\n"},
		{"cap zero", "CAP_W=0\nUV_MV=0\nSCLK_MHZ=0\nMCLK_MHZ=0\n"},
		{"cap negative", "CAP_W=-400\n"},
		{"limits only", "UV_LIMIT_MV=80\nSCLK_LIMIT_MHZ=100\nMCLK_LIMIT_MHZ=1280\n"},
	} {
		c := parseConf([]byte(tc.in))
		if c.capSet {
			t.Errorf("%s: capSet is true (capW=%d), so a cap would be applied", tc.name, c.capW)
		}
		if c.odRequested() {
			t.Errorf("%s: odRequested is true (uv=%d sclk=%d mclk=%d), so pp_od_clk_voltage would be written",
				tc.name, c.uvMV, c.sclkMHz, c.mclkMHz)
		}
		if p := planApply(c, false); !p.nothing() {
			t.Errorf("%s: planApply = %+v, want nothing to do", tc.name, p)
		}
		// the limits must still be populated -- they only ever refuse a value
		if c.uvLimit <= 0 || c.sclkLimit <= 0 || c.mclkLimit <= 0 {
			t.Errorf("%s: limits not set: %+v", tc.name, c)
		}
	}
}

func TestParseConfRequests(t *testing.T) {
	for _, tc := range []struct {
		name    string
		in      string
		capSet  bool
		capW    int
		od      bool
		nothing bool
	}{
		{"cap only", "CAP_W=200\n", true, 200, false, false},
		{"undervolt only", "UV_MV=-50\n", false, 0, true, false},
		{"core offset only", "SCLK_MHZ=100\n", false, 0, true, false},
		{"negative core offset", "SCLK_MHZ=-100\n", false, 0, true, false},
		{"memory clock only", "MCLK_MHZ=1310\n", false, 0, true, false},
		{"cap and undervolt", "CAP_W=200\nUV_MV=-50\n", true, 200, true, false},
		{"spaces and comments", " CAP_W = 200 \n# a comment\n", true, 200, false, false},
	} {
		c := parseConf([]byte(tc.in))
		if c.capSet != tc.capSet || c.capW != tc.capW {
			t.Errorf("%s: capSet=%v capW=%d, want %v %d", tc.name, c.capSet, c.capW, tc.capSet, tc.capW)
		}
		if c.odRequested() != tc.od {
			t.Errorf("%s: odRequested=%v, want %v", tc.name, c.odRequested(), tc.od)
		}
		p := planApply(c, false)
		if p.nothing() != tc.nothing {
			t.Errorf("%s: planApply = %+v, nothing=%v want %v", tc.name, p, p.nothing(), tc.nothing)
		}
		if p.cap != tc.capSet || p.od != tc.od {
			t.Errorf("%s: planApply = %+v, want cap=%v od=%v", tc.name, p, tc.capSet, tc.od)
		}
	}
}

// a watts argument on the command line (`gpucap apply 200`) is an explicit request, so it applies
// a cap even with no config -- but it still must not drag any voltage or clock write along.
func TestPlanApplyOverride(t *testing.T) {
	p := planApply(parseConf(nil), true)
	if !p.cap || p.od || p.nothing() {
		t.Errorf("planApply(empty, override) = %+v, want cap only", p)
	}
}

// saving a voltage offset on a host with no cap must not invent a CAP_W line, and must not
// overwrite an operator's unparseable one with a zero.
func TestConfTextOmitsUnsetCap(t *testing.T) {
	c := parseConf([]byte("CAP_W=not-a-number\n"))
	c.uvMV = -50
	out := confText(c)
	if strings.Contains(out, "CAP_W") {
		t.Errorf("confText wrote a CAP_W line with no cap configured:\n%s", out)
	}
	if !strings.Contains(out, "UV_MV=-50\n") {
		t.Errorf("confText lost the voltage offset:\n%s", out)
	}
	// and a configured cap must round-trip
	c.capW, c.capSet = 200, true
	if out := confText(c); !strings.Contains(out, "CAP_W=200\n") {
		t.Errorf("confText dropped a configured cap:\n%s", out)
	}
	if got := parseConf([]byte(confText(c))); !got.capSet || got.capW != 200 || got.uvMV != -50 {
		t.Errorf("round trip lost settings: %+v", got)
	}
}

// planOD still writes zeros when asked to, because `sudo gpucap undervolt 0` is how an operator
// resets an offset. The boot path avoids it by not calling applyOD at all (planApply above).
func TestPlanODStillResetsOnRequest(t *testing.T) {
	tbl := parseOD(sample)
	cmds, err := planOD(tbl, true, limits(0, 0, 0), false)
	if err != nil {
		t.Fatalf("planOD: %v", err)
	}
	joined := strings.Join(cmds, ";")
	if !strings.Contains(joined, "vo 0") {
		t.Errorf("explicit zero no longer resets the voltage offset: %q", joined)
	}
}
