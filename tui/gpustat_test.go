package main

import (
	"errors"
	"os"
	"testing"
)

// Fixtures are real captures from this hardware (4x R9700, ROCm 10.1 amd-smi / ROCm 7 rocm-smi).
func fixture(t *testing.T, name string) string {
	t.Helper()
	b, err := os.ReadFile("../tests/fixtures/" + name)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func TestParseAmdSMI_realCapture(t *testing.T) {
	gpus := parseAmdSMI(fixture(t, "amd_smi_metric.json"))
	if len(gpus) != 4 {
		t.Fatalf("want 4 GPUs, got %d", len(gpus))
	}
	// amd-smi "MB" is MiB: 32624 MiB == 34,208,743,424 B, the figure rocm-smi prints in bytes.
	if gpus[0].VRAMTotal != 34208743424 {
		t.Errorf("VRAMTotal = %d", gpus[0].VRAMTotal)
	}
	if gpus[0].VRAMUsed != 29762*mib {
		t.Errorf("VRAMUsed = %d", gpus[0].VRAMUsed)
	}
	for i, g := range gpus {
		if g.Index != i {
			t.Errorf("gpus[%d].Index = %d", i, g.Index)
		}
	}
}

func TestParseAmdSMI_naSectionsAndGarbage(t *testing.T) {
	na := `{"gpu_data":[{"gpu":0,"mem_usage":{"total_vram":{"value":100,"unit":"MB"},"used_vram":"N/A"},"usage":"N/A","temperature":"N/A"},
		{"gpu":1,"mem_usage":"N/A"}]}`
	gpus := parseAmdSMI(na)
	if len(gpus) != 1 || gpus[0].VRAMTotal != 100*mib || gpus[0].VRAMUsed != 0 || gpus[0].UsePercent != 0 || gpus[0].Temp != 0 {
		t.Fatalf("gpus = %+v", gpus)
	}
	for _, bad := range []string{"", "not json", "{}", `{"gpu_data":"N/A"}`, "[]"} {
		if got := parseAmdSMI(bad); len(got) != 0 {
			t.Errorf("parseAmdSMI(%q) = %+v", bad, got)
		}
	}
}

func TestParseROCMText_realCapture(t *testing.T) {
	gpus := parseROCMText(fixture(t, "rocm_smi_show.txt"))
	if len(gpus) != 4 {
		t.Fatalf("want 4 GPUs, got %d", len(gpus))
	}
	// Both tools must agree on the same card state, which is what makes the fallback safe.
	if gpus[0].VRAMTotal != 34208743424 {
		t.Errorf("VRAMTotal = %d", gpus[0].VRAMTotal)
	}
}

func TestReadGPUs_prefersAmdSMIThenFallsBack(t *testing.T) {
	amd, rocm := fixture(t, "amd_smi_metric.json"), fixture(t, "rocm_smi_show.txt")

	var calls []string
	both := func(argv []string) (string, error) {
		calls = append(calls, argv[0])
		if argv[0] == "amd-smi" {
			return amd, nil
		}
		return rocm, nil
	}
	if gpus, tool := readGPUs(both); tool != "amd-smi" || len(gpus) != 4 || len(calls) != 1 {
		t.Errorf("tool=%s gpus=%d calls=%v", tool, len(gpus), calls)
	}

	onlyRocm := func(argv []string) (string, error) {
		if argv[0] == "amd-smi" {
			return "", errors.New("not found")
		}
		return rocm, nil
	}
	if gpus, tool := readGPUs(onlyRocm); tool != "rocm-smi" || len(gpus) != 4 {
		t.Errorf("tool=%s gpus=%d", tool, len(gpus))
	}

	// amd-smi that runs but yields nothing parseable also falls through.
	junk := func(argv []string) (string, error) {
		if argv[0] == "amd-smi" {
			return "{}", nil
		}
		return rocm, nil
	}
	if _, tool := readGPUs(junk); tool != "rocm-smi" {
		t.Errorf("tool = %s", tool)
	}

	none := func([]string) (string, error) { return "", errors.New("not found") }
	if gpus, tool := readGPUs(none); tool != "none" || len(gpus) != 0 {
		t.Errorf("tool=%s gpus=%d", tool, len(gpus))
	}
}
