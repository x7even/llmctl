package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// ── helpers ───────────────────────────────────────────────────────────────────

// hwFixture builds a Models-panel app on a stubbed machine: no probing, no
// network. Profiles, in models.yaml order:
//
//	small (no requires) · big4 (gpus [4], estimate) · mid (gpus [2,4])
//	huge (min_gpus 8)   · tail (no requires, unlisted: true)
//
// On a 2-GPU box small, mid and tail are runnable; big4 and huge are not.
func hwFixture(t *testing.T, hw HW) (*app, *[]string) {
	t.Helper()
	a := newTestApp()
	a.focused = paneModels
	a.reg = &Registry{
		Order: []string{"small", "big4", "mid", "huge", "tail"},
		Models: map[string]ModelConfig{
			"small": {Name: "Small"},
			"big4":  {Name: "Big4", Metadata: &ModelMetadata{Requires: &Requires{GPUs: []int{4}, Estimate: true}}},
			"mid":   {Name: "Mid", Metadata: &ModelMetadata{Requires: &Requires{GPUs: []int{2, 4}}}},
			"huge":  {Name: "Huge", Metadata: &ModelMetadata{Requires: &Requires{MinGPUs: 8}}},
			"tail":  {Name: "Tail", Unlisted: true},
		},
	}
	a.detectHW = func() HW { return hw }
	a.refreshHW()
	var swaps []string
	a.swapFn = func(baseURL, profile string) error {
		swaps = append(swaps, profile)
		return nil
	}
	return a, &swaps
}

func twoGPUs() HW {
	return HW{GPUCount: 2, HostRAMGiB: 188, Source: "sysfs"}
}

func indexOf(s, sub string) int { return strings.Index(s, sub) }

func skeyEnter() tea.KeyMsg { return skey(tea.KeyEnter) }

// ── verdicts + filtering ──────────────────────────────────────────────────────

func TestModels_filteredByDefault(t *testing.T) {
	a, _ := hwFixture(t, twoGPUs())
	got := a.profiles()
	want := []string{"small", "mid", "tail"} // models.yaml order, unlisted kept as before
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("profiles(): want %v, got %v", want, got)
	}
	out := a.renderModels()
	for _, p := range want {
		if !strings.Contains(out, p) {
			t.Errorf("want %q listed:\n%s", p, out)
		}
	}
	for _, p := range []string{"big4", "huge"} {
		if strings.Contains(out, p) {
			t.Errorf("%q must be hidden by default:\n%s", p, out)
		}
	}
	if !strings.Contains(out, "2 hidden") || !strings.Contains(out, "a: show all") {
		t.Errorf("want '2 hidden ... a: show all' footer:\n%s", out)
	}
}

func TestModels_footerFullTextWhenWide(t *testing.T) {
	a, _ := hwFixture(t, twoGPUs())
	a.fullscreen = true // full terminal width available to the panel
	out := a.renderModels()
	want := "2 hidden (needs more GPUs/RAM) - a: show all"
	if !strings.Contains(out, want) {
		t.Errorf("want %q in:\n%s", want, out)
	}
}

func TestModels_showAllGreysWithReason(t *testing.T) {
	a, _ := hwFixture(t, twoGPUs())
	a = update(a, key('a'))
	if !a.showAll {
		t.Fatal("a: want showAll=true")
	}
	a.fullscreen = true // plenty of width for the reason suffix
	out := a.renderModels()

	// Same order as models.yaml.
	prev := -1
	for _, p := range []string{"small", "big4", "mid", "huge", "tail"} {
		i := indexOf(out, p)
		if i < 0 {
			t.Fatalf("show-all must list %q:\n%s", p, out)
		}
		if i < prev {
			t.Errorf("%q out of models.yaml order:\n%s", p, out)
		}
		prev = i
	}
	if !strings.Contains(out, "big4 4 GPU est") {
		t.Errorf("want estimate-marked reason for big4:\n%s", out)
	}
	if !strings.Contains(out, "huge 8+ GPU") {
		t.Errorf("want min_gpus reason for huge:\n%s", out)
	}
	for _, line := range strings.Split(out, "\n") {
		if strings.Contains(line, "small") && strings.Contains(line, "needs") {
			t.Errorf("supported profile must not carry a reason: %q", line)
		}
	}
	if !strings.Contains(out, "a: hide") {
		t.Errorf("want 'a: hide' footer in show-all mode:\n%s", out)
	}
}

func TestModels_reasonSuffixTruncatedToPanelWidth(t *testing.T) {
	a, _ := hwFixture(t, twoGPUs())
	a = update(a, key('a'))
	w := a.modelsWidth()
	for _, line := range strings.Split(a.renderModels(), "\n") {
		if lipgloss.Width(line) > w {
			t.Errorf("line wider than the %d-col panel (%d): %q", w, lipgloss.Width(line), line)
		}
	}
}

func TestModels_ramShortfallReason(t *testing.T) {
	a, _ := hwFixture(t, HW{GPUCount: 4, HostRAMGiB: 62, Source: "sysfs"})
	a.reg.Models["small"] = ModelConfig{Metadata: &ModelMetadata{Requires: &Requires{HostRAMGiB: 96}}}
	a.recomputeVerdicts()
	if got := a.reasonText("small"); got != "needs 96 GiB RAM, have 62" {
		t.Errorf("reasonText: got %q", got)
	}
	for _, p := range a.profiles() {
		if p == "small" {
			t.Error("RAM-starved profile must be hidden")
		}
	}
}

func TestShortReason(t *testing.T) {
	cases := map[string]string{
		"needs gpus [4], detected 2":                        "needs 4 GPUs, have 2",
		"needs gpus [2, 4], detected 1":                     "needs 2 or 4 GPUs, have 1",
		"needs gpus [1, 2, 4], detected 0":                  "needs 1, 2 or 4 GPUs, have 0",
		"needs gpus [1], detected 0":                        "needs 1 GPU, have 0",
		"needs min_gpus 2, detected 1":                      "needs 2+ GPUs, have 1",
		"needs host RAM 96 GiB (min 88.3), measured 62 GiB": "needs 96 GiB RAM, have 62",
		"something unexpected":                              "something unexpected",
	}
	for in, want := range cases {
		if got := shortReason(in); got != want {
			t.Errorf("shortReason(%q): want %q, got %q", in, want, got)
		}
	}
}

// ── selection + scrolling ─────────────────────────────────────────────────────

func TestToggle_keepsSelectionOnSameProfile(t *testing.T) {
	a, _ := hwFixture(t, twoGPUs())
	a = update(a, key('j')) // small -> mid
	if a.selectedProfile() != "mid" {
		t.Fatalf("setup: want mid selected, got %q", a.selectedProfile())
	}
	a = update(a, key('a')) // list grows: mid is now index 2
	if a.cursor != 2 || a.selectedProfile() != "mid" {
		t.Errorf("show all: want cursor 2 on mid, got %d on %q", a.cursor, a.selectedProfile())
	}
	a = update(a, key('a')) // list shrinks back: mid is index 1
	if a.cursor != 1 || a.selectedProfile() != "mid" {
		t.Errorf("hide again: want cursor 1 on mid, got %d on %q", a.cursor, a.selectedProfile())
	}
}

func TestToggle_clampsWhenSelectedProfileVanishes(t *testing.T) {
	a, _ := hwFixture(t, twoGPUs())
	a = update(a, key('a'))
	a = update(a, key('j')) // small -> big4 (unsupported)
	if a.selectedProfile() != "big4" {
		t.Fatalf("setup: want big4 selected, got %q", a.selectedProfile())
	}
	a = update(a, key('a')) // big4 disappears
	ps := a.profiles()
	if a.cursor < 0 || a.cursor >= len(ps) {
		t.Fatalf("cursor %d outside visible list %v", a.cursor, ps)
	}
	if a.selectedProfile() == "big4" {
		t.Error("big4 must not remain selected once hidden")
	}

	// Last row selected, then the list shrinks underneath it.
	a = update(a, key('a'))
	a.cursor = len(a.profiles()) - 1 // tail
	a = update(a, key('a'))
	if a.cursor != len(a.profiles())-1 || a.selectedProfile() != "tail" {
		t.Errorf("tail stays visible: got cursor %d on %q", a.cursor, a.selectedProfile())
	}
}

func TestToggle_scrollStaysValidWhenListShrinks(t *testing.T) {
	a := newTestApp()
	a.focused = paneModels
	a.reg = &Registry{Models: map[string]ModelConfig{}}
	for i := 0; i < 30; i++ {
		id := fmt.Sprintf("p%02d", i)
		a.reg.Order = append(a.reg.Order, id)
		cfg := ModelConfig{}
		if i%3 != 0 { // two thirds need 4 GPUs
			cfg.Metadata = &ModelMetadata{Requires: &Requires{GPUs: []int{4}}}
		}
		a.reg.Models[id] = cfg
	}
	a.detectHW = func() HW { return twoGPUs() }
	a.refreshHW() // 10 visible, 20 hidden

	a = update(a, key('a'))
	for i := 0; i < 29; i++ {
		a = update(a, key('j')) // walk to the end of all 30 rows
	}
	if a.cursor != 29 || a.modelsScroll == 0 {
		t.Fatalf("setup: cursor %d scroll %d", a.cursor, a.modelsScroll)
	}
	a = update(a, key('a')) // 10 rows left

	vis := a.modelsVisible()
	n := len(a.profiles())
	if n != 10 {
		t.Fatalf("want 10 visible, got %d", n)
	}
	if a.cursor < 0 || a.cursor >= n {
		t.Errorf("cursor %d outside 0..%d", a.cursor, n-1)
	}
	if a.modelsScroll < 0 || a.modelsScroll > max(0, n-vis) {
		t.Errorf("scroll %d outside 0..%d (vis %d)", a.modelsScroll, max(0, n-vis), vis)
	}
	if a.cursor < a.modelsScroll || a.cursor >= a.modelsScroll+vis {
		t.Errorf("cursor %d not within window [%d,%d)", a.cursor, a.modelsScroll, a.modelsScroll+vis)
	}
}

func TestModels_neverRendersMoreRowsThanThePanelHas(t *testing.T) {
	a := newTestApp()
	a.focused = paneModels
	a.reg = &Registry{Models: map[string]ModelConfig{}}
	for i := 0; i < 30; i++ {
		id := fmt.Sprintf("p%02d", i)
		a.reg.Order = append(a.reg.Order, id)
		a.reg.Models[id] = ModelConfig{Metadata: &ModelMetadata{Requires: &Requires{GPUs: []int{2, 4}}}}
	}
	a.detectHW = func() HW { return HW{GPUCount: 1, HostRAMGiB: 64, Source: "sysfs"} }
	a.refreshHW()
	_, h2, _, _ := rowHeights(a.h)
	for _, showAll := range []bool{false, true} {
		a.showAll = showAll
		a.cursor, a.modelsScroll = 0, 0
		for i := 0; i < 31; i++ {
			rows := strings.Count(a.renderModels(), "\n") + 1
			if rows > h2-1 { // panel body = h2 minus its header line
				t.Fatalf("showAll=%v cursor=%d: %d rows > %d available:\n%s", showAll, a.cursor, rows, h2-1, a.renderModels())
			}
			a = update(a, key('j'))
		}
	}
}

// ── swap guard ────────────────────────────────────────────────────────────────

func TestSwap_unsupportedIsRefusedAndNeverCallsSwap(t *testing.T) {
	a, swaps := hwFixture(t, twoGPUs())
	a = update(a, key('a'))
	a = update(a, key('j')) // big4
	if a.selectedProfile() != "big4" {
		t.Fatalf("setup: got %q", a.selectedProfile())
	}
	for name, k := range map[string]tea.KeyMsg{"enter": skeyEnter(), "s": key('s'), "y": key('y')} {
		m, cmd := a.Update(k)
		a = m.(*app)
		if cmd != nil {
			t.Errorf("%s on unsupported profile: want nil cmd, got a command", name)
		}
		if a.confirming || a.swapping {
			t.Errorf("%s: must not enter confirm/swap state (confirming=%v swapping=%v)", name, a.confirming, a.swapping)
		}
	}
	if len(*swaps) != 0 {
		t.Fatalf("swap function was called: %v", *swaps)
	}
	if a.swapMsg != "✗ needs 4 GPUs, have 2 (est)" {
		t.Errorf("panel message: got %q", a.swapMsg)
	}
	want := "unsupported: use 'llmctl swap --force big4' to try anyway (needs 4 GPUs, have 2 (est))"
	if a.hwBlockMsg != want {
		t.Errorf("status message:\n want %q\n  got %q", want, a.hwBlockMsg)
	}
	if st := a.renderStatus(); !strings.Contains(st, "llmctl swap --force big4") {
		t.Errorf("status bar must carry the message:\n%s", st)
	}
	if strings.Contains(a.renderStatus(), "--force") && strings.Contains(a.renderModels(), "--force") {
		// The panel shows the short form only; the force hint lives in the status bar.
		t.Error("panel should not duplicate the long --force text")
	}
}

func TestSwap_supportedUnchanged(t *testing.T) {
	a, swaps := hwFixture(t, twoGPUs())
	a = update(a, skeyEnter())
	if !a.confirming || a.pendingSwap != "small" {
		t.Fatalf("enter: want confirming small, got confirming=%v pending=%q", a.confirming, a.pendingSwap)
	}
	m, cmd := a.Update(key('y'))
	a = m.(*app)
	if cmd == nil || !a.swapping || a.swapFor != "small" {
		t.Fatalf("y: want swap started for small (cmd=%v swapping=%v for=%q)", cmd != nil, a.swapping, a.swapFor)
	}
	// Run only the swap command (the batch also holds a 3 s poll timer).
	msg := a.cmdSwap("small")()
	done, ok := msg.(msgSwapDone)
	if !ok || done.profile != "small" || done.err != nil {
		t.Errorf("swap result: %#v", msg)
	}
	if len(*swaps) != 1 || (*swaps)[0] != "small" {
		t.Errorf("swap function calls: %v", *swaps)
	}
}

func TestSwap_reloadBetweenConfirmAndYesRechecksHardware(t *testing.T) {
	path := writeModelsYAML(t)
	hw := twoGPUs()
	a := newApp("http://127.0.0.1:8080", 0, path, "/nonexistent.log")
	a.w, a.h = 120, 40
	a.sizeViewports()
	a.focused = paneModels
	a.detectHW = func() HW { return hw }
	a.refreshHW()
	var swaps []string
	a.swapFn = func(_, p string) error { swaps = append(swaps, p); return nil }

	a = update(a, key('r')) // load the file registry + verdicts
	a = update(a, key('j')) // small -> mid
	if a.selectedProfile() != "mid" {
		t.Fatalf("setup: got %q (profiles %v)", a.selectedProfile(), a.profiles())
	}
	a = update(a, skeyEnter()) // confirm prompt for mid
	if !a.confirming {
		t.Fatal("mid is runnable on 2 GPUs: want confirm prompt")
	}
	hw = HW{GPUCount: 1, HostRAMGiB: 188, Source: "sysfs"} // a GPU drops off the bus
	a = update(a, key('r'))
	m, cmd := a.Update(key('y'))
	a = m.(*app)
	if cmd != nil || a.swapping || len(swaps) != 0 {
		t.Errorf("hardware no longer fits: want no swap (cmd=%v swapping=%v calls=%v)", cmd != nil, a.swapping, swaps)
	}
	if !strings.Contains(a.hwBlockMsg, "needs 2 or 4 GPUs, have 1") {
		t.Errorf("status message: %q", a.hwBlockMsg)
	}
}

// ── fail open ─────────────────────────────────────────────────────────────────

func TestFailOpen_unknownHardwareShowsEverything(t *testing.T) {
	a, swaps := hwFixture(t, UnknownHW())
	if got := len(a.profiles()); got != 5 {
		t.Fatalf("unknown hardware: want all 5 profiles, got %d", got)
	}
	if a.hiddenCount() != 0 {
		t.Error("unknown hardware: nothing may be hidden")
	}
	out := a.renderModels()
	if !strings.Contains(out, "not detected - showing all") {
		t.Errorf("want the dim 'not detected - showing all' note:\n%s", out)
	}
	if strings.Contains(out, "hidden") || strings.Contains(out, "needs") {
		t.Errorf("fail-open must not filter or grey anything:\n%s", out)
	}
	// An unsupported-on-paper profile is still swappable.
	a.cursor = 1 // big4
	a = update(a, skeyEnter())
	if !a.confirming || a.pendingSwap != "big4" {
		t.Errorf("fail-open: want confirm prompt for big4, got confirming=%v pending=%q", a.confirming, a.pendingSwap)
	}
	if len(*swaps) != 0 {
		t.Errorf("swap should not have run yet: %v", *swaps)
	}
}

func TestFailOpen_zeroGPUsIsARealAnswer(t *testing.T) {
	a, _ := hwFixture(t, HW{GPUCount: 0, HostRAMGiB: 64, Source: "sysfs"})
	if got := strings.Join(a.profiles(), ","); got != "small,tail" {
		t.Errorf("0 GPUs: want only requirement-free profiles, got %s", got)
	}
}

// ── reload ────────────────────────────────────────────────────────────────────

func writeModelsYAML(t *testing.T) string {
	t.Helper()
	const doc = `models:
  small:
    cmd: llama-server
  mid:
    cmd: vllm serve
    metadata:
      requires:
        gpus: [2, 4]
  big4:
    cmd: vllm serve
    metadata:
      requires:
        gpus: [4]
`
	p := filepath.Join(t.TempDir(), "models.yaml")
	if err := os.WriteFile(p, []byte(doc), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestReload_redetectsAndRecomputesVerdicts(t *testing.T) {
	path := writeModelsYAML(t)
	hw := twoGPUs()
	detections := 0
	a := newApp("http://127.0.0.1:8080", 0, path, "/nonexistent.log")
	a.w, a.h = 120, 40
	a.sizeViewports()
	a.detectHW = func() HW { detections++; return hw }
	a.refreshHW() // startup
	if detections != 1 {
		t.Fatalf("startup: want 1 detection, got %d", detections)
	}
	if got := strings.Join(a.profiles(), ","); got != "small,mid" {
		t.Fatalf("2 GPUs: got %s", got)
	}

	hw = HW{GPUCount: 4, HostRAMGiB: 188, Source: "sysfs"}
	a = update(a, key('r'))
	if detections != 2 {
		t.Errorf("r: want a second detection, got %d", detections)
	}
	if got := strings.Join(a.profiles(), ","); got != "small,mid,big4" {
		t.Errorf("4 GPUs after r: got %s", got)
	}
	if a.hiddenCount() != 0 {
		t.Errorf("hiddenCount: got %d", a.hiddenCount())
	}
	// Detection is not repeated by ordinary keys or redraws.
	_ = a.View()
	a = update(a, key('j'))
	if detections != 2 {
		t.Errorf("only startup and r detect; got %d", detections)
	}
}

func TestReload_keepsSelectionOnSameProfile(t *testing.T) {
	path := writeModelsYAML(t)
	hw := twoGPUs()
	a := newApp("http://127.0.0.1:8080", 0, path, "/nonexistent.log")
	a.w, a.h = 120, 40
	a.sizeViewports()
	a.focused = paneModels
	a.detectHW = func() HW { return hw }
	a.refreshHW()
	a = update(a, key('j'))
	if a.selectedProfile() != "mid" {
		t.Fatalf("setup: got %q", a.selectedProfile())
	}
	hw = HW{GPUCount: 4, HostRAMGiB: 188, Source: "sysfs"}
	a = update(a, key('r'))
	if a.selectedProfile() != "mid" {
		t.Errorf("selection after reload: got %q", a.selectedProfile())
	}
}

func TestReload_failedDetectionFailsOpen(t *testing.T) {
	path := writeModelsYAML(t)
	hw := twoGPUs()
	a := newApp("http://127.0.0.1:8080", 0, path, "/nonexistent.log")
	a.w, a.h = 120, 40
	a.sizeViewports()
	a.detectHW = func() HW { return hw }
	a.refreshHW()
	hw = UnknownHW()
	a = update(a, key('r'))
	if got := strings.Join(a.profiles(), ","); got != "small,mid,big4" {
		t.Errorf("detection lost: want everything listed, got %s", got)
	}
}

// ── header summary + layout ───────────────────────────────────────────────────

func TestHWSummary(t *testing.T) {
	a := newTestApp()
	cases := []struct {
		hw      HW
		compact bool
		want    string
	}{
		{HW{GPUCount: 4, HostRAMGiB: 188.2, Source: "sysfs"}, false, "4 GPU · 188 GiB RAM"},
		{HW{GPUCount: 4, HostRAMGiB: 188.2, Source: "sysfs"}, true, "4 GPU"},
		{HW{GPUCount: 2, HostRAMGiB: 188.2, Source: "override"}, false, "2 GPU (override) · 188 GiB RAM"},
		{HW{GPUCount: 2, Source: "override"}, false, "2 GPU (override)"},
		{UnknownHW(), false, "GPU ?"},
	}
	for _, c := range cases {
		a.hw = c.hw
		if got := a.hwSummary(c.compact); got != c.want {
			t.Errorf("hwSummary(%+v, compact=%v): want %q, got %q", c.hw, c.compact, c.want, got)
		}
	}
}

func TestView_showsHardwareInModelsHeader(t *testing.T) {
	a, _ := hwFixture(t, HW{GPUCount: 2, HostRAMGiB: 188, Source: "override"})
	out := a.View()
	if !strings.Contains(out, "2 GPU (override)") {
		t.Errorf("Models header should show the (override) hardware summary:\n%s", out)
	}
}

func TestView_narrowTerminalKeepsLayout(t *testing.T) {
	for _, size := range [][2]int{{60, 30}, {80, 30}, {100, 30}, {120, 40}} { // 30 rows is the grid's minimum height
		a, _ := hwFixture(t, twoGPUs())
		a.w, a.h = size[0], size[1]
		a.sizeViewports()
		a = update(a, key('a'))
		a.cursor = 1 // big4
		a = update(a, skeyEnter())
		out := a.View()
		for i, line := range strings.Split(out, "\n") {
			if w := lipgloss.Width(line); w > size[0] {
				t.Errorf("%dx%d line %d is %d wide: %q", size[0], size[1], i, w, line)
			}
		}
		if n := strings.Count(out, "\n") + 1; n > size[1] {
			t.Errorf("%dx%d: view is %d lines tall", size[0], size[1], n)
		}
	}
}

func TestHeaderFor_hardwareOnlyOnModelsPanel(t *testing.T) {
	a, _ := hwFixture(t, twoGPUs())
	if h := a.headerFor("GPU", paneGPU, 40, clrDim, false); strings.Contains(h, "2 GPU") {
		t.Errorf("only the Models header carries the summary: %q", h)
	}
	if h := a.headerFor("Models", paneModels, 40, clrDim, false); !strings.Contains(h, "2 GPU") {
		t.Errorf("Models header: want summary, got %q", h)
	}
	// Too narrow for any summary: header unchanged, still exactly w wide.
	if h := a.headerFor("Models", paneModels, 12, clrDim, false); lipgloss.Width(h) != 12 || strings.Contains(h, "GPU") {
		t.Errorf("narrow Models header: %q (width %d)", h, lipgloss.Width(h))
	}
}

func TestUnlistedProfilesBehaveAsBefore(t *testing.T) {
	// The TUI has never filtered on `unlisted`; hardware filtering must not
	// change that in either direction.
	a, _ := hwFixture(t, twoGPUs())
	found := false
	for _, p := range a.profiles() {
		found = found || p == "tail"
	}
	if !found {
		t.Error("unlisted but runnable profile must stay listed")
	}
}
