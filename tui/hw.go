package main

import (
	"context"
	"fmt"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Hardware detection and per-profile requirement checks.
//
// This is a port of scripts/llmhw.py (the reference implementation shared by
// scripts/configure and bin/llmctl). The two must agree: tests/fixtures/
// llmhw_cases.json is loaded by both this package's tests and
// tests/test_llmhw_parity.py. If you change a rule here, change it there.

const (
	gib             = 1024 * 1024 * 1024
	minGPUVRAMBytes = 8 * gib // smaller devices are iGPUs / display adapters
	ramTolerance    = 0.92    // a "96 GB" box reports ~94 GiB MemTotal

	defaultDRMRoot     = "/sys/class/drm"
	defaultMeminfoPath = "/proc/meminfo"

	// GPUCountEnv is the environment override for the detected GPU count.
	GPUCountEnv = "LLMSTACK_GPU_COUNT"

	// UnknownGPUs is HW.GPUCount when nothing could be detected.
	UnknownGPUs = -1
)

// HW describes the machine the stack runs on.
//
// GPUCount is UnknownGPUs (-1) when nothing was detected; 0 is a real answer
// ("sysfs/rocm-smi answered, no discrete GPU"). HostRAMGiB <= 0 means unknown.
// Both unknown values are permissive in Supports.
type HW struct {
	GPUCount       int       // discrete GPUs with >= 8 GiB VRAM; UnknownGPUs if undetected
	VRAMGiB        []float64 // per counted GPU, when known (empty for override / rocm-smi --listdevices)
	HostRAMGiB     float64   // /proc/meminfo MemTotal in GiB; <= 0 = unknown
	Source         string    // "override" | "sysfs" | "amd-smi" | "rocm-smi" | "none"
	IgnoredDevices int       // devices under 8 GiB VRAM that were not counted (iGPU)
}

// UnknownHW is "nothing detected": Supports is permissive for it. Note that
// the zero HW{} is NOT unknown (it means zero GPUs), so use this constructor.
func UnknownHW() HW { return HW{GPUCount: UnknownGPUs, Source: "none"} }

// GPUsKnown reports whether the GPU count is a real value.
func (h HW) GPUsKnown() bool { return h.GPUCount >= 0 }

// RAMKnown reports whether the host RAM size is a real value.
func (h HW) RAMKnown() bool { return h.HostRAMGiB > 0 }

// HWProbe holds the injectable inputs of detection. The zero value probes the
// real machine; tests point DRMRoot / MeminfoPath at fake trees and set Run.
type HWProbe struct {
	DRMRoot     string                              // default /sys/class/drm
	MeminfoPath string                              // default /proc/meminfo
	Run         func(argv []string) (string, error) // default: exec argv, stdout only, 10 s timeout
}

// DetectHW probes the real machine. override >= 0 replaces GPU detection
// (see GPUCountOverride); pass -1 for none.
func DetectHW(override int) HW { return HWProbe{}.Detect(override) }

// Detect describes the machine. Rules (identical to llmhw.detect):
//   - override >= 0: GPUCount = override, Source "override", host RAM still read.
//   - else count discrete GPUs under DRMRoot/card<N>, de-duplicated by the
//     resolved `device` path, whose mem_info_vram_total is >= 8 GiB.
//   - amd-smi (then rocm-smi) is consulted only when no sysfs device exposes VRAM info at all.
//   - nothing found: GPUCount UnknownGPUs, Source "none".
func (p HWProbe) Detect(override int) HW {
	meminfoPath := p.MeminfoPath
	if meminfoPath == "" {
		meminfoPath = defaultMeminfoPath
	}
	hw := UnknownHW()
	if text, err := os.ReadFile(meminfoPath); err == nil {
		if g, ok := ParseMemTotalGiB(string(text)); ok {
			hw.HostRAMGiB = g
		}
	}
	if override >= 0 {
		hw.GPUCount, hw.Source = override, "override"
		return hw
	}

	drm := p.DRMRoot
	if drm == "" {
		drm = defaultDRMRoot
	}
	sizes, found := sysfsVRAMSizes(drm)
	source := "sysfs"
	if !found {
		run := p.Run
		if run == nil {
			run = runCmd
		}
		sizes, found, source = smiVRAMSizes(run)
	}
	if !found {
		return hw
	}
	count := 0
	for _, s := range sizes {
		if s < 0 || s >= minGPUVRAMBytes { // s < 0 = size unknown, counted
			count++
			if s >= 0 {
				hw.VRAMGiB = append(hw.VRAMGiB, math.Round(float64(s)/gib*100)/100)
			}
		}
	}
	hw.GPUCount, hw.Source, hw.IgnoredDevices = count, source, len(sizes)-count
	return hw
}

var reCardDir = regexp.MustCompile(`^card\d+$`)

// sysfsVRAMSizes returns the VRAM bytes of every distinct device under a DRM
// sysfs root; found is false when no device exposes mem_info_vram_total.
// Connector entries (card0-DP-1) are ignored.
func sysfsVRAMSizes(drmRoot string) (sizes []int64, found bool) {
	cards, _ := filepath.Glob(filepath.Join(drmRoot, "card*"))
	sort.Strings(cards)
	seen := map[string]bool{}
	for _, card := range cards {
		if !reCardDir.MatchString(filepath.Base(card)) {
			continue
		}
		dev := filepath.Join(card, "device")
		real, err := filepath.EvalSymlinks(dev)
		if err != nil {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(dev, "mem_info_vram_total"))
		if err != nil {
			continue
		}
		vram, err := strconv.ParseInt(strings.TrimSpace(string(raw)), 10, 64)
		if err != nil {
			continue
		}
		if vram < 0 {
			vram = 0 // nonsense: seen but too small to count (negative means "size unknown" downstream)
		}
		found = true
		if seen[real] {
			continue
		}
		seen[real] = true
		sizes = append(sizes, vram)
	}
	return sizes, found
}

func runCmd(argv []string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	out, err := exec.CommandContext(ctx, argv[0], argv[1:]...).Output() // stderr discarded
	return string(out), err
}

var reRocmGPU = regexp.MustCompile(`(?m)^GPU\[(\d+)\]`)

// smiVRAMSizes asks readGPUs (amd-smi first, then rocm-smi) for per-GPU VRAM, which lets detection drop iGPUs.
// When neither reports sizes it falls back to `rocm-smi --listdevices` (sizes unknown, reported as -1).
// source is the tool that answered.
func smiVRAMSizes(run func([]string) (string, error)) (sizes []int64, found bool, source string) {
	gpus, tool := readGPUs(run)
	if len(gpus) > 0 {
		for _, g := range gpus {
			sizes = append(sizes, g.VRAMTotal)
		}
		return sizes, true, tool
	}
	out, err := run([]string{"rocm-smi", "--listdevices"})
	if err != nil {
		return nil, false, "none"
	}
	idx := map[string]bool{}
	for _, m := range reRocmGPU.FindAllStringSubmatch(out, -1) {
		idx[m[1]] = true
	}
	if len(idx) == 0 {
		return nil, false, "none"
	}
	for range idx {
		sizes = append(sizes, -1)
	}
	return sizes, true, "rocm-smi"
}

var reMemTotal = regexp.MustCompile(`(?m)^MemTotal:\s+(\d+)\s*kB`)

// ParseMemTotalGiB reads MemTotal (kB) from /proc/meminfo text, in GiB.
func ParseMemTotalGiB(meminfo string) (float64, bool) {
	m := reMemTotal.FindStringSubmatch(meminfo)
	if m == nil {
		return 0, false
	}
	kb, err := strconv.ParseInt(m[1], 10, 64)
	if err != nil {
		return 0, false
	}
	return float64(kb) / (1024 * 1024), true
}

// ParseGPUCount parses a GPU-count override (non-negative integer).
// origin names the source in the error ("--gpu-count", GPUCountEnv).
func ParseGPUCount(value, origin string) (int, error) {
	n, err := strconv.Atoi(strings.TrimSpace(value))
	if err != nil || n < 0 {
		return 0, fmt.Errorf("%s must be a non-negative integer, got %q", origin, value)
	}
	return n, nil
}

// GPUCountOverride resolves the GPU count to simulate: the --gpu-count flag
// value wins, else the LLMSTACK_GPU_COUNT environment variable, else -1.
// An invalid flag value is an error (fatal for the caller); an invalid env
// value is returned as warn and ignored (fail open), like bin/llmctl.
func GPUCountOverride(flagVal string, getenv func(string) string) (n int, warn, err error) {
	if strings.TrimSpace(flagVal) != "" {
		n, err = ParseGPUCount(flagVal, "--gpu-count")
		if err != nil {
			return -1, nil, err
		}
		return n, nil, nil
	}
	if getenv == nil {
		getenv = os.Getenv
	}
	raw := strings.TrimSpace(getenv(GPUCountEnv))
	if raw == "" {
		return -1, nil, nil
	}
	n, err = ParseGPUCount(raw, GPUCountEnv)
	if err != nil {
		return -1, err, nil
	}
	return n, nil, nil
}

// ── Supports ───────────────────────────────────────────────────────────────────

// Verdict is the outcome of Supports.
type Verdict struct {
	OK       bool     // profile fits this hardware (permissive when unknown)
	Use      int      // TP size (gpus) or split size (min_gpus); 0 when not OK or no GPU rule
	Reasons  []string // one entry per failed check; empty when OK
	Estimate bool     // the profile's requirements are estimates, not measured here
}

// Supports reports whether a profile with requirements req can run on hw.
// Mirrors llmhw.supports exactly:
//   - gpus: [..]   the largest allowed count <= hw.GPUCount is the TP size
//   - min_gpus: N  OK when GPUCount >= N; the split size is GPUCount
//   - host_ram_gib not OK when host RAM is known and < 0.92 x the need
//   - nil req, or unknown GPU count / host RAM: permissive
//
// If both gpus and min_gpus are set, gpus wins (as in Python). min_gpus 0 is
// "unset" here, whereas Python would return Use = GPUCount for `min_gpus: 0`;
// that value is meaningless in real configs.
func Supports(req *Requires, hw HW) Verdict {
	var r Requires
	if req != nil {
		r = *req
	}
	v := Verdict{Estimate: r.Estimate}
	var reasons []string
	if hw.GPUsKnown() {
		n := hw.GPUCount
		switch {
		case r.GPUs != nil:
			best, fits := 0, false
			for _, g := range r.GPUs {
				if g <= n && (!fits || g > best) {
					best, fits = g, true
				}
			}
			if fits {
				v.Use = best
			} else {
				reasons = append(reasons, fmt.Sprintf("needs gpus %s, detected %d", fmtIntList(r.GPUs), n))
			}
		case r.MinGPUs > 0:
			if n >= r.MinGPUs {
				v.Use = n
			} else {
				reasons = append(reasons, fmt.Sprintf("needs min_gpus %d, detected %d", r.MinGPUs, n))
			}
		}
	}
	if need := r.HostRAMGiB; need > 0 && hw.RAMKnown() && hw.HostRAMGiB < ramTolerance*need {
		reasons = append(reasons, fmt.Sprintf("needs host RAM %s GiB (min %s), measured %s GiB",
			fmtGiB(need), fmtGiB(ramTolerance*need), fmtGiB(hw.HostRAMGiB)))
	}
	if len(reasons) > 0 {
		v.Use = 0
		v.Reasons = reasons
		return v
	}
	v.OK = true
	return v
}

// fmtGiB formats like llmhw._fmt_gib: "96" for whole values, else one decimal.
func fmtGiB(x float64) string {
	if math.Abs(x-math.RoundToEven(x)) < 0.05 {
		return fmt.Sprintf("%.0f", x)
	}
	return fmt.Sprintf("%.1f", x)
}

// fmtIntList formats like a Python list repr: [2, 4].
func fmtIntList(xs []int) string {
	parts := make([]string, len(xs))
	for i, x := range xs {
		parts[i] = strconv.Itoa(x)
	}
	return "[" + strings.Join(parts, ", ") + "]"
}
