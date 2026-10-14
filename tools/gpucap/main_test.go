package main

import "testing"

// sample mirrors a real Navi 48 (R9700) dump: sections separated by NUL padding,
// and the range line in lowercase "mv".
const sample = "OD_SCLK_OFFSET:\n0Mhz\nOD_MCLK:\n0: 97Mhz\n1: 1259MHz\n\x00\x00\x00\x00" +
	"OD_VDDGFX_OFFSET:\n-30mV\n\x00\x00\x00\x00\x00" +
	"OD_RANGE:\nSCLK_OFFSET:    -500Mhz       1000Mhz\nMCLK:      97Mhz       1500Mhz\n" +
	"VDDGFX_OFFSET:    -200mv          0mv\n\x00\x00"

func TestParseOD(t *testing.T) {
	cur, lo, hi, ok := parseOD(sample)
	if !ok || cur != -30 || lo != -200 || hi != 0 {
		t.Fatalf("got %d %d %d %v", cur, lo, hi, ok)
	}
	if _, _, _, ok := parseOD("OD_SCLK:\n0: 500Mhz\n"); ok {
		t.Fatal("expected no offset entry")
	}
}
