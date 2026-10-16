package main

import (
	"encoding/json"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// GPU stats, amd-smi first with a rocm-smi fallback. Port of scripts/gpustat.py (same contract, same
// fixtures in tests/fixtures/): rocm-smi is deprecated and not installed with ROCm 10, amd-smi replaces it.
//
// amd-smi reports VRAM as {"value": N, "unit": "MB"} where MB is really MiB (32624 == 34,208,743,424 B, the
// figure rocm-smi prints in bytes), so the conversion to bytes happens once, here.

const mib = 1 << 20

var (
	amdSMIArgv  = []string{"amd-smi", "metric", "--mem-usage", "--usage", "--temperature", "--json"}
	rocmSMIArgv = []string{"rocm-smi", "--showmeminfo", "vram", "--showuse", "--showtemp"}
)

// readGPUs returns the per-GPU stats and the tool that answered ("amd-smi", "rocm-smi", or "none" with an
// empty slice). run executes argv and returns stdout (see runCmd); tests inject a fake.
func readGPUs(run func([]string) (string, error)) ([]GPUInfo, string) {
	if out, err := run(amdSMIArgv); err == nil {
		if gpus := parseAmdSMI(out); len(gpus) > 0 {
			return gpus, "amd-smi"
		}
	}
	if out, err := run(rocmSMIArgv); err == nil {
		if gpus := parseROCMText(out); len(gpus) > 0 {
			return gpus, "rocm-smi"
		}
	}
	return nil, "none"
}

// amdNum reads amd-smi's {"value": N, "unit": "..."} wrapper (or a bare number). "N/A" and anything else
// is reported as missing.
func amdNum(v any) (float64, bool) {
	if m, ok := v.(map[string]any); ok {
		v = m["value"]
	}
	f, ok := v.(float64)
	return f, ok
}

func amdSection(row map[string]any, key string) map[string]any {
	m, _ := row[key].(map[string]any) // "N/A" in place of a whole section -> nil map, reads are safe
	return m
}

// parseAmdSMI parses `amd-smi metric --mem-usage --usage --temperature --json`. GPUs without a VRAM total
// are dropped; a missing utilisation or temperature reads as 0.
func parseAmdSMI(text string) []GPUInfo {
	var rows []map[string]any
	var doc struct {
		GPUData []map[string]any `json:"gpu_data"`
	}
	if err := json.Unmarshal([]byte(text), &doc); err == nil {
		rows = doc.GPUData
	} else if err := json.Unmarshal([]byte(text), &rows); err != nil {
		return nil
	}
	var gpus []GPUInfo
	for _, row := range rows {
		mem := amdSection(row, "mem_usage")
		total, ok := amdNum(mem["total_vram"])
		if !ok {
			continue
		}
		used, _ := amdNum(mem["used_vram"])
		g := GPUInfo{Index: len(gpus), VRAMTotal: int64(total) * mib, VRAMUsed: int64(used) * mib}
		if idx, ok := amdNum(row["gpu"]); ok {
			g.Index = int(idx)
		}
		g.UsePercent, _ = amdNum(amdSection(row, "usage")["gfx_activity"])
		temp := amdSection(row, "temperature")
		if t, ok := amdNum(temp["hotspot"]); ok {
			g.Temp = t
		} else {
			g.Temp, _ = amdNum(temp["edge"])
		}
		gpus = append(gpus, g)
	}
	sort.Slice(gpus, func(i, j int) bool { return gpus[i].Index < gpus[j].Index })
	return gpus
}

var (
	numRe      = regexp.MustCompile(`[\d.]+`)
	rocmLineRe = regexp.MustCompile(`GPU\[(\d+)\]\s*:\s*(.+)`)
)

// parseROCMText parses `rocm-smi --showmeminfo vram --showuse --showtemp` text output.
func parseROCMText(text string) []GPUInfo {
	gpuMap := map[int]*GPUInfo{}
	for _, line := range strings.Split(text, "\n") {
		m := rocmLineRe.FindStringSubmatch(line)
		if m == nil {
			continue
		}
		idx, _ := strconv.Atoi(m[1])
		if gpuMap[idx] == nil {
			gpuMap[idx] = &GPUInfo{Index: idx}
		}
		g := gpuMap[idx]
		c := strings.TrimSpace(m[2])
		switch {
		case strings.Contains(c, "VRAM Total Memory (B):"):
			g.VRAMTotal, _ = strconv.ParseInt(numRe.FindString(c), 10, 64)
		case strings.Contains(c, "VRAM Total Used Memory (B):"):
			g.VRAMUsed, _ = strconv.ParseInt(numRe.FindString(c), 10, 64)
		case strings.Contains(c, "GPU use (%):"):
			g.UsePercent, _ = strconv.ParseFloat(numRe.FindString(c), 64)
		case strings.Contains(c, "Temperature (Sensor junction) (C):"):
			g.Temp, _ = strconv.ParseFloat(numRe.FindString(c), 64)
		}
	}
	gpus := make([]GPUInfo, 0, len(gpuMap))
	for _, g := range gpuMap {
		gpus = append(gpus, *g)
	}
	sort.Slice(gpus, func(i, j int) bool { return gpus[i].Index < gpus[j].Index })
	return gpus
}
