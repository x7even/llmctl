# ROCm 10.x canary plan (target: v0.5.0)

Status: revised 2026-10-16 after the user asked for a comprehensive current-state vs new-state benchmark
(speed and quality) **before** any cut-over. B0 is done and passed (section 3). The production pin stays
`docker.io/vllm/vllm-openai-rocm:v0.26.0` (Flash-Next: nightly `8cbd5d03006c33185f402249ff2b448efd594986`) until
the comparison in section 6 passes every gate and the user has read it. Nothing in `config/` changes before B3.

## 1. What "ROCm 10 support" means here

The host runs ROCm 7.2.0 (amdgpu 6.16.6, `rocm-smi` 4.0.0, `amd-smi` 26.2.1). Every model runs in a
container that carries its own ROCm userspace (the production vLLM images use ROCm 7.2.3), so the host
only supplies the kernel driver (amdgpu/KFD) and the monitoring tools. That splits the work:

| Track | What changes | Host risk | Needed for |
|-------|--------------|-----------|------------|
| A. Tooling | `rocm-smi` is deprecated; move the repo to `amd-smi` with `rocm-smi` as fallback | none | any host move |
| B. Runtime | a vLLM image with ROCm 10 userspace (B1), then (only if it helps) the host driver (B2) | B1 none, B2 high: one box, no spare | ROCm 10 itself |

## 2. Track A: tooling (no host change, ships on its own)

`rocm-smi` call sites to migrate (from `grep -rn rocm-smi`, 2026-10-16):

| File | Use | Notes |
|------|-----|-------|
| `bin/llmctl:502` | `llmctl status` GPU VRAM block | `--showmeminfo vram` |
| `tui/data.go:195-245` | llmpanel GPU panel, every 3 s | VRAM, utilisation, temperature; needs a Go port |
| `scripts/llmhw.py:80-100` | GPU count / VRAM fallback when sysfs has no VRAM info | sysfs stays primary |
| `scripts/configure:31,324` | error message only | wording |
| `bench/concurrent_bench.py`, `bench/opt_probe.py` | peak VRAM sampler | bytes today |
| `tests/smoke.sh:118-122` | VRAM snapshot | |
| docs | README, tui/README.md, tui/CLAUDE.md, docs/llmctl.md, docs/gpu-counts.md | wording |

`amd-smi metric --mem-usage --usage --temperature --json` returns everything these need in one call
(`gpu_data[].mem_usage.{total_vram,used_vram}`, `usage.gfx_activity`, `temperature.{edge,hotspot,mem}`). Sizes are
labelled `MB` but are MiB (32624 = 31.86 GiB), while `rocm-smi` prints bytes, so conversion happens once.
Cost is the same as today (~60 ms per call), so the TUI's 3 s poll is unaffected.

`scripts/gpustat.py` is the shared Python module (amd-smi first, rocm-smi fallback, empty list when neither exists;
`read_gpus()` returns `(gpus, tool)`). It is already used by `bench/canary_suite.py`. The Go TUI gets the same
contract in `tui/` with a parity fixture. Unit tests feed canned JSON and canned `rocm-smi` text through an
injectable runner (the pattern in `tests/test_llmhw.py`).

Exit criterion: `llmctl status`, `llmpanel`, `scripts/configure`, both bench samplers and `tests/smoke.sh`
work with only `amd-smi` present and with only `rocm-smi` present. Release as v0.4.7 if it lands before B2.

## 3. Track B: runtime

**B0. Re-verify the premise: DONE, passed (2026-10-16).** Docker Hub `vllm/vllm-openai-rocm` now publishes daily
`nightly-rocm100-<sha>` and `base-nightly-rocm100-<sha>` tags (first seen 2026-10-09) next to `nightly-<sha>`.
There are no rocm100 variants of v0.26.0, v0.30.0 or v0.31.0, so the candidate is a nightly. The pulled image
`nightly-rocm100-8cbd5d03006c33185f402249ff2b448efd594986` was inspected, and it carries ROCm 10 userspace:

| | production Flash-Next nightly | candidate |
|---|---|---|
| tag | `nightly-8cbd5d03…` | `nightly-rocm100-8cbd5d03…` |
| vLLM | `0.31.1rc1.dev173+g8cbd5d030.rocm723` | `0.31.1rc1.dev173+g8cbd5d030.rocm100` |
| ROCm userspace | 7.2.3 (`/opt/rocm-7.2.3`) | 10.0.0 (`rocm-sdk-*` 10.0.0 pip wheels, gfx1201 device package present) |
| torch | 2.13.0+git733fca1 (hip 7.2.53211) | 2.12.0+rocm10.0.0 |
| triton | 3.8.0+git669b31ac | 3.8.0+git669b31ac |
| amd-aiter | 0.1.24.post1 | 0.1.24.post1 |
| amdsmi (python) | 26.2.2 | 27.0.0 |
| size | 34.7 GB | 34.3 GB |

Same vLLM commit, so this is a clean pair for Flash-Next, with two caveats that every result must carry:

- It is ROCm **10.0.0**, not the 10.1.0 listed in the 2026-10-05 release notes (which list R9700/gfx1201, PyTorch
  2.14.0, vLLM 0.29.0, AMD SMI 27.1.0). If a 10.1 image appears later, the same matrix is re-run.
- The torch build differs too (2.12.0 vs 2.13.0+git; triton and aiter versions match). The
  comparison measures "the ROCm 10 image", not ROCm 10 in isolation. State S0c below separates the vLLM-commit
  effect from the rest for the 27B.

**B1. Container-only trial (zero host risk).** Run the candidate image on the unchanged 7.2 host driver through
the throwaway-router pattern (own port :8099, own container names such as `llmstack-vllm-<profile>-rocm100`,
shipped profiles untouched, see the `bench/CLAUDE.md` canary checklist). Flags identical to the production profile,
including `--cudagraph-capture-sizes`, `scripts/llm-prestart` for Flash-Next, and the same `--gpu-memory-utilization`.
Use **separate** vLLM and triton cache directories (under the job tmp dir) so the repo's `.vllm-cache/` is not
polluted and the true cold-start time is recorded. This answers "does ROCm 10 userspace run on the 7.2 driver"
and yields the full comparison numbers without touching the host.

**B2. Host driver move (only if B1 shows a gain worth the risk; user at the console).** The host is the only
machine, so before any change: record `dpkg -l | grep -E 'rocm|amdgpu|hsa'` and the kernel version into this
document, keep the old package repo pinned and cached, and confirm the previous driver can be reinstalled offline.
Install the new driver, reboot, run `llmctl hw`, then repeat the full suite on the candidate image (state S2) and
smoke the production images and the Vulkan path (`gemma4-26b-q8` on llama-server), because the amdgpu kernel driver
is shared by both. Rollback is reinstalling the recorded versions; if the GPUs do not enumerate, that is a console
job, so this is never done unattended.

**B3. Cut over: blocked on the comparison in section 6.** Change the pins in one PR (models.yaml,
`config/CLAUDE.md`, root `CLAUDE.md`, `scripts/`), keep `localhost/llmstack-vllm-rollback:v0.26.0` until the next
release, tag v0.5.0. Starts only after the user has read the S0 vs S1 (and S2, if B2 was done) comparison.

## 4. Why the order matters

Rollback is what a failed canary leans on, and v0.4.6 just repaired the rollback anchors. Track A removes the
last tooling dependency on a deprecated binary, so a host move cannot break `llmctl status` or `llmpanel`
mid-experiment. B1 before B2 means the expensive, one-way step is only taken with measurements in hand.

## 5. Known risks to test, not assume

- Userspace/driver skew in either direction: 10.0 userspace on the 7.2 driver in B1; 7.2.3 userspace on a ROCm 10
  driver after B2. Symptom to watch: HIP init errors, or silent slowdowns.
- Pinned-host-RAM behaviour for Flash-Next: PLE pinning goes through the HIP pinned-host allocator, so a
  runtime change can move the half-speed behaviour (`docs/flash-next-half-speed.md`). Re-run the serial
  speed check with a full page cache.
- Kernel-side counters that disappear: do not use `VmLck`/`Mlocked` to judge pinning.
- Cold-start and compile cache: `.vllm-cache/` and `.triton-cache/` are keyed on image and ROCm, so first boot
  recompiles; record the real cold start and a warm second start.
- A different torch/ROCm math stack under the same vLLM commit may pick different attention/GEMM backends: FP8 KV and long-context decode are where
  the Radiance trial regressed, so depth probes are mandatory.

## 6. The comparison that gates B3

### States

| State | vLLM image | Host driver | Models | Purpose |
|-------|-----------|-------------|--------|---------|
| **S0** | production: 27B `v0.26.0`, Flash-Next `nightly-8cbd5d03…` | ROCm 7.2.0 / amdgpu 6.16.6 | 27B, Flash-Next | the current state |
| **S0c** | `nightly-8cbd5d03…` (ROCm 7.2.3) | unchanged | 27B only | control: separates "newer vLLM commit" from "ROCm 10 image" for the 27B (Flash-Next's S0 already is this image) |
| **S1** | `nightly-rocm100-8cbd5d03…` | unchanged (7.2.0) | 27B, Flash-Next | the new state, container-only (B1) |
| **S2** | `nightly-rocm100-8cbd5d03…` | ROCm 10 host driver | 27B, Flash-Next | the new state fully (B2, only with the user) |

27B uses the shipped `qwen3.8-27b-code` flags (FP8, MTP, TP4, 131K, util 0.95); Flash-Next uses the shipped
`qwen3.8-flash-next-vllm` flags (TP4+EP, 262K, medium effort).

### What each state runs (`bench/canary_suite.py`, same frozen harness every time)

| Stage | What | Gate |
|-------|------|------|
| env | kernel, host ROCm/amdgpu, image, container ROCm/vLLM/torch, exact `vllm serve` command | recorded, not gated |
| speed | `concurrent_bench.py`: all four prompt sizes, `--no-thinking`, sweep 1,2,4,8,16, 32 requests per level | `medium-256` serial, conc=8 and conc=16 within -5% of S0 |
| depth | streamed decode tok/s and prefill tok/s at 1K, 8K, 32K, 64K, 128K, 200K prompt tokens, unique prompts so prefix caching cannot help | decode within -10% at every depth, no errors |
| tools | tool-call checks, streaming and non-streaming (8 cases each) | no fewer passes than S0, at least 14 of 16 |
| stress | 7 concurrent unique ~100K-token prompts at the profile's real utilisation; records preemptions and peak VRAM per GPU through `gpustat` | all 7 finish |
| quality | hard tasks (`regex_engine`, `mini_scheme`, `json_strict`, `date_math`, `cron_next`) x 8 samples, thinking at medium effort, cap 81,920; plus the six common tasks x 2 samples | no hard task more than 10 points below S0; early stops (empty/cut) not above S0 + 2 |

Flash-Next additionally needs gate 4: ~55 tok/s serial after a cold start with a warm page cache, and again after
`llm-prestart` with a full page cache (must not start at half speed). Cold-start time and a warm second start are
recorded for both models.

Noise floor: S0 vs a repeat of S0 sets the noise for speed (earlier controls agreed within 1.2%); quality noise is
~10 points at 8 samples. If an S0 cell and its S1 cell differ by less than that, it is reported as equal.

`bench/canary_compare.py OLD NEW [NEW...]` renders the tables and the per-gate verdict from the saved result
directories (first directory is the baseline). When a candidate fails a gate, rerun the failing cell on its own,
and run the image's own published recipe verbatim before ruling it out (config vs image fault).

### Results layout

`bench/results/canary-rocm10-20261016/<model>-<state>/` (`27b-s0`, `27b-s0c`, `27b-s1`, `27b-s2`, `fn-s0`,
`fn-s1`, `fn-s2`), one directory per run with `env.json`, `speed.json`, `depth.json`, `tools.json`, `stress.json`,
`quality-hard/`, `quality-common/` and the stage logs. The write-up goes in `docs/upgrade-plan-2026-10.md` once
the numbers exist.

### Time budget (GPU is exclusive, runs are sequential)

Roughly 3-4 h per state for the 27B and 4-5 h for Flash-Next (quality dominates: thinking up to 81,920 tokens per
sample). S0 + S0c + S1 for both models is about 10-12 h of wall clock, unattended; S2 repeats S1 after the driver
move. The orchestration is resumable (stages with existing output are skipped).

## 7. Decision points for the user

- After B0: continue only if an image exists. **Passed**, running S0/S0c/S1.
- After S0 vs S1: does the comparison pass every gate, and is the gain big enough to justify a host driver change
  on the only machine? If S1 shows no gain or a regression, the plan stops here and S2 is never run.
- B2 needs the user at the console in case the driver move needs recovery.
- B3 (the pin change and v0.5.0) happens only after the user has read the comparison.
