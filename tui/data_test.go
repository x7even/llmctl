package main

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

// ── parseMetric ────────────────────────────────────────────────────────────────

const sampleMetrics = `
# HELP vllm:num_requests_running Number of requests currently running.
vllm:num_requests_running{model_name="qwen3.6-35b-code",version="0.20.0"} 4.0
vllm:num_requests_waiting{model_name="qwen3.6-35b-code",version="0.20.0"} 2.0
vllm:kv_cache_usage_perc{model_name="qwen3.6-35b-code"} 0.1234
vllm:gpu_prefix_cache_hit_rate{model_name="qwen3.6-35b-code"} 0.873
vllm:avg_generation_throughput_toks_per_s{model_name="qwen3.6-35b-code"} 387.5
vllm:time_to_first_token_seconds_sum{model_name="qwen3.6-35b-code"} 8.4
vllm:time_to_first_token_seconds_count{model_name="qwen3.6-35b-code"} 10.0
vllm:generation_tokens_total{model_name="qwen3.6-35b-code"} 123456.0
`

func pf(f float64) *float64 { return &f }

func TestParseMetric_present(t *testing.T) {
	cases := []struct {
		metric string
		want   float64
	}{
		{"vllm:num_requests_running", 4.0},
		{"vllm:num_requests_waiting", 2.0},
		{"vllm:kv_cache_usage_perc", 0.1234},
		{"vllm:gpu_prefix_cache_hit_rate", 0.873},
		{"vllm:avg_generation_throughput_toks_per_s", 387.5},
		{"vllm:time_to_first_token_seconds_sum", 8.4},
		{"vllm:time_to_first_token_seconds_count", 10.0},
		{"vllm:generation_tokens_total", 123456.0},
	}
	for _, tc := range cases {
		t.Run(tc.metric, func(t *testing.T) {
			got := parseMetric(sampleMetrics, tc.metric)
			if got == nil {
				t.Fatalf("want %v, got nil", tc.want)
			}
			if *got != tc.want {
				t.Errorf("want %v, got %v", tc.want, *got)
			}
		})
	}
}

func TestParseMetric_absent(t *testing.T) {
	got := parseMetric(sampleMetrics, "vllm:nonexistent_metric")
	if got != nil {
		t.Errorf("want nil for missing metric, got %v", *got)
	}
}

func TestParseMetric_prefixNotMatch(t *testing.T) {
	// "vllm:num_requests" must not match "vllm:num_requests_running"
	got := parseMetric(sampleMetrics, "vllm:num_requests")
	if got != nil {
		t.Errorf("want nil for prefix-only match, got %v", *got)
	}
}

func TestParseMetric_emptyText(t *testing.T) {
	got := parseMetric("", "vllm:num_requests_running")
	if got != nil {
		t.Errorf("want nil for empty text, got %v", *got)
	}
}

// ── parseROCMText ──────────────────────────────────────────────────────────────

const rocmOutput = `
GPU[0]  : VRAM Total Memory (B): 34208743424
GPU[0]  : VRAM Total Used Memory (B): 12345678901
GPU[0]  : GPU use (%): 87
GPU[0]  : Temperature (Sensor junction) (C): 72.0
GPU[1]  : VRAM Total Memory (B): 34208743424
GPU[1]  : VRAM Total Used Memory (B): 11000000000
GPU[1]  : GPU use (%): 65
GPU[1]  : Temperature (Sensor junction) (C): 68.5
GPU[2]  : VRAM Total Memory (B): 34208743424
GPU[2]  : VRAM Total Used Memory (B): 10000000000
GPU[2]  : GPU use (%): 50
GPU[2]  : Temperature (Sensor junction) (C): 71.0
GPU[3]  : VRAM Total Memory (B): 34208743424
GPU[3]  : VRAM Total Used Memory (B): 9000000000
GPU[3]  : GPU use (%): 45
GPU[3]  : Temperature (Sensor junction) (C): 66.0
`

func TestParseROCMText_fourGPUs(t *testing.T) {
	gpus := parseROCMText(rocmOutput)
	if len(gpus) != 4 {
		t.Fatalf("want 4 GPUs, got %d", len(gpus))
	}
}

func TestParseROCMText_orderedByIndex(t *testing.T) {
	gpus := parseROCMText(rocmOutput)
	for i, g := range gpus {
		if g.Index != i {
			t.Errorf("gpus[%d].Index = %d, want %d", i, g.Index, i)
		}
	}
}

func TestParseROCMText_values(t *testing.T) {
	gpus := parseROCMText(rocmOutput)
	g := gpus[0]
	if g.VRAMTotal != 34208743424 {
		t.Errorf("VRAMTotal: want 34208743424, got %d", g.VRAMTotal)
	}
	if g.VRAMUsed != 12345678901 {
		t.Errorf("VRAMUsed: want 12345678901, got %d", g.VRAMUsed)
	}
	if g.UsePercent != 87 {
		t.Errorf("UsePercent: want 87, got %f", g.UsePercent)
	}
	if g.Temp != 72.0 {
		t.Errorf("Temp: want 72.0, got %f", g.Temp)
	}
}

func TestParseROCMText_empty(t *testing.T) {
	gpus := parseROCMText("")
	if len(gpus) != 0 {
		t.Errorf("want empty slice for empty input, got %v", gpus)
	}
}

func TestParseROCMText_noGPULines(t *testing.T) {
	gpus := parseROCMText("System GPU information\nTotal GPUs: 0\n")
	if len(gpus) != 0 {
		t.Errorf("want empty slice, got %d GPUs", len(gpus))
	}
}

// ── fetchRunning ──────────────────────────────────────────────────────────────

func TestFetchRunning_loaded(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `{"running":[{"id":"qwen3.6-35b-code","port":9104}]}`)
	}))
	defer srv.Close()

	active := fetchRunning(srv.URL)
	if active == nil {
		t.Fatal("want active model, got nil")
	}
	if active.ID != "qwen3.6-35b-code" {
		t.Errorf("ID: want qwen3.6-35b-code, got %s", active.ID)
	}
	if active.Port != 9104 {
		t.Errorf("Port: want 9104, got %d", active.Port)
	}
}

func TestFetchRunning_empty(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, `{"running":[]}`)
	}))
	defer srv.Close()

	if got := fetchRunning(srv.URL); got != nil {
		t.Errorf("want nil for empty running list, got %+v", got)
	}
}

func TestFetchRunning_portFromProxy(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, `{"running":[{"id":"qwen3.6-35b-code","port":0,"proxy":"http://127.0.0.1:9104/"}]}`)
	}))
	defer srv.Close()

	active := fetchRunning(srv.URL)
	if active == nil {
		t.Fatal("want active, got nil")
	}
	if active.Port != 9104 {
		t.Errorf("Port from proxy: want 9104, got %d", active.Port)
	}
}

func TestFetchRunning_modelFieldFallback(t *testing.T) {
	// newer llama-swap versions return "model" instead of "id"
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, `{"running":[{"model":"qwen3.6-35b-code","proxy":"http://127.0.0.1:9104"}]}`)
	}))
	defer srv.Close()

	active := fetchRunning(srv.URL)
	if active == nil {
		t.Fatal("want active, got nil")
	}
	if active.ID != "qwen3.6-35b-code" {
		t.Errorf("ID from model field: want qwen3.6-35b-code, got %q", active.ID)
	}
	if active.Port != 9104 {
		t.Errorf("Port: want 9104, got %d", active.Port)
	}
}

func TestFetchRunning_unreachable(t *testing.T) {
	// port 1 is never listening
	if got := fetchRunning("http://127.0.0.1:1"); got != nil {
		t.Errorf("want nil for unreachable server, got %+v", got)
	}
}

// ── fetchProfiles ─────────────────────────────────────────────────────────────

func TestFetchProfiles(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, `{"data":[{"id":"model-a"},{"id":"model-b"},{"id":"model-c"}]}`)
	}))
	defer srv.Close()

	profiles := fetchProfiles(srv.URL)
	if len(profiles) != 3 {
		t.Fatalf("want 3 profiles, got %d", len(profiles))
	}
	if profiles[0] != "model-a" || profiles[1] != "model-b" || profiles[2] != "model-c" {
		t.Errorf("profiles: got %v", profiles)
	}
}

func TestFetchProfiles_empty(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, `{"data":[]}`)
	}))
	defer srv.Close()

	profiles := fetchProfiles(srv.URL)
	if len(profiles) != 0 {
		t.Errorf("want empty, got %v", profiles)
	}
}

// ── fetchVLLM ─────────────────────────────────────────────────────────────────

func TestFetchVLLM_metrics(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, sampleMetrics)
	}))
	defer srv.Close()

	// extract port from srv.URL
	var port int
	fmt.Sscanf(srv.URL, "http://127.0.0.1:%d", &port)

	m := fetchVLLM(port)
	if m == nil {
		t.Fatal("want metrics, got nil")
	}
	if m.Running != 4.0 {
		t.Errorf("Running: want 4, got %f", m.Running)
	}
	if m.Waiting != 2.0 {
		t.Errorf("Waiting: want 2, got %f", m.Waiting)
	}
	if m.KVCache == nil || *m.KVCache != 0.1234 {
		t.Errorf("KVCache: want 0.1234, got %v", m.KVCache)
	}
	if m.PrefixHitRate == nil || *m.PrefixHitRate != 0.873 {
		t.Errorf("PrefixHitRate: want 0.873, got %v", m.PrefixHitRate)
	}
	if m.TTFT == nil {
		t.Fatal("want TTFT, got nil")
	}
	wantTTFT := 8.4 / 10.0
	if diff := *m.TTFT - wantTTFT; diff < -1e-9 || diff > 1e-9 {
		t.Errorf("TTFT: want %f, got %f", wantTTFT, *m.TTFT)
	}
}

func TestFetchVLLM_ttftZeroCount(t *testing.T) {
	body := `
vllm:num_requests_running{model_name="m"} 0.0
vllm:time_to_first_token_seconds_sum{model_name="m"} 0.0
vllm:time_to_first_token_seconds_count{model_name="m"} 0.0
`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprint(w, body)
	}))
	defer srv.Close()

	var port int
	fmt.Sscanf(srv.URL, "http://127.0.0.1:%d", &port)

	m := fetchVLLM(port)
	if m == nil {
		t.Fatal("want metrics, got nil")
	}
	if m.TTFT != nil {
		t.Errorf("TTFT: want nil when count=0, got %v", *m.TTFT)
	}
}

func TestFetchVLLM_zeroPort(t *testing.T) {
	if m := fetchVLLM(0); m != nil {
		t.Errorf("want nil for port 0, got %+v", m)
	}
}

// ── unloadAll ─────────────────────────────────────────────────────────────────

func TestUnloadAll_ok(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/unload" {
			http.NotFound(w, r)
			return
		}
		fmt.Fprint(w, "OK")
	}))
	defer srv.Close()

	if err := unloadAll(srv.URL); err != nil {
		t.Errorf("want nil error, got %v", err)
	}
}

func TestUnloadAll_serverError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "internal error", http.StatusInternalServerError)
	}))
	defer srv.Close()

	if err := unloadAll(srv.URL); err == nil {
		t.Error("want error for 500 response, got nil")
	}
}
