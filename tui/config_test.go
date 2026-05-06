package main

import (
	"os"
	"strings"
	"testing"
)

const registryYAML = `
healthCheckTimeout: 600
startPort: 9100
globalTTL: 0

models:
  alpha:
    name: "Alpha Model"
    ttl: 600
    concurrencyLimit: 64
    aliases:
      - alpha-alias
      - a
    cmd: |
      podman run alpha --port ${PORT}
    cmdStop: podman stop alpha

  beta:
    name: "Beta Model"
    ttl: 300
    concurrencyLimit: 8
    aliases:
      - b
    cmd: |
      podman run beta --port ${PORT}
    cmdStop: podman stop beta

  gamma:
    name: "Gamma Model"
    ttl: 0
    cmd: |
      podman run gamma --port ${PORT}
    cmdStop: podman stop gamma
`

func writeTempYAML(t *testing.T, content string) string {
	t.Helper()
	f, err := os.CreateTemp("", "models-*.yaml")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Remove(f.Name()) })
	if _, err := f.WriteString(content); err != nil {
		t.Fatal(err)
	}
	f.Close()
	return f.Name()
}

// ── loadRegistry ──────────────────────────────────────────────────────────────

func TestLoadRegistry_basic(t *testing.T) {
	reg, err := loadRegistry(writeTempYAML(t, registryYAML))
	if err != nil {
		t.Fatalf("loadRegistry: %v", err)
	}
	if reg.HealthCheckTimeout != 600 {
		t.Errorf("HealthCheckTimeout: want 600, got %d", reg.HealthCheckTimeout)
	}
	if reg.StartPort != 9100 {
		t.Errorf("StartPort: want 9100, got %d", reg.StartPort)
	}
	if len(reg.Models) != 3 {
		t.Errorf("want 3 models, got %d", len(reg.Models))
	}
}

func TestLoadRegistry_modelFields(t *testing.T) {
	reg, _ := loadRegistry(writeTempYAML(t, registryYAML))

	alpha, ok := reg.Models["alpha"]
	if !ok {
		t.Fatal("model 'alpha' not found")
	}
	if alpha.Name != "Alpha Model" {
		t.Errorf("Name: want 'Alpha Model', got %q", alpha.Name)
	}
	if alpha.TTL != 600 {
		t.Errorf("TTL: want 600, got %d", alpha.TTL)
	}
	if alpha.ConcurrencyLimit != 64 {
		t.Errorf("ConcurrencyLimit: want 64, got %d", alpha.ConcurrencyLimit)
	}
	if len(alpha.Aliases) != 2 {
		t.Errorf("Aliases: want 2, got %d: %v", len(alpha.Aliases), alpha.Aliases)
	}
	if alpha.CmdStop != "podman stop alpha" {
		t.Errorf("CmdStop: got %q", alpha.CmdStop)
	}
}

func TestLoadRegistry_preservesOrder(t *testing.T) {
	reg, _ := loadRegistry(writeTempYAML(t, registryYAML))

	want := []string{"alpha", "beta", "gamma"}
	if len(reg.Order) != len(want) {
		t.Fatalf("Order length: want %d, got %d", len(want), len(reg.Order))
	}
	for i, id := range want {
		if reg.Order[i] != id {
			t.Errorf("Order[%d]: want %q, got %q", i, id, reg.Order[i])
		}
	}
}

func TestLoadRegistry_pathStored(t *testing.T) {
	path := writeTempYAML(t, registryYAML)
	reg, _ := loadRegistry(path)
	if reg.Path != path {
		t.Errorf("Path: want %q, got %q", path, reg.Path)
	}
}

func TestLoadRegistry_missingFile(t *testing.T) {
	_, err := loadRegistry("/nonexistent/definitely/missing.yaml")
	if err == nil {
		t.Error("want error for missing file, got nil")
	}
}

func TestLoadRegistry_invalidYAML(t *testing.T) {
	path := writeTempYAML(t, "models: {bad yaml [[[")
	_, err := loadRegistry(path)
	if err == nil {
		t.Error("want error for invalid YAML, got nil")
	}
}

func TestLoadRegistry_emptyModels(t *testing.T) {
	yaml := "healthCheckTimeout: 60\nstartPort: 9100\nmodels:\n"
	reg, err := loadRegistry(writeTempYAML(t, yaml))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(reg.Models) != 0 {
		t.Errorf("want 0 models, got %d", len(reg.Models))
	}
	if len(reg.Order) != 0 {
		t.Errorf("want empty Order, got %v", reg.Order)
	}
}

// ── ProfileYAML ───────────────────────────────────────────────────────────────

func TestProfileYAML_containsFields(t *testing.T) {
	reg, _ := loadRegistry(writeTempYAML(t, registryYAML))
	out := reg.ProfileYAML("alpha")

	checks := []string{"Alpha Model", "alpha-alias", "podman run alpha"}
	for _, s := range checks {
		if !strings.Contains(out, s) {
			t.Errorf("ProfileYAML: want %q in output, not found in:\n%s", s, out)
		}
	}
}

func TestProfileYAML_missing(t *testing.T) {
	reg, _ := loadRegistry(writeTempYAML(t, registryYAML))
	out := reg.ProfileYAML("no-such-model")
	if !strings.Contains(out, "not found") {
		t.Errorf("ProfileYAML: want 'not found' message, got:\n%s", out)
	}
}

func TestProfileYAML_allModels(t *testing.T) {
	reg, _ := loadRegistry(writeTempYAML(t, registryYAML))
	for _, id := range reg.Order {
		out := reg.ProfileYAML(id)
		if strings.Contains(out, "not found") {
			t.Errorf("ProfileYAML(%q): unexpected 'not found'", id)
		}
		if len(out) == 0 {
			t.Errorf("ProfileYAML(%q): empty output", id)
		}
	}
}
