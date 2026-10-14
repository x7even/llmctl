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

`make build` writes `../bin/llmpanel` directly. That binary is gitignored and must not be
committed (`git ls-files bin` lists only `llmctl` and `llmproxy`).

---

## Architecture

```
main.go      Entry point, CLI flags, initial config load
app.go       Bubbletea model (Init/Update/View), panel routing, key bindings
data.go      Polling logic: /v1/models, /metrics, rocm-smi, YAML config
config.go    models.yaml parser, profile structs (incl. metadata.requires)
hw.go        Hardware detection + Supports(); port of scripts/llmhw.py (shared fixtures)
hwpanel.go   Models-panel hardware logic: verdicts, filtering, reasons, swap guard
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

Startup and `r` (not the ticker):
    hw.go: DetectHW(override)   → app.hw          (sysfs, rocm-smi fallback, --gpu-count)
    hw.go: Supports(requires,hw) → app.verdicts[profile]   (one per profile)
    app.profiles() = models.yaml order filtered by verdicts (all of them when showAll)
```

### Hardware filtering (Models panel)

- Detection happens once at startup (`main.go` wires `app.detectHW` and calls
  `refreshHW`) and again on `r`; never on the poll tick. `newApp` does not probe the
  machine, so tests stay hermetic: they set `app.hw`/`app.detectHW` directly.
- `app.profiles()` is the *visible* list and `app.cursor`/`modelsScroll` index into it;
  `app.allProfiles()` is the unfiltered models.yaml order. Anything that changes the visible
  list (`a`, `r`) must go through `selectedProfile()` / `restoreSelection()` so the cursor stays on
  the same profile (or clamps) and `clampModelsScroll()` re-validates the window.
- `modelsVisible()` reserves rows for the footer and the `↑/↓ more` markers; keep
  `renderModels` within `h2-1` rows or the footer is cut off (covered by a test).
- Unsupported rows (show-all only) use `stUnsupported` (adaptive grey) plus a reason from
  `compactReasonText()` (`4 GPU`, `2/4 GPU`, `96 GiB RAM`, trailing `est`) so it survives the
  ~14 columns left beside long names; `reasonText()` has the full wording
  (`needs 4 GPUs, have 2 (est)`) for the Config panel and the swap messages. Both paraphrase
  the `llmhw` reasons that `llmctl` prints raw (`needs gpus [4], detected 2`).
- The refusal messages (`swapMsg` / `hwBlockMsg`) are cut to the column / terminal width, so the
  actionable part comes first; `clearBlock()` drops them on cursor move, `a`, `r` and new swaps.
- Everything on the status row must stay one row (truncate, do not wrap): `modelsVisible()`
  assumes it. The `Swap to X?` prompt falls back to `Swap to X? y/n` when narrow.
- Footer variants shrink with width; the common 40-column Models column shows the short ones
  (`N hidden - a: show all`, `hw not detected - showing all`).
- A swap of an unsupported profile never reaches `swapFn` (`blockUnsupported`, checked at
  `Enter` and again when confirming, because `r` can change the verdict in between). The TUI
  has no force path; `llmctl swap --force` owns that.
- Fail open: GPU count unknown means no verdicts are stored, so nothing is hidden or greyed
  and the footer shows a dim "not detected" note. A missing verdict means allowed.
- `unlisted:` in models.yaml is not read by the panel (as before); do not conflate it with the
  hardware verdict. `scripts/configure` writes `unlisted: true  # llmstack:auto` for unsupported
  profiles, which only affects llama-swap's `/v1/models`.
- `swapFn` is injectable (default `swapModel`) so tests can assert it was not called.
- If you change a requirement rule, change it in `scripts/llmhw.py` too; both are tested
  against `tests/fixtures/llmhw_cases.json`.

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
The reload re-calls the config.go parser, re-detects the hardware, recomputes every
profile's verdict, and updates the in-memory profile list (selection is kept).

### Keys

`a` toggles show-all in the Models panel (unsupported profiles greyed with a reason). The
full key table is in `tui/README.md`; keep the status-bar hint in `renderStatus` in sync.

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
