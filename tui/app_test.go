package main

import (
	"strings"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// ── helpers ───────────────────────────────────────────────────────────────────

func newTestApp() *app {
	a := newApp("http://127.0.0.1:8080", time.Second, "/nonexistent.yaml", "/nonexistent.log")
	// Give it a real terminal size so View() doesn't short-circuit
	a.w, a.h = 120, 40
	a.sizeViewports()
	return a
}

// key sends a rune key press.
func key(r rune) tea.KeyMsg { return tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{r}} }

// skey sends a special key press.
func skey(t tea.KeyType) tea.KeyMsg { return tea.KeyMsg{Type: t} }

func update(a *app, msg tea.Msg) *app {
	m, _ := a.Update(msg)
	return m.(*app)
}

// ── Init & construction ───────────────────────────────────────────────────────

func TestNewApp_defaults(t *testing.T) {
	a := newTestApp()
	if a.baseURL != "http://127.0.0.1:8080" {
		t.Errorf("baseURL: got %s", a.baseURL)
	}
	if pollIntervals[a.intervalIdx] != time.Second {
		t.Errorf("interval: want 1s, got %v", pollIntervals[a.intervalIdx])
	}
	if a.focused != paneInference {
		t.Errorf("focused: want paneInference(0), got %d", a.focused)
	}
	if a.fullscreen {
		t.Error("fullscreen: want false on init")
	}
}

func TestNewApp_intervalResolution(t *testing.T) {
	cases := []struct {
		in   time.Duration
		want int
	}{
		{500 * time.Millisecond, 0},
		{time.Second, 1},
		{2 * time.Second, 2},
		{5 * time.Second, 3},
		{15 * time.Second, 4},
	}
	for _, tc := range cases {
		a := newApp("", tc.in, "", "")
		if a.intervalIdx != tc.want {
			t.Errorf("interval %v → want idx %d, got %d", tc.in, tc.want, a.intervalIdx)
		}
	}
}

// ── Window sizing ─────────────────────────────────────────────────────────────

func TestWindowSize_stored(t *testing.T) {
	a := newTestApp()
	a = update(a, tea.WindowSizeMsg{Width: 200, Height: 60})
	if a.w != 200 || a.h != 60 {
		t.Errorf("want 200×60, got %d×%d", a.w, a.h)
	}
}

func TestWindowSize_viewportsResized(t *testing.T) {
	a := newTestApp()
	a = update(a, tea.WindowSizeMsg{Width: 160, Height: 50})
	if a.logVP.Width == 0 || a.logVP.Height == 0 {
		t.Errorf("logVP not sized after window resize: %dx%d", a.logVP.Width, a.logVP.Height)
	}
	if a.cfgVP.Width == 0 || a.cfgVP.Height == 0 {
		t.Errorf("cfgVP not sized after window resize: %dx%d", a.cfgVP.Width, a.cfgVP.Height)
	}
}

// ── Panel navigation ──────────────────────────────────────────────────────────

func TestTab_cyclesAllPanels(t *testing.T) {
	a := newTestApp()
	for i := 0; i < int(paneCount); i++ {
		if a.focused != panelID(i) {
			t.Errorf("step %d: want panel %d, got %d", i, i, a.focused)
		}
		a = update(a, skey(tea.KeyTab))
	}
	// After full cycle, back to first
	if a.focused != paneInference {
		t.Errorf("after full cycle: want paneInference, got %d", a.focused)
	}
}

func TestShiftTab_cyclesReverse(t *testing.T) {
	a := newTestApp()
	a = update(a, skey(tea.KeyShiftTab))
	if a.focused != paneLogs {
		t.Errorf("shift-tab from inference: want paneLogs(%d), got %d", paneLogs, a.focused)
	}
}

func TestDirectPanelKeys(t *testing.T) {
	cases := []struct {
		r    rune
		want panelID
	}{
		{'1', paneInference},
		{'2', paneGPU},
		{'3', paneModels},
		{'4', paneConfig},
		{'5', paneLogs},
	}
	for _, tc := range cases {
		a := newTestApp()
		a = update(a, key(tc.r))
		if a.focused != tc.want {
			t.Errorf("key '%c': want panel %d, got %d", tc.r, tc.want, a.focused)
		}
	}
}

// ── Fullscreen ────────────────────────────────────────────────────────────────

func TestFullscreen_toggle(t *testing.T) {
	a := newTestApp()
	a = update(a, key('f'))
	if !a.fullscreen {
		t.Error("f: want fullscreen=true")
	}
	a = update(a, key('f'))
	if a.fullscreen {
		t.Error("f again: want fullscreen=false")
	}
}

func TestEsc_exitsFullscreen(t *testing.T) {
	a := newTestApp()
	a = update(a, key('f'))
	a = update(a, skey(tea.KeyEsc))
	if a.fullscreen {
		t.Error("esc: want fullscreen=false")
	}
}

func TestEsc_noopWhenNotFullscreen(t *testing.T) {
	a := newTestApp()
	a = update(a, skey(tea.KeyEsc))
	if a.fullscreen {
		t.Error("esc without fullscreen: should stay false")
	}
}

// ── Poll interval ─────────────────────────────────────────────────────────────

func TestPollCycle(t *testing.T) {
	a := newTestApp()
	a.intervalIdx = 0 // start at beginning of cycle for a predictable walk
	for i, want := range pollIntervals {
		if pollIntervals[a.intervalIdx] != want {
			t.Errorf("step %d: want %v, got %v", i, want, pollIntervals[a.intervalIdx])
		}
		a = update(a, key('p'))
	}
	// After cycling through all intervals, wraps back to first (500ms)
	if pollIntervals[a.intervalIdx] != pollIntervals[0] {
		t.Errorf("after full cycle: want %v, got %v", pollIntervals[0], pollIntervals[a.intervalIdx])
	}
}

// ── Model cursor ──────────────────────────────────────────────────────────────

func appWithProfiles(t *testing.T) *app {
	t.Helper()
	a := newTestApp()
	a.focused = paneModels
	// Inject registry so profiles() returns something
	a.reg = &Registry{
		Order: []string{"alpha", "beta", "gamma"},
		Models: map[string]ModelConfig{
			"alpha": {Name: "Alpha"},
			"beta":  {Name: "Beta"},
			"gamma": {Name: "Gamma"},
		},
	}
	a.cursor = 0
	return a
}

func TestModelCursor_down(t *testing.T) {
	a := appWithProfiles(t)
	a = update(a, skey(tea.KeyDown))
	if a.cursor != 1 {
		t.Errorf("down from 0: want cursor=1, got %d", a.cursor)
	}
}

func TestModelCursor_up(t *testing.T) {
	a := appWithProfiles(t)
	a.cursor = 2
	a = update(a, skey(tea.KeyUp))
	if a.cursor != 1 {
		t.Errorf("up from 2: want cursor=1, got %d", a.cursor)
	}
}

func TestModelCursor_clampBottom(t *testing.T) {
	a := appWithProfiles(t)
	a.cursor = 2 // already at last
	a = update(a, skey(tea.KeyDown))
	if a.cursor != 2 {
		t.Errorf("down at last: want cursor=2 (clamped), got %d", a.cursor)
	}
}

func TestModelCursor_clampTop(t *testing.T) {
	a := appWithProfiles(t)
	a.cursor = 0
	a = update(a, skey(tea.KeyUp))
	if a.cursor != 0 {
		t.Errorf("up at first: want cursor=0 (clamped), got %d", a.cursor)
	}
}

func TestModelCursor_jkAlias(t *testing.T) {
	a := appWithProfiles(t)
	a = update(a, key('j'))
	if a.cursor != 1 {
		t.Errorf("j: want cursor=1, got %d", a.cursor)
	}
	a = update(a, key('k'))
	if a.cursor != 0 {
		t.Errorf("k: want cursor=0, got %d", a.cursor)
	}
}

func TestModelCursor_onlyInModelsPanel(t *testing.T) {
	a := appWithProfiles(t)
	a.focused = paneInference // different panel
	a = update(a, skey(tea.KeyDown))
	if a.cursor != 0 {
		t.Errorf("down in non-models panel: cursor should not move, got %d", a.cursor)
	}
}

// ── applyData ─────────────────────────────────────────────────────────────────

func TestApplyData_decodeRate(t *testing.T) {
	a := newTestApp()
	gen1 := 1000.0
	t1 := time.Now()

	a.prevGen = &gen1
	a.prevGenTime = t1
	a.prevModelID = "model-x"

	gen2 := 1387.5
	data := AppData{
		Active:    &ActiveModel{ID: "model-x", Port: 9100},
		Metrics:   &VLLMMetrics{GenTotal: &gen2},
		FetchedAt: t1.Add(time.Second),
	}
	a.applyData(data)

	if a.decodeRate == nil {
		t.Fatal("want decodeRate set, got nil")
	}
	// (1387.5 - 1000) / 1.0 = 387.5
	if *a.decodeRate < 380 || *a.decodeRate > 395 {
		t.Errorf("decodeRate: want ~387.5, got %f", *a.decodeRate)
	}
}

func TestApplyData_decodeRateResetOnModelSwitch(t *testing.T) {
	a := newTestApp()
	gen := 5000.0
	a.prevGen = &gen
	a.prevGenTime = time.Now().Add(-time.Second)
	a.prevModelID = "old-model"

	gen2 := 6000.0
	data := AppData{
		Active:    &ActiveModel{ID: "new-model", Port: 9100},
		Metrics:   &VLLMMetrics{GenTotal: &gen2},
		FetchedAt: time.Now(),
	}
	a.applyData(data)

	// Rate should NOT be calculated — model changed, prevGen was reset
	if a.decodeRate != nil {
		t.Errorf("decodeRate: want nil after model switch, got %f", *a.decodeRate)
	}
}

func TestApplyData_fallsBackToTPS(t *testing.T) {
	a := newTestApp()
	tps := 250.0
	data := AppData{
		Active:    &ActiveModel{ID: "m", Port: 9100},
		Metrics:   &VLLMMetrics{TokPerS: &tps},
		FetchedAt: time.Now(),
	}
	a.applyData(data)

	if a.decodeRate == nil {
		t.Fatal("want decodeRate from TokPerS, got nil")
	}
	if *a.decodeRate != tps {
		t.Errorf("want %f, got %f", tps, *a.decodeRate)
	}
}

func TestApplyData_noModel(t *testing.T) {
	a := newTestApp()
	a.applyData(AppData{FetchedAt: time.Now()})
	if a.data.Active != nil {
		t.Errorf("want nil active model, got %+v", a.data.Active)
	}
	if a.decodeRate != nil {
		t.Errorf("want nil decodeRate with no model, got %f", *a.decodeRate)
	}
}

// ── View ──────────────────────────────────────────────────────────────────────

func TestView_loadingBeforeSize(t *testing.T) {
	a := newApp("", time.Second, "", "")
	// w=0, h=0 — no window size message yet
	out := a.View()
	if out != "Loading..." {
		t.Errorf("want 'Loading...', got %q", out)
	}
}

func TestView_rendersWithNoData(t *testing.T) {
	a := newTestApp()
	out := a.View()
	if len(out) == 0 {
		t.Error("View() returned empty string")
	}
	if strings.Contains(out, "panic") {
		t.Errorf("View() contains 'panic': %s", out)
	}
}

func TestView_rendersWithActiveModel(t *testing.T) {
	a := newTestApp()
	kv := 0.12
	tps := 300.0
	ttft := 0.9
	gen := 5000.0
	a.applyData(AppData{
		Active:  &ActiveModel{ID: "qwen3.6-35b-code", Port: 9104},
		Metrics: &VLLMMetrics{Running: 2, Waiting: 1, KVCache: &kv, TokPerS: &tps, TTFT: &ttft, GenTotal: &gen},
		GPUs: []GPUInfo{
			{Index: 0, VRAMUsed: 32e9, VRAMTotal: 34e9, UsePercent: 95, Temp: 72},
		},
		ROCMAvail: true,
		FetchedAt: time.Now(),
	})
	out := a.View()
	if !strings.Contains(out, "qwen3.6-35b-code") {
		t.Errorf("View(): want model name in output, got:\n%s", out)
	}
}

func TestView_fullscreenRendersOnlyFocusedPanel(t *testing.T) {
	a := newTestApp()
	a.focused = paneGPU
	a = update(a, key('f'))
	out := a.View()
	if !strings.Contains(out, "fullscreen") {
		t.Errorf("fullscreen view: want 'fullscreen' indicator in output")
	}
}

func TestView_statusBarShowsPollInterval(t *testing.T) {
	a := newTestApp()
	out := a.View()
	if !strings.Contains(out, "1s") {
		t.Errorf("status bar: want current poll interval (1s), got:\n%s", out)
	}
}

// ── Quit ─────────────────────────────────────────────────────────────────────

func TestQuit_returnsCmd(t *testing.T) {
	a := newTestApp()
	_, cmd := a.Update(key('q'))
	if cmd == nil {
		t.Error("q: want quit cmd, got nil")
	}
}
