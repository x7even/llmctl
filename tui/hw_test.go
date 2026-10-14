package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

// ── fakes ──────────────────────────────────────────────────────────────────────

const testGiB = int64(1024 * 1024 * 1024)

// fakeDRM builds <root>/drm/<card> -> ../devices/pci-<card> symlinks like sysfs.
// vram < 0 = the device exposes no mem_info_vram_total file.
func fakeDRM(t *testing.T, root string, cards map[string]int64, connectors bool) string {
	t.Helper()
	drm := filepath.Join(root, "drm")
	if err := os.MkdirAll(drm, 0o755); err != nil {
		t.Fatal(err)
	}
	for name, vram := range cards {
		dev := filepath.Join(root, "devices", "pci-"+name)
		if err := os.MkdirAll(dev, 0o755); err != nil {
			t.Fatal(err)
		}
		if vram >= 0 {
			if err := os.WriteFile(filepath.Join(dev, "mem_info_vram_total"), []byte(fmt.Sprintf("%d\n", vram)), 0o644); err != nil {
				t.Fatal(err)
			}
		}
		card := filepath.Join(drm, name)
		if err := os.MkdirAll(card, 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.Symlink(dev, filepath.Join(card, "device")); err != nil {
			t.Fatal(err)
		}
		if connectors {
			if err := os.MkdirAll(filepath.Join(drm, name+"-DP-1"), 0o755); err != nil {
				t.Fatal(err)
			}
		}
	}
	return drm
}

func fakeMeminfo(t *testing.T, gib float64) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "meminfo")
	text := fmt.Sprintf("MemTotal:       %d kB\nMemFree:        1 kB\n", int64(gib*1024*1024))
	if err := os.WriteFile(p, []byte(text), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func noRocm(t *testing.T) func([]string) (string, error) {
	return func(argv []string) (string, error) {
		t.Errorf("rocm-smi must not be called: %v", argv)
		return "", errors.New("unexpected")
	}
}

func missingMeminfo(t *testing.T) string { return filepath.Join(t.TempDir(), "nope") }

// ── DetectHW ───────────────────────────────────────────────────────────────────

func TestDetect_fakeSysfsFourGPUs(t *testing.T) {
	cards := map[string]int64{}
	for i := 0; i < 4; i++ {
		cards[fmt.Sprintf("card%d", i)] = 32 * testGiB
	}
	p := HWProbe{DRMRoot: fakeDRM(t, t.TempDir(), cards, true), MeminfoPath: fakeMeminfo(t, 188), Run: noRocm(t)}
	hw := p.Detect(-1)
	if hw.GPUCount != 4 || hw.Source != "sysfs" || hw.IgnoredDevices != 0 {
		t.Fatalf("hw = %+v", hw)
	}
	if !reflect.DeepEqual(hw.VRAMGiB, []float64{32, 32, 32, 32}) {
		t.Errorf("VRAMGiB = %v", hw.VRAMGiB)
	}
	if hw.HostRAMGiB != 188 || !hw.RAMKnown() || !hw.GPUsKnown() {
		t.Errorf("RAM = %v", hw.HostRAMGiB)
	}
}

func TestDetect_iGPUAndSmallDevicesExcluded(t *testing.T) {
	cards := map[string]int64{
		"card0": 32 * testGiB, "card1": 32 * testGiB, "card2": 32 * testGiB,
		"card3": 512 * 1024 * 1024, // iGPU carve-out
		"card4": 8*testGiB - 1,     // just under the 8 GiB bar
		"card5": 8 * testGiB,       // exactly 8 GiB counts
	}
	p := HWProbe{DRMRoot: fakeDRM(t, t.TempDir(), cards, true), MeminfoPath: missingMeminfo(t), Run: noRocm(t)}
	hw := p.Detect(-1)
	if hw.GPUCount != 4 || hw.IgnoredDevices != 2 {
		t.Fatalf("hw = %+v", hw)
	}
	if !reflect.DeepEqual(hw.VRAMGiB, []float64{32, 32, 32, 8}) {
		t.Errorf("VRAMGiB = %v", hw.VRAMGiB)
	}
	if hw.RAMKnown() || hw.HostRAMGiB != 0 {
		t.Errorf("unreadable meminfo must leave RAM unknown, got %v", hw.HostRAMGiB)
	}
}

func TestDetect_allSmallDevicesIsKnownZero(t *testing.T) {
	// Only an iGPU: sysfs answered, so the count is a real 0 (not unknown) and
	// rocm-smi is not consulted.
	p := HWProbe{DRMRoot: fakeDRM(t, t.TempDir(), map[string]int64{"card0": 512 * 1024 * 1024}, false),
		MeminfoPath: missingMeminfo(t), Run: noRocm(t)}
	hw := p.Detect(-1)
	if hw.GPUCount != 0 || !hw.GPUsKnown() || hw.Source != "sysfs" || hw.IgnoredDevices != 1 {
		t.Fatalf("hw = %+v", hw)
	}
}

func TestDetect_dedupesSymlinkedNodesAndIgnoresConnectors(t *testing.T) {
	root := t.TempDir()
	drm := fakeDRM(t, root, map[string]int64{"card0": 32 * testGiB}, true)
	// a second node (card1) pointing at the same device must not double count
	card1 := filepath.Join(drm, "card1")
	if err := os.MkdirAll(card1, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(root, "devices", "pci-card0"), filepath.Join(card1, "device")); err != nil {
		t.Fatal(err)
	}
	// non card<N> names are ignored even if they have a device dir
	if err := os.MkdirAll(filepath.Join(drm, "cardX", "device"), 0o755); err != nil {
		t.Fatal(err)
	}
	got, found := sysfsVRAMSizes(drm)
	if !found || !reflect.DeepEqual(got, []int64{32 * testGiB}) {
		t.Fatalf("sizes = %v found=%v", got, found)
	}
	hw := HWProbe{DRMRoot: drm, MeminfoPath: missingMeminfo(t), Run: noRocm(t)}.Detect(-1)
	if hw.GPUCount != 1 {
		t.Errorf("GPUCount = %d, want 1", hw.GPUCount)
	}
}

func TestDetect_overrideSkipsGPUDetectionButReadsRAM(t *testing.T) {
	cards := map[string]int64{"card0": 32 * testGiB, "card1": 32 * testGiB}
	p := HWProbe{DRMRoot: fakeDRM(t, t.TempDir(), cards, false), MeminfoPath: fakeMeminfo(t, 94), Run: noRocm(t)}
	hw := p.Detect(3)
	if hw.GPUCount != 3 || hw.Source != "override" || len(hw.VRAMGiB) != 0 {
		t.Fatalf("hw = %+v", hw)
	}
	if hw.HostRAMGiB != 94 {
		t.Errorf("override must still read host RAM, got %v", hw.HostRAMGiB)
	}
	if got := p.Detect(0); got.GPUCount != 0 || got.Source != "override" || !got.GPUsKnown() {
		t.Errorf("override 0 is a real answer, got %+v", got)
	}
}

func TestDetect_rocmSMIFallbackOnlyWithoutSysfsVRAMInfo(t *testing.T) {
	// A device node without mem_info_vram_total is "no VRAM info" -> fallback.
	drm := fakeDRM(t, t.TempDir(), map[string]int64{"card0": -1}, false)
	var calls [][]string
	run := func(argv []string) (string, error) {
		calls = append(calls, argv)
		return strings.Join([]string{
			"GPU[0]\t\t: VRAM Total Memory (B): 34342961152",
			"GPU[0]\t\t: VRAM Total Used Memory (B): 123",
			"GPU[1]\t\t: VRAM Total Memory (B): 34342961152",
			"GPU[2]\t\t: VRAM Total Memory (B): 536870912",
		}, "\n"), nil
	}
	hw := HWProbe{DRMRoot: drm, MeminfoPath: missingMeminfo(t), Run: run}.Detect(-1)
	if hw.GPUCount != 2 || hw.Source != "rocm-smi" || hw.IgnoredDevices != 1 {
		t.Fatalf("hw = %+v", hw)
	}
	if len(calls) != 1 || calls[0][1] != "--showmeminfo" {
		t.Errorf("calls = %v", calls)
	}
}

func TestDetect_rocmSMIListDevicesFallbackAndNone(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "no-drm")
	run := func(argv []string) (string, error) {
		if argv[1] == "--showmeminfo" {
			return "", errors.New("unsupported")
		}
		return "GPU[0]  : x\nGPU[1]  : x\nGPU[1]  : y\nGPU[3]  : z\n", nil
	}
	hw := HWProbe{DRMRoot: missing, MeminfoPath: missingMeminfo(t), Run: run}.Detect(-1)
	if hw.GPUCount != 3 || hw.Source != "rocm-smi" || len(hw.VRAMGiB) != 0 {
		t.Fatalf("hw = %+v", hw)
	}

	fail := func([]string) (string, error) { return "", errors.New("rocm-smi: not found") }
	hw = HWProbe{DRMRoot: missing, MeminfoPath: missingMeminfo(t), Run: fail}.Detect(-1)
	if hw.GPUCount != UnknownGPUs || hw.Source != "none" || hw.GPUsKnown() {
		t.Fatalf("nothing detectable must be unknown, got %+v", hw)
	}
}

func TestUnknownHW(t *testing.T) {
	hw := UnknownHW()
	if hw.GPUsKnown() || hw.RAMKnown() || hw.Source != "none" {
		t.Errorf("UnknownHW = %+v", hw)
	}
	if v := Supports(&Requires{GPUs: []int{4}, HostRAMGiB: 96}, hw); !v.OK {
		t.Errorf("unknown hardware must be permissive, got %+v", v)
	}
}

// ── meminfo ────────────────────────────────────────────────────────────────────

func TestParseMemTotalGiB(t *testing.T) {
	g, ok := ParseMemTotalGiB("MemTotal:       197132288 kB\nMemFree:  12 kB\n")
	if !ok || g != 197132288.0/(1024*1024) {
		t.Errorf("got %v %v", g, ok)
	}
	if _, ok := ParseMemTotalGiB("MemFree: 1 kB\n"); ok {
		t.Error("no MemTotal line must be not-ok")
	}
	if _, ok := ParseMemTotalGiB(""); ok {
		t.Error("empty must be not-ok")
	}
	// only a line-anchored MemTotal counts
	if _, ok := ParseMemTotalGiB("HugeMemTotal: 5 kB\n"); ok {
		t.Error("prefixed key must not match")
	}
}

// ── overrides ──────────────────────────────────────────────────────────────────

func envOf(m map[string]string) func(string) string { return func(k string) string { return m[k] } }

func TestGPUCountOverride(t *testing.T) {
	cases := []struct {
		name    string
		flag    string
		env     string
		want    int
		warn    bool
		wantErr bool
	}{
		{"none", "", "", -1, false, false},
		{"env only", "", "2", 2, false, false},
		{"env padded", "", " 3 ", 3, false, false},
		{"flag only", "1", "", 1, false, false},
		{"flag wins over env", "1", "4", 1, false, false},
		{"flag zero wins over env", "0", "4", 0, false, false},
		{"flag invalid is an error", "x", "4", -1, false, true},
		{"flag negative is an error", "-1", "", -1, false, true},
		{"bad env warns and is ignored", "", "many", -1, true, false},
		{"negative env warns and is ignored", "", "-2", -1, true, false},
		{"bad env ignored when flag is good", "5", "many", 5, false, false},
	}
	for _, c := range cases {
		n, warn, err := GPUCountOverride(c.flag, envOf(map[string]string{GPUCountEnv: c.env}))
		if n != c.want || (warn != nil) != c.warn || (err != nil) != c.wantErr {
			t.Errorf("%s: got n=%d warn=%v err=%v", c.name, n, warn, err)
		}
	}
}

// ── Supports: parity with scripts/llmhw.py ─────────────────────────────────────

type parityCase struct {
	Name     string    `json:"name"`
	Requires *Requires `json:"requires"`
	HW       struct {
		GPUCount   *int     `json:"gpu_count"`
		HostRAMGiB *float64 `json:"host_ram_gib"`
	} `json:"hw"`
	Expect struct {
		OK       bool     `json:"ok"`
		Use      *int     `json:"use"`
		Reasons  []string `json:"reasons"`
		Estimate bool     `json:"estimate"`
	} `json:"expect"`
}

func TestSupportsParity(t *testing.T) {
	raw, err := os.ReadFile("../tests/fixtures/llmhw_cases.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []parityCase
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	if len(cases) < 30 {
		t.Fatalf("fixture shrank to %d cases", len(cases))
	}
	for _, c := range cases {
		hw := UnknownHW()
		hw.Source = "test"
		if c.HW.GPUCount != nil {
			hw.GPUCount = *c.HW.GPUCount
		}
		if c.HW.HostRAMGiB != nil {
			hw.HostRAMGiB = *c.HW.HostRAMGiB
		}
		v := Supports(c.Requires, hw)
		if v.OK != c.Expect.OK {
			t.Errorf("%s: OK = %v, want %v", c.Name, v.OK, c.Expect.OK)
		}
		wantUse := 0
		if c.Expect.Use != nil {
			wantUse = *c.Expect.Use
		}
		if v.Use != wantUse {
			t.Errorf("%s: Use = %d, want %d", c.Name, v.Use, wantUse)
		}
		if len(v.Reasons) != len(c.Expect.Reasons) || (len(v.Reasons) > 0 && !reflect.DeepEqual(v.Reasons, c.Expect.Reasons)) {
			t.Errorf("%s: Reasons = %q, want %q", c.Name, v.Reasons, c.Expect.Reasons)
		}
		if v.Estimate != c.Expect.Estimate {
			t.Errorf("%s: Estimate = %v, want %v", c.Name, v.Estimate, c.Expect.Estimate)
		}
		if v.OK && len(v.Reasons) != 0 {
			t.Errorf("%s: OK verdict carries reasons %q", c.Name, v.Reasons)
		}
	}
}

func TestSupports_zeroValueIsPermissiveAboutRules(t *testing.T) {
	if v := Supports(nil, HW{GPUCount: 1, HostRAMGiB: 16}); !v.OK || v.Use != 0 || v.Estimate {
		t.Errorf("nil requires: %+v", v)
	}
}

// ── metadata.requires parsing ──────────────────────────────────────────────────

const requiresYAML = `
healthCheckTimeout: 300
models:
  with-gpus:
    name: "A"
    ttl: 0
    metadata:
      requires:
        gpus: [2, 4]
        host_ram_gib: 96
        vram_total_gib: 66.5
        estimate: true
        note: "has a # inside, and: colons"
    cmd: |
      echo hi
  with-min:
    ttl: 0
    metadata:
      requires:
        min_gpus: 3   # trailing comment
    cmd: echo
  no-metadata:
    ttl: 0
    cmd: echo
  other-metadata:
    ttl: 0
    metadata:
      owner: someone
    cmd: echo
  empty-requires:
    ttl: 0
    metadata:
      requires: {}
    cmd: echo
  malformed:
    ttl: 0
    metadata:
      requires:
        gpus: 4
        min_gpus: 2
        host_ram_gib: lots
        estimate: maybe
    cmd: echo
  scalar-metadata:
    ttl: 0
    metadata: nonsense
    cmd: echo
`

func TestRequires_parseFixture(t *testing.T) {
	reg, err := loadRegistry(writeTempYAML(t, requiresYAML))
	if err != nil {
		t.Fatalf("loadRegistry: %v", err)
	}
	if len(reg.Order) != 7 {
		t.Fatalf("Order = %v", reg.Order)
	}

	r := reg.Models["with-gpus"].Requirements()
	want := &Requires{GPUs: []int{2, 4}, HostRAMGiB: 96, VRAMTotalGiB: 66.5, Estimate: true, Note: "has a # inside, and: colons"}
	if !reflect.DeepEqual(r, want) {
		t.Errorf("with-gpus = %+v, want %+v", r, want)
	}

	if r := reg.Models["with-min"].Requirements(); r == nil || r.MinGPUs != 3 || r.GPUs != nil || r.Estimate {
		t.Errorf("with-min = %+v", r)
	}

	// absent / unknown: nil, and permissive in Supports
	for _, id := range []string{"no-metadata", "other-metadata", "scalar-metadata"} {
		if r := reg.Models[id].Requirements(); r != nil {
			t.Errorf("%s: want nil requires, got %+v", id, r)
		}
		if v := Supports(reg.Models[id].Requirements(), HW{GPUCount: 1, HostRAMGiB: 1}); !v.OK {
			t.Errorf("%s: nil requires must be permissive", id)
		}
	}
	// the rest of a profile still decodes next to a metadata block
	if reg.Models["with-gpus"].Name != "A" || !strings.Contains(reg.Models["with-gpus"].Cmd, "echo hi") {
		t.Error("profile fields must be unaffected by metadata")
	}

	if r := reg.Models["empty-requires"].Requirements(); r == nil || !reflect.DeepEqual(*r, Requires{}) {
		t.Errorf("empty-requires = %+v", r)
	}

	// mistyped values drop only that constraint; the registry still loads
	r = reg.Models["malformed"].Requirements()
	if r == nil || r.GPUs != nil || r.MinGPUs != 2 || r.HostRAMGiB != 0 || r.Estimate {
		t.Errorf("malformed = %+v", r)
	}
}

func TestRequires_realConfig(t *testing.T) {
	reg, err := loadRegistry("../config/models.yaml")
	if err != nil {
		t.Fatalf("real config must parse (placeholders and all): %v", err)
	}
	if len(reg.Order) == 0 {
		t.Fatal("no profiles")
	}
	for _, id := range reg.Order {
		r := reg.Models[id].Requirements()
		if r == nil {
			t.Errorf("%s: no metadata.requires", id)
			continue
		}
		if (r.GPUs != nil) == (r.MinGPUs > 0) {
			t.Errorf("%s: exactly one of gpus / min_gpus expected, got %+v", id, r)
		}
		for _, g := range r.GPUs {
			if g < 1 {
				t.Errorf("%s: bad gpus entry %d", id, g)
			}
		}
		// every shipped profile must be decidable on the reference 4-GPU rig
		if v := Supports(r, HW{GPUCount: 4, HostRAMGiB: 188}); !v.OK {
			t.Errorf("%s: not supported on the 4-GPU reference rig: %q", id, v.Reasons)
		}
	}
	t.Logf("%d profiles carry requires", len(reg.Order))

	// spot-checks against config/models.yaml
	if r := reg.Models["qwen3.8-27b-code"].Requirements(); r == nil || !reflect.DeepEqual(r.GPUs, []int{2, 4}) || r.Estimate {
		t.Errorf("qwen3.8-27b-code = %+v", r)
	}
	if r := reg.Models["qwen3.6-35b-code"].Requirements(); r == nil || !reflect.DeepEqual(r.GPUs, []int{2, 4}) || r.Estimate {
		t.Errorf("qwen3.6-35b-code must be measured at [2 4], got %+v", r)
	}
	if r := reg.Models["qwen3.8-flash-next"].Requirements(); r == nil || r.MinGPUs != 2 || r.Estimate {
		t.Errorf("qwen3.8-flash-next = %+v", r)
	}
}
