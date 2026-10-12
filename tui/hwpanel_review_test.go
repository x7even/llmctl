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

// Regression tests for the hardware-aware Models panel review findings.

func plainProfiles(t *testing.T, n int, hw HW) *app {
	t.Helper()
	a := newTestApp()
	a.focused = paneModels
	a.reg = &Registry{Models: map[string]ModelConfig{}}
	for i := 0; i < n; i++ {
		id := fmt.Sprintf("p%02d", i)
		a.reg.Order = append(a.reg.Order, id)
		a.reg.Models[id] = ModelConfig{}
	}
	a.detectHW = func() HW { return hw }
	a.refreshHW()
	return a
}

func TestResize_keepsCursorRowInView(t *testing.T) {
	a := plainProfiles(t, 25, twoGPUs())
	a.w, a.h = 120, 60
	a.sizeViewports()
	for i := 0; i < 10; i++ {
		a = update(a, key('j'))
	}
	a = update(a, tea.WindowSizeMsg{Width: 120, Height: 20})
	if out := a.renderModels(); !strings.Contains(out, "▶ p10") {
		t.Errorf("after shrinking the window the selected row is not rendered:\n%s", out)
	}
	// fullscreen toggles re-validate the window too
	a.fullscreen = true
	a = update(a, key('f')) // leaves fullscreen
	if out := a.renderModels(); !strings.Contains(out, "▶ p10") {
		t.Errorf("after leaving fullscreen the selected row is not rendered:\n%s", out)
	}
}

func TestBlockMessage_doesNotLeakToOtherProfiles(t *testing.T) {
	a, swaps := hwFixture(t, twoGPUs())
	a = update(a, key('a'))
	a = update(a, key('j')) // big4 (unsupported)
	a = update(a, skeyEnter())
	if a.hwBlockMsg == "" || a.swapMsg == "" {
		t.Fatalf("setup: want a refusal, got status=%q panel=%q", a.hwBlockMsg, a.swapMsg)
	}
	a = update(a, key('k')) // small (supported)
	if a.hwBlockMsg != "" || a.swapMsg != "" {
		t.Errorf("moving the cursor must clear the refusal: status=%q panel=%q", a.hwBlockMsg, a.swapMsg)
	}
	a = update(a, skeyEnter())
	if !a.confirming || a.pendingSwap != "small" {
		t.Fatalf("want confirm prompt for small, got confirming=%v pending=%q", a.confirming, a.pendingSwap)
	}
	if st := a.renderStatus(); strings.Contains(st, "unsupported") || strings.Contains(st, "big4") {
		t.Errorf("status bar still talks about the other profile:\n%s", st)
	}
	if len(*swaps) != 0 {
		t.Errorf("unexpected swap: %v", *swaps)
	}

	// 'a', 'r' and a new refusal-then-toggle also clear it
	a = update(a, key('n'))
	a = update(a, key('j')) // big4 again (show-all is still on)
	a = update(a, skeyEnter())
	if a.hwBlockMsg == "" {
		t.Fatal("setup: want a refusal")
	}
	a = update(a, key('a'))
	if a.hwBlockMsg != "" || a.swapMsg != "" {
		t.Errorf("toggling show-all must clear the refusal: status=%q panel=%q", a.hwBlockMsg, a.swapMsg)
	}
}

func TestBlockMessage_clearKeepsLaterSwapResult(t *testing.T) {
	a, _ := hwFixture(t, twoGPUs())
	a = update(a, key('a'))
	a = update(a, key('j'))
	a = update(a, skeyEnter()) // refusal
	a = update(a, msgUnloadDone{})
	if a.swapMsg != "✓ unloaded" {
		t.Fatalf("setup: swapMsg = %q", a.swapMsg)
	}
	a.clearBlock()
	if a.swapMsg != "✓ unloaded" {
		t.Errorf("clearBlock must not erase a newer swap result, got %q", a.swapMsg)
	}
}

func TestConfirmPrompt_staysOneRowAtRealColumnWidth(t *testing.T) {
	for _, w := range []int{80, 100, 140, 200} {
		a, _ := hwFixture(t, twoGPUs())
		a.w, a.h = w, 40
		a.sizeViewports()
		a.confirming = true
		a.pendingSwap = "qwen3.8-flash-next-vllm"
		width := a.modelsWidth()
		out := a.renderModels()
		for _, line := range strings.Split(out, "\n") {
			if lipgloss.Width(line) > width {
				t.Errorf("w=%d: line wider than the %d-col panel (%d): %q", w, width, lipgloss.Width(line), line)
			}
		}
		if first := strings.Split(out, "\n")[0]; !strings.Contains(first, "y/") {
			t.Errorf("w=%d: prompt lost its key hint: %q", w, first)
		}
	}
}

func TestConfirmPrompt_keepsFooterAndCursorRow(t *testing.T) {
	// 8 profiles on 2 GPUs with a hidden one: the confirm prompt must not push
	// the footer or the last row out of the panel.
	a := plainProfiles(t, 8, twoGPUs())
	a.reg.Models["p07"] = ModelConfig{Metadata: &ModelMetadata{Requires: &Requires{GPUs: []int{4}}}}
	a.recomputeVerdicts()
	a.w, a.h = 100, 20
	a.sizeViewports()
	for i := 0; i < 6; i++ {
		a = update(a, key('j'))
	}
	a = update(a, skeyEnter())
	if !a.confirming {
		t.Fatal("setup: want confirm prompt")
	}
	_, h2, _, _ := rowHeights(a.h)
	out := a.renderModels()
	if rows := len(strings.Split(out, "\n")); rows > h2-1 {
		t.Errorf("%d rows > %d available:\n%s", rows, h2-1, out)
	}
	if !strings.Contains(out, "▶ p06") || !strings.Contains(out, "a: show all") {
		t.Errorf("cursor row or footer missing:\n%s", out)
	}
}

func TestBlockStatus_actionablePartSurvivesNarrowTerminals(t *testing.T) {
	a, _ := hwFixture(t, HW{GPUCount: 1, HostRAMGiB: 188, Source: "sysfs"})
	id := "qwen3.6-35b-128k-nomtp"
	a.reg.Order = append(a.reg.Order, id)
	a.reg.Models[id] = ModelConfig{Metadata: &ModelMetadata{Requires: &Requires{GPUs: []int{2, 4}, Estimate: true}}}
	a.recomputeVerdicts()
	for _, w := range []int{80, 100} {
		a.w = w
		a.blockUnsupported(id)
		st := a.renderStatus()
		if !strings.Contains(st, "llmctl swap --force "+id) {
			t.Errorf("w=%d: --force hint cut off:\n%s", w, st)
		}
		// the panel line is cut to the column; the reason should still be readable at the common 40 cols
		a.fullscreen = false
		if !strings.HasPrefix(a.swapMsg, "✗ needs 2 or 4 GPUs") {
			t.Errorf("panel message: %q", a.swapMsg)
		}
	}
}

func TestShowAllRow_reasonFitsBesideLongNames(t *testing.T) {
	a, _ := hwFixture(t, HW{GPUCount: 1, HostRAMGiB: 188, Source: "sysfs"})
	long := map[string]*Requires{
		"qwen3.8-flash-next-vllm": {GPUs: []int{4}},
		"qwen3.8-27b-code":        {GPUs: []int{2, 4}},
		"qwen3.6-35b-128k-nomtp":  {GPUs: []int{2, 4}, Estimate: true},
	}
	for id, req := range long {
		a.reg.Order = append(a.reg.Order, id)
		a.reg.Models[id] = ModelConfig{Metadata: &ModelMetadata{Requires: req}}
	}
	a.recomputeVerdicts()
	a.w, a.h = 140, 60 // Models column is capped at 40 columns
	a.sizeViewports()
	a = update(a, key('a'))
	if w := a.modelsWidth(); w != 40 {
		t.Fatalf("setup: models column is %d wide, want 40", w)
	}
	want := map[string]string{
		"qwen3.8-flash-next-vllm": "4 GPU",
		"qwen3.8-27b-code":        "2/4 GPU",
		"qwen3.6-35b-128k-nomtp":  "2/4 GPU est",
	}
	// walk the cursor over every long profile: selected and unselected rows both show the reason
	for i := range a.profiles() {
		a.cursor = i
		a.clampModelsScroll()
		out := a.renderModels()
		for id, reason := range want {
			found := false
			for _, line := range strings.Split(out, "\n") {
				if strings.Contains(line, id) {
					found = true
					if !strings.Contains(line, reason) {
						t.Errorf("cursor=%d: row for %s lacks %q: %q", i, id, reason, line)
					}
				}
			}
			if !found && a.cursor == 0 {
				t.Logf("%s scrolled out at cursor 0", id)
			}
		}
	}
}

func TestReasonPhrase_compact(t *testing.T) {
	cases := map[string]string{
		"needs gpus [4], detected 2":                        "4 GPU",
		"needs gpus [2, 4], detected 1":                     "2/4 GPU",
		"needs min_gpus 3, detected 2":                      "3+ GPU",
		"needs host RAM 96 GiB (min 88.3), measured 62 GiB": "96 GiB RAM",
		"something unexpected":                              "something unexpected",
	}
	for in, want := range cases {
		if got := reasonPhrase(in, true); got != want {
			t.Errorf("reasonPhrase(%q, compact): want %q, got %q", in, want, got)
		}
	}
}

func TestRequires_floatsAreNotInts(t *testing.T) {
	reg, err := loadRegistry(writeTempYAML(t, `models:
  floaty:
    cmd: x
    metadata:
      requires:
        min_gpus: 3.0
  listy:
    cmd: x
    metadata:
      requires:
        gpus: [2.0, 4, "8"]
`))
	if err != nil {
		t.Fatal(err)
	}
	if r := reg.Models["floaty"].Requirements(); r == nil || r.MinGPUs != 0 {
		t.Errorf("min_gpus: 3.0 must be ignored like llmhw.py does, got %+v", r)
	}
	if r := reg.Models["listy"].Requirements(); r == nil || fmt.Sprint(r.GPUs) != "[4]" {
		t.Errorf("gpus: only real integers count, got %+v", r)
	}
}

func TestDetect_negativeSysfsVRAMIsIgnoredNotCounted(t *testing.T) {
	root := t.TempDir()
	drm := fakeDRM(t, root, map[string]int64{"card0": 32 * testGiB, "card1": 32 * testGiB}, false)
	neg := filepath.Join(root, "devices", "pci-card1", "mem_info_vram_total")
	if err := os.WriteFile(neg, []byte("-1\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	hw := HWProbe{DRMRoot: drm, MeminfoPath: missingMeminfo(t), Run: noRocm(t)}.Detect(-1)
	if hw.GPUCount != 1 || hw.IgnoredDevices != 1 {
		t.Errorf("GPUCount=%d Ignored=%d, want 1 and 1 (llmhw.py ignores a negative size)", hw.GPUCount, hw.IgnoredDevices)
	}
}
