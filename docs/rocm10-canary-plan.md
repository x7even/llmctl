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

**B2. Host stack move (user at the console).** Scope changed after B1: see **section 9** for the full runbook.
B1 showed the ROCm 10 image is unusable on the 7.2 driver, and AMD's 10.1 matrix explains why — the pairing was
never a supported configuration. So B2 is no longer "only if B1 shows a gain": it is the first measurement of a
stack AMD actually validates, and B1's numbers are discarded rather than used as a gate.

The host is the only machine. Because the move stays on 24.04.5 and only adds the HWE 7.0 kernel, rollback is
selecting kernel 6.8 in GRUB plus reinstalling the cached `noble` 30.20 debs in
`/home/xin/rocm-rollback-20261016/` — no disk imaging and no filesystem snapshot. If the GPUs do not enumerate,
that is a console job, so this is never done unattended.

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
  on the only machine? **Superseded by section 8**: S1 failed, but on an unsupported driver pairing, so the
  result is void rather than a stop signal. The user's call (2026-10-16) was to move the host to the stack AMD
  validates for 10.1 and measure there.
- B2 needs the user at the console in case the driver move needs recovery.
- B3 (the pin change and v0.5.0) happens only after the user has read the comparison.

## 8. B1 result: the ROCm 10 image fails on the 7.2 driver (2026-10-16)

Both candidate states fail, and neither failure is attributable to our flags.

**27B does not boot at all.** Startup memory profiling reaches the Qwen3-VL vision encoder and dies in
`F.scaled_dot_product_attention`: `torch.AcceleratorError: CUDA error: invalid argument`
(`hipErrorInvalidValue`). Path: `gpu_worker.determine_available_memory` → `model_runner.profile_run` →
`encoder_runner.profile_encoder_cache` → `qwen3_vl._process_image_input` → `mm_encoder_attention._forward_sdpa`.
Reproducible; log in `bench/results/canary-rocm10-20261016/27b-s1/boot-fail.log`.

**Flash-Next boots and runs, but decode collapses.** `canary_compare.py fn-s0 fn-s1`:

| Measure | S0 | S1 | Δ | Gate |
|---|---|---|---|---|
| medium-256 serial | 58.0 | 49.4 | **−12.2%** | −5% |
| medium-256 conc=8 | — | — | **−12.1%** | −5% |
| medium-256 conc=16 | — | — | **−9.0%** | −5% |
| streamed decode, 1K–200K | ~57.8 | ~30.5 | **−46% to −47% at all six depths** | −10% |
| prefill, all depths | ~2.7K tok/s | ~2.7K tok/s | unchanged | — |
| tools | 16/16 | 16/16 | pass | ≥14/16 |
| stress | 7/7, 0 preempt | 7/7, 0 preempt | pass | 7/7 |
| peak VRAM | 29.9 GiB/GPU | 29.8 GiB/GPU | pass | — |
| quality `regex_engine` | 21% | 8% | −13 pts | 10 pts |

Other quality tasks moved within noise at 8 samples (cron_next 98→89, date_math 69→83, json_strict 89→80,
mini_scheme 42→61; early stops 3→5).

**Reading of it.** Prefill is unchanged while decode loses a flat ~47% at every depth. That is the signature of a
fixed per-token cost, not a math-kernel regression: Flash-Next decode is latency-bound small all-reduces across
TP4+EP over PCIe. The image delta that fits is **RCCL 2.27.7 → 2.30.4** (7.2.3 `/opt/rocm-7.2.3/librccl.so.1.0.70203`
vs the 10.0.0 `_rocm_sdk_*` wheels). Other deltas: HIP 7.2.53211 → 7.15.26333, torch 2.13.0+git → 2.12.0+rocm10.0.0,
amdsmi 26.2.2 → 27.0.0, amd_mori 0.0.0 → 1.2.3.post1; aiter and flash_attn identical.

**But the whole comparison is void as a verdict on ROCm 10**, because AMD's 10.1.0 matrix shows this pairing was
never supported: gfx1201 under ROCm 10.1 requires amdgpu **31.60.0 or 31.50.0**, and we ran ROCm 10.0 userspace on
amdgpu **30.20**. (30.20 is inside 10.0.0's wider 30.10–31.50 Radeon range, so driver skew alone does not explain
the slowdown — but it does mean the configuration is untested by AMD and not worth tuning.) The S1 numbers are
therefore recorded as evidence that the shortcut does not work, not as a measurement of ROCm 10. Tuning was
explicitly not attempted. The pin stays at `v0.26.0` / `nightly-8cbd5d03…`.

## 9. B2 runbook: stay on 24.04.5, add HWE 7.0 + amdgpu 31.60 + ROCm 10.1

### Corrected: no release upgrade. Why 24.04.5 + HWE 7.0, not 26.04.1

An earlier draft of this section recommended upgrading to Ubuntu 26.04.1. **That recommendation is withdrawn.**
It rested on one argument — "there is no `graphics/31.x` repo, so on 24.04 the GGUF/Vulkan path would be stranded
at AMD's 7.2 mesa overlay while ROCm moved to 10.1" — and that argument fails twice over:

1. **Host mesa is not on the serving path at all.** `containers/llama-vulkan-base/Containerfile` builds the
   llama-server runtime base `FROM ubuntu:26.04` precisely so it carries its own Mesa 26.0.x RADV, and both
   `containers/llama-server` and `containers/llama-server-qwen4exp` build `FROM
   localhost/llama-vulkan-bleeding:mesa26`. The GGUF backends therefore use the container's RADV, never the
   host's. Host mesa matters only for the desktop session. **Mesa is irrelevant to this decision in either
   direction** — including the counter-argument below, which is recorded only so the repo facts aren't lost.
2. **The repo exists anyway.** AMD numbers its graphics overlay on the ROCm release train, not the driver train,
   so it is **`graphics/26.16`**, which is why a search for `graphics/31.x` found nothing. Verified live
   2026-10-16: `repo.radeon.com/graphics/26.16/ubuntu` serves **noble and resolute** with
   `mesa-amdgpu-vulkan-drivers` **1:26.2.0.26160000** (mesa 26.2.0) — newer than the `mesa-vulkan-drivers`
   **26.0.8** Ubuntu 26.04 ships. Had host mesa mattered, staying on noble would have been the better side.

The real reasons to stay on 24.04.5 are rollback, blast radius and image match — see "Decisive advantages" below.

ROCm 10.1 itself is equally available on noble: `amdgpu-install` 31.60 configures
`repo.radeon.com/rocmradeon/apt/26.16 noble` (481 packages, all `amdrocm*` at **10.1.0-3**, including
`amdrocm10.1-gfx1201` and `amdrocm-rccl10.1-gfx1201`). That repo is never named in AMD's install prose — it was
established by extracting the `amdgpu-install` deb and reading the live index, so treat the mapping
"release 26.16 ⇒ ROCm 10.1.0-3" as an observed repository fact rather than an AMD statement.

24.04.5 + HWE 7.0 is a documented-supported row: AMD's 10.1.0 matrix for Radeon lists *only* HWE 7.0 for 24.04.5
(no GA 6.8 row for Radeon — the GA 6.8 row is Instinct-only), and `linux-generic-hwe-24.04` **7.0.0-38.38~24.04.4**
is in `noble-updates`, already confirmed available on this host.

Decisive advantages of staying:

- **Rollback becomes far cheaper.** The HWE metapackage does not remove the installed 6.8 images, so recovery
  starts from a GRUB entry rather than a disk image. No LVM snapshot, no `/boot` imaging, no
  restore-from-backup, and no `do-release-downgrade` (which does not exist). **But see "Rollback, precisely"
  below — picking 6.8 in GRUB is a complete rollback only before step 1, not after it.**
- **The cached rollback debs become valid again.** `/home/xin/rocm-rollback-20261016/` holds *noble* builds of
  amdgpu-dkms 30.20 — useless after a release upgrade, but exactly right if we stay on noble.
- **No podman 4.9.3 → 5.x migration** of the 95 GB rootless store, and no release-upgrade blast radius across
  podman, glibc, Python and the Go toolchain.
- **The official ROCm 10.1 vLLM image is built on 24.04**: `rocm/vllm:rocm10.1.0_ubuntu24.04_py3.14-pytorch_2.13.0_vllm-0.29.0`
  (31.3 GB, pushed 2026-10-05), matching the host.

26.04.1 keeps only its generic merits — support to 2031, newer podman/Python. Neither is needed here, so it is
deferred to a separate, deliberate move rather than bundled into a GPU-stack change.

### Use the official ROCm 10.1 image for S2, not the 10.0 nightly

B1 tested `nightly-rocm100-8cbd5d03…`, which is ROCm **10.0.0** with torch 2.12. AMD publishes an official ROCm
**10.1.0** vLLM image — `rocm/vllm:rocm10.1.0_ubuntu24.04_py3.14-pytorch_2.13.0_vllm-0.29.0` — carrying vLLM
0.29.0 and PyTorch 2.13.0, which is the vLLM version AMD's 10.1 matrix validates for gfx1201. S2 should run this
image. Caveats to carry: it is vLLM 0.29.0 against our 0.26.0 production pin (not the same-commit A/B that B1
had), and AMD's matrix lists PyTorch **2.14.0** as the validated version for Radeon while simultaneously saying
vLLM 0.29.0 "requires PyTorch 2.13.0" — a tension AMD does not reconcile.

**Image pulled and probed on CPU, 2026-10-16** (75.4 GB on disk). Contents differ from the tag in ways that
matter:

| | production `v0.26.0` | B1 `nightly-rocm100` | official 10.1 (S2 candidate) |
|---|---|---|---|
| ROCm | 7.2.3 | 10.0.0 | **10.1.0** (pip `rocm-sdk-*`, no `/opt/rocm/.info/version`) |
| torch | 2.13.0+git733fca1 | 2.12.0+rocm10.0.0 | 2.13.0+rocm10.1.0 |
| HIP | 7.2.53211 | 7.15.26333 | 7.16.26385 |
| **RCCL** | **2.27.7** | **2.30.4** | **2.30.7** |
| vLLM | 0.26.0 | 0.26.0 (`8cbd5d03`) | **0.29.1.dev0+g98dff2a81** (not 0.29.0) |
| transformers | — | — | **5.18.0** |
| aiter / amd_mori | present | present | **absent** |
| `rocm-sdk-device-gfx1201` | n/a | present | present |

Three things to carry into S2 planning:

1. **The RCCL hypothesis is testable but not escaped.** B1's flat −47% decode loss with unchanged prefill points
   at per-token collective cost, and the leading suspect was RCCL 2.27.7 → 2.30.4. The official 10.1 image is
   **2.30.7** — the same 2.30.x family. So if RCCL is the cause, S2 may well reproduce the loss even on the
   supported driver, and the supported-stack retest will not by itself exonerate or convict ROCm 10. Run the
   `depth` stage early in S2 and, if the loss reappears, try `NCCL_PROTO=LL128,Simple` and
   `NCCL_DEBUG=INFO` before concluding anything.
2. **`aiter` and `amd_mori` are gone**, and production carries both. Flash-Next is a 125B MoE whose kernels may
   route through aiter, so a throughput difference here has at least two candidate causes beyond ROCm itself.
3. **transformers 5.18.0.** Root `CLAUDE.md` records that a transformers-5.x image (5.7.0.dev0) raised
   `AttributeError: all_special_tokens_extended` on Qwen3 at startup and was abandoned. 5.18 is far later and
   vLLM 0.29 presumably tracks it, but the 27B is a Qwen3.8 model and this is exactly the failure class B1 hit
   on the other image — so boot the 27B before investing in any benchmark run.

The tag claims `vllm-0.29.0`; the installed version is a dev build `0.29.1.dev0+g98dff2a81.d20261002`. Quote the
installed version in results, not the tag.

Also relevant to B1's finding: the only RCCL known issue in 10.1.0 is scoped to Instinct MI350
(LL-protocol allreduce producing incorrect results), with workaround `export NCCL_PROTO=LL128,Simple`. It is not
a gfx1201 issue and must not be quoted as one, but given that B1's decode loss points at RCCL, it is a cheap
debugging lever if the slowdown reappears on the supported stack. No gfx1201-specific known issues are listed in
10.1.0 at all.

### Hazards specific to this host

1. **No iGPU.** All four VGA controllers are `1002:7551` (R9700) and `card0` drives the DisplayPort console, so
   the display depends on the same driver as compute. This is why the kernel goes in **before** the old driver
   comes out: on kernel 7.0 the in-tree amdgpu supports gfx1201 and keeps the console alive even with no DKMS
   module built. Never purge `amdgpu-dkms` while 6.8 is the only installed kernel — 6.8's in-tree amdgpu predates
   gfx1201. Have SSH available regardless.
2. **apt conffile collision on `/etc/apt/sources.list.d/rocm.list`.** The host has a hand-written `rocm.list`
   (`rocm/apt/7.2`) plus a `repo-radeon-pin-600` pin at exactly the paths `amdgpu-install` ships as its own
   conffiles. Installing the 31.60 deb over them triggers a conffile prompt and can leave duplicate/conflicting
   pins. Remove the old `rocm.list`, `amdgpu.list`, the `graphics/7.2` line and the old pin **before** installing.
3. **Third-party mesa sources are present** and will fight AMD's `graphics/26.16` overlay: an
   `oibaf-ubuntu-graphics-drivers-noble` PPA (bleeding-edge mesa) and `amdgpu-proprietary.list`. Disable the oibaf
   PPA before installing the graphics usecase, or RADV may resolve to PPA builds instead of AMD's.
4. **Rollback target must stay installed.** Do not `apt autoremove` the 6.8 images. See "Rollback, precisely".
5. **gfx1201 firmware comes only from `amdgpu-dkms-firmware`.** Checked on this host 2026-10-16: the 11
   `gc_12_0_1_*` blobs in `/lib/firmware/amdgpu/` are all owned by `amdgpu-dkms-firmware` 30.20, and noble's
   `linux-firmware` (20240318.git3b128b60.0ubuntu3.1, the only candidate) contains **zero** of them
   (`dpkg -L linux-firmware | grep -c gc_12_0_1` → 0). Firmware is kernel-independent: without those files even
   kernel 7.0's in-tree amdgpu cannot bring up an R9700. Step 1 purges that package, so **there must be no reboot
   between steps 1 and 2** — the firmware is only restored when `amdgpu-install` lands the 31.60
   `amdgpu-dkms-firmware`. If the sequence has to be abandoned between those steps, reinstall the cached
   `amdgpu-dkms-firmware` deb from `/home/xin/rocm-rollback-20261016/` *before* rebooting.
6. **Kernel 6.8.0-147 is a pre-existing landmine, unrelated to this plan.** `linux-image-generic` is at
   6.8.0-147.147 and `/boot/vmlinuz-6.8.0-147-generic` exists, but it has **no initrd** and **no DKMS amdgpu**
   (`dkms status` lists only -137 and -146; `/lib/modules/6.8.0-147-generic` has only the in-tree module, which
   predates gfx1201). The current `grub.cfg` predates it, so today's default is -146 — but any kernel package
   operation re-runs `update-grub`. Always pick **6.8.0-146** (or -137) by name when rolling back, never "the
   newest 6.8", and treat finishing or removing -147 as separate cleanup.
7. **Unchanged from the superseded plan:** the local-only container images are backed up (see pre-flight), and
   `podman system reset` must never be used — though with no release upgrade there is now no podman 5.x store
   migration at all.

### Pre-flight (done, no sudo needed)

- Local-only images saved to `/mnt/models/_host-backup-20261016/local-images.tar` (2.5 GB): `llmstack-llama:latest`,
  `llmstack-llama:b9542-baseline`, `llama-vulkan-bleeding:mesa26`, `llmstack-llama-qwen4exp:6fcaa16`. All four are
  also reproducible from `containers/*/Containerfile`.
- `localhost/llmstack-vllm-rollback:v0.26.0` needs no backup: it shares image ID `3d7fe5e20f0d` with
  `docker.io/vllm/vllm-openai-rocm:v0.26.0`, so it is a retag — re-create with `podman tag` after a re-pull.
- The docker.io vLLM images (~137 GB) are re-pullable, slowly.
- **Host state verified 2026-10-16, nothing yet changed:** Ubuntu 24.04.5, running 6.8.0-146, `amdgpu-dkms`
  1:6.16.6.30200000 + `amdgpu-dkms-firmware` 30.20 installed, `rocm-core` 7.2.0, `dpkg --audit` clean, no
  release upgrade started. The superseded 26.04 steps were never run.
- Still to do before step 0 (no sudo for the copy target, but the reads need it):
  `sudo cp -a /etc/apt/sources.list.d/{rocm.list,amdgpu.list,amdgpu-proprietary.list} /etc/apt/preferences.d/repo-radeon-pin-600 /mnt/models/_host-backup-20261016/apt/`
  — these are what a post-step-2 rollback restores.

### Steps

No release upgrade, no LVM snapshot. Kernel first, so the console never depends on a driver that is being removed.

**0. HWE 7.0 kernel, while the current 30.20 driver is still intact on 6.8.**

```bash
sudo apt update
sudo apt install --install-recommends linux-generic-hwe-24.04     # no -y: read what it proposes to remove
```

**Gate before rebooting.** The old amdgpu-dkms 30.20 will probably fail to build against kernel 7.0, and on noble
`/etc/kernel/postinst.d/dkms` can make the kernel package's own install fail when a module won't build, leaving
the initramfs or GRUB entry half-written. Do not reboot until all four pass:

```bash
echo "apt exit: $?"                     # must be 0
dpkg --audit                            # must print nothing
ls /boot/initrd.img-7.0*                # must exist
grep -c 'vmlinuz-7\.0' /boot/grub/grub.cfg   # must be > 0 (needs sudo to read)
```

If the initrd or GRUB entry is missing, repair before rebooting (`sudo update-initramfs -c -k <7.0 version>` then
`sudo update-grub`) — rebooting without them lands on a 6.8 kernel at best, or an unbootable entry at worst.

Then `sudo reboot`, choosing the 7.0 entry. After it: `uname -r` shows 7.0.x, and a missing DKMS build for 7.0 is
expected and harmless at this point — kernel 7.0's in-tree amdgpu supports gfx1201, and the 30.20 firmware is
still installed, so console and cards both work. Confirm with `ls /sys/class/drm/card*` (expect card0–card3) and
`ls /sys/module/amdgpu`. **This is the last point where rollback is a single GRUB pick**: boot 6.8.0-146 and
nothing has changed.

**1. Remove the ROCm 7.2 / amdgpu 30.20 userspace and its apt sources — then go straight to step 2.**

Required by AMD's own 10.1 instructions ("If you have ROCm 7.2.4 or older installed, please uninstall it before
proceeding"), and necessary to avoid the conffile/pin collision in hazard 2.

**No reboot between this step and step 2.** This removes both the 6.8 DKMS modules and the gfx1201 firmware
(hazard 5), so between here and a successful step 2 there is no kernel on the box that can drive these cards.

```bash
sudo apt autoremove -y rocm rocm-core amdgpu-dkms
sudo apt purge -y 'mesa-amdgpu*' 'libdrm-amdgpu*' 'libllvm*-amdgpu*' '*-amdgpu-mesa*' amdgpu-install
sudo rm -f /etc/apt/sources.list.d/rocm.list /etc/apt/sources.list.d/amdgpu.list \
           /etc/apt/sources.list.d/amdgpu-proprietary.list \
           /etc/apt/preferences.d/repo-radeon-pin-600
sudo mv /etc/apt/sources.list.d/oibaf-ubuntu-graphics-drivers-noble.sources ~/oibaf.sources.disabled
sudo apt update
dkms status                    # expect empty
```

**2. Install driver + ROCm 10.1 + graphics in one coherent step.**

This is AMD's documented path for Radeon (the `amdgpu-install` method row is marked "Radeon and Ryzen only").
The deb configures `amdgpu/31.60`, `rocmradeon/apt/26.16` and `graphics/26.16` together, which is what keeps the
driver, ROCm and RADV matched.

```bash
sudo apt install -y "linux-headers-$(uname -r)" "linux-modules-extra-$(uname -r)"
cd /tmp
wget https://repo.radeon.com/amdgpu-install/31.60/ubuntu/noble/amdgpu-install_31.60.316000-1_all.deb
sudo apt install ./amdgpu-install_31.60.316000-1_all.deb
sudo amdgpu-install --usecase=rocm,graphics --gfxversion=gfx1201
sudo reboot
```

`--gfxversion=gfx1201` is the deterministic form. `auto` also resolves correctly here (it dedupes by gfx target,
so four identical R9700s collapse to one `gfx1201`), but it hard-exits if discovery ever returns more than one
distinct target, so the explicit form is preferred.

**3. Verify the driver and userspace before anything else.**

```bash
uname -r                                       # 7.0.x
dkms status                                    # amdgpu/31.60 (1:7.1.9.31600000) built for 7.0
ls /sys/class/drm/card*                        # card0..card3
ls /lib/firmware/amdgpu/ | grep -c gc_12_0_1   # non-zero: 31.60 firmware landed
amd-smi version && amd-smi list                # 4 GPUs, gfx1201
rocminfo | grep -cE '^\s*Name:\s+gfx1201$'     # expect 4 (plain `grep -c gfx1201` counts ~2 lines per GPU)
groups                                         # render, video
dpkg -l mesa-amdgpu-vulkan-drivers             # desktop RADV only; the GGUF containers carry their own
```

`rocminfo` may not be on `PATH` in the 10.1 layout — try `/opt/rocm/bin/rocminfo`, or skip it, since
`amd-smi list` already proves enumeration.

### Rollback, precisely

- **Between step 0 and step 1:** pick **6.8.0-146** in GRUB (never "newest 6.8" — see hazard 6). Nothing else
  to undo.
- **After step 1, before step 2 succeeds:** do *not* reboot. Reinstall the cached debs from
  `/home/xin/rocm-rollback-20261016/` (`amdgpu-dkms`, `amdgpu-dkms-firmware`) *while still on 7.0*, confirm
  `dkms status` shows amdgpu 6.16.6 built for 6.8.0-146 and that `gc_12_0_1` firmware is back, and only then
  boot 6.8.0-146. `linux-headers-6.8.0-146` is installed, so the DKMS rebuild has what it needs.
- **After step 2:** same as above, plus restoring `rocm.list`, `amdgpu.list`, `amdgpu-proprietary.list` and
  `repo-radeon-pin-600`. Back them up in pre-flight so this is a copy, not a rewrite.

### Post-move validation, before any S2 benchmarking

The driver change cuts both ways: production `v0.26.0` carries ROCm **7.2.3** userspace and will now be running on
an amdgpu **31.60** driver — the inverse skew to the one B1 just failed on. A boot check is not enough.

- `podman images` intact (podman stays at 4.9.3, so no store migration — but check anyway); `podman tag` the
  rollback alias back if it was lost.
- `llmctl hw`, `llmctl up`, then boot production 27B `v0.26.0` and Flash-Next `nightly-8cbd5d03…`.
- GGUF/Vulkan backends: `llmctl swap gemma4-26b-q8`, then `llmctl swap qwen3.8-flash-next` (llama.cpp fork).
  These carry their own RADV in the container, so what is actually being tested is whether the **31.60 kernel
  driver + `/dev/dri` + render-group plumbing** still satisfies a container RADV built for gfx1201 — not host
  mesa. Expect `vulkaninfo --summary` inside the container to list 4 gfx1201 devices as before.
- `cd tui && go test ./...`. Python stays at 3.12.3 (no release upgrade), so the tooling should be untouched;
  still confirm `llmctl` and `bench/canary_router.py` import, since `amd-smi` moves 26.2.x → 27.x and
  `scripts/gpustat.py` parses its JSON.
- **Re-run the full S0 suite on the unchanged production images as state S0′**, then
  `canary_compare.py bench/results/canary-rocm10-20261016/{fn-s0,fn-s0prime}`. This is the "production still
  works" gate and the thing that must pass before the pin is allowed to move.

Only then run S2 — on `rocm/vllm:rocm10.1.0_ubuntu24.04_py3.14-pytorch_2.13.0_vllm-0.29.0` (see above), with
`nightly-rocm100-8cbd5d03…` as a secondary datapoint if the official image misbehaves.

**Confound to carry in the write-up:** S2 vs S1 mixes kernel, driver, mesa *and* (if S2 is the official image)
the vLLM version. The clean readings are **S0′ vs S0** — kernel/driver/mesa effect with the image held constant —
and **S2 vs S0′** — image effect on a supported host. Do not quote S2 vs S1 as "the ROCm 10 delta". If S2 uses
the official 10.1 image, its vLLM is 0.29.0 against our 0.26.0 pin, so a loss there is not attributable to ROCm
alone; the `nightly-rocm100` run (same vLLM commit as production Flash-Next) is the only same-vLLM comparison
available and is the one to use for attribution.
