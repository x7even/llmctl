package main

import (
	"reflect"
	"strings"
	"testing"
)

// sample mirrors a real Navi 48 (R9700) dump from amdgpu 6.16.6: sections separated by NUL padding,
// mixed Mhz/MHz casing, and the voltage range line in lowercase "mv".
const sample = "OD_SCLK_OFFSET:\n0Mhz\n\x00\x00\x00\x00OD_MCLK:\n0: 97Mhz\n1: 1259MHz\n\x00\x00\x00\x00" +
	"OD_VDDGFX_OFFSET:\n-30mV\n\x00\x00\x00\x00\x00" +
	"OD_RANGE:\nSCLK_OFFSET:    -500Mhz       1000Mhz\nMCLK:      97Mhz       1500Mhz\n" +
	"VDDGFX_OFFSET:    -200mv          0mv\n\x00\x00"

func limits(uv, sclk, mclk int) odSettings {
	return odSettings{uv: uv, sclk: sclk, mclk: mclk, uvLimit: 100, sclkLimit: 150, mclkLimit: 1350}
}

func TestParseOD(t *testing.T) {
	got := parseOD(sample)
	want := odTable{
		hasV: true, hasS: true, hasM: true,
		vo: -30, voLo: -200, voHi: 0,
		sclk: 0, sLo: -500, sHi: 1000,
		mMin: 97, mMax: 1259, mLo: 97, mHi: 1500,
	}
	if got != want {
		t.Fatalf("got %+v\nwant %+v", got, want)
	}
	if parseOD("OD_SCLK:\n0: 500Mhz\n").hasV {
		t.Fatal("expected no voltage entry")
	}
}

func TestPlanOD(t *testing.T) {
	tab := parseOD(sample)
	cases := []struct {
		name    string
		s       odSettings
		reset   bool
		want    []string
		wantErr string
	}{
		{"all stock", limits(0, 0, 0), false, []string{"vo 0", "s 0", "c"}, ""},
		{"undervolt", limits(-50, 0, 0), false, []string{"vo -50", "s 0", "c"}, ""},
		{"all three", limits(-20, 40, 1310), false, []string{"vo -20", "s 40", "m 1 1310", "c"}, ""},
		{"stock memory needs reset", limits(0, 0, 0), true, []string{"r", "vo 0", "s 0", "c"}, ""},
		{"undervolt past gpucap limit", limits(-150, 0, 0), false, nil, "UV_LIMIT_MV"},
		{"core offset past gpucap limit", limits(0, 200, 0), false, nil, "SCLK_LIMIT_MHZ"},
		{"memory past gpucap limit", limits(0, 0, 1400), false, nil, "MCLK_LIMIT_MHZ"},
		{"memory below current min", limits(0, 0, 50), false, nil, "memory clock"},
		{"positive voltage offset", limits(10, 0, 0), false, nil, "voltage offset"},
	}
	for _, c := range cases {
		got, err := planOD(tab, true, c.s, c.reset)
		if c.wantErr != "" {
			if err == nil || !strings.Contains(err.Error(), c.wantErr) {
				t.Errorf("%s: err = %v, want containing %q", c.name, err, c.wantErr)
			}
			continue
		}
		if err != nil || !reflect.DeepEqual(got, c.want) {
			t.Errorf("%s: got %v, %v; want %v", c.name, got, err, c.want)
		}
	}
	// driver ranges still apply when gpucap's own limits are raised
	s := limits(0, 0, 1600)
	s.mclkLimit = 2000
	if _, err := planOD(tab, true, s, false); err == nil {
		t.Error("memory above driver range should be rejected")
	}
	// unavailable: fine if nothing asked for, error if something is
	if cmds, err := planOD(odTable{}, false, limits(0, 0, 0), false); err != nil || cmds != nil {
		t.Errorf("unavailable with nothing requested: %v %v", cmds, err)
	}
	if _, err := planOD(odTable{}, false, limits(-30, 0, 0), false); err == nil {
		t.Error("unavailable with a request should error")
	}
}
