package main

import (
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// ── Panel IDs ──────────────────────────────────────────────────────────────────

type panelID int

const (
	paneInference panelID = iota
	paneGPU
	paneModels
	paneConfig
	paneLogs
	paneTokens
	paneCount
)

var panelNames = [paneCount]string{"Inference", "GPU", "Models", "Config", "Logs", "Tokens"}

// ── Poll intervals ─────────────────────────────────────────────────────────────

var pollIntervals = []time.Duration{
	500 * time.Millisecond,
	1 * time.Second,
	2 * time.Second,
	5 * time.Second,
	15 * time.Second,
}

// ── Styles ─────────────────────────────────────────────────────────────────────

var (
	clrFocused  = lipgloss.Color("39")  // bright blue
	clrActive   = lipgloss.Color("82")  // bright green — loaded model indicator
	clrSelected = lipgloss.Color("33")  // blue — cursor in model list
	clrGreen    = lipgloss.Color("82")
	clrYellow   = lipgloss.Color("220")
	clrRed      = lipgloss.Color("196")
	clrDim      = lipgloss.Color("240")
	clrWhite    = lipgloss.Color("15")

	stDim     = lipgloss.NewStyle().Foreground(clrDim)
	stGreen   = lipgloss.NewStyle().Foreground(clrGreen)
	stYellow  = lipgloss.NewStyle().Foreground(clrYellow)
	stRed     = lipgloss.NewStyle().Foreground(clrRed)
	stActive  = lipgloss.NewStyle().Foreground(clrActive).Bold(true)
	stBold    = lipgloss.NewStyle().Foreground(clrWhite).Bold(true)
	stCursor  = lipgloss.NewStyle().Foreground(clrSelected).Bold(true)
)

func thStyle(v, lo, hi float64) lipgloss.Style {
	switch {
	case v < lo:
		return stGreen
	case v < hi:
		return stYellow
	default:
		return stRed
	}
}

// ── Messages ───────────────────────────────────────────────────────────────────

type msgTick        struct{}
type msgData        AppData
type msgLog         []string
type msgSwapDone    struct{ profile string; err error }
type msgUnloadDone  struct{ err error }

// ── App ────────────────────────────────────────────────────────────────────────

type app struct {
	// Terminal size
	w, h int

	// Navigation
	focused    panelID
	fullscreen bool

	// Settings
	baseURL     string
	intervalIdx int
	configPath  string
	logPath     string

	// Registry
	reg    *Registry
	regErr error

	// Live data
	data        AppData
	prevGen     *float64
	prevGenTime time.Time
	prevModelID string
	decodeRate  *float64

	// Token throughput history
	tokHist     RingBuffer
	peakTokPerS float64

	// Prefill (encode) throughput history
	prefillHist     RingBuffer
	prevPrompt      *float64
	prefillRate     *float64
	peakPrefillPerS float64

	// Models panel
	cursor    int
	swapping  bool
	swapFor   string
	swapMsg   string
	swapMsgAt time.Time
	spin      spinner.Model

	// Scrollable panels
	cfgVP viewport.Model
	logVP viewport.Model
}

func newApp(baseURL string, interval time.Duration, configPath, logPath string) *app {
	idx := 1
	for i, d := range pollIntervals {
		if d == interval {
			idx = i
			break
		}
	}
	reg, regErr := loadRegistry(configPath)

	sp := spinner.New()
	sp.Spinner = spinner.Dot
	sp.Style = lipgloss.NewStyle().Foreground(clrFocused)

	a := &app{
		baseURL:     baseURL,
		intervalIdx: idx,
		configPath:  configPath,
		logPath:     logPath,
		reg:         reg,
		regErr:      regErr,
		spin:        sp,
		cfgVP:       viewport.New(40, 10),
		logVP:       viewport.New(80, 10),
	}
	a.refreshConfigView()
	return a
}

// ── bubbletea interface ────────────────────────────────────────────────────────

func (a *app) Init() tea.Cmd {
	return tea.Batch(
		tea.SetWindowTitle("llmpanel"),
		a.cmdFetch(),
		a.cmdLog(),
		a.cmdTick(),
	)
}

func (a *app) cmdTick() tea.Cmd {
	return tea.Tick(pollIntervals[a.intervalIdx], func(time.Time) tea.Msg { return msgTick{} })
}

func (a *app) cmdFetch() tea.Cmd {
	url := a.baseURL
	return func() tea.Msg { return msgData(fetchAll(url)) }
}

func (a *app) cmdLog() tea.Cmd {
	path := a.logPath
	return func() tea.Msg {
		f, err := os.Open(path)
		if err != nil {
			return msgLog(nil)
		}
		defer f.Close()
		b, _ := io.ReadAll(f)
		lines := strings.Split(strings.TrimRight(string(b), "\n"), "\n")
		if len(lines) > 500 {
			lines = lines[len(lines)-500:]
		}
		return msgLog(lines)
	}
}

func (a *app) cmdSwap(profile string) tea.Cmd {
	url := a.baseURL
	return func() tea.Msg {
		err := swapModel(url, profile)
		return msgSwapDone{profile: profile, err: err}
	}
}

func (a *app) cmdUnload() tea.Cmd {
	url := a.baseURL
	return func() tea.Msg {
		return msgUnloadDone{err: unloadAll(url)}
	}
}

func (a *app) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {

	case tea.WindowSizeMsg:
		a.w, a.h = msg.Width, msg.Height
		a.sizeViewports()
		return a, nil

	case tea.KeyMsg:
		return a.handleKey(msg)

	case msgTick:
		return a, tea.Batch(a.cmdFetch(), a.cmdLog(), a.cmdTick())

	case msgData:
		a.applyData(AppData(msg))
		return a, nil

	case msgLog:
		a.applyLog([]string(msg))
		return a, nil

	case msgSwapDone:
		a.swapping = false
		if msg.err != nil {
			a.swapMsg = fmt.Sprintf("✗ %v", msg.err)
		} else {
			a.swapMsg = fmt.Sprintf("✓ loaded %s", msg.profile)
		}
		a.swapMsgAt = time.Now()
		return a, a.cmdFetch()

	case msgUnloadDone:
		a.swapping = false
		if msg.err != nil {
			a.swapMsg = fmt.Sprintf("✗ unload: %v", msg.err)
		} else {
			a.swapMsg = "✓ unloaded"
		}
		a.swapMsgAt = time.Now()
		return a, a.cmdFetch()

	case spinner.TickMsg:
		if a.swapping {
			var cmd tea.Cmd
			a.spin, cmd = a.spin.Update(msg)
			return a, cmd
		}
		return a, nil
	}

	return a, nil
}

func (a *app) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "q", "ctrl+c":
		return a, tea.Quit

	case "f":
		a.fullscreen = !a.fullscreen
		a.sizeViewports()

	case "esc":
		if a.fullscreen {
			a.fullscreen = false
			a.sizeViewports()
		}

	case "tab":
		a.focused = (a.focused + 1) % paneCount
		a.sizeViewports()

	case "shift+tab":
		a.focused = (a.focused + paneCount - 1) % paneCount
		a.sizeViewports()

	case "1":
		a.focused = paneInference
	case "2":
		a.focused = paneGPU
	case "3":
		a.focused = paneModels
	case "4":
		a.focused = paneConfig
	case "5":
		a.focused = paneLogs
	case "6":
		a.focused = paneTokens

	case "p":
		a.intervalIdx = (a.intervalIdx + 1) % len(pollIntervals)
		return a, a.cmdTick()

	case "r":
		reg, regErr := loadRegistry(a.configPath)
		a.reg, a.regErr = reg, regErr
		a.refreshConfigView()

	case "up", "k":
		switch a.focused {
		case paneModels:
			if a.cursor > 0 {
				a.cursor--
				a.refreshConfigView()
			}
		case paneConfig:
			a.cfgVP.LineUp(1)
		case paneLogs:
			a.logVP.LineUp(3)
		}

	case "down", "j":
		switch a.focused {
		case paneModels:
			profiles := a.profiles()
			if a.cursor < len(profiles)-1 {
				a.cursor++
				a.refreshConfigView()
			}
		case paneConfig:
			a.cfgVP.LineDown(1)
		case paneLogs:
			a.logVP.LineDown(3)
		}

	case "pgup":
		switch a.focused {
		case paneConfig:
			a.cfgVP.LineUp(a.cfgVP.Height)
		case paneLogs:
			a.logVP.LineUp(a.logVP.Height)
		}

	case "pgdown":
		switch a.focused {
		case paneConfig:
			a.cfgVP.LineDown(a.cfgVP.Height)
		case paneLogs:
			a.logVP.LineDown(a.logVP.Height)
		}

	case "G":
		a.logVP.GotoBottom()

	case "g":
		a.logVP.GotoTop()

	case "enter", "s":
		if a.focused == paneModels && !a.swapping {
			profiles := a.profiles()
			if a.cursor >= 0 && a.cursor < len(profiles) {
				target := profiles[a.cursor]
				a.swapping = true
				a.swapFor = target
				a.swapMsg = ""
				return a, tea.Batch(a.cmdSwap(target), a.spin.Tick)
			}
		}

	case "u":
		if !a.swapping && a.data.Active != nil {
			a.swapping = true
			a.swapFor = ""
			a.swapMsg = ""
			return a, tea.Batch(a.cmdUnload(), a.spin.Tick)
		}
	}

	return a, nil
}

// ── Data updates ───────────────────────────────────────────────────────────────

func (a *app) applyData(data AppData) {
	currID := ""
	if data.Active != nil {
		currID = data.Active.ID
	}
	if currID != a.prevModelID {
		a.prevGen = nil
		a.decodeRate = nil
		a.prevPrompt = nil
		a.prefillRate = nil
		a.prevModelID = currID
	}
	prevTime := a.prevGenTime
	if data.Metrics != nil && data.Metrics.GenTotal != nil {
		gen := *data.Metrics.GenTotal
		if a.prevGen != nil && !a.prevGenTime.IsZero() {
			elapsed := data.FetchedAt.Sub(a.prevGenTime).Seconds()
			if elapsed > 0.1 {
				r := (gen - *a.prevGen) / elapsed
				a.decodeRate = &r
			}
		}
		a.prevGen = &gen
		a.prevGenTime = data.FetchedAt
	} else {
		if data.Metrics != nil {
			a.decodeRate = data.Metrics.TokPerS
		} else {
			a.decodeRate = nil
		}
	}

	if data.Metrics != nil && data.Metrics.PromptTotal != nil {
		pt := *data.Metrics.PromptTotal
		if a.prevPrompt != nil && !prevTime.IsZero() {
			elapsed := data.FetchedAt.Sub(prevTime).Seconds()
			if elapsed > 0.1 {
				r := (pt - *a.prevPrompt) / elapsed
				a.prefillRate = &r
			}
		}
		a.prevPrompt = &pt
	} else {
		a.prefillRate = nil
	}

	a.data = data

	rate := 0.0
	if a.decodeRate != nil {
		rate = *a.decodeRate
	}
	a.tokHist.Push(rate)
	if rate > a.peakTokPerS {
		a.peakTokPerS = rate
	}

	prefillVal := 0.0
	if a.prefillRate != nil {
		prefillVal = *a.prefillRate
	}
	a.prefillHist.Push(prefillVal)
	if prefillVal > a.peakPrefillPerS {
		a.peakPrefillPerS = prefillVal
	}

	// Keep model cursor on the loaded model unless user is navigating
	if !a.swapping && data.Active != nil {
		for i, p := range a.profiles() {
			if p == data.Active.ID {
				a.cursor = i
				break
			}
		}
	}
}

func (a *app) applyLog(lines []string) {
	if lines == nil {
		return
	}
	a.logVP.SetContent(strings.Join(lines, "\n"))
	a.logVP.GotoBottom()
}

func (a *app) profiles() []string {
	if a.reg != nil && len(a.reg.Order) > 0 {
		return a.reg.Order
	}
	return a.data.Profiles
}

func (a *app) refreshConfigView() {
	profiles := a.profiles()
	if a.reg == nil {
		if a.regErr != nil {
			a.cfgVP.SetContent(fmt.Sprintf("# registry load error\n%v", a.regErr))
		} else {
			a.cfgVP.SetContent("# registry not loaded")
		}
		return
	}
	if len(profiles) == 0 || a.cursor >= len(profiles) {
		a.cfgVP.SetContent("# no profiles")
		return
	}
	a.cfgVP.SetContent(a.reg.ProfileYAML(profiles[a.cursor]))
}

// ── Viewport sizing ────────────────────────────────────────────────────────────

func (a *app) sizeViewports() {
	if a.w == 0 || a.h == 0 {
		return
	}
	if a.fullscreen {
		a.cfgVP.Width = a.w - 1
		a.cfgVP.Height = a.h - 2
		a.logVP.Width = a.w - 1
		a.logVP.Height = a.h - 2
		return
	}
	_, h2, h3, _ := rowHeights(a.h)
	_, rightW := colWidths(a.w)

	a.cfgVP.Width = rightW - 1
	a.cfgVP.Height = h2 - 1
	a.logVP.Width = a.w - 1
	a.logVP.Height = h3 - 1
}

func rowHeights(total int) (h1, h2, h3, h4 int) {
	h1 = clamp(total*15/100, 7, 10)
	h2 = clamp(total*28/100, 8, 14)
	h4 = 9
	h3 = total - h1 - h2 - h4 - 1 // 1 for status bar
	if h3 < 5 {
		h3 = 5
	}
	return
}

func colWidths(total int) (left, right int) {
	left = clamp(total*30/100, 20, 40)
	right = total - left - 1 // -1 for column gap
	return
}

func clamp(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

// ── View ───────────────────────────────────────────────────────────────────────

func (a *app) View() string {
	if a.w == 0 {
		return "Loading..."
	}
	if a.fullscreen {
		return a.viewFull()
	}
	return a.viewGrid()
}

func (a *app) viewFull() string {
	var content string
	switch a.focused {
	case paneInference:
		content = a.renderInference()
	case paneGPU:
		content = a.renderGPU()
	case paneModels:
		content = a.renderModels()
	case paneConfig:
		content = a.cfgVP.View()
	case paneLogs:
		content = a.logVP.View()
	case paneTokens:
		content = a.renderTokens(a.w - 1)
	}
	titleStr := panelNames[a.focused] + " [fullscreen — esc]"
	body := panelHeader(titleStr, a.w, clrFocused, true) + "\n" + content
	pane := lipgloss.NewStyle().
		Width(a.w).
		Height(a.h - 1).
		MaxHeight(a.h - 1).
		Render(body)
	return pane + "\n" + a.renderStatus()
}

func (a *app) viewGrid() string {
	h1, h2, h3, h4 := rowHeights(a.h)
	leftW, rightW := colWidths(a.w)

	gap1 := lipgloss.NewStyle().Width(1).Height(h1).Render("")
	gap2 := lipgloss.NewStyle().Width(1).Height(h2).Render("")

	// Row 1: Inference (60%) + gap + GPU (remaining)
	iW := a.w * 6 / 10
	gW := a.w - iW - 1
	row1 := lipgloss.JoinHorizontal(lipgloss.Top,
		a.panel(paneInference, iW, h1, a.renderInference()),
		gap1,
		a.panel(paneGPU, gW, h1, a.renderGPU()),
	)

	// Row 2: Models (30%) + gap + Config (remaining)
	row2 := lipgloss.JoinHorizontal(lipgloss.Top,
		a.panel(paneModels, leftW, h2, a.renderModels()),
		gap2,
		a.panel(paneConfig, rightW, h2, a.cfgVP.View()),
	)

	// Row 4: Token throughput sparkline (full width)
	row4 := a.panel(paneTokens, a.w, h4, a.renderTokens(a.w-1))

	// Row 3: Logs
	row3 := a.panel(paneLogs, a.w, h3, a.logVP.View())

	return lipgloss.JoinVertical(lipgloss.Left,
		row1, row2, row4, row3, a.renderStatus(),
	)
}

// panelHeader builds a "Name ─────" header rule of exactly w columns.
func panelHeader(name string, w int, fg lipgloss.Color, bold bool) string {
	titleSt := lipgloss.NewStyle().Foreground(fg).Bold(bold)
	title := titleSt.Render(name)
	ruleLen := max(0, w-lipgloss.Width(title)-1)
	return title + " " + lipgloss.NewStyle().Foreground(fg).Render(strings.Repeat("─", ruleLen))
}

// panel renders a section with a "Name ───────" header line, highlighted when focused.
func (a *app) panel(id panelID, w, h int, content string) string {
	focused := a.focused == id
	fg := clrDim
	if focused {
		fg = clrFocused
	}
	header := panelHeader(panelNames[id], w, fg, focused)
	return lipgloss.NewStyle().
		Width(w).
		Height(h).
		MaxHeight(h).
		Render(header + "\n" + content)
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// ── Panel content renderers ────────────────────────────────────────────────────

func (a *app) renderInference() string {
	var sb strings.Builder
	if a.data.Active == nil {
		sb.WriteString(stDim.Render(" No model loaded") + "\n")
		sb.WriteString(stDim.Render(" Running: —  Waiting: —  KV: —") + "\n")
		sb.WriteString(stDim.Render(" Decode: —  PP: —") + "\n")
		sb.WriteString(stDim.Render(" TTFT: —  pfill: —"))
		return sb.String()
	}
	ac := a.data.Active
	sb.WriteString(stActive.Render(fmt.Sprintf(" %s  (:%d)  [● ACTIVE]", ac.ID, ac.Port)) + "\n")

	if a.data.Metrics == nil {
		sb.WriteString(stDim.Render(" Running: —  Waiting: —  KV: —") + "\n")
		sb.WriteString(stDim.Render(" Decode: —  PP: —") + "\n")
		sb.WriteString(stDim.Render(" TTFT: —  pfill: —"))
		return sb.String()
	}

	m := a.data.Metrics

	concLimit := 0
	if a.reg != nil && a.data.Active != nil {
		concLimit = a.reg.Models[a.data.Active.ID].ConcurrencyLimit
	}

	running := int(m.Running)
	waiting := int(m.Waiting)

	var queueStr string
	switch {
	case waiting == 0:
		queueStr = stDim.Render("Q:0")
	case waiting <= 2:
		queueStr = stYellow.Render(fmt.Sprintf("Q:%d", waiting))
	default:
		queueStr = stRed.Render(fmt.Sprintf("Q:%d", waiting))
	}

	if concLimit > 0 {
		barW := 20
		filled := running * barW / concLimit
		if filled > barW {
			filled = barW
		}
		bar := stGreen.Render(strings.Repeat("█", filled)) +
			stDim.Render(strings.Repeat("░", barW-filled))
		frac := stBold.Render(fmt.Sprintf("%d/%d", running, concLimit))
		sb.WriteString(fmt.Sprintf(" [%s] %s  %s\n", bar, frac, queueStr))
	} else {
		sb.WriteString(fmt.Sprintf(" Running: %s  %s\n",
			stBold.Render(fmt.Sprintf("%d", running)), queueStr))
	}

	kvStr := "—"
	if m.KVCache != nil {
		kvStr = fmt.Sprintf("%.1f%%", *m.KVCache*100)
	}
	pfxStr := stDim.Render("—")
	if m.PrefixHitRate != nil {
		pct := *m.PrefixHitRate * 100
		var st lipgloss.Style
		switch {
		case pct >= 70:
			st = stGreen
		case pct >= 30:
			st = stYellow
		default:
			st = stRed
		}
		pfxStr = st.Render(fmt.Sprintf("%.1f%%", pct))
	}
	sb.WriteString(fmt.Sprintf(" KV: %s  PfxHit: %s\n", kvStr, pfxStr))

	decStr := "—"
	if a.decodeRate != nil {
		decStr = fmt.Sprintf("%.0f tok/s", *a.decodeRate)
	} else if m.TokPerS != nil {
		decStr = fmt.Sprintf("%.0f tok/s", *m.TokPerS)
	}
	ppStr := "—"
	if a.prefillRate != nil {
		ppStr = fmt.Sprintf("%.0f tok/s", *a.prefillRate)
	}
	sb.WriteString(fmt.Sprintf(" Decode: %s  PP: %s\n",
		stBold.Render(decStr), stBold.Render(ppStr)))

	ttftStr := stDim.Render("—")
	if m.TTFT != nil {
		t := *m.TTFT
		ttftStr = thStyle(t, 1, 3).Render(fmt.Sprintf("%.2fs", t))
	}
	pfillStr := stDim.Render("—")
	if m.AvgPrefillTime != nil {
		t := *m.AvgPrefillTime
		pfillStr = thStyle(t, 1, 3).Render(fmt.Sprintf("%.2fs", t))
	}
	sb.WriteString(fmt.Sprintf(" TTFT: %s  pfill: %s", ttftStr, pfillStr))

	if !a.data.FetchedAt.IsZero() {
		ago := int(time.Since(a.data.FetchedAt).Seconds())
		sb.WriteString("\n" + stDim.Render(fmt.Sprintf(" refreshed %ds ago", ago)))
	}
	return sb.String()
}

func (a *app) renderGPU() string {
	if !a.data.ROCMAvail {
		return stDim.Render(" rocm-smi unavailable")
	}
	if len(a.data.GPUs) == 0 {
		return stDim.Render(" No GPU data")
	}
	var sb strings.Builder
	sb.WriteString(stDim.Render(fmt.Sprintf(" %-2s  %-11s  %-4s  %-4s  %s",
		"#", "VRAM/Tot GB", "VRM%", "Use%", "Temp")) + "\n")
	for _, g := range a.data.GPUs {
		used := float64(g.VRAMUsed) / 1e9
		total := float64(g.VRAMTotal) / 1e9
		vp := 0.0
		if total > 0 {
			vp = used / total * 100
		}
		sb.WriteString(fmt.Sprintf(" %-2d  %4.1f/%4.1fG   %s  %s  %s\n",
			g.Index, used, total,
			thStyle(vp, 50, 80).Render(fmt.Sprintf("%3.0f%%", vp)),
			thStyle(g.UsePercent, 50, 80).Render(fmt.Sprintf("%3.0f%%", g.UsePercent)),
			thStyle(g.Temp, 70, 85).Render(fmt.Sprintf("%3.0f°C", g.Temp)),
		))
	}
	return strings.TrimRight(sb.String(), "\n")
}

func (a *app) renderModels() string {
	profiles := a.profiles()
	var sb strings.Builder

	// Status line at top
	if a.swapping {
		action := fmt.Sprintf("Loading %s…", a.swapFor)
		if a.swapFor == "" {
			action = "Unloading…"
		}
		sb.WriteString(a.spin.View() + " " + action + "\n")
	} else if a.swapMsg != "" && time.Since(a.swapMsgAt) < 5*time.Second {
		if strings.HasPrefix(a.swapMsg, "✓") {
			sb.WriteString(stGreen.Render(a.swapMsg) + "\n")
		} else {
			sb.WriteString(stRed.Render(a.swapMsg) + "\n")
		}
	}

	activeID := ""
	if a.data.Active != nil {
		activeID = a.data.Active.ID
	}

	for i, p := range profiles {
		sel := i == a.cursor
		loaded := p == activeID
		prefix := "  "
		if sel {
			prefix = "▶ "
		}
		line := prefix + p
		if loaded {
			line += " ●"
		}
		switch {
		case sel && loaded:
			sb.WriteString(stActive.Render(line))
		case sel:
			sb.WriteString(stCursor.Render(line))
		case loaded:
			sb.WriteString(stGreen.Render(line))
		default:
			sb.WriteString(line)
		}
		sb.WriteString("\n")
	}
	return strings.TrimRight(sb.String(), "\n")
}

const sparkIndent = 10

var prefillGradient = buildGradient([]colorStop{
	{0, 60, 0, 120},
	{30, 0, 80, 220},
	{65, 0, 200, 200},
	{100, 0, 230, 100},
})

func (a *app) renderTokens(w int) string {
	sparkW := max(8, w-sparkIndent)
	blank := strings.Repeat(" ", sparkIndent)

	var sb strings.Builder

	// Decode (generation) track — 3 rows
	decVmax := a.peakTokPerS
	if decVmax < 50 {
		decVmax = 50
	}
	decRows := renderMultilineSparkline(a.tokHist.Values(), sparkW, 3, 0, decVmax, tokGradient, decVmax)

	decLabel := stDim.Render(fmt.Sprintf("%-*s", sparkIndent, "decode"))
	sb.WriteString(decLabel + decRows[0] + "\n")
	sb.WriteString(blank + decRows[1] + "\n")
	sb.WriteString(blank + decRows[2] + "\n")

	currStr := "—"
	if a.decodeRate != nil {
		currStr = fmt.Sprintf("%.0f", *a.decodeRate)
	}
	peakStr := "—"
	if a.peakTokPerS > 0 {
		peakStr = fmt.Sprintf("%.0f", a.peakTokPerS)
	}
	genStr := "—"
	if a.data.Metrics != nil && a.data.Metrics.GenTotal != nil {
		genStr = fmt.Sprintf("%.0f", *a.data.Metrics.GenTotal)
	}
	runStr := "—"
	if a.data.Metrics != nil {
		runStr = fmt.Sprintf("%.0f", a.data.Metrics.Running)
	}
	sb.WriteString(fmt.Sprintf(" cur: %s tok/s  peak: %s tok/s  req: %s  gen: %s\n",
		stBold.Render(currStr),
		stGreen.Render(peakStr),
		runStr,
		stDim.Render(genStr),
	))

	// Prefill (encode) track — 2 rows (shorter than decode)
	pfVmax := a.peakPrefillPerS
	if pfVmax < 200 {
		pfVmax = 200
	}
	pfRows := renderMultilineSparkline(a.prefillHist.Values(), sparkW, 2, 0, pfVmax, prefillGradient, pfVmax)

	pfLabel := stDim.Render(fmt.Sprintf("%-*s", sparkIndent, "prefill"))
	sb.WriteString(pfLabel + pfRows[0] + "\n")
	sb.WriteString(blank + pfRows[1] + "\n")

	pfCurStr := "—"
	if a.prefillRate != nil {
		pfCurStr = fmt.Sprintf("%.0f", *a.prefillRate)
	}
	pfPeakStr := "—"
	if a.peakPrefillPerS > 0 {
		pfPeakStr = fmt.Sprintf("%.0f", a.peakPrefillPerS)
	}
	ptStr := "—"
	if a.data.Metrics != nil && a.data.Metrics.PromptTotal != nil {
		ptStr = fmt.Sprintf("%.0f", *a.data.Metrics.PromptTotal)
	}
	sb.WriteString(fmt.Sprintf(" cur: %s tok/s  peak: %s tok/s  prompt: %s",
		stBold.Render(pfCurStr),
		lipgloss.NewStyle().Foreground(lipgloss.Color("#00c8c8")).Render(pfPeakStr),
		stDim.Render(ptStr),
	))

	return sb.String()
}

func (a *app) renderStatus() string {
	d := pollIntervals[a.intervalIdx]
	dStr := d.String()
	hint := fmt.Sprintf(
		" tab panel  f full  ↑↓/jk nav  s/↵ swap  u unload  p poll:%s  r reload  q quit ",
		dStr,
	)
	return lipgloss.NewStyle().
		Foreground(clrDim).
		Width(a.w).
		Render(hint)
}
