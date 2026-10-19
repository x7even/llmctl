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
llmctl hw                        # detected GPUs/RAM + which profiles this hardware can run
llmctl list --all                # list shows only runnable profiles by default
llmctl logs qwen3.6-35b-code     # tail container log (essential for debugging startup)
llmctl unload                    # free VRAM, keep router running
llmctl down                      # stop everything
llmpanel                         # TUI: inference metrics, GPU, model list, config, logs
                                 #   Models panel hides profiles this hardware can't run; `a` shows them greyed
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

Every vLLM profile **must** have these five things:

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

```yaml
# 4. useModelName — a llama-swap key (NOT a vllm flag), set to this profile's
#    --served-model-name. Without it every alias of the profile 404s: llama-swap routes
#    by alias but forwards the client's model string upstream unchanged, and vLLM only
#    answers to --served-model-name. Measured 2026-10-17 — 3 of 4 routing names failed.
    useModelName: qwen3.8-27b-code
```

```yaml
# 5. GPU_MAX_HW_QUEUES=1 — a container env var. Without it a gfx1201 container can come
#    up in the slow decode band and serve at ~half speed for its whole life, with nothing
#    in the logs, gpu_busy pinned at 100% and MTP acceptance unchanged. Measured 2026-10-18
#    on the 27B at TP4: stock 5/5 slow at 35.6 serial / 320.9 conc=8; with the flag 3/3 fast at
#    67.2 / 357.6, within 4% of the stored baseline at every level. A fixed per-step tax, so it
#    amortises: 1.89x serial, 1.11x at conc=8. Now also measured on the 35B and gemma4 MoE
#    profiles (2026-10-19), which both wanted it: 2.11x / 2.27x serial, and gemma4 keeps 1.71x
#    at conc=8. Now set on every vLLM profile, Flash-Next included: a medium-256 pair there said
#    no, but long generations say 1.66x (4x8192-token streams, 104 -> 173 tok/s) for no
#    short-prompt cost. Details: config/CLAUDE.md item 5.
-e GPU_MAX_HW_QUEUES=1
```

`__LLMSTACK_DIR__` is a placeholder. Run `scripts/configure` to replace it with the
repo's absolute path before first use (llama-swap v223+ executes cmd without a shell).

If you add a new vLLM profile and omit any of items 1-3, the first startup will take 18+ minutes
or fail with `unrecognized arguments`. Omit item 4 and startup is fine but every alias is a 404
— the profile answers only to its full name. Omit item 5 and everything looks healthy while
throughput is halved; `scripts/llmband` is how you find out. Details for 5:
`docs/rdna4-decode-bands.md` and `config/CLAUDE.md`.

**Important**: llama-swap v223+ executes `cmd` without a shell — `$LLMSTACK_DIR` and other
shell variables are NOT expanded. Volume mounts therefore need an absolute path at run time,
which `scripts/configure` writes into the working copy. Do **not** hand-write one and do not
commit the configured file: the committed `config/models.yaml` carries `__LLMSTACK_DIR__`, and
`tests/test_configure.py` fails if a real `/home/...` path reaches HEAD. Committing the
configured form is what broke every fresh clone between `8f42c4e` and `89179ce` — the
substitution silently no-ops when there is no placeholder left to replace.

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

The locally-built image (`localhost/llmstack-vllm:latest`, deleted from the build host in the 2026-10 podman
cleanup; the rollback image is `localhost/llmstack-vllm-rollback:v0.26.0`) used vLLM 0.10.2rc2 with
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
- Never add any AI assistant trailers, co-authored-by lines, sign-offs, or session links
- Never use `--no-verify`
- Include benchmark data in commit messages when changing performance-relevant config

---

## Model profiles quick reference

| Profile | Backend | VRAM | Active params | Notes |
|---------|---------|------|--------------|-------|
| `qwen3.8-27b-code` ✓ | vLLM + MTP | ~31 GB + KV | 27B (dense) | **Default.** Thinking (medium effort); 131K ctx; 350 tok/s @ conc=8, 843 @ conc=32 |
| `qwen3.8-27b-think` ✓ | vLLM + TRITON_ATTN | ~31 GB + KV | 27B (dense) | Thinking, no MTP — parallel agent fleets. **The long-context profile:** 33 tok/s at 131K vs 1.4 without the backend flag |
| `qwen3.8-27b-fast` | vLLM + MTP | ~31 GB + KV | 27B (dense) | Thinking OFF by default |
| `qwen3.8-flash-next` | llama-server (Vulkan) | ~81 GB | 6B (MoE, 125B) | UD-IQ4_XS GGUF, custom llama.cpp fork; single-user |
| `qwen3.8-flash-next-vllm` | vLLM TP4+EP (nightly image) | ~19 GB/GPU + ~48 GB pinned PLE in host RAM (~96 GB host RAM recommended) | 6B (MoE, 125B) | W4A16 INT4 + FP8 PLE; 262K ctx, **medium effort by default** (xhigh runs away); 55.4 tok/s serial (clean-cell median; **intermittent single-stream latency tail, cause not established** -- see `docs/models.md`), 140-182 @ conc=8 (that cell is not reproducible to better than ~13%), 244 @ conc=16, 451 @ conc=32, flat ~55 out to 258K; needs `--ulimit memlock=-1:-1` and all 4 GPUs; exclusive VRAM |
| `qwen3.6-27b-code` ✓ | vLLM + MTP | ~31 GB + KV | 27B (dense) | Previous-gen dense 27B, restored 2026-10-19; 131K ctx; matches `qwen3.8-27b-code` at `medium-256`, 6-9% behind it at depth |
| `qwen3.6-35b-code` | vLLM + MTP | ~35 GB | 3B (MoE) | Previous gen, MTP + thinking |
| `qwen3.6-35b-128k-nomtp` ✓ | vLLM + TRITON_ATTN | ~35 GB | 3B (MoE) | **The deep-context profile.** 62 tok/s at 130K serial (vs 33 on `27b-think`), 440 at 16K×8, 231 at 64K×4; no short-prompt cost either (TRITON +3.9% at conc=8, matched n=128) |
| `qwen3.6-35b-fast` | vLLM | ~35 GB | 3B (MoE) | Previous gen, thinking OFF |
| `gemma4-26b-a4b` ✓ | vLLM BF16 | ~123 GB | 4B (MoE) | **the stack's throughput leader:** 891 tok/s @ conc=16, 1443 @ conc=32; exclusive VRAM |
| `gemma4-26b-fp8` | vLLM FP8 | — | 4B (MoE) | Long-context Gemma 4 |
| `gemma4-26b-q8` ✓ | llama-server + mmproj | ~32 GB | 4B (MoE) | **Vision**; alias `gemma4` |
| `gemma4-12b-q4` ✓ | llama-server + mmproj | ~13 GB | 12B (dense) | Lightest vision; co-loadable |

Qwen3.8 is the norm; the three Qwen3.6-35B profiles are kept as an MTP / thinking / no-thinking
reference set, and `qwen3.6-27b-code` as the previous-generation dense 27B. Older profiles
(Qwen3.6-35B AWQ/512K/GGUF variants, Qwen3.6-27B BF16/Q4_K_M, Qwen3-Coder-30B, Qwen3.5-122B)
were removed from `config/models.yaml`; restore from git history if needed.

Use aliases for common swaps: `llmctl swap qwen3.8` (→ 27b-code), `llmctl swap 27b-fast`, `llmctl swap 27b-think`,
`llmctl swap flash-next`, `llmctl swap flash-next-vllm`, `llmctl swap gemma4` (→ 26B Q8 vision), `llmctl swap gemma4-vllm` (→ 26B vLLM).
✓ = on disk and benchmarked

---

## Benchmark baselines summary

`medium-256` prompt, decode tok/s, `--no-thinking`, 4× R9700, MTP where noted. **Every row below
is one fresh spawn of the shipped profile, all seven re-measured on 2026-10-19 at `--requests 128`**
(`--serial-n 8` for the serial column) on the shipped image pins — so the columns are comparable
with each other, which the previous table's mix of 0.22.1 and 0.26.0 figures from four different
months was not. Each spawn's provenance was recorded before it was benchmarked: container argv,
`GPU_MAX_HW_QUEUES=1` presence, KV-pool size, the attention backend read out of the log, and
`scripts/llmband`. Two driver scripts produced it — `qwen3.6-35b-code` and `gemma4-26b-a4b` in
one, the other five in the other — same harness, same prompt, same day. One exception in the
serial column: `qwen3.8-flash-next-vllm` has an intermittent single-stream latency tail, so its
serial figure is the median of the clean one-stream cells (55.4, reproducing the 55.3 measured
independently on an earlier spawn) rather than the sweep's own 8-sample cell. **That tail is an
open issue, not a measurement artifact** — see `docs/models.md`.

| Profile | serial | conc=8 | conc=16 | conc=32 |
|---------|--------|--------|---------|---------|
| gemma4-26b-a4b (BF16, 4B active) | 129.2 | 539.9 | 890.8 | **1442.9** |
| qwen3.6-35b-128k-nomtp (TRITON_ATTN, no MTP) | 91.8 | 457.0 | 747.4 | 1198.9 |
| qwen3.6-35b-code (MTP, 3B active) | 109.7 | 302.0 | 584.8 | 1065.7 |
| qwen3.6-27b-code (MTP, 131K ctx) | 67.7 | 347.3 | 584.6 | 869.5 |
| qwen3.8-27b-code (MTP, 131K ctx) | 66.0 | 350.4 | 569.4 | 842.7 |
| qwen3.8-27b-think (TRITON_ATTN, no MTP) | 46.3 | 275.1 | 479.8 | 763.1 |
| qwen3.8-flash-next-vllm (no MTP, 262K ctx) | 55.4 | 154.4 | 244.5 | 451.0 |

Baselines: `bench/baselines/<profile>-<pin>-peak-nothink-matched-20261019.json` (`v0.26.0` on
every profile but Flash-Next, which is on the nightly pin). `llmband` returned **fast** for
`qwen3.6-27b-code`, `qwen3.8-27b-code` and `qwen3.8-flash-next-vllm`, and **undecided** for
`qwen3.8-27b-think` and `qwen3.6-35b-128k-nomtp` — it holds no baseline for those two, which is
what exit 2 means. Both nonetheless land within ~1% of a same-methodology reference
(`27b-think` reproduces the previous published row at all four levels; `nomtp` matches the
matched-pair TRITON arm's 91.5 serial / 463.9 conc=8), so neither is an anomalous draw. Four
things to read out of the table:

- **conc=32 is worth having.** Every profile is still gaining there, by 1.48x to 1.84x over
  conc=16. Nothing in this table has saturated.
- **Only two rows moved, and not because the measurement got better.** `gemma4-26b-a4b` gained
  2.30x serial and 1.53x at conc=32 against the previous table, and `qwen3.6-35b-code` 2.14x and
  1.12x, while the three carried-over dense rows moved 0.98-1.03x — i.e. not at all. Those two
  were last measured *before* `0c05be5` landed `GPU_MAX_HW_QUEUES=1` on them, so each correctly
  described the configuration shipped on the day it ran: superseded, not a bad draw. That is why
  the published numbers looked slow. Flash-Next is the fourth carried-over row and also MoE; its
  conc=16/32 cells reproduce to 0.5% and its conc=8 cell is unstable at ±13% (see its own note
  in `docs/models.md`), so do not read it as part of either group.
- **`qwen3.6-35b-128k-nomtp` enters this table for the first time, second-fastest at conc=32.**
  The deep-context profile is also one of the strongest short-prompt profiles here — the
  opposite of what this file claimed while the retracted 19% TRITON_ATTN cost stood.
- **The two dense 27B MTP profiles are indistinguishable on this prompt**, 0.9-3.2% apart on one
  run each, which is inside this harness's spawn-to-spawn spread — so choose between them on
  output quality, not on this table (at depth `qwen3.8-27b-code` is 6-9% ahead on the prewarmed
  rows). **`27b-think` pays 9-30% here** — 30% serial, 21% at conc=8, 9% at conc=32 — for the
  long-context behaviour it buys, the trade `docs/rdna4-long-context.md` describes.

`medium-256` is a 41-word prompt with a 256-token completion cap, and it measures
almost nothing about serving real work. For prefill and decode
together, at depth and with distributions rather than single figures, see
`docs/benchmark-results-full.md` (every measured cell) and `docs/models.md` (per-profile
history, including the earlier vintages these rows replace).

### Flash-Next and GPU-count facts (0.4.1)

- Hard code needs a generation cap of 64K-96K on Flash-Next (at 32K it truncates; at 81,920 nothing does),
  and a 200K cap buys nothing more. The 4-bit weights show no visible quality loss against the FP8 27B at
  equal room. The 27B sometimes ends a reply early (`<|im_end|>` mid-reasoning, empty content, `finish=stop`):
  clients should retry. Findings: `docs/hard-code-tasks.md`.
- vLLM `--max-model-len -1` (auto-fit) picks the native 262,144 on Flash-Next TP4 and the 27B at TP4 and TP2, so
  the 27B's shipped 131,072 is policy (decode slows with depth), not memory. Table in `docs/gpu-counts.md`.

- `qwen3.8-flash-next-vllm` defaults to `reasoning_effort=medium` (`--default-chat-template-kwargs`).
  The template's xhigh default runs away on this model (4/32 code-test passes vs 29-32/32 at medium across two runs of 8 samples x 4 tasks).
- 262K context costs nothing on Flash-Next: KV pool ~535K tokens at 131K, ~551K at 262K; decode
  stays ~55 tok/s from 1K to 258K. The dense 27B does not: 83 tok/s at 1K, 3.3 at 258K (v0.26).
- vLLM TP must be 1, 2 or 4 (head counts). TP3 fails for both Qwen3.8 models (27B: 16 linear-attention heads
  not divisible by 3; Flash-Next: vocab 248320 not divisible by 3). 27B TP2 works
  (serial 46.6, conc=8 219, conc=16 418 tok/s); 27B TP1 and Flash-Next TP2 OOM while loading weights.
  GGUF profiles split on any count. Details: `docs/gpu-counts.md`.
- Flash-Next pins ~48 GiB in host RAM. If the page cache is full of other models' weights at launch
  (MemFree below ~80 GiB) it comes up at half speed (~28 vs ~56 tok/s serial) and stays there. The
  profile's `cmd` therefore starts with `scripts/llm-prestart`, which drops cached model files first.
  Keep the wrapper in front of podman. Details: `docs/flash-next-half-speed.md`.

### Check the PCIe links before trusting any TP benchmark

**A GPU whose slot link trains one generation low is a real fault, but on this stack it did
NOT measurably cost throughput — do not reach for it as an explanation.** gfx1201 has no fast
all-reduce backend (QuickReduce is gfx94/gfx95 only, CustomAllreduce disables above two
PCIe-only GPUs, AITER unsupported), so vLLM TP falls back to `PYNCCL` over PCIe and every decode
step ends in an all-reduce. That sounds decisive and isn't: for a 27B dense model at TP4 the
per-step collective traffic is ~2 MB over one rank's link, i.e. ~35 us at Gen5 against ~76 us at
Gen4 — a 41 us difference against a ~25 ms step. **~600x too small to see.** Do the arithmetic
for your own model before blaming a link.

This stack has had one card's slot link sit at Gen4 (16 GT/s) at x16 while the other three
reached Gen5 (32 GT/s). It survived a cold power-off and a forced DPM level, so it is physical.
It was initially blamed for a ~2x decode-throughput loss measured around the same time, and that
was wrong — the arithmetic above is the reason, and a slow decode-band draw turned out to account
for the loss in full. Suggestive but not proof: the kernel log of the boot that produced the
fastest stored baseline shows that card already enumerating at 16.0 GT/s. Enumeration is the
BIOS-trained speed, logged before amdgpu loads and before the SMU retrains the link, so it does
not establish what the link did under load that day. Fix a downtrained link because it is a
fault, not because it will give throughput back.

What actually halves decode on this hardware is the gfx1201 bimodal decode band (next section).
The two are near-indistinguishable on every metric people reach for: ~2x step-rate loss,
`gpu_busy` pinned at 100%, low `mem_busy`, unchanged MTP acceptance, clean logs. **The one thing
that tells them apart is a host-to-device bandwidth probe** — `scripts/pcie-link-check` — because
only the link fault shows up in it.

Do not use "it came back slow after a restart" as the separator. It is tempting and it is wrong:
on this stack the slow state repeated across more than a dozen spawns and two reboots and the
link was still not the cause. A draw that persists tells you the cause is not per-process; it
does not tell you the cause is hardware.

**Every GPU-level PCIe readout is blind to this.** `roctop`, `amd-smi metric` (`PCIE: SPEED`)
and anything else reporting "the GPU's PCIe speed" read the *endpoint's* link. These cards carry
their own PCIe switch, so the endpoint's link is the on-card one — GPU to its own switch — and
that stays Gen5 even when the slot link below it is Gen4. During the incident above, all four
cards showed x16 32 GT/s in `roctop` while one card's slot link was at 16 GT/s, and the two
bridges upstream of that GPU were the only devices reporting it. Confirm with a host-to-device
bandwidth probe, which has to cross the slot link: the bad card read 26 GB/s against 56 GB/s on
the other three.

**And the naive sysfs check gives a false pass too.** These links idle at 2.5 GT/s, so reading
`current_link_speed` at rest reports 2.5 on a healthy card. Only the speed reached *under load*
means anything:

```bash
scripts/pcie-link-check --load     # needs the GPUs free; exit 0 ok / 1 downtrained / 2 inconclusive
scripts/pcie-link-check            # passive: sample while a model is actually serving
```

Run it before any TP benchmark you intend to trust, and first whenever throughput drops without
a config change. It reports per *link*, not per device — these cards carry their own PCIe
switch, so each GPU's chain is four devices but only two links, and link 0 is the one that
leaves the motherboard. A downtrain on link 0 is physical: cold power-off (PSU off ~30 s), then
reseat the card and riser, then swap slots to tell a bad card from a bad slot. A downtrain on a
later link is inside the card. Also check `max_link_speed` — if that is low too, something is
capping the slot in BIOS.

### The decode band is drawn at spawn — classify every cold start

On gfx1201 a vLLM server's decode throughput is **bimodal**. The process lands in one of two
stable bands when it spawns, stays there for most of its life, and serves every request at that
band's rate. Within-band variance is almost nil, and **nothing in the startup log distinguishes
them**: clocks, temperature, power, VRAM, graph-capture sizes and the log lines are identical.
Reported fast:slow ratios are 1.21-1.28 dense, 1.73 MoE, **2.00-2.2 gated-delta-net hybrid** —
and both Qwen3.8 profiles are GDN hybrids (the 27B is 16 full-attention + 48 GDN layers), so
they sit on the worst row. Upstream: `ROCm/legacy-rocm-build#6347` (= `ROCm/TheRock#9228`).

**The remedy is `-e GPU_MAX_HW_QUEUES=1` in the container, and on this hardware it is
complete.** Measured 2026-10-18 on the 27B at TP4, same image and profile either side, varying
only that variable: stock drew slow 5/5 at 35.6 tok/s serial, 320.9 at conc=8, 460.5 at conc=16;
with the flag it drew fast 3/3 at 67.2 / 357.6 / 536.8 — within 4% of the stored baseline at
every level, for no measurable cost. The penalty is a fixed per-step tax and so **amortises with
batch size**: 1.89x on a single stream, 1.76x at conc=2, 1.11x at conc=8. Quote the level you
mean; "1.9x" is the single-stream figure, not the fleet figure. The three `qwen3.8-27b-*` profiles ship with it (mandatory item 5 above).

**Flash-Next looked like the exception and is not — the `medium-256` pair that cleared it was
measuring the wrong workload.** That 2026-10-18 pair read serial 55.6 stock vs 53.5 flagged,
conc=8 187.4 vs 197.2, `mem_busy` ~31% on *both* arms where the 27B's bands separate at
26%/46% with no overlap, and the flag was left off. On **long generations** the same matched
design says the opposite: 4 streams x 8,192-token generations go **104.0/104.3 -> 173.0/171.3
tok/s (1.66x)**, each arm run twice, reproducing within 0.3%. Stock scales 1.82x from one
stream to four where flagged scales 3.07x — the per-step tax is invisible at conc=1 and has
eaten the concurrency scaling by conc=4. Short prompts cost nothing (serial -0.7%, conc=16
-0.6%, conc=8 204.3 = its best ever) and the KV pool is unchanged, so **it ships on
Flash-Next as of 2026-10-19**. `mem_busy` was not sampled in the long-generation arms, so
whether this is the same band is unestablished; the flag is worth 1.66x on this profile's
real workload either way. **Lesson: a `medium-256` pair is not enough to clear this flag off
a profile** — price it on the workload the profile exists for.

**The 35B and gemma4 MoE profiles were measured on 2026-10-19 and both wanted the flag**:
`qwen3.6-35b-code` 46.8 → 98.9 serial (2.11x), `gemma4-26b-a4b` 56.4 → 128.2 (2.27x),
`qwen3.6-35b-128k-nomtp` 30.7 → 87.7 (2.86x). **Gemma 4 breaks the amortisation rule** — it
keeps **1.71x at conc=8** (305.1 → 522.1), where the 35B-code curve is flat by then (1.00x).
So "the band only costs you on one stream" is a property of particular models, not of the band;
on gemma4 a slow draw costs fleet throughput outright. The flag now ships on every vLLM
profile. Two rows of the baseline table above — `gemma4-26b-a4b` and
`qwen3.6-35b-code` — were measured *before* the flag reached their profiles, so they were
superseded readings of a configuration the stack no longer ships rather than slow draws on the
shipped one. See `config/CLAUDE.md` for the dating and `bench/band_audit.py` for the check.

Two local corrections to the upstream framing. **Here the draw is deterministic, not a
lottery** — stock was slow on every one of five spawns across two launchers, three launch
contexts, two reboots and a cold power-off, which makes the flag a reliable fix rather than a
way of improving odds, and makes a slow draw *after* the flag genuinely anomalous. And
**`mem_busy` under load is the discriminator that held** (26% slow against 46% fast, no
overlap) where step rate alone did not; a low `mem_busy` still must not be read as "band" on its
own, since a PCIe fault produces one too.

So a benchmark that does not state which band it was drawn in is not a measurement. Classify
after every cold start:

```bash
scripts/llmband --model <profile> --calibrate   # once, against a server believed to be fast
scripts/llmband --model <profile>               # thereafter; exit 0 fast / 1 slow / 2 undecided
```

The signal is **decode step rate**, not token rate: with MTP one SSE chunk is one decode step
carrying however many tokens that step accepted, so token rate moves with acceptance while step
rate does not. Baselines live in `config/band-baselines.json`.

Things that are NOT the band, each ruled out by measurement here: clocks (full boost, 3382-3455
MHz, while in the slow band), power (the GPUs were not power-limited in either band), the PCIe
slot link (see the arithmetic above), page cache at load, MTP acceptance (not a discriminator —
the slow band read both the higher and the lower of the two observed values), CUDA-graph capture
sizes, and the card in any particular slot. Full write-up and the
ruled-out list: `docs/rdna4-decode-bands.md`. Also ruled out, by direct test: the launch
context (a stock spawn forked by the user systemd manager at nice 0, fresh cgroup, full CPU
affinity, verified on every thread, was still slow) and the compile cache (fast and slow spawns
load byte-identical AOT entries — `GPU_MAX_HW_QUEUES` is not part of the compile key, so the two
bands run the *same generated kernels*).

`llmband` warms up before it measures, because a server's first decode after startup runs ~12%
below steady state — the same order as the detector's own tolerance, so an unwarmed probe of a
healthy cold spawn read `undecided`. That 12% was never a cost of the flag; end-to-end
throughput is at baseline at all six concurrency levels. Use `--warmup-tokens 0` only to study
the warmup effect itself.
### Long context: the default attention backend collapses, TRITON_ATTN does not

On gfx1201 a Qwen3.x profile's decode rate can fall away to nothing as the prompt gets
deeper — 40 tok/s at 1K down to **1.4 tok/s at 131K** on the no-MTP 27B, a **28x** decay
across the window. `--attention-backend TRITON_ATTN` turns that into a 1.39x decay (46.3 ->
33.4), i.e. **24x faster at 131K**, and it wins every depth x concurrency cell measured
(65,536 x conc=8: 24.5 -> 143.4 tok/s). Shipped on `qwen3.8-27b-think`.

**Also shipped on `qwen3.6-35b-128k-nomtp` as of 2026-10-19, where it is a bigger win and the
stack's new long-context record.** Fast band both arms, single variable, aggregate tok/s:
2,048x1 59.2 -> 97.1; 16,384x1 18.4 -> 91.5; 16,384x8 prewarmed 131.9 -> **439.8**; 65,536x4
prewarmed 20.7 -> **231.1**; 129,984x1 2.2 -> **62.4 (28x)**. Decay across the window falls
26.9x -> 1.56x, prefill improves too (TTFT at 65,536x4: 55.2s -> 23.8s), and 62.4 tok/s on a
130K prompt beats `qwen3.8-27b-think`'s 33.4 — 3B active params against 27B dense. Retrieval
gated: `needle_check` 3 depths x 5 positions, 15/15.

**"It also costs 19% at `medium-256` conc=8" is WITHDRAWN — it does not.** That claim
compared one `concurrent_bench` run per arm at `--requests 32`, and the request count alone
moves a conc=8 reading by +4% to +32% here (`bench/CLAUDE.md`). Re-measured as a matched pair
— fresh spawn per arm, 3 reps each, `--requests 128`, `--serial-n 8`, TRITON the single
variable — **TRITON is faster at every level**: serial 91.5 vs 88.1, conc=8 463.9 vs 446.7,
conc=32 1208.6 vs 1180.2 (+3.9/+3.9/+2.4%), spreads non-overlapping, same-server noise 0.6% at
conc=8. KV pool parity verified too (1,538,425 vs 1,538,939). So this profile's backend is not
a trade against short prompts. Two things still stand: **gate 4 is a source-code fact** (the
3D predicate is per *batch*, so a co-batched prefill chunk drops deep decoders to the 2D
grid), and **the depth figures above are a no-arrival best case** — `depth_bench` launched
exactly `conc` streams once, `depth_bench.py --requests N` measures churn, and depth under
churn is still unmeasured, so do not quote 11x or 28x as fleet numbers. One thing reverses:
with no TRITON cost at short prompts, `bfe8115`'s cost for `27b-think` points back at losing
MTP.

The cause is parallelism starvation: no kernel on this GPU parallelises over context length
unless TRITON_ATTN's 3D split-KV path is open. Four gates decide it, all keyed on `query_len`:

1. ROCm's custom paged-attention kernel needs `head_size == 128`. **Every Qwen3.x checkpoint
   here is `head_dim = 256`**, so it is permanently disqualified — a shape mismatch, not a
   tuning problem.
2. The 2D fallback launches `(num_seqs, num_kv_heads)`. At TP4 with 2-4 KV heads that is
   **one workgroup** at conc=1, however long the context is.
3. TRITON_ATTN's 3D path adds a segment dimension and is the only depth-scaling kernel — but
   its predicate excludes `max_query_len > 1`, so **MTP closes it**.
4. The predicate is evaluated per *batch*. A step carrying a prefill chunk drops every
   co-batched deep decoder to the 2D grid. This one cannot be configured away.

Operational consequences:

- **`--max-num-seqs` above 32 silently closes the 3D path.** The threshold snaps to the
  nearest CUDA-graph capture size, which is 32 today. Changing `--max-num-seqs` or the
  capture-size list can undo the whole fix with nothing in the log.
- **`VLLM_ATTENTION_BACKEND` does not exist in 0.26.0.** Use the CLI `--attention-backend`.
  **A bad name fails loudly, it does not fall back** — an earlier version of this file said it
  silently reverted to auto-selection, which is not true of this image. Read in the image:
  `arg_utils.py:2257` routes the flag through `AttentionConfig.validate_backend_before`, which
  is `AttentionBackendEnum[value.upper()]`, so a typo raises `KeyError` before the server
  starts; and `rocm.py`'s `get_attn_backend_cls` raises
  `Selected backend ... is not valid for this configuration` for a name that is spelled right
  but incompatible with the model's shapes. `auto` is the one string that means auto-selection
  (the validator maps it to `None`).
- **Two different questions, two different checks.** What was *passed* is on the container's
  argv: `podman inspect <container> --format '{{json .Args}}' | grep -c attention-backend`.
  What is *running* is in the log — `Using <BACKEND> backend` means that backend is active,
  `Found incompatible backend(s) [...] Overriding with ROCM_ATTN out of potential backends:
  [...]` means auto-selection rejected something and chose for you. Check argv when you want to
  know whether the profile shipped the flag; check the log when you want to know what the
  engine runs. **The `(selected via --attention-backend)` parenthetical misreports the source:**
  `rocm.py` prints that string whenever *anything* set a backend, including vLLM itself.
- **`gemma4-26b-a4b` runs TRITON_ATTN without any flag, and that is correct behaviour.**
  `model_executor/models/config.py:239` forces it for Gemma 4, because the model has
  heterogeneous head dimensions (per-layer `head_dim` differing from the global one) and the
  FA4 path that would otherwise handle it is unavailable here — so it logs
  `Gemma4 model has heterogeneous head dimensions ... forcing TRITON_ATTN backend` and then the
  misleading "selected via" line. Verified on two spawns whose argv contained no such flag.
  Consequence worth knowing: gemma4 is already on the only depth-scaling kernel on this
  hardware, so unlike the Qwen3.x profiles there is no backend change left to make there.
- **Do not flip `qwen3.8-27b-code`.** On the `medium-256` sweep the MTP profile wins at every
  concurrency, by a margin that shrinks as the batch widens: 43% serial, 27% at conc=8, 19% at
  16, 10% at 32 (66.0/350.4/569.4/842.7 against 46.3/275.1/479.8/763.1, measured as a same-day
  matched pair on 2026-10-19 at `--requests 128`). Read that as the gap between the two shipped
  *configurations*, not as MTP's own margin: `27b-think` drops MTP **and** carries TRITON_ATTN,
  so the pair differs in two variables and this sweep cannot apportion the gap between them.
  Either way the default keeps MTP and long-context work goes to `27b-think` explicitly.
  The 35B pair splits on MTP alone: `qwen3.6-35b-code` keeps MTP (and so gets ROCM_ATTN by
  auto-selection, since MTP gates the 3D path shut), `qwen3.6-35b-128k-nomtp` drops MTP and
  carries TRITON_ATTN. **Route that pair by depth only** — TRITON_ATTN itself costs nothing at
  `medium-256`, so arrival rate is not the axis an earlier version of this file claimed it was.
- **Benchmark depth, and check retrieval.** `bench/depth_bench.py` sweeps depth x concurrency
  (`--prewarm` for steady-state decode); `concurrent_bench.py` at `medium-256` cannot see any
  of this. A split-KV kernel that mis-combines its softmax segments benchmarks perfectly while
  losing context, so any attention or kernel change must also pass `bench/needle_check.py`.

Full write-up, with source lines and the prefill-kernel caveat: `docs/rdna4-long-context.md`.

**Note:** R9700-tuned MoE configs (-33% at conc=8) were reverted; all 35b profiles use MI300X
defaults, which outperform at concurrent load.

Full data across all prompt sizes: `bench/CLAUDE.md` and `bench/baselines/`.

---

## File map

```
bin/llmctl           Python CLI — lifecycle, model switching, log tailing
bin/llmproxy         Python SSE shim — fixes vLLM null tool-call names for @ai-sdk
bin/llmpanel         TUI binary built by `cd tui && make build` (gitignored, never commit)
config/models.yaml   Single source of truth for all model profiles
config/templates/    Custom Jinja chat templates
tui/                 Go source for llmpanel (Bubbletea)
bench/               Benchmark scripts + saved baselines
tests/smoke.sh       Integration smoke test (both backends)
scripts/configure    GPU-count auto-detector; patches models.yaml
docs/benchmarks.md   The benchmark campaign behind the README table: caveats, depth x concurrency,
                     prefill, reproduction commands, how to read a live llmpanel peak
docs/models.md       Full benchmark data + per-profile architecture notes
docs/benchmark-results-full.md  Every measured cell (prefill+decode+concurrency) with steady-state distributions; generated, do not hand-edit
docs/gpu-counts.md   Running with fewer than 4 GPUs (valid TP sizes, per-profile limits, auto-fit)
docs/llmctl.md       Full CLI reference
docs/workarounds.md  Active bugs + workarounds (vLLM SSE null name)
docs/flash-next-half-speed.md  Half-speed Flash-Next starts: cause (full page cache) and the llm-prestart guard
docs/rdna4-decode-bands.md     gfx1201 bimodal decode bands: detection with llmband, ratios, ruled-out list
docs/rdna4-long-context.md     Why decode collapses at depth on gfx1201 and the TRITON_ATTN fix (four query_len gates)
docs/hard-code-tasks.md        Harder code tests: caps vs 4-bit weights, 27B early stops, ceiling check
docs/upgrade-plan-2026-*.md    Image/ROCm upgrade canaries and their gates
scripts/llm-prestart  exec wrapper in front of Flash-Next's podman run (drops page cache first)
scripts/pcie-link-check  Checks every GPU's PCIe link reaches its rated speed UNDER LOAD
scripts/llmhw.py     Hardware/requirements checker used by configure, llmctl and llmpanel
bench/codetests/     Code-correctness suite (11 tasks, 5 of them the harder set) run by run_codetests.py
bench/depth_bench.py Context-depth x concurrency sweep (--prewarm for steady-state decode)
bench/report_full_table.py  Regenerates docs/benchmark-results-full.{md,csv} from bench/baselines/
bench/needle_check.py Long-context retrieval, sweeping needle position — the correctness gate for kernel changes
.vllm-cache/         Persistent Inductor compilation cache (gitignored)
.triton-cache/       Persistent Triton kernel cache (gitignored)
```
