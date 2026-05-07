package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// ── Types ──────────────────────────────────────────────────────────────────────

type ActiveModel struct {
	ID   string
	Port int
}

type VLLMMetrics struct {
	Running       float64
	Waiting       float64
	KVCache       *float64 // nil = unavailable
	PrefixHitRate *float64 // nil = unavailable; 0–1 fraction
	TokPerS       *float64
	GenTotal      *float64
	TTFT          *float64 // nil = no data yet
}

type GPUInfo struct {
	Index      int
	VRAMUsed   int64
	VRAMTotal  int64
	UsePercent float64
	Temp       float64
}

type AppData struct {
	Active    *ActiveModel // nil = nothing loaded
	Profiles  []string
	Metrics   *VLLMMetrics // nil = metrics endpoint not available
	GPUs      []GPUInfo
	ROCMAvail bool
	FetchedAt time.Time
}

// ── HTTP ───────────────────────────────────────────────────────────────────────

var httpClient = &http.Client{Timeout: 2 * time.Second}

func getJSON(url string, v any) error {
	resp, err := httpClient.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return json.NewDecoder(resp.Body).Decode(v)
}

// ── llama-swap ────────────────────────────────────────────────────────────────

func fetchRunning(baseURL string) *ActiveModel {
	var result struct {
		Running []struct {
			ID    string `json:"id"`    // older llama-swap versions
			Model string `json:"model"` // newer llama-swap versions
			Port  int    `json:"port"`
			Proxy string `json:"proxy"`
		} `json:"running"`
	}
	if err := getJSON(baseURL+"/running", &result); err != nil || len(result.Running) == 0 {
		return nil
	}
	r := result.Running[0]
	id := r.ID
	if id == "" {
		id = r.Model
	}
	port := r.Port
	if port == 0 && r.Proxy != "" {
		parts := strings.Split(strings.TrimRight(r.Proxy, "/"), ":")
		if len(parts) > 0 {
			port, _ = strconv.Atoi(parts[len(parts)-1])
		}
	}
	return &ActiveModel{ID: id, Port: port}
}

func fetchProfiles(baseURL string) []string {
	var result struct {
		Data []struct {
			ID string `json:"id"`
		} `json:"data"`
	}
	if err := getJSON(baseURL+"/v1/models", &result); err != nil {
		return nil
	}
	out := make([]string, len(result.Data))
	for i, d := range result.Data {
		out[i] = d.ID
	}
	return out
}

// ── vLLM metrics ──────────────────────────────────────────────────────────────

func parseMetric(text, name string) *float64 {
	re := regexp.MustCompile(`(?m)^` + regexp.QuoteMeta(name) + `\{[^}]*\}\s+([\d.eE+\-]+)`)
	m := re.FindStringSubmatch(text)
	if m == nil {
		return nil
	}
	f, err := strconv.ParseFloat(m[1], 64)
	if err != nil {
		return nil
	}
	return &f
}

func fetchVLLM(port int) *VLLMMetrics {
	if port == 0 {
		return nil
	}
	client := &http.Client{Timeout: time.Second}
	resp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/metrics", port))
	if err != nil {
		return nil
	}
	defer resp.Body.Close()

	var sb strings.Builder
	buf := make([]byte, 32*1024)
	for {
		n, err := resp.Body.Read(buf)
		sb.Write(buf[:n])
		if err != nil {
			break
		}
	}
	txt := sb.String()

	kv := parseMetric(txt, "vllm:kv_cache_usage_perc")
	if kv == nil {
		kv = parseMetric(txt, "vllm:gpu_cache_usage_perc")
	}
	s := parseMetric(txt, "vllm:time_to_first_token_seconds_sum")
	c := parseMetric(txt, "vllm:time_to_first_token_seconds_count")
	var ttft *float64
	if s != nil && c != nil && *c > 0 {
		v := *s / *c
		ttft = &v
	}
	return &VLLMMetrics{
		Running:       derefF(parseMetric(txt, "vllm:num_requests_running")),
		Waiting:       derefF(parseMetric(txt, "vllm:num_requests_waiting")),
		KVCache:       kv,
		PrefixHitRate: parseMetric(txt, "vllm:gpu_prefix_cache_hit_rate"),
		TokPerS:       parseMetric(txt, "vllm:avg_generation_throughput_toks_per_s"),
		GenTotal:      parseMetric(txt, "vllm:generation_tokens_total"),
		TTFT:          ttft,
	}
}

func derefF(p *float64) float64 {
	if p == nil {
		return 0
	}
	return *p
}

// ── rocm-smi ──────────────────────────────────────────────────────────────────

var numRe = regexp.MustCompile(`[\d.]+`)

func fetchROCM() ([]GPUInfo, bool) {
	out, err := exec.Command("rocm-smi",
		"--showmeminfo", "vram", "--showuse", "--showtemp").Output()
	if err != nil {
		return nil, false
	}
	return parseROCMText(string(out)), true
}

var rocmLineRe = regexp.MustCompile(`GPU\[(\d+)\]\s*:\s*(.+)`)

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
	for i := range gpuMap {
		gpus = append(gpus, *gpuMap[i])
	}
	for i := 1; i < len(gpus); i++ {
		for j := i; j > 0 && gpus[j].Index < gpus[j-1].Index; j-- {
			gpus[j], gpus[j-1] = gpus[j-1], gpus[j]
		}
	}
	return gpus
}

// ── Composite fetch ───────────────────────────────────────────────────────────

func fetchAll(baseURL string) AppData {
	type rocmResult struct {
		gpus  []GPUInfo
		avail bool
	}
	ch := make(chan rocmResult, 1)
	go func() {
		g, a := fetchROCM()
		ch <- rocmResult{g, a}
	}()

	active := fetchRunning(baseURL)
	profiles := fetchProfiles(baseURL)

	var metrics *VLLMMetrics
	if active != nil && active.Port > 0 {
		metrics = fetchVLLM(active.Port)
	}

	rr := <-ch
	return AppData{
		Active:    active,
		Profiles:  profiles,
		Metrics:   metrics,
		GPUs:      rr.gpus,
		ROCMAvail: rr.avail,
		FetchedAt: time.Now(),
	}
}

// ── Swap / Unload ─────────────────────────────────────────────────────────────

func unloadAll(baseURL string) error {
	resp, err := httpClient.Get(baseURL + "/unload")
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return nil
}

func swapModel(baseURL, profile string) error {
	client := &http.Client{Timeout: 300 * time.Second}
	body := strings.NewReader(fmt.Sprintf(
		`{"model":%q,"messages":[{"role":"user","content":"hi"}],"max_tokens":1}`,
		profile,
	))
	resp, err := client.Post(baseURL+"/v1/chat/completions", "application/json", body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return nil
}
