package main

import (
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
	flag.Parse()

	if *showVersion {
		fmt.Println(version)
		return
	}

	a := newApp(*baseURL, *interval, *configPath, *logPath)
	p := tea.NewProgram(a, tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func defaultConfig() string {
	home, _ := os.UserHomeDir()
	candidates := []string{
		filepath.Join(home, "ai/llmstack/config/models.yaml"),
		"/home/xin/ai/llmstack/config/models.yaml",
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
