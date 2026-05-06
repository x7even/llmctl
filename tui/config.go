package main

import (
	"fmt"
	"os"
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
