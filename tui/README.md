# llmpanel

Terminal control panel for the llmstack serving stack.  
Live monitoring, model switching, config viewing, and log tailing — all from
one roctop-style TUI.

Built with [Bubbletea](https://github.com/charmbracelet/bubbletea) +
[Lipgloss](https://github.com/charmbracelet/lipgloss).

---

## Installation

**Build and install (from the `tui/` directory):**

```bash
make install
# Builds bin/llmpanel and symlinks it to ~/.local/bin/llmpanel
```

Or build only:

```bash
make build
# Produces bin/llmpanel (one directory up from tui/)
```

Requires Go 1.24+. The Makefile auto-detects `go` on `$PATH` or falls back to
`~/go-sdk/go/bin/go`.

---

## Running

```bash
llmpanel
```

Connects to llama-swap at `http://127.0.0.1:8080` by default. llama-swap must
already be running (`llmctl up`).

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--url URL` | `http://127.0.0.1:8080` | llama-swap base URL |
| `--interval DURATION` | `1s` | Poll interval. One of: `500ms` `1s` `2s` `5s` `15s` |
| `--config PATH` | `~/ai/llmstack/config/models.yaml` | Path to models.yaml |
| `--log PATH` | `~/.local/share/llmstack/llama-swap.log` | Log file to tail |

---

## Layout

```
╭─ Inference ──────────────────────────╮╭─ GPU ──────────────────────────────╮
│ Inference                            ││ GPU                                │
│ ────────────────────────────────     ││ ────────────────────────────────   │
│   qwen3.6-35b-code  (:9104)  [● ACTIVE]   VRAM used/tot GB  VRAM%  Use%  Temp
│   Running: 2  Waiting: 0  KV: 12.3% ││   0   33.0 /  34.2     97%   99%   72°C
│   Decode: 387 tok/s  TTFT: 0.84s    ││   1   32.3 /  34.2     94%  100%   74°C
│   refreshed 0s ago                  ││   2   32.4 /  34.2     95%   98%   71°C
╰──────────────────────────────────────╯│   3   32.4 /  34.2     95%  100%   74°C
╭─ Models ──────────╮╭─ Config ────────╯───────────────────────────────────────╮
│ Models            ││ Config                                                  │
│ ──────────────    ││ ──────────────────────────────────────────────────────  │
│   qwen3-coder...  ││ # qwen3.6-35b-code                                     │
│ ▶ qwen3.6-35b-... ●  name: Qwen3.6-35B-A3B-FP8 (code)                      │
│   qwen3.6-35b-... ││ ttl: 600                                               │
│   qwen3.6-35b-... ││ concurrencyLimit: 64                                   │
│   qwen3.6-35b-... ││ aliases:                                               │
│   qwen3.5-122b... ││   - qwen3.6                                            │
╰───────────────────╯╰─────────────────────────────────────────────────────────╯
╭─ Logs ─────────────────────────────────────────────────────────────────────╮
│ Logs                                                                       │
│ ────────────────────────────────────────────────────────────────────────   │
│ 2026-05-06 12:34:01 starting backend qwen3.6-35b-code on :9104            │
│ 2026-05-06 12:34:58 backend healthy                                        │
╰────────────────────────────────────────────────────────────────────────────╯
 [tab] panel  [f] fullscreen  [↑↓/jk] nav  [s/↵] swap  [u] unload  [p] poll:1s  [r] reload  [q] quit
```

**Colour coding:**

| Metric | Green | Yellow | Red |
|--------|-------|--------|-----|
| VRAM % | < 50% | 50–80% | > 80% |
| GPU use % | < 50% | 50–80% | > 80% |
| TTFT | < 1 s | 1–3 s | > 3 s |
| Temperature | < 70°C | 70–85°C | > 85°C |

---

## Key bindings

### Global

| Key | Action |
|-----|--------|
| `Tab` | Focus next panel |
| `Shift+Tab` | Focus previous panel |
| `1` | Focus Inference panel |
| `2` | Focus GPU panel |
| `3` | Focus Models panel |
| `4` | Focus Config panel |
| `5` | Focus Logs panel |
| `f` | Toggle fullscreen for focused panel |
| `Esc` | Exit fullscreen |
| `p` | Cycle poll interval: 500ms → 1s → 2s → 5s → 15s |
| `r` | Reload `models.yaml` from disk (picks up edits without restart) |
| `q` / `Ctrl+C` | Quit |

### Models panel (when focused)

| Key | Action |
|-----|--------|
| `↑` / `k` | Move cursor up |
| `↓` / `j` | Move cursor down |
| `Enter` / `s` | Swap to selected model (blocks with spinner until loaded) |
| `u` | Unload all running models (free VRAM, keep llama-swap running) |

### Config panel (when focused)

| Key | Action |
|-----|--------|
| `↑` / `k` | Scroll up one line |
| `↓` / `j` | Scroll down one line |
| `PgUp` | Scroll up one page |
| `PgDn` | Scroll down one page |

### Logs panel (when focused)

| Key | Action |
|-----|--------|
| `↑` / `k` | Scroll up 3 lines |
| `↓` / `j` | Scroll down 3 lines |
| `PgUp` | Scroll up one page |
| `PgDn` | Scroll down one page |
| `g` | Jump to top |
| `G` | Jump to bottom (most recent) |

---

## Panels

### Inference

Polls `GET /running` and the active backend's `/metrics` Prometheus endpoint
every poll interval.

Shows:
- Active model name and port — green `[● ACTIVE]` indicator
- Requests currently being processed (`num_requests_running`)
- Requests queued but not yet started (`num_requests_waiting`)
- KV cache utilisation percentage
- Decode throughput in tok/s (computed from `generation_tokens_total` delta
  between polls; falls back to `avg_generation_throughput_toks_per_s`)
- Mean time-to-first-token (TTFT) — colour-coded by latency tier
- Seconds since last successful poll

When no model is loaded, all fields show `—`.  
When a model is loaded but metrics are unavailable (e.g. llama-server backend),
inference fields show `—`.

### GPU

Polls `rocm-smi --showmeminfo vram --showuse --showtemp` in a background
goroutine on every tick to avoid blocking the UI.

Shows per-GPU:
- Index
- VRAM used / total in GB
- VRAM utilisation % (colour-coded)
- GPU compute utilisation % (colour-coded)
- Junction temperature in °C (colour-coded)

Shows `rocm-smi unavailable` if the binary is not found.

### Models

Lists all profiles from `config/models.yaml` in their YAML-defined order
(not alphabetical). The registry is read at startup and refreshed with `r`.

- `▶` marks the cursor position
- `●` marks the currently loaded model
- Moving the cursor updates the Config panel in real time

During a swap: shows a spinner and "Loading `<profile>`…"  
After swap completes: shows `✓ loaded <profile>` or `✗ <error>` for 5 s.  
After unload: shows `✓ unloaded` for 5 s.

### Config

Scrollable YAML view of the profile under the Models cursor. Updates
immediately as you navigate the model list.

Shows: name, TTL, concurrency limit, aliases, `cmd` (the full podman
invocation), and `cmdStop`. Formatted as clean YAML for readability.

Use `r` to reload after editing `models.yaml` on disk.

### Logs

Tails the llama-swap log file (default:
`~/.local/share/llmstack/llama-swap.log`). Reads the last 500 lines on each
poll and scrolls to the bottom automatically. Scroll up with `↑`/`PgUp` to
read history; `G` snaps back to the bottom.

---

## Data sources

| Source | Endpoint / Command | Timeout |
|--------|--------------------|---------|
| Active model | `GET /running` | 2 s |
| Profile list | `GET /v1/models` | 2 s |
| vLLM metrics | `GET http://127.0.0.1:<port>/metrics` | 1 s |
| GPU stats | `rocm-smi` subprocess | 3 s |
| Log file | `os.ReadFile` | — |

All fetches run concurrently with the rocm-smi call. A single slow source does
not block the others.

---

## Building from source

```bash
cd tui/
make tidy    # fetch / update go.sum
make build   # produces ../bin/llmpanel
make install # build + symlink to ~/.local/bin/llmpanel
make clean   # remove binary
```

**Dependencies** (managed by Go modules):

| Package | Purpose |
|---------|---------|
| `github.com/charmbracelet/bubbletea` | TUI event loop and model |
| `github.com/charmbracelet/lipgloss` | Styling and layout |
| `github.com/charmbracelet/bubbles` | Viewport (scrollable panels) and spinner |
| `gopkg.in/yaml.v3` | models.yaml parsing with key-order preservation |

---

## Running tests

```bash
cd tui/
go test ./...
```

58 tests covering data parsing, config loading, and the bubbletea model
(navigation, poll cycling, decode-rate calculation, view rendering).
