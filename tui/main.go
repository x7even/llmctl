package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

// set by -ldflags "-X main.version=v1.2.3" at build time
var version = "dev"

func main() {
	baseURL := flag.String("url", "http://127.0.0.1:8080", "llama-swap base URL")
	interval := flag.Duration("interval", time.Second, "poll interval (500ms, 1s, 2s, 5s, 15s)")
	configPath := flag.String("config", defaultConfig(), "path to models.yaml")
	logPath := flag.String("log", defaultLog(), "path to llama-swap log")
	showVersion := flag.Bool("version", false, "print version and exit")
	status := flag.Bool("status", false, "print stack status as JSON and exit")
	flag.Parse()

	if *showVersion {
		fmt.Println(version)
		return
	}

	if *status {
		runStatus(*baseURL, *configPath)
		return
	}

	a := newApp(*baseURL, *interval, *configPath, *logPath)
	p := tea.NewProgram(a, tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

// StatusResult is the JSON shape emitted by --status.
type StatusResult struct {
	Model            string `json:"model"`                      // profile ID; empty = nothing loaded
	State            string `json:"state"`                      // "idle" | "starting" | "ready"
	Name             string `json:"name,omitempty"`             // human-readable name from models.yaml
	Port             int    `json:"port,omitempty"`             // backend port
	MTP              bool   `json:"mtp"`                        // speculative MTP enabled
	MTPTokens        int    `json:"mtp_tokens,omitempty"`       // num_speculative_tokens
	Reasoning        bool   `json:"reasoning"`                  // --reasoning-parser present
	ThinkingDefault  string `json:"thinking_default,omitempty"` // "on" | "off"
	ContextLen       int    `json:"context_len,omitempty"`      // --max-model-len; 0 = model native
	ConcurrencyLimit int    `json:"concurrency_limit,omitempty"`
}

func runStatus(baseURL, configPath string) {
	data := fetchAll(baseURL)

	var result StatusResult
	if data.Active == nil {
		result.State = "idle"
	} else {
		result.Model = data.Active.ID
		result.Port = data.Active.Port
		if data.Metrics != nil {
			result.State = "ready"
		} else {
			result.State = "starting"
		}
		if reg, err := loadRegistry(configPath); err == nil {
			if cfg, ok := reg.Models[data.Active.ID]; ok {
				result.Name = cfg.Name
				result.ConcurrencyLimit = cfg.ConcurrencyLimit
				caps := ParseCapabilities(cfg)
				result.MTP = caps.MTP
				result.MTPTokens = caps.MTPTokens
				result.Reasoning = caps.Reasoning
				result.ThinkingDefault = caps.ThinkingDefault
				result.ContextLen = caps.ContextLen
			}
		}
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	enc.Encode(result) //nolint:errcheck
}

func defaultConfig() string {
	home, _ := os.UserHomeDir()
	candidates := []string{
		filepath.Join(home, "ai/llmstack/config/models.yaml"),
		"/opt/llmstack/config/models.yaml",
	}
	for _, c := range candidates {
		if _, err := os.Stat(c); err == nil {
			return c
		}
	}
	return candidates[0]
}

func defaultLog() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".local/share/llmstack/llama-swap.log")
}
