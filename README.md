# llmstack

OpenAI-compatible LLM serving stack for **concurrent agent use**.  
Designed for: Claude Code · OpenCode · MCP testing · agent frameworks · raw API clients.

Hardware: 4× AMD Radeon AI PRO R9700 (gfx1201, 32 GB each = 128 GB total VRAM)  
Backends: **vLLM** (FP8/safetensors, PagedAttention, high concurrency) + **llama-server Vulkan** (GGUF models)  
Router: **llama-swap** — one OpenAI endpoint, models loaded on demand by the `model` field

---

## Quick start

```bash
# Install CLI tools (one-time, from llmstack directory)
ln -sf "$(pwd)/bin/llmctl"   ~/.local/bin/llmctl
ln -sf "$(pwd)/bin/llmpanel" ~/.local/bin/llmpanel

# Start the router
llmctl up

# Load a model (waits until ready — ~60 s cold start for 35B FP8)
llmctl swap qwen3.6-35b-code

# Open the terminal control panel
llmpanel

# Or use the API directly
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.6-35b-code","messages":[{"role":"user","content":"hello"}]}'
```

---

## Client configuration

| Client | Setting |
|--------|---------|
| Claude Code | `ANTHROPIC_BASE_URL=http://localhost:8080/v1` |
| OpenCode | `baseURL: http://localhost:9000/v1` (via llmproxy — see below) |
| Continue.dev | `apiBase: http://localhost:8080/v1` |
| aichat / llm CLI | `--url http://localhost:8080/v1` |
| curl / scripts | `http://localhost:8080/v1/chat/completions` |

> **OpenCode note:** OpenCode uses `@ai-sdk/openai-compatible` which has a
> strict tool-call streaming validator. Point it at `:9000` (llmproxy) rather
> than `:8080` directly. See `docs/workarounds.md`.

---

## Model profiles

| Profile | Backend | VRAM | Context | Best for |
|---------|---------|------|---------|---------|
| `qwen3-coder-30b-fp8` | vLLM TP=4 | ~30 GB | 32K | Code, agents, high concurrency |
| `qwen3.6-35b-code` | vLLM TP=4 + MTP | ~35 GB | 262K | Claude Code, OpenCode, agentic coding |
| `qwen3.6-35b-fast` | vLLM TP=4 | ~35 GB | 262K | Low-latency chat, thinking disabled by default |
| `qwen3.6-35b-512k` | vLLM TP=4 + MTP + YaRN | ~35 GB | 512K | Large codebase ingestion, long documents |
| `qwen3.6-35b-q4ks` | llama-server Vulkan | ~20 GB | 32K | Fast GGUF alternative, lower VRAM |
| `qwen3.5-122b-a10b-q4` | llama-server Vulkan | ~73 GB | 32K | Heavyweight reasoning, one-off queries |
| `qwen3.5-122b-a10b-q6` | llama-server Vulkan | ~98 GB | 16K | Maximum quality (tight VRAM budget) |

**Aliases** (short names that route to the same profile):

| Alias | Resolves to |
|-------|-------------|
| `coder` | `qwen3-coder-30b-fp8` |
| `qwen3.6`, `qwen3.6-35b`, `qwen3.6-35b-fp8` | `qwen3.6-35b-code` |
| `qwen3.6-fast`, `qwen3.6-nothin` | `qwen3.6-35b-fast` |
| `qwen3.6-512k`, `qwen3.6-long` | `qwen3.6-35b-512k` |
| `qwen3.6-gguf` | `qwen3.6-35b-q4ks` |
| `qwen3.5-122b`, `122b` | `qwen3.5-122b-a10b-q4` |
| `qwen3.5-122b-q6`, `122b-q6` | `qwen3.5-122b-a10b-q6` |

See `docs/models.md` for benchmark data, architecture details, and tuning notes.

---

## CLI reference (`llmctl`)

```
llmctl up                start llama-swap (auto-downloads binary if missing)
llmctl down              stop llama-swap
llmctl status            running state, loaded models, GPU VRAM snapshot
llmctl list              list all profiles [* = loaded]
llmctl swap <profile>    load a model and wait until ready
llmctl unload            unload all backends, free VRAM (llama-swap stays up)
llmctl pick              interactive fzf / numbered picker
llmctl logs              tail the llama-swap process log
llmctl logs <profile>    tail a model's container log
llmctl bench [profile]   concurrent benchmark (Phase 2)
llmctl proxy-up          start llmproxy shim on :9000
llmctl proxy-down        stop llmproxy shim
llmctl proxy-status      show llmproxy state
```

Full reference: [`docs/llmctl.md`](docs/llmctl.md)

---

## Terminal control panel (`llmpanel`)

`llmpanel` is a roctop-style TUI that combines monitoring and control in one
terminal window.

```bash
llmpanel [--url URL] [--interval DURATION] [--config PATH] [--log PATH]
```

**Panels** (press `1`–`5` or `Tab` to focus, `f` for fullscreen):

| # | Panel | Shows |
|---|-------|-------|
| 1 | Inference | Active model, running/waiting requests, KV%, decode tok/s, TTFT |
| 2 | GPU | Per-GPU VRAM, use%, temperature — colour-coded |
| 3 | Models | All profiles; `▶` cursor, `●` loaded; `Enter`/`s` to swap, `u` to unload |
| 4 | Config | Scrollable YAML for the selected profile; updates as cursor moves |
| 5 | Logs | Live tail of llama-swap log |

**Key bindings:**

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Cycle panel focus |
| `1`–`5` | Jump to panel |
| `f` / `Esc` | Toggle fullscreen |
| `↑↓` / `jk` | Navigate model list or scroll Config/Logs |
| `Enter` / `s` | Swap to selected model |
| `u` | Unload all models |
| `p` | Cycle poll interval (500ms → 1s → 2s → 5s → 15s) |
| `r` | Reload models.yaml from disk |
| `q` / `Ctrl+C` | Quit |

Build: `cd tui && make install`  
Full reference: [`tui/README.md`](tui/README.md)

---

## Adding a new model

**vLLM (safetensors / FP8 / AWQ):**
1. Copy the vLLM template block at the bottom of `config/models.yaml`
2. Set `name:`, the model path in `serve /models/<dir>`, `--served-model-name`, and `--dtype`
3. Adjust `--gpu-memory-utilization` and `--max-num-seqs` as needed
4. `llmctl swap <new-profile>` to load and verify
5. `r` in llmpanel to reload the profile list without restarting

**GGUF (llama-server):**
1. Copy the GGUF template block from `config/models.yaml`
2. Set the `-m /models/<path>.gguf` argument
3. For split GGUFs (`-00001-of-0000N`), point at part 1 — llama.cpp auto-discovers the rest

---

## Architecture

```
Clients  ──►  llmproxy :9000  ──►  llama-swap :8080  ──►  vLLM container   :910x
                (optional)              (router)       └──►  llama-server     :910x
```

- **llama-swap** runs on the host; one OpenAI endpoint, backends loaded on demand
- Each backend is a rootless podman container with GPU device passthrough
- **llmproxy** is an HTTP shim that fixes vLLM SSE tool-call streaming for `@ai-sdk` clients
- Models swap by `model` field routing; TTL-based auto-unload configurable per profile
- No reverse proxy in Phase 1 — clients hit `:8080` (or `:9000` via llmproxy) directly

---

## Smoke test

```bash
# Checks both backends — slow on first run (cold container pull + model load)
./tests/smoke.sh
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `llmctl up` hangs | Check `~/.local/share/llmstack/llama-swap.log` |
| `llmctl swap` times out | Cold GGUF load can take 3 min; check `llmctl logs <profile>` |
| vLLM fails to start | `llmctl logs <profile>`; confirm image exists with `podman images` |
| GGUF model not found | Verify path in `config/models.yaml` matches `/mnt/models/llm/...` |
| GPU not visible in container | Check user is in `video` and `render` groups: `groups` |
| Tool call errors in OpenCode | Use llmproxy (`llmctl proxy-up`); see `docs/workarounds.md` |
| `Expected 'function.name' to be a string` | Same — llmproxy fixes this; point client at `:9000` |

---

## Files

```
bin/llmctl               CLI lifecycle manager (Python)
bin/llmpanel             Terminal control panel binary (Go, built from tui/)
bin/llmproxy             Streaming shim for @ai-sdk tool-call bug (Python)
config/models.yaml       Model profiles — edit here to add/change models
config/templates/        Custom Jinja chat templates (e.g. no-think variant)
containers/vllm/         vLLM Containerfile
containers/llama-server/ llama-server Vulkan Containerfile
tui/                     Go source for llmpanel
docs/llmctl.md           Full llmctl command reference
docs/llmpanel.md         → see tui/README.md
docs/models.md           Model benchmark data and tuning notes
docs/workarounds.md      Known issues and active workarounds
tests/smoke.sh           Phase 1 verification
bench/                   Benchmark scripts (Phase 2)
```

---

## Phases

- **Phase 1** (current): serving stack, all 7 model profiles, llmctl, llmpanel, smoke test
- **Phase 2** (after benchmark approval): prefix caching tuned, MCP sidecar (mcpo), Caddy front door, llmpanel model editing
- **Phase 3** (after Phase 2 approval): Prometheus scrape, Grafana dashboard, ROCm-HIP llama.cpp variant
