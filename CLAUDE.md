# llmstack — Claude context

OpenAI-compatible LLM serving stack for concurrent agent use on 4× AMD Radeon AI PRO R9700.
You are the expert agent responsible for this codebase. Every change you make should leave
the stack more reliable, faster, or better documented than you found it.

---

## Hardware

- **4× AMD Radeon AI PRO R9700** (gfx1201 / RDNA4), 32 GB VRAM each = **128 GB total**
- ROCm 7.2, Vulkan/RADV available
- Models stored at `/mnt/models/llm/` (read-only mount inside containers)
- Host OS: Linux, rootless podman, no sudo needed for containers

VRAM budget is the primary constraint on every model and config decision.

---

## Stack architecture

```
Claude Code / OpenCode / curl
        │
        ▼
  llmproxy :9000          ← optional SSE fix shim (for @ai-sdk clients)
        │
        ▼
  llama-swap :8080         ← router (host process, no container)
        │
        ├── vLLM container :9100+    (FP8 / AWQ / safetensors)
        └── llama-server container :9100+  (GGUF / Vulkan)
```

| Component | Port | Process | Managed by |
|-----------|------|---------|-----------|
| llama-swap | :8080 | host | `llmctl up/down` |
| llmproxy | :9000 | host | `llmctl proxy-up/down` |
| vLLM backends | :9100+ | podman container | llama-swap |
| llama-server | :9100+ | podman container | llama-swap |

Container naming: `llmstack-vllm-<profile-id>` / `llmstack-llama-<profile-id>`  
State files: `~/.local/share/llmstack/llama-swap.{pid,log}`, `llmproxy.{pid,log}`

---

## Key commands

```bash
llmctl up                        # start llama-swap router
llmctl swap qwen3.6-35b-code     # load a model (blocks until healthy)
llmctl status                    # show running state + VRAM
llmctl logs qwen3.6-35b-code     # tail container log (essential for debugging startup)
llmctl unload                    # free VRAM, keep router running
llmctl down                      # stop everything
llmpanel                         # TUI: inference metrics, GPU, model list, config, logs
```

After changing `config/models.yaml`, restart llama-swap for the change to take effect:
```bash
llmctl down && llmctl up
```

---

## vLLM cold start — critical knowledge

**First boot on a fresh machine takes 18–20 minutes.** This is normal. Breakdown:

| Phase | Time | Cached? |
|-------|------|---------|
| Inductor torch.compile (4 TP ranks in parallel) | ~14 min | ✅ `.vllm-cache/` |
| CUDA graph capture (6 batch sizes) | ~13 s | ❌ every start |
| FP8 KV scale calibration | ~3 min | ❌ every start |
| **Total — first boot** | **~18–20 min** | |
| **Total — subsequent boots** | **~2–3 min** | |

The cache directories `.vllm-cache/` and `.triton-cache/` live in this repo root (gitignored).
They **must exist on the host** — created automatically by `mkdir -p .vllm-cache .triton-cache`
and mounted into every vLLM container. Without the mounts, every start is a cold compile.

To watch startup progress: `llmctl logs <profile>` — wait for "Application startup complete."
`healthCheckTimeout: 300` in models.yaml is set for warm starts. For first boot, wait manually.

---

## CRITICAL RULES — never break these

### vLLM profiles: mandatory flags

Every vLLM profile **must** have these three things:

```yaml
# 1. Nullify the AMD official image's broken ENTRYPOINT
--entrypoint=""
# ...then explicitly invoke:
vllm serve /models/...

# 2. Explicit CUDA graph sizes — without this, vLLM generates ~2000+ sizes = 18+ min startup
--cudagraph-capture-sizes 1 2 4 8 16 32

# 3. Persistent cache volumes — without these, torch.compile re-runs every start (~14 min)
-v ${LLMSTACK_DIR:-$HOME/ai/llmstack}/.vllm-cache:/root/.cache/vllm
-v ${LLMSTACK_DIR:-$HOME/ai/llmstack}/.triton-cache:/root/.triton/cache
```

If you add a new vLLM profile and omit any of these, the first startup will take 18+ minutes
or fail with `unrecognized arguments`.

### AWQ + expert-parallel = hard crash

**Never combine `--quantization awq` with `--enable-expert-parallel`.**

AWQ MoE layers fall back to a Triton WNA16 kernel that is incompatible with expert
parallelism. It crashes mid-startup with `IndexError: index 3 is out of bounds for
dimension 1 with size 1`. AWQ profiles must omit `--enable-expert-parallel`.

### GGUF in vLLM: qwen35moe not supported

`ValueError: GGUF model with architecture qwen35moe is not supported yet.`
Do not attempt to serve Qwen3.x MoE GGUF files via vLLM. Use llama-server (Vulkan) for GGUF.
Use safetensors (FP8/AWQ) for vLLM.

### Never use --enforce-eager

`--enforce-eager` skips CUDA graph capture and saves startup time but permanently reduces
throughput by ~10–20%. The user explicitly rejected this trade-off. Use
`--cudagraph-capture-sizes` instead to keep graphs small.

### localhost/llmstack-vllm:latest is broken

The locally-built image (`localhost/llmstack-vllm:latest`) uses vLLM 0.10.2rc2 with
transformers 5.7.0.dev0. Transformers 5.x removed `all_special_tokens_extended`, which
causes `AttributeError` on Qwen3 models at startup. **Do not use this image.**

All vLLM profiles must use: `docker.io/vllm/vllm-openai-rocm:latest` (vLLM 0.22.1, ROCm 7.2)

### FP8 kernel config warnings are expected

vLLM prints at startup:
```
Using default W8A8 Block FP8 kernel config. Performance might be sub-optimal!
Config file not found for device_name=AMD_Radeon_R9700
```
This is a known issue — the R9700 (gfx1201) has no hand-tuned FP8 GEMM kernel in
vLLM's registry. It falls back to MI300X defaults. Performance is measurable but acceptable.
Do not attempt to suppress or work around this warning; it requires upstream tuning work.

---

## Development workflow

### Adding a model profile
1. Copy the vLLM or GGUF template from the bottom of `config/models.yaml`
2. See `config/CLAUDE.md` for mandatory settings checklist
3. `llmctl down && llmctl up` to reload the config
4. `llmctl swap <new-profile>` — watch startup with `llmctl logs <profile>`
5. Once healthy: run a quick benchmark (see `bench/CLAUDE.md`)
6. Save baseline to `bench/baselines/<profile>.json`
7. Commit config + baseline together

### Benchmarking
Always use `--no-thinking` for comparable numbers across models:
```bash
python3 bench/concurrent_bench.py \
  --model qwen3.6-35b-code \
  --sweep 1,2,4,8,16 --prompt all --no-thinking \
  --save bench/baselines/qwen3.6-35b-code-$(date +%Y%m%d).json
```
See `bench/CLAUDE.md` for full methodology and comparison rules.

### TUI changes
```bash
cd tui && go test ./...        # must pass before committing
cd tui && make build           # build llmpanel binary
llmpanel --config config/models.yaml   # test it live
```
See `tui/CLAUDE.md` for architecture and coding conventions.

### Committing
- Write commit messages explaining **why**, not just what changed
- Never add `Co-Authored-By:` lines
- Never use `--no-verify`
- Include benchmark data in commit messages when changing performance-relevant config

---

## Model profiles quick reference

| Profile | Backend | VRAM | Active params | Notes |
|---------|---------|------|--------------|-------|
| `qwen3.6-35b-code` | vLLM + MTP | ~35 GB | 3B (MoE) | Primary; thinking ON; 262K ctx |
| `qwen3.6-35b-fast` | vLLM | ~35 GB | 3B (MoE) | Thinking OFF by default |
| `qwen3.6-35b-512k` | vLLM + MTP + YaRN | ~35 GB | 3B (MoE) | 512K ctx via RoPE scaling |
| `qwen3.6-35b-awq` | vLLM AWQ | ~20 GB | 3B (MoE) | Int4; no expert-parallel |
| `qwen3.6-27b-fp8` | vLLM | ~29 GB | 27B (dense) | Highest SWE-bench (77.2) |
| `qwen3.6-27b-q4km` | llama-server | ~17 GB | 27B (dense) | GGUF; low VRAM |
| `qwen3.6-35b-q4ks` | llama-server | ~20 GB | 3B (MoE) | GGUF; fast cold start |
| `qwen3-coder-30b-fp8` | vLLM | ~30 GB | 3B (MoE) | Legacy baseline only |
| `qwen3.5-122b-a10b-q4` | llama-server | ~73 GB | 10B (MoE) | Heavyweight; single-user |
| `qwen3.5-122b-a10b-q6` | llama-server | ~98 GB | 10B (MoE) | Max quality; tight VRAM |
| `gemma4-26b-a4b` ✓ | vLLM BF16 | ~123 GB | 4B (MoE) | 528 tok/s @ conc=16; exclusive VRAM |
| `gemma4-26b-q8` ✓ | llama-server + mmproj | ~32 GB | 4B (MoE) | **Vision**; alias `gemma4` |
| `gemma4-12b-q4` ✓ | llama-server + mmproj | ~13 GB | 12B (dense) | Lightest vision; co-loadable |

Use aliases for common swaps: `llmctl swap qwen3.6` (→ code), `llmctl swap 122b` (→ Q4), `llmctl swap gemma4` (→ 26B Q8 vision), `llmctl swap gemma4-vllm` (→ 26B vLLM).
✓ = on disk and benchmarked

---

## Benchmark baselines summary

All measured on 4× R9700, vLLM 0.22.1, `--no-thinking`, MTP where noted.
`medium-256` prompt, decode tok/s:

| Profile | serial | conc=8 | conc=16 |
|---------|--------|--------|---------|
| qwen3.6-35b-code (MTP) | 43 | 261 | 481 |
| qwen3.6-35b-awq | 92 | 250 | — |
| qwen3.6-35b-fp8 no-MTP | 69 | 222 | — |
| qwen3.6-27b-fp8 | 23 | 153 | — |
| qwen3-coder-30b-fp8 | 39 | 158 | — |
| gemma4-26b-a4b (vLLM BF16) | 53.4 | 287.1 | **528.2** |
| gemma4-26b-q8 (GGUF, llama-server) | 65.5 | 153.9 | 135.8 |
| gemma4-12b-q4 (GGUF, llama-server) | 36.1 | 108.9 | 94.8 |

Full data across all prompt sizes: `bench/CLAUDE.md` and `bench/baselines/`.

---

## File map

```
bin/llmctl           Python CLI — lifecycle, model switching, log tailing
bin/llmproxy         Python SSE shim — fixes vLLM null tool-call names for @ai-sdk
bin/llmpanel         Pre-built TUI binary (or build from tui/)
config/models.yaml   Single source of truth for all model profiles
config/templates/    Custom Jinja chat templates
tui/                 Go source for llmpanel (Bubbletea)
bench/               Benchmark scripts + saved baselines
tests/smoke.sh       Integration smoke test (both backends)
scripts/configure    GPU-count auto-detector; patches models.yaml
docs/models.md       Full benchmark data + per-profile architecture notes
docs/llmctl.md       Full CLI reference
docs/workarounds.md  Active bugs + workarounds (vLLM SSE null name)
.vllm-cache/         Persistent Inductor compilation cache (gitignored)
.triton-cache/       Persistent Triton kernel cache (gitignored)
```
