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
| Model profiling/warmup (FP8 KV calibration) | ~14 min | ❌ every start |
| CUDA graph capture (6 batch sizes) | ~13 s | ❌ every start |
| **Total — first boot** | **~30 min** | |
| **Total — subsequent boots** | **~16 min** | |

Note: the model profiling/warmup run (FP8 KV calibration + memory profiling) takes ~800 s every
cold start for Qwen3.6-35B-A3B-FP8 with TP=4/EP=4 and 262K context. This is unavoidable.
`healthCheckTimeout: 1200` in models.yaml and `llmctl swap` timeout of 1260 s accommodate this.

**TTL must be 0 for these profiles.** llama-swap's TTL timer starts from container launch, not
from when the model becomes healthy. If startup (800 s) exceeds TTL (600 s), the model is
immediately unloaded the moment it becomes healthy. All three FP8-35B profiles set `ttl: 0`.

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
-v __LLMSTACK_DIR__/.vllm-cache:/root/.cache/vllm
-v __LLMSTACK_DIR__/.triton-cache:/root/.triton/cache
```

`__LLMSTACK_DIR__` is a placeholder. Run `scripts/configure` to replace it with the
repo's absolute path before first use (llama-swap v223+ executes cmd without a shell).

If you add a new vLLM profile and omit any of these, the first startup will take 18+ minutes
or fail with `unrecognized arguments`.

**Important**: llama-swap v223+ executes `cmd` without a shell — `$LLMSTACK_DIR` and other
shell variables are NOT expanded. Use hardcoded absolute paths in all volume mounts.

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

### FP8 kernel config — MoE experts are tuned, dense layers are not

At startup, vLLM will show two types of FP8 config messages:

**MoE expert layers (tuned — expected "Using configuration from"):**
```
Using configuration from /vllm-tuned-configs/E=64,N=512,device_name=AMD_Radeon_R9700,dtype=fp8_w8a8,block_shape=[128,128].json
```
This file lives in `vllm-tuned-configs/` and is mounted via `-v __LLMSTACK_DIR__/vllm-tuned-configs:/vllm-tuned-configs:ro`
with `-e VLLM_TUNED_CONFIG_FOLDER=/vllm-tuned-configs` set in the env.

**Dense attention/FFN layers (not yet tuned — expected warning):**
```
Using default W8A8 Block FP8 kernel config. Performance might be sub-optimal!
Config file not found at .../N=3072,K=2048,device_name=AMD_Radeon_R9700,dtype=fp8_w8a8,block_shape=[128,128].json
```
The `N=3072,K=2048` config (shared attention GEMM layers) has not been tuned for R9700.
This warning is expected and acceptable — it falls back to MI300X defaults.

If startup shows "Config file not found for device_name=AMD_Radeon_R9700" for the MoE config
(E=64,N=512), the VLLM_TUNED_CONFIG_FOLDER env var or the volume mount is broken.

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
| qwen3.6-35b-code (MTP, no tuned MoE config) | 43 | 261 | 481 |
| qwen3.6-35b-code (MTP, R9700 tuned MoE config) | 43 | 175 | — |
| qwen3.6-35b-awq | 92 | 250 | — |
| qwen3.6-35b-fp8 no-MTP | 69 | 222 | — |
| qwen3.6-27b-fp8 | 23 | 153 | — |
| qwen3-coder-30b-fp8 | 39 | 158 | — |
| gemma4-26b-a4b (vLLM BF16) | 53.4 | 287.1 | **528.2** |
| gemma4-26b-q8 (GGUF, llama-server) | 65.5 | 153.9 | 135.8 |
| gemma4-12b-q4 (GGUF, llama-server) | 36.1 | 108.9 | 94.8 |

**Note:** The R9700-tuned MoE configs (2026-06-18) show -33% regression at conc=8 vs
MI300X defaults (175 vs 261 tok/s), while serial throughput is unchanged (43 tok/s).
The tuning was done under isolated single-request load; the configs appear suboptimal
for concurrent inference (conc≥8) where multiple requests compete for GPU memory/cache.
Consider reverting `VLLM_TUNED_CONFIG_FOLDER` to use MI300X defaults for concurrent workloads.

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
