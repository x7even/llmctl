package main

import (
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/charmbracelet/lipgloss"
)

// Hardware-aware Models panel: which profiles this machine can run, the
// "N hidden" footer, greyed rows with a reason, and the swap guard.
//
// All state lives on the app model (hw, verdicts, showAll). Verdicts come from
// Supports (hw.go); llmctl owns --force, so the panel never offers a way to
// swap an unsupported profile.

// Style for profiles this hardware cannot run. Adaptive so the grey stays
// readable on both light and dark terminal backgrounds.
var (
	clrUnsupported   = lipgloss.AdaptiveColor{Light: "244", Dark: "241"}
	stUnsupported    = lipgloss.NewStyle().Foreground(clrUnsupported)
	stUnsupportedSel = lipgloss.NewStyle().Foreground(clrUnsupported).Bold(true)
)

// blockMsgTTL is how long the full "cannot run on this hardware" message stays
// in the status bar.
const blockMsgTTL = 10 * time.Second

// ── Hardware + verdicts ────────────────────────────────────────────────────────

// refreshHW detects the hardware once (via a.detectHW, injectable) and
// recomputes every profile's verdict. Called at startup and on 'r'.
func (a *app) refreshHW() {
	if a.detectHW != nil {
		a.hw = a.detectHW()
	}
	a.recomputeVerdicts()
}

// recomputeVerdicts evaluates every profile against a.hw. When the GPU count
// is unknown the panel fails open: no verdicts are stored, so nothing is
// hidden or greyed (verdictFor treats a missing entry as OK).
func (a *app) recomputeVerdicts() {
	a.verdicts = map[string]Verdict{}
	if !a.hw.GPUsKnown() {
		return
	}
	for _, id := range a.allProfiles() {
		var req *Requires
		if a.reg != nil {
			req = a.reg.Models[id].Requirements()
		}
		a.verdicts[id] = Supports(req, a.hw)
	}
}

// verdictFor returns the stored verdict; an unknown profile is permitted.
func (a *app) verdictFor(id string) Verdict {
	if v, ok := a.verdicts[id]; ok {
		return v
	}
	return Verdict{OK: true}
}

// hiddenCount is the number of profiles this hardware cannot run.
func (a *app) hiddenCount() int {
	n := 0
	for _, id := range a.allProfiles() {
		if !a.verdictFor(id).OK {
			n++
		}
	}
	return n
}

// selectedProfile returns the profile under the cursor, or "".
func (a *app) selectedProfile() string {
	ps := a.profiles()
	if a.cursor >= 0 && a.cursor < len(ps) {
		return ps[a.cursor]
	}
	return ""
}

// restoreSelection puts the cursor back on id when it is still listed, else
// clamps it into the (possibly shorter) list, then re-validates the scroll.
func (a *app) restoreSelection(id string) {
	ps := a.profiles()
	if id != "" {
		for i, p := range ps {
			if p == id {
				a.cursor = i
				a.clampModelsScroll()
				return
			}
		}
	}
	a.cursor = clamp(a.cursor, 0, max(0, len(ps)-1))
	a.clampModelsScroll()
}

// toggleShowAll flips the show-all view, keeping the selection on the same
// profile when it is still visible.
func (a *app) toggleShowAll() {
	sel := a.selectedProfile()
	a.clearBlock()
	a.showAll = !a.showAll
	a.restoreSelection(sel)
	a.refreshConfigView()
}

// ── Swap guard ─────────────────────────────────────────────────────────────────

// blockUnsupported reports whether profile cannot run here. When it cannot, it
// sets the panel message and the full status-bar message; the caller must not
// swap. llmctl owns --force.
func (a *app) blockUnsupported(profile string) bool {
	v := a.verdictFor(profile)
	if v.OK {
		return false
	}
	reason := a.reasonText(profile)
	// Short and stable first: both lines are cut to the terminal / column width,
	// so the reason goes in the panel and the way out leads the status bar.
	a.swapMsg = "✗ " + reason
	a.swapMsgAt = time.Now()
	a.hwBlockMsg = fmt.Sprintf("unsupported: use 'llmctl swap --force %s' to try anyway (%s)", profile, reason)
	a.hwBlockAt = a.swapMsgAt
	return true
}

// clearBlock drops a pending "unsupported" message (status bar and panel line)
// so it cannot linger about one profile while the user acts on another. A
// swap result that replaced the panel message since is left alone.
func (a *app) clearBlock() {
	if a.hwBlockMsg == "" {
		return
	}
	if a.swapMsgAt.Equal(a.hwBlockAt) {
		a.swapMsg = ""
	}
	a.hwBlockMsg = ""
}

// reasonText is the short, human reason a profile is unsupported, e.g.
// "needs 4 GPUs, have 2 (est)". Empty for a supported profile.
func (a *app) reasonText(profile string) string {
	v := a.verdictFor(profile)
	if v.OK {
		return ""
	}
	parts := make([]string, 0, len(v.Reasons))
	for _, r := range v.Reasons {
		parts = append(parts, shortReason(r))
	}
	s := strings.Join(parts, "; ")
	if v.Estimate {
		s += " (est)"
	}
	return s
}

var (
	reReasonGPUs    = regexp.MustCompile(`^needs gpus \[([^\]]*)\], detected (\d+)$`)
	reReasonMinGPUs = regexp.MustCompile(`^needs min_gpus (\d+), detected (\d+)$`)
	reReasonRAM     = regexp.MustCompile(`^needs host RAM (\S+) GiB \(min \S+\), measured (\S+) GiB$`)
)

// shortReason rewrites a Verdict.Reasons entry into a compact phrase:
//
//	needs gpus [4], detected 2        -> needs 4 GPUs, have 2
//	needs gpus [2, 4], detected 1     -> needs 2 or 4 GPUs, have 1
//	needs min_gpus 2, detected 1      -> needs 2+ GPUs, have 1
//	needs host RAM 96 GiB (min 88.3), measured 62 GiB -> needs 96 GiB RAM, have 62
//
// An unrecognised reason is returned unchanged.
func shortReason(r string) string { return reasonPhrase(r, false) }

// reasonPhrase renders a Verdict.Reasons entry. compact drops "needs" and
// "have N" (the title already shows the hardware) so it fits beside a long
// profile name: "4 GPU", "2/4 GPU", "2+ GPU", "96 GiB RAM".
func reasonPhrase(r string, compact bool) string {
	if m := reReasonGPUs.FindStringSubmatch(r); m != nil {
		var nums []string
		for _, f := range strings.Split(m[1], ",") {
			if f = strings.TrimSpace(f); f != "" {
				nums = append(nums, f)
			}
		}
		if len(nums) > 0 {
			if compact {
				return strings.Join(nums, "/") + " GPU"
			}
			list := nums[0]
			if len(nums) > 1 {
				list = strings.Join(nums[:len(nums)-1], ", ") + " or " + nums[len(nums)-1]
			}
			unit := "GPUs"
			if len(nums) == 1 && nums[0] == "1" {
				unit = "GPU"
			}
			return fmt.Sprintf("needs %s %s, have %s", list, unit, m[2])
		}
	}
	if m := reReasonMinGPUs.FindStringSubmatch(r); m != nil {
		if compact {
			return m[1] + "+ GPU"
		}
		return fmt.Sprintf("needs %s+ GPUs, have %s", m[1], m[2])
	}
	if m := reReasonRAM.FindStringSubmatch(r); m != nil {
		if compact {
			return m[1] + " GiB RAM"
		}
		return fmt.Sprintf("needs %s GiB RAM, have %s", m[1], m[2])
	}
	return r
}

// compactReasonText is reasonText in the short form used on greyed list rows,
// where only ~14 columns are left beside the longest profile names. The
// estimate marker is a trailing "est"; the full wording is in the status bar.
func (a *app) compactReasonText(profile string) string {
	v := a.verdictFor(profile)
	if v.OK {
		return ""
	}
	parts := make([]string, 0, len(v.Reasons))
	for _, r := range v.Reasons {
		parts = append(parts, reasonPhrase(r, true))
	}
	s := strings.Join(parts, ", ")
	if v.Estimate {
		s += " est"
	}
	return s
}

// ── Rendering helpers ──────────────────────────────────────────────────────────

// modelsWidth is the column width available to the Models panel.
func (a *app) modelsWidth() int {
	if a.fullscreen {
		return a.w
	}
	left, _ := colWidths(a.w)
	return left
}

// modelsFooter returns the plain-text footer line for the Models panel, or ""
// when there is nothing to say. It picks the longest variant that fits width.
func (a *app) modelsFooter(width int) string {
	var variants []string
	switch hidden := a.hiddenCount(); {
	case !a.hw.GPUsKnown():
		variants = []string{"hardware not detected - showing all", "hw not detected - showing all", "hw not detected"}
	case hidden == 0:
		return ""
	case a.showAll:
		variants = []string{
			fmt.Sprintf("%d greyed (needs more GPUs/RAM) - a: hide", hidden),
			fmt.Sprintf("%d greyed - a: hide", hidden),
			"a: hide",
		}
	default:
		variants = []string{
			fmt.Sprintf("%d hidden (needs more GPUs/RAM) - a: show all", hidden),
			fmt.Sprintf("%d hidden - a: show all", hidden),
			"a: show all",
		}
	}
	for _, v := range variants {
		if lipgloss.Width(" "+v) < width {
			return " " + v
		}
	}
	return truncateRunes(" "+variants[len(variants)-1], width-1)
}

// modelsFooterLines is how many rows the footer takes (0 or 1); it does not
// depend on the width so scrolling maths stays stable.
func (a *app) modelsFooterLines() int {
	if a.modelsFooter(1<<20) != "" {
		return 1
	}
	return 0
}

// hwSummary describes the detected hardware: "4 GPU · 188 GiB RAM", with
// "(override)" when the GPU count was forced. compact drops the RAM part.
func (a *app) hwSummary(compact bool) string {
	var gpu string
	if a.hw.GPUsKnown() {
		gpu = fmt.Sprintf("%d GPU", a.hw.GPUCount)
		if a.hw.Source == "override" {
			gpu += " (override)"
		}
	} else {
		gpu = "GPU ?"
	}
	if compact || !a.hw.RAMKnown() {
		return gpu
	}
	return fmt.Sprintf("%s · %.0f GiB RAM", gpu, a.hw.HostRAMGiB)
}

// hwTitleSuffix returns the hardware summary if it fits in avail columns,
// trying the full form first and the compact one second; "" when neither fits.
func (a *app) hwTitleSuffix(avail int) string {
	for _, compact := range []bool{false, true} {
		if s := a.hwSummary(compact); lipgloss.Width(s) <= avail {
			return s
		}
	}
	return ""
}

// panelHeaderSuffix is panelHeader plus an optional dim suffix after the name.
func panelHeaderSuffix(name, suffix string, w int, fg lipgloss.Color, bold bool) string {
	if suffix == "" {
		return panelHeader(name, w, fg, bold)
	}
	title := lipgloss.NewStyle().Foreground(fg).Bold(bold).Render(name) + " " + stDim.Render(suffix)
	ruleLen := max(0, w-lipgloss.Width(title)-1)
	return title + " " + lipgloss.NewStyle().Foreground(fg).Render(strings.Repeat("─", ruleLen))
}

// headerFor builds the header rule for panel id, adding the hardware summary
// to the Models panel when it fits.
func (a *app) headerFor(name string, id panelID, w int, fg lipgloss.Color, bold bool) string {
	if id != paneModels {
		return panelHeader(name, w, fg, bold)
	}
	// name + " " + suffix + " " + at least one rule character
	suffix := a.hwTitleSuffix(w - lipgloss.Width(name) - 3)
	return panelHeaderSuffix(name, suffix, w, fg, bold)
}

// truncateRunes shortens plain text to at most n columns, ending in an
// ellipsis when cut. Only for unstyled strings.
func truncateRunes(s string, n int) string {
	if n <= 0 {
		return ""
	}
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	if n == 1 {
		return "…"
	}
	return string(r[:n-1]) + "…"
}
