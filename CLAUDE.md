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

**Historical figures (vLLM ≤0.25.x, per-shape Inductor compilation):** first boot on a
fresh machine took 18–20 minutes — ~14 min Inductor torch.compile (4 TP ranks in
parallel, cached after the first run in `.vllm-cache/`) plus ~14 min (~800 s) of model
profiling/warmup (FP8 KV calibration), uncached, every start. `healthCheckTimeout: 1200`
and `llmctl swap` timeout `1260` s were sized for this.

**vLLM 0.26.0 changed this dramatically.** It replaced per-shape Inductor compilation
with a single dynamic-shape "compile range" (log: `Compiling a graph for compile range
(1, 32768) takes ~20s`), and the FP8 KV-calibration/profiling step dropped from ~800s to
~20-40s. Measured cold-start totals on this hardware (warm `.vllm-cache/`, 2026-07-27):

| Profile | Profiling/warmup step | Total swap time |
|---------|----------------------|-----------------|
| `qwen3.6-35b-128k-nomtp` (FP8, no MTP) | 20.98 s | 2m04s |
| `qwen3.6-35b-128k` (FP8, MTP) | — | 2m41s |
| `gemma4-26b-a4b` (BF16) | — | 3m07s |
| `qwen3.6-35b-awq` (AWQ Int4) | 37.17 s | 3m21s |

First boot is now **~2-3 minutes**, not 18-20. `healthCheckTimeout`/swap timeouts are kept
at a generous 2100 s ceiling (see `config/models.yaml`) as headroom for profiles not
covered by this measurement (256K/512K YaRN-scaled contexts, dense 27B) — treat that
number as a safety margin, not the expected wait.

**TTL must be 0 for these profiles.** llama-swap's TTL timer starts from container launch, not
from when the model becomes healthy. Even at the new ~2-3 min startup, a TTL below that would
unload the model the moment it becomes healthy. All FP8-35B profiles set `ttl: 0`.

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

All vLLM profiles must use: `docker.io/vllm/vllm-openai-rocm:v0.26.0` (vLLM 0.26.0, ROCm 7.2.3). Pinned tag policy: never reference the moving `:latest` tag — bump the pin here, in config/models.yaml, config/CLAUDE.md, and scripts/ together after canary validation (see docs/upgrade-plan-2026-07.md; the 2026-10 v0.31.0 canary was held back for a conc=8/16 throughput regression — docs/upgrade-plan-2026-10.md)

### FP8 kernel config — MoE experts are tuned, dense layers are not

At startup, vLLM will show two types of FP8 config messages:

**MoE expert layers (tuned — expected "Using configuration from"):**
```
Using configuration from /vllm-tuned-configs/E=64,N=512,device_name=AMD_Radeon_R9700,dtype=fp8_w8a8,block_shape=[128,128].json
```
This file lives in `vllm-tuned-configs/` and is mounted via `-v __LLMSTACK_DIR__/vllm-tuned-configs:/vllm-tuned-configs:ro`
with `-e VLLM_TUNED_CONFIG_FOLDER=/vllm-tuned-configs` set in the env.

**Dense attention/FFN layers (not tuned — expected warning):**
```
Using default W8A8 Block FP8 kernel config. Performance might be sub-optimal!
Config file not found at .../N=4096,K=5120,device_name=AMD_Radeon_R9700,dtype=fp8_w8a8,block_shape=[128,128].json
```
The 5 dense GEMM shapes have not been tuned for R9700. This warning is expected and acceptable.
The MI300X defaults are intentionally kept: a synthetic Triton tile sweep was attempted
(scripts/tune-dense-fp8) and produced a -50% regression under real inference. Isolated
do_bench tuning finds tile configs that win on random tensors but underperform under full
model inference (memory pressure, interleaved ops, cache effects). Do not add R9700 dense
configs unless tuned under actual vLLM inference load.

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
| `qwen3.8-27b-code` ✓ | vLLM + MTP | ~31 GB + KV | 27B (dense) | **Default.** Thinking (medium effort); 131K ctx; 361 tok/s @ conc=8 |
| `qwen3.8-27b-think` | vLLM | ~31 GB + KV | 27B (dense) | Thinking, no MTP — parallel agent fleets |
| `qwen3.8-27b-fast` | vLLM + MTP | ~31 GB + KV | 27B (dense) | Thinking OFF by default |
| `qwen3.8-flash-next` | llama-server (Vulkan) | ~81 GB | 6B (MoE, 125B) | UD-IQ4_XS GGUF, custom llama.cpp fork; vLLM path under evaluation |
| `qwen3.6-35b-code` | vLLM + MTP | ~35 GB | 3B (MoE) | Previous gen, MTP + thinking |
| `qwen3.6-35b-128k-nomtp` | vLLM | ~35 GB | 3B (MoE) | Previous gen, thinking, no MTP |
| `qwen3.6-35b-fast` | vLLM | ~35 GB | 3B (MoE) | Previous gen, thinking OFF |
| `gemma4-26b-a4b` ✓ | vLLM BF16 | ~123 GB | 4B (MoE) | 528 tok/s @ conc=16; exclusive VRAM |
| `gemma4-26b-fp8` | vLLM FP8 | — | 4B (MoE) | Long-context Gemma 4 |
| `gemma4-26b-q8` ✓ | llama-server + mmproj | ~32 GB | 4B (MoE) | **Vision**; alias `gemma4` |
| `gemma4-12b-q4` ✓ | llama-server + mmproj | ~13 GB | 12B (dense) | Lightest vision; co-loadable |

Qwen3.8 is the norm; the three Qwen3.6-35B profiles are kept as an MTP / thinking / no-thinking
reference set. Older profiles (Qwen3.6-27B, Qwen3.6-35B AWQ/512K/GGUF variants, Qwen3-Coder-30B,
Qwen3.5-122B) were removed from `config/models.yaml`; restore from git history if needed.

Use aliases for common swaps: `llmctl swap qwen3.8` (→ 27b-code), `llmctl swap 27b-fast`, `llmctl swap 27b-think`,
`llmctl swap flash-next`, `llmctl swap gemma4` (→ 26B Q8 vision), `llmctl swap gemma4-vllm` (→ 26B vLLM).
✓ = on disk and benchmarked

---

## Benchmark baselines summary

`medium-256` prompt, decode tok/s, `--no-thinking`, 4× R9700, MTP where noted. Qwen3.8 row measured
on vLLM 0.26.0 (2026-10); older rows on vLLM 0.22.1.

| Profile | serial | conc=8 | conc=16 |
|---------|--------|--------|---------|
| qwen3.8-27b-code (MTP, 131K ctx) | 66 | 361 | 549 |
| qwen3.6-35b-code (MTP, MI300X defaults) | 43 | 261 | 481 |
| qwen3.6-35b-fp8 no-MTP | 69 | 222 | — |
| gemma4-26b-a4b (vLLM BF16) | 53.4 | 287.1 | **528.2** |
| gemma4-26b-q8 (GGUF, llama-server) | 65.5 | 153.9 | 135.8 |
| gemma4-12b-q4 (GGUF, llama-server) | 36.1 | 108.9 | 94.8 |

Baselines for removed profiles remain in `docs/models.md` and `bench/baselines/`.

**Note:** R9700-tuned MoE configs (-33% at conc=8) were reverted; all 35b profiles use MI300X
defaults, which outperform at concurrent load.

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
