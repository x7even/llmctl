# tui/ — llmpanel development guide

`llmpanel` is a Bubbletea TUI providing live inference metrics, GPU monitoring,
model switching, and config/log viewing in a single terminal window.

---

## Build and test

```bash
cd tui

# Run tests (must pass before every commit)
go test ./...

# Build to bin/llmpanel
make build

# Build and install to ~/.local/bin/llmpanel
make install

# Run directly from source
go run . --config ../config/models.yaml
```

The pre-built binary is committed at `bin/llmpanel`. After `make build`, copy it:
```bash
cp tui/llmpanel bin/llmpanel
```

---

## Architecture

```
main.go      Entry point, CLI flags, initial config load
app.go       Bubbletea model (Init/Update/View), panel routing, key bindings
data.go      Polling logic: /v1/models, /metrics, rocm-smi, YAML config
config.go    models.yaml parser, profile structs
```

### Data flow

```
Ticker (poll interval)
    │
    ▼
data.go: fetchAll()
    ├── GET /v1/models       → loaded model list
    ├── GET /metrics         → vLLM Prometheus metrics (tok/s, TTFT, KV%)
    ├── exec rocm-smi        → per-GPU VRAM and temp
    └── read models.yaml     → profile list for Models panel
    │
    ▼
app.go: Update() receives DataMsg
    │
    ▼
View() renders 5 panels
```

### Panel layout

5 panels numbered 1–5. Focus cycling via `Tab`/`Shift+Tab` or number keys.
Each panel renders independently; fullscreen (`f`) expands the focused panel.

| # | Panel | Primary data source |
|---|-------|-------------------|
| 1 | Inference | vLLM `/metrics` endpoint |
| 2 | GPU | `rocm-smi --showmeminfo vram` |
| 3 | Models | models.yaml profiles + `/v1/models` |
| 4 | Config | models.yaml YAML for selected profile |
| 5 | Logs | tail of `~/.local/share/llmstack/llama-swap.log` |

---

## Key conventions

### No global state

Data is passed through the Bubbletea `Model` struct. Do not use package-level
variables for runtime state — only for constants and config defaults.

### Error display

Surface errors in the affected panel rather than crashing. If `rocm-smi` is
unavailable, GPU panel shows "rocm-smi unavailable" gracefully. If `/metrics`
returns 404 (llama-server doesn't expose Prometheus), show "--" for metrics.

### Poll interval

Default 1 s. User-cyclable with `p` key: 500ms → 1s → 2s → 5s → 15s.
`rocm-smi` is the most expensive call — it's a subprocess exec. Do not poll
faster than 500ms.

### Config hot-reload

`r` key re-reads `models.yaml` from disk without restarting llmpanel.
This is the primary way to reflect profile additions during a session.
The reload just re-calls the config.go parser and updates the in-memory profile list.

---

## Adding a new panel or metric

1. Add the metric to the fetch logic in `data.go` (include in `DataMsg`)
2. Add the field to the `Model` struct in `app.go`
3. Update `Update()` to store the new value from `DataMsg`
4. Update `View()` for the relevant panel (or add a new panel case)
5. If adding a new panel: update the panel count, key bindings, and tab cycling in `app.go`
6. `go test ./...` must still pass

---

## Testing without a live llama-swap

Tests use stubs for all external calls (HTTP, subprocess). Do not add tests that
require a running llama-swap or vLLM instance — those are integration tests and
belong in `tests/smoke.sh`, not in Go unit tests.

---

## Dependencies

Managed via Go modules (`go.mod` / `go.sum`). Key deps:

| Package | Use |
|---------|-----|
| `github.com/charmbracelet/bubbletea` | TUI event loop |
| `github.com/charmbracelet/lipgloss` | Styles, colors, layout |
| `github.com/charmbracelet/bubbles` | Viewport, list, spinner widgets |

Keep dependencies minimal. Do not add a dep for something the standard library covers.
Run `go mod tidy` after any dep change.
