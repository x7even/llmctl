package main

import (
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

// ── Types ──────────────────────────────────────────────────────────────────────

// ModelConfig mirrors a models.yaml profile entry.
// All fields are exported so yaml.v3 can decode them and future
// editor code can re-marshal them back to YAML.
type ModelConfig struct {
	Name             string   `yaml:"name"`
	TTL              int      `yaml:"ttl"`
	CheckEndpoint    string   `yaml:"checkEndpoint"`
	ConcurrencyLimit int      `yaml:"concurrencyLimit"`
	Unlisted         bool     `yaml:"unlisted"`
	Aliases          []string `yaml:"aliases"`
	Cmd              string   `yaml:"cmd"`
	CmdStop          string   `yaml:"cmdStop"`

	// Metadata carries the per-profile hardware requirements (metadata.requires).
	// nil = profile declares nothing = unknown = permissive. See Requirements().
	Metadata *ModelMetadata `yaml:"metadata"`
}

// ModelMetadata is the profile's `metadata:` map. Only `requires` is read;
// llama-swap exposes the whole map in /v1/models, other keys are ignored here.
type ModelMetadata struct {
	Requires *Requires `yaml:"requires"`
}

// Requires is a profile's metadata.requires block (schema: config/CLAUDE.md,
// reader of record: scripts/llmhw.py). Zero values mean "not declared":
// GPUs nil, MinGPUs 0 and HostRAMGiB 0 add no constraint.
type Requires struct {
	GPUs         []int   `yaml:"gpus"          json:"gpus"`            // allowed GPU counts (vLLM TP sizes)
	MinGPUs      int     `yaml:"min_gpus"      json:"min_gpus"`        // llama-server: any count >= N
	HostRAMGiB   float64 `yaml:"host_ram_gib"  json:"host_ram_gib"`    // system RAM needed
	VRAMTotalGiB float64 `yaml:"vram_total_gib" json:"vram_total_gib"` // informational, never gates
	Estimate     bool    `yaml:"estimate"      json:"estimate"`        // numbers not measured on this rig
	Note         string  `yaml:"note"          json:"note"`
}

// Requirements returns the profile's metadata.requires, or nil when absent.
func (m ModelConfig) Requirements() *Requires {
	if m.Metadata == nil {
		return nil
	}
	return m.Metadata.Requires
}

// UnmarshalYAML decodes `metadata:` leniently: a malformed metadata value
// (e.g. a scalar) means "no requirements" instead of failing the whole config.
func (m *ModelMetadata) UnmarshalYAML(n *yaml.Node) error {
	if n.Kind != yaml.MappingNode {
		return nil
	}
	for i := 0; i+1 < len(n.Content); i += 2 {
		if n.Content[i].Value != "requires" {
			continue
		}
		var r Requires
		if err := n.Content[i+1].Decode(&r); err == nil && n.Content[i+1].Kind == yaml.MappingNode {
			m.Requires = &r
		}
	}
	return nil
}

// UnmarshalYAML decodes each requires key independently so one mistyped
// value (`gpus: 4`, `host_ram_gib: lots`) only drops that constraint; the
// registry still loads and the other keys still apply. The Python reader
// ignores mistyped values the same way.
func (r *Requires) UnmarshalYAML(n *yaml.Node) error {
	if n.Kind != yaml.MappingNode {
		return nil
	}
	for i := 0; i+1 < len(n.Content); i += 2 {
		key, val := n.Content[i].Value, n.Content[i+1]
		switch key {
		case "gpus":
			if val.Kind != yaml.SequenceNode {
				continue
			}
			list := []int{}
			for _, item := range val.Content {
				var g int
				// Only real integers: yaml.v3 would truncate 2.0 to 2, llmhw.py ignores it.
				if item.Tag == "!!int" && item.Decode(&g) == nil {
					list = append(list, g)
				}
			}
			r.GPUs = list
		case "min_gpus":
			if val.Tag == "!!int" {
				_ = val.Decode(&r.MinGPUs)
			}
		case "host_ram_gib":
			_ = val.Decode(&r.HostRAMGiB)
		case "vram_total_gib":
			_ = val.Decode(&r.VRAMTotalGiB)
		case "estimate":
			_ = val.Decode(&r.Estimate)
		case "note":
			_ = val.Decode(&r.Note)
		}
	}
	return nil
}

// Registry is the parsed models.yaml.
// Order preserves the YAML key order (map iteration is random).
type Registry struct {
	HealthCheckTimeout int                    `yaml:"healthCheckTimeout"`
	StartPort          int                    `yaml:"startPort"`
	GlobalTTL          int                    `yaml:"globalTTL"`
	Models             map[string]ModelConfig `yaml:"models"`
	Order              []string               // profile IDs in YAML order
	Path               string                 // source file path
}

// ── Loading ────────────────────────────────────────────────────────────────────

func loadRegistry(path string) (*Registry, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}

	// Use yaml.Node to decode — preserves key order for Order extraction.
	var doc yaml.Node
	if err := yaml.Unmarshal(data, &doc); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	if len(doc.Content) == 0 {
		return nil, fmt.Errorf("empty document: %s", path)
	}

	var reg Registry
	if err := doc.Content[0].Decode(&reg); err != nil {
		return nil, fmt.Errorf("decode %s: %w", path, err)
	}
	reg.Path = path
	reg.Order = extractOrder(doc.Content[0], "models")
	return &reg, nil
}

// extractOrder walks a YAML mapping node and returns the keys of a
// named child mapping in document order.
func extractOrder(mapping *yaml.Node, key string) []string {
	if mapping.Kind != yaml.MappingNode {
		return nil
	}
	for i := 0; i+1 < len(mapping.Content); i += 2 {
		if mapping.Content[i].Value == key {
			child := mapping.Content[i+1]
			if child.Kind != yaml.MappingNode {
				return nil
			}
			keys := make([]string, 0, len(child.Content)/2)
			for j := 0; j+1 < len(child.Content); j += 2 {
				keys = append(keys, child.Content[j].Value)
			}
			return keys
		}
	}
	return nil
}

// ── Capabilities ──────────────────────────────────────────────────────────────

// ModelCapabilities summarises the runtime features derived from cmd flags.
type ModelCapabilities struct {
	MTP             bool
	MTPTokens       int    // num_speculative_tokens; 0 if MTP off
	Reasoning       bool   // --reasoning-parser present
	ThinkingDefault string // "on" or "off"; "" when reasoning not supported
	ContextLen      int    // --max-model-len value; 0 = model native (no override)
}

var (
	reMTPTokens  = regexp.MustCompile(`"num_speculative_tokens"\s*:\s*(\d+)`)
	reContextLen = regexp.MustCompile(`--max-model-len\s+(\d+)`)
)

// ParseCapabilities extracts MTP, reasoning and context flags from a profile's Cmd.
func ParseCapabilities(cfg ModelConfig) ModelCapabilities {
	cmd := cfg.Cmd
	var c ModelCapabilities

	if strings.Contains(cmd, `"method": "mtp"`) || strings.Contains(cmd, `"method":"mtp"`) {
		c.MTP = true
		if m := reMTPTokens.FindStringSubmatch(cmd); m != nil {
			c.MTPTokens, _ = strconv.Atoi(m[1])
		}
	}

	c.Reasoning = strings.Contains(cmd, "--reasoning-parser")
	if c.Reasoning {
		if strings.Contains(cmd, "no-think") || strings.Contains(cmd, "no_think") {
			c.ThinkingDefault = "off"
		} else {
			c.ThinkingDefault = "on"
		}
	}

	if m := reContextLen.FindStringSubmatch(cmd); m != nil {
		c.ContextLen, _ = strconv.Atoi(m[1])
	}

	return c
}

// ── Config display ─────────────────────────────────────────────────────────────

// ProfileYAML returns a human-readable YAML block for a single model,
// suitable for the config panel viewer.
func (r *Registry) ProfileYAML(id string) string {
	cfg, ok := r.Models[id]
	if !ok {
		return fmt.Sprintf("# profile %q not found in registry\n", id)
	}

	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("# %s\n", id))
	if cfg.Name != "" {
		sb.WriteString(fmt.Sprintf("name: %s\n", cfg.Name))
	}
	sb.WriteString(fmt.Sprintf("ttl: %d\n", cfg.TTL))
	if cfg.ConcurrencyLimit > 0 {
		sb.WriteString(fmt.Sprintf("concurrencyLimit: %d\n", cfg.ConcurrencyLimit))
	}
	if cfg.CheckEndpoint != "" {
		sb.WriteString(fmt.Sprintf("checkEndpoint: %s\n", cfg.CheckEndpoint))
	}
	if len(cfg.Aliases) > 0 {
		sb.WriteString("aliases:\n")
		for _, a := range cfg.Aliases {
			sb.WriteString(fmt.Sprintf("  - %s\n", a))
		}
	}
	if cfg.Cmd != "" {
		sb.WriteString("cmd: |\n")
		for _, line := range strings.Split(strings.TrimSpace(cfg.Cmd), "\n") {
			sb.WriteString("  " + strings.TrimSpace(line) + "\n")
		}
	}
	if cfg.CmdStop != "" {
		sb.WriteString(fmt.Sprintf("cmdStop: %s\n", cfg.CmdStop))
	}
	return sb.String()
}
