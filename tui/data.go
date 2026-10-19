package main

import (
	"encoding/json"
	"fmt"
	"net/http"
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
	Running        float64
	Waiting        float64
	KVCache        *float64 // nil = unavailable
	PrefixHitRate  *float64 // nil = unavailable; 0–1 fraction
	TokPerS        *float64
	GenTotal       *float64
	PromptTotal    *float64 // vllm:prompt_tokens_total counter
	TTFT           *float64 // avg time-to-first-token (sum/count); nil = no data
	AvgPrefillTime *float64 // avg GPU prefill phase duration per request; nil = no data
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
	GPUAvail  bool
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
	pfs := parseMetric(txt, "vllm:request_prefill_time_seconds_sum")
	pfc := parseMetric(txt, "vllm:request_prefill_time_seconds_count")
	var avgPrefill *float64
	if pfs != nil && pfc != nil && *pfc > 0 {
		v := *pfs / *pfc
		avgPrefill = &v
	}
	return &VLLMMetrics{
		Running:       derefF(parseMetric(txt, "vllm:num_requests_running")),
		Waiting:       derefF(parseMetric(txt, "vllm:num_requests_waiting")),
		KVCache:       kv,
		PrefixHitRate: parseMetric(txt, "vllm:gpu_prefix_cache_hit_rate"),
		TokPerS:       parseMetric(txt, "vllm:avg_generation_throughput_toks_per_s"),
		GenTotal:      parseMetric(txt, "vllm:generation_tokens_total"),
		PromptTotal: firstNonNil(
			parseMetric(txt, "vllm:prompt_tokens_total"),
			parseMetric(txt, "vllm:prompt_tokens"),
		),
		TTFT:           ttft,
		AvgPrefillTime: avgPrefill,
	}
}

func derefF(p *float64) float64 {
	if p == nil {
		return 0
	}
	return *p
}

func firstNonNil(ptrs ...*float64) *float64 {
	for _, p := range ptrs {
		if p != nil {
			return p
		}
	}
	return nil
}

// ── GPU stats (amd-smi, rocm-smi fallback; see gpustat.go) ───────────────────────

func fetchGPUs() ([]GPUInfo, bool) {
	gpus, tool := readGPUs(runCmd)
	return gpus, tool != "none"
}

// ── Composite fetch ───────────────────────────────────────────────────────────

func fetchAll(baseURL string) AppData {
	type gpuResult struct {
		gpus  []GPUInfo
		avail bool
	}
	ch := make(chan gpuResult, 1)
	go func() {
		g, a := fetchGPUs()
		ch <- gpuResult{g, a}
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
		GPUAvail:  rr.avail,
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
	client := &http.Client{Timeout: 2100 * time.Second} // matches llmctl swap timeout; safety ceiling only — v0.26.0 first-boot typically ~2-3 min
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
