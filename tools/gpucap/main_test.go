package main

import "testing"

const sample = `OD_SCLK:
0: 500Mhz
1: 3000Mhz
OD_VDDGFX_OFFSET:
-30mV
OD_RANGE:
SCLK:     500Mhz       3200Mhz
VDDGFX_OFFSET: -200mV 0mV
`

func TestParseOD(t *testing.T) {
	cur, lo, hi, ok := parseOD(sample)
	if !ok || cur != -30 || lo != -200 || hi != 0 {
		t.Fatalf("got %d %d %d %v", cur, lo, hi, ok)
	}
	if _, _, _, ok := parseOD("OD_SCLK:\n0: 500Mhz\n"); ok {
		t.Fatal("expected no offset entry")
	}
}
