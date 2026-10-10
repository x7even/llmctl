# llmstack

OpenAI-compatible LLM serving stack for **concurrent agent use**.  
Designed for: Claude Code · OpenCode · MCP testing · agent frameworks · raw API clients.

Reference hardware: 1–4× AMD Radeon AI PRO R9700 (gfx1201, 32 GB each) — `scripts/configure` auto-detects your GPU count and patches the config accordingly. See [Hardware compatibility](#hardware-compatibility) for details.  
Backends: **vLLM 0.26.0** (FP8/AWQ/safetensors, PagedAttention, high concurrency) + **llama-server Vulkan** (GGUF models)  
Router: **llama-swap** — one OpenAI endpoint, models loaded on demand by the `model` field

---

## Prerequisites

Before cloning, confirm these are in place:

- **ROCm installed** — `/dev/kfd` must exist. If `ls /dev/kfd` returns "No such file", install ROCm first: [ROCm installation guide](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/)
- **podman installed** — `which podman`. Rootless podman is assumed throughout.
- **GPU device group membership** — your user must be in the `render` (and optionally `video`) group: `groups | grep render`. If not: `sudo usermod -aG render,video $USER` then log out and back in.
- **Models on disk** — the config expects models at `/mnt/models/llm/`. Adjust the `-v` mount paths in `config/models.yaml` if yours are elsewhere.

The vLLM container image (`docker.io/vllm/vllm-openai-rocm:v0.26.0`) is large (~35 GB) and will be pulled automatically on first `llmctl swap`. Make sure you have the disk space and a reasonable connection before starting.

---

## Quick start

```bash
# 1. Clone and install tools
git clone https://github.com/x7even/llmctl.git ~/ai/llmstack
cd ~/ai/llmstack
ln -sf "$(pwd)/bin/llmctl" ~/.local/bin/llmctl

# 2. Install llmpanel TUI (pre-built binary — no Go required)
curl -fsSL https://raw.githubusercontent.com/x7even/llmctl/master/install-llmpanel.sh | bash

# 3. Configure for your machine (GPU count + absolute paths)
#    This is required — models.yaml ships with __LLMSTACK_DIR__ placeholders
#    that configure replaces with the actual repo path, and patches GPU count.
scripts/configure

# 4. Start the router
llmctl up

# 5. Load a model and wait until ready
llmctl swap qwen3.8-27b-code

# 6. Make a request
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.8-27b-code","messages":[{"role":"user","content":"Write a Python quicksort"}]}'

# 7. Open the TUI control panel (optional)
llmpanel
```

> **First-boot note:** vLLM compiles Inductor kernels and calibrates the FP8 KV cache
> on cold start — this is a one-time 18–20 min process. Compiled artifacts are cached in
> `.vllm-cache/` and `.triton-cache/`. Subsequent starts take ~2–3 min.

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
| `qwen3.8-27b-code` | vLLM TP=4 + MTP | ~31 GB + KV | 131K | **Default.** Claude Code, OpenCode, agentic coding; thinking on (medium effort) |
| `qwen3.8-27b-think` | vLLM TP=4 | ~31 GB + KV | 131K | Same model without MTP — better for parallel agent fleets |
| `qwen3.8-27b-fast` | vLLM TP=4 + MTP | ~31 GB + KV | 131K | Thinking off by default — quick answers, bulk work |
| `qwen3.8-flash-next` | llama-server Vulkan | ~81 GB | 262K (2 slots) | Qwen3.8-Flash-Next 125B (6B active), UD-IQ4_XS GGUF; vLLM path in progress |
| `qwen3.6-35b-code` | vLLM TP=4 + MTP | ~35 GB | 131K | Previous generation (MoE, 3B active) — MTP + thinking |
| `qwen3.6-35b-128k-nomtp` | vLLM TP=4 | ~35 GB | 131K | Previous generation — thinking, no MTP, high concurrency |
| `qwen3.6-35b-fast` | vLLM TP=4 | ~35 GB | 262K | Previous generation — thinking disabled by default |
| `gemma4-26b-a4b` | vLLM TP=4, BF16 | ~123 GB | 128K | High-concurrency; **528 tok/s conc=16**; vision; exclusive VRAM |
| `gemma4-26b-fp8` | vLLM TP=4, FP8 | — | 262K | Long-context Gemma 4 agent serving |
| `gemma4-26b-q8` | llama-server Vulkan | ~32 GB | 32K | Vision-capable; 154 tok/s conc=8; co-loadable |
| `gemma4-12b-q4` | llama-server Vulkan | ~13 GB | 32K | Lightest vision option; co-loadable with any profile |

Older Qwen profiles (3.6-27B, 3.6-35B 32K/64K/128K/512K/AWQ/GGUF, Qwen3-Coder-30B,
Qwen3.5-122B) were removed from the shipped config; their benchmark data is kept in
`docs/models.md` and the profiles can be restored from git history.

**Aliases** (short names that route to the same profile):

| Alias | Resolves to |
|-------|-------------|
| `qwen3.8`, `qwen3.8-27b`, `27b-3.8` | `qwen3.8-27b-code` |
| `27b-think` | `qwen3.8-27b-think` |
| `27b-fast`, `qwen3.8-nothink` | `qwen3.8-27b-fast` |
| `flash-next`, `qwen3.8-flash` | `qwen3.8-flash-next` |
| `qwen3.6`, `qwen3.6-35b`, `qwen3.6-35b-fp8` | `qwen3.6-35b-code` |
| `35b-nomtp` | `qwen3.6-35b-128k-nomtp` |
| `qwen3.6-fast`, `qwen3.6-nothin` | `qwen3.6-35b-fast` |
| `gemma4`, `gemma4-26b`, `gemma4-moe`, `gemma4-vision` | `gemma4-26b-q8` |
| `gemma4-vllm`, `gemma4-concurrent` | `gemma4-26b-a4b` |

See `docs/models.md` for benchmark data, architecture details, and tuning notes.

---

## Benchmarks at a glance

Measured on 4× R9700 (128 GB total), no-thinking unless noted, MTP enabled where noted (Qwen3.8 on vLLM 0.26.0; older rows on vLLM 0.22.1).
Metric: decode tok/s.

| Profile | serial | conc=4 | conc=8 | conc=16 |
|---------|--------|--------|--------|---------|
| `qwen3.8-27b-code` (medium-256, MTP)² | 66 | 194 | **361** | 549 |
| `gemma4-26b-a4b` (medium-256, BF16, thinking on¹)² | 53 | 167 | 287 | **528** |
| `qwen3.6-35b-code` (xlarge-2048, MTP)² | 43 | 155 | **335** | 651 |
| `qwen3.6-35b-code` (medium-256, MTP)² | 43 | 145 | **261** | 481 |
| `qwen3.6-35b-fp8` no-MTP (medium-256)² | 69 | — | **222** | — |
| `gemma4-26b-q8` (medium-256, Q8 GGUF, thinking on¹) | 66 | 117 | **154** | — |
| `gemma4-12b-q4` (medium-256, Q4 GGUF, thinking on¹) | 36 | 81 | **109** | — |

¹ Gemma 4 IT activates extended reasoning by default. The table numbers come from the original thinking-on baselines (2026-06-13). No-thinking baselines (2026-06-18) show that `chat_template_kwargs: {enable_thinking: false}` successfully suppresses `<think>` output, but does NOT meaningfully improve throughput — differences between thinking-on and no-thinking runs are within session-to-session noise (~0–6%). Both baseline sets are kept in `bench/baselines/`; see `bench/CLAUDE.md` for the dual-baseline convention.

² vLLM profiles (non-GGUF) use PagedAttention and continuous batching, enabling dramatically better concurrency scaling — throughput grows near-linearly from serial to conc=16 and beyond. GGUF profiles (llama-server Vulkan) plateau early due to fixed-thread batching; serial latency is comparable but concurrent throughput is several times lower at the same concurrency level.

See `docs/models.md` for full tables across all prompt sizes and concurrency levels.

---

## CLI reference (`llmctl`)

```
llmctl up                 start llama-swap (auto-downloads binary if missing)
llmctl down               stop llama-swap
llmctl status             running state, loaded models, GPU VRAM snapshot
llmctl list               list all profiles [* = loaded]
llmctl swap <profile>     load a model and wait until ready
llmctl unload             unload all backends, free VRAM (llama-swap stays up)
llmctl pick               interactive fzf / numbered picker
llmctl logs               tail the llama-swap process log
llmctl logs <profile>     tail a model's container log
llmctl bench [profile]    run concurrent benchmark
llmctl proxy-up           start llmproxy shim on :9000
llmctl proxy-down         stop llmproxy shim
llmctl proxy-status       show llmproxy state
```

Full reference: [`docs/llmctl.md`](docs/llmctl.md)

### Common workflows

```bash
# Check what's running and VRAM state
llmctl status

# Switch between models
llmctl swap qwen3.8-27b-code     # default: MTP + thinking, best single-stream latency
llmctl swap qwen3.8-27b-think    # no MTP — better for many parallel agents
llmctl swap qwen3.8-27b-fast     # thinking off
llmctl swap flash-next           # Qwen3.8-Flash-Next 125B (GGUF)
llmctl swap gemma4               # Gemma 4 26B Q8 vision (alias → gemma4-26b-q8)
llmctl swap gemma4-vllm          # Gemma 4 26B BF16 vLLM — highest concurrent tok/s

# Free VRAM without stopping the router
llmctl unload

# Benchmark the loaded model
llmctl bench qwen3.8-27b-code

# Tail model startup logs (useful during first boot)
llmctl logs qwen3.8-27b-code

# Interactive picker (requires fzf)
llmctl pick
```

---

## Terminal control panel (`llmpanel`)

`llmpanel` is a [roctop-style](https://github.com/x7even/roctop) TUI that combines monitoring and control in one
terminal window.

```bash
llmpanel [--url URL] [--interval DURATION] [--config PATH] [--log PATH]
```

**Panels** (press `1`–`5` or `Tab` to focus, `f` for fullscreen):

| # | Panel | Shows |
|---|-------|-------|
| 1 | Inference | Active model, running/waiting requests, KV%, decode tok/s, TTFT, prefix hit rate |
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

Build from source: `cd tui && make install`  
Full reference: [`tui/README.md`](tui/README.md)

---

## Adding a new model

**vLLM (safetensors / FP8 / AWQ):**
1. Copy the vLLM template block at the bottom of `config/models.yaml`
2. Set `name:`, the model path in `vllm serve /models/<dir>`, `--served-model-name`, and `--dtype`
3. Include `--cudagraph-capture-sizes 1 2 4 8 16 32` and the `.vllm-cache` / `.triton-cache` volume mounts (already in the template) to keep cold starts fast
4. Adjust `--gpu-memory-utilization` and `--max-num-seqs` as needed
5. `llmctl swap <new-profile>` to load and verify
6. Press `r` in llmpanel to reload the profile list without restarting

**GGUF (llama-server):**
1. Copy the GGUF template block from `config/models.yaml`
2. Set the `-m /models/<path>.gguf` argument
3. For split GGUFs (`-00001-of-0000N`), point at part 1 — llama.cpp auto-discovers the rest

---

## Architecture

```
Clients  ──►  llmproxy :9000  ──►  llama-swap :8080  ──►  vLLM container    :910x
                (optional)              (router)       └──►  llama-server      :910x
```

- **llama-swap** runs on the host; one OpenAI endpoint, backends loaded on demand
- Each backend is a rootless podman container with GPU device passthrough
- **llmproxy** is an HTTP shim that fixes vLLM SSE tool-call streaming for `@ai-sdk` clients
- Models swap by `model` field routing; TTL-based auto-unload configurable per profile
- Compilation caches (`.vllm-cache/`, `.triton-cache/`) are mounted into vLLM containers so Inductor kernels survive restarts
- No reverse proxy in default config — clients hit `:8080` (or `:9000` via llmproxy) directly

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
| Container exits immediately with `invalid argument` | Run `scripts/configure` — `models.yaml` still has `__LLMSTACK_DIR__` placeholders. podman rejects them as invalid volume source paths. |
| `llmctl up` hangs | Check `~/.local/share/llmstack/llama-swap.log` |
| `llmctl swap` times out | First vLLM boot compiles Inductor kernels — up to 20 min; check `llmctl logs <profile>`. Subsequent starts are ~2–3 min (cached). |
| Log shows `exit status 125` | The container failed to start before running. Most likely cause: `/dev/kfd` doesn't exist (ROCm not installed). Run `ls /dev/kfd` — if missing, see [Prerequisites](#prerequisites). Also check `podman images` to confirm the image was pulled. |
| vLLM fails to start | `llmctl logs <profile>`; confirm image exists with `podman images` |
| GGUF model not found | Verify path in `config/models.yaml` matches `/mnt/models/llm/...` |
| GPU not visible in container | Check user is in `video` and `render` groups: `groups` |
| Tool call errors in OpenCode | Use llmproxy (`llmctl proxy-up`); see `docs/workarounds.md` |
| `Expected 'function.name' to be a string` | Same — llmproxy fixes this; point client at `:9000` |

---

## Hardware compatibility

The containers and config in this repo are built for the **AMD Radeon AI PRO R9700 (gfx1201 / RDNA4)**. **1 to 4 GPUs are supported** — `scripts/configure` auto-detects your count and patches `tensor-parallel-size`, `tensor-split`, and expert-parallel settings accordingly. The benchmarks in this repo use 4× R9700 (128 GB total); fewer GPUs reduce throughput and limit which models fit. Here is what each backend requires if you want to adapt it to other hardware:

| Backend | Requirement | Notes |
|---------|-------------|-------|
| **vLLM** | ROCm-compatible AMD GPU | Container image is `vllm/vllm-openai-rocm` (ROCm 7.2). Other AMD cards need `HSA_OVERRIDE_GFX_VERSION` set appropriately. NVIDIA requires a CUDA build of vLLM instead. |
| **llama-server (Vulkan)** | Any Vulkan-capable GPU | Works on AMD, NVIDIA, and Intel out of the box. No code changes needed — just point the `-m` path at your GGUF. |
| **llama-swap** | None | CPU-only router; hardware-agnostic. |
| **GPU monitoring** | AMD with `rocm-smi` | `llmpanel` displays `rocm-smi unavailable` gracefully on other platforms. |

### Configuration (required after cloning)

`scripts/configure` must be run once after cloning. It does two things:

1. **Replaces `__LLMSTACK_DIR__`** — `config/models.yaml` ships with this literal placeholder in all volume mount paths. llama-swap executes container commands without a shell, so environment variables like `$HOME` aren't expanded at runtime. `configure` substitutes the placeholder with the absolute path to your repo clone.

2. **Patches GPU count** — auto-detected via `rocm-smi`, or set with `--gpu-count`.

```bash
scripts/configure                  # auto-detect GPU count, apply both fixes
scripts/configure --dry-run        # preview the result without writing
scripts/configure --gpu-count 2    # override GPU count (if rocm-smi isn't available)
```

What it adjusts in `config/models.yaml`:

| Setting | What changes |
|---------|-------------|
| `__LLMSTACK_DIR__` | Replaced with the absolute path to this repo (e.g. `/home/alice/ai/llmstack`) |
| `--tensor-parallel-size` | Set to your GPU count |
| `--tensor-split` (llama-server) | Set to `1,1,...` matching GPU count (removed for 1 GPU) |
| `--enable-expert-parallel` | Removed when GPU count is 1 |

**VRAM limits** — `qwen3.8-flash-next` (~81 GB) won't fit on fewer than 3 GPUs. The script warns if your GPU count is below the minimum; those profiles should be removed from `models.yaml` in that case.

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
docs/models.md           Model benchmark data and tuning notes
docs/workarounds.md      Known issues and active workarounds
tests/smoke.sh           Smoke test (both backends)
bench/                   Benchmark scripts and saved baselines
bench/baselines/         Saved benchmark JSON files (one per model/config)
.vllm-cache/             Persistent vLLM Inductor compilation cache (gitignored)
.triton-cache/           Persistent Triton kernel cache (gitignored)
```
