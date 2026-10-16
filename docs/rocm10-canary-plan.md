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

The host is the only machine. The move goes to Ubuntu 26.04.1 (user's call, 2026-10-16), so rollback is an LVM
snapshot of the root LV plus images of `/boot` and `/boot/efi`, which live outside the LV. If the GPUs do not
enumerate, that is a console job, so this is never done unattended. Note that the host currently has four
unconfigured kernel packages that block `do-release-upgrade` outright — see the BLOCKER in section 9.

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

## 9. B2 runbook: Ubuntu 26.04.1 + kernel 7.0 GA + amdgpu 31.60 + ROCm 10.1

### Decision: 26.04.1, and the base is now also the safer one

The user's call (2026-10-16), on strategic grounds: ROCm 10.x is AMD's deliberate reset onto TheRock unified
build system, 24.04/noble will age out of AMD's support matrix while resolute is where the 31.x + ROCm 10.x
packaging is being maintained, and the stack is already at 0.4.5 on the 7.x landscape. Doing the move once, onto
the base AMD is building toward, beats doing it twice.

Two intermediate recommendations in this document were wrong and are both withdrawn:

1. The original case *for* 26.04 was "there is no `graphics/31.x` repo, so 24.04 would strand the Vulkan path on
   old mesa". False twice over: AMD's overlay is numbered on the ROCm train as `graphics/26.16` and serves noble
   as well as resolute with mesa 26.2.0; and host mesa is not on the serving path at all, because
   `containers/llama-vulkan-base/Containerfile` is `FROM ubuntu:26.04` so llama-server carries its own Mesa 26
   RADV. **Mesa is irrelevant to this decision in either direction.**
2. The case *against* 26.04 was that staying on noble made rollback a single GRUB pick. That is weaker than it
   looked (see "Rollback, precisely") and, more importantly, it is outweighed by the finding below.

**The finding that settles it.** Verified 2026-10-16 by probing the `ubuntu:26.04` archive directly:

| | Ubuntu 24.04.5 (noble) | Ubuntu 26.04.1 (resolute) |
|---|---|---|
| GA kernel (`linux-generic`) | 6.8.0 — **in-tree amdgpu predates gfx1201** | **7.0.0-38.38** — in-tree amdgpu supports gfx1201 |
| gfx1201 firmware in the distro | `linux-firmware-amd-graphics` present, but no GA kernel that can use it | `linux-firmware-amd-graphics` 20260319.git217ca6e4: **11** `gc_12_0_1_*`, 4 `psp_14_0_3`, `sdma_7_0_1`, `vcn_5_0_1`, 3 `smu_14` |

On 26.04 the distro alone — GA kernel plus distro firmware, with **zero AMD packages installed** — can light the
console and enumerate all four R9700s. Noble cannot, because its GA kernel is 6.8. That makes 26.04 the base with
a working floor to fall back to during the move, which is the opposite of what this document claimed yesterday.

ROCm 10.1 is available for resolute: `amdgpu-dkms 1:7.1.9.31600000-2407772.26.04` in
`repo.radeon.com/amdgpu/31.60/ubuntu/dists/resolute`, `amdrocm10.1-gfx1201 10.1.0-3` in
`stable.repo.amd.com/rocm/core/packages/ubuntu2604`, and `amdgpu-install` additionally configures
`repo.radeon.com/rocmradeon/apt/26.16` (481 packages, all `amdrocm*` at 10.1.0-3). That last mapping —
"release 26.16 ⇒ ROCm 10.1.0-3" — is an observed repository fact from extracting the `amdgpu-install` deb, not an
AMD statement.

### BLOCKER: the host has a broken dpkg state right now

**`do-release-upgrade` cannot run until this is cleared**, and it was not caused by anything in this plan.

On 2026-10-16 06:13–06:14 unattended-upgrades installed kernel **6.8.0-147**. `amdgpu-dkms 6.16.6` failed to
compile against its headers:

```
make[4]: *** [scripts/Makefile.build:243: /tmp/amd.0Uw3W211/amd/amdgpu/amdgpu_device.o] Error 1
dkms autoinstall on 6.8.0-147-generic/x86_64 failed for amdgpu(10)
run-parts: /etc/kernel/postinst.d/dkms exited with return code 11
dpkg: error processing package linux-image-6.8.0-147-generic (--configure): ... error exit status 11
```

The postinst aborted, so four packages are still unconfigured:

```
iF  linux-image-6.8.0-147-generic     6.8.0-147.147
iF  linux-headers-6.8.0-147-generic   6.8.0-147.147
iU  linux-headers-generic             6.8.0-147.147
iU  linux-generic                     6.8.0-147.147
```

Consequences:

- `/boot/vmlinuz-6.8.0-147-generic` exists with **no initrd** (the postinst never got that far), and
  `/lib/modules/6.8.0-147-generic` has only the in-tree amdgpu. The current `grub.cfg` predates it so today's
  default is 6.8.0-146, but any `update-grub` run can change that. Never roll back to "the newest 6.8" — name
  **6.8.0-146**.
- **This is empirical proof of the premise of the whole runbook:** `amdgpu-dkms 6.16.6` already cannot build
  against a kernel one point release newer than the running one. It will certainly not build against 7.0. Purging
  the AMD stack before the release upgrade is not a precaution, it is the prerequisite.
- Conveniently, the purge *is* the repair: with no amdgpu DKMS module to build, the 147 postinst succeeds and
  `dpkg --configure -a` clears all four packages.

*Correction to an earlier note in this document: a previous revision recorded `dpkg --audit` as clean. That
command needs root for the dpkg lock and had failed with "Permission denied"; its empty output was misread.*

### Hazards specific to this host

1. **No iGPU.** All four VGA controllers are `1002:7551` (R9700) and `card0` drives the DisplayPort console, so
   the display depends on the same driver as compute. The dangerous window is between the purge (step 2) and the
   first boot of kernel 7.0 (step 4): during it the box is on 6.8 with no gfx1201-capable driver at all. **Do not
   reboot between step 2 and step 3.** Have SSH available throughout.
2. **gfx1201 firmware is *not* at risk from the purge.** Corrected from an earlier revision of this document,
   which claimed all gfx1201 firmware came from `amdgpu-dkms-firmware`. In fact
   `dpkg -S /lib/firmware/amdgpu/gc_12_0_1_me.bin.zst` → **`linux-firmware-amd-graphics`**: the distro owns the
   `.bin.zst` blobs in `/lib/firmware/amdgpu/`, while AMD's package ships uncompressed `.bin` into
   `/lib/firmware/updates/amdgpu/`, which merely takes precedence. Removing AMD's package leaves the distro's
   firmware in place, and the two use different directories so there is no dpkg file conflict during the upgrade.
   The purge is safe with respect to firmware; it is the *kernel* that is the constraint (hazard 1).
3. **apt conffile collision on `/etc/apt/sources.list.d/rocm.list`.** The host has a hand-written `rocm.list`
   (`rocm/apt/7.2`) plus a `repo-radeon-pin-600` pin at exactly the paths `amdgpu-install` ships as its own
   conffiles. Remove the old `rocm.list`, `amdgpu.list`, the `graphics/7.2` line and the old pin before
   installing the 31.60 deb, or expect a conffile prompt and possibly duplicate pins.
4. **Third-party mesa sources will fight AMD's overlay**: an `oibaf-ubuntu-graphics-drivers-noble` PPA and
   `amdgpu-proprietary.list`. `do-release-upgrade` disables third-party sources itself, but disable the oibaf PPA
   explicitly beforehand so the result is deterministic, and do not re-enable it afterwards — a noble PPA has no
   resolute suite anyway.
5. **`/boot` and `/boot/efi` are outside the root LV** (`nvme2n1p2` and `nvme2n1p1`). A root-LV snapshot alone
   would roll back a 24.04 root underneath 26.04-era kernels, so image both partitions as well.
6. **podman 4.9.3 → 5.x migrates the 95 GB rootless image store.** This is expected and is the main reason to
   have the local-only images backed up. **Never run `podman system reset`.** The network backend is already
   netavark, so there is no CNI migration.
7. **Python moves 3.12 → 3.14** and the Go toolchain changes. `python3-yaml` is a distro package so apt carries
   it, but `llmctl`, `bench/*.py` and `scripts/gpustat.py` need an import check afterwards, and `tui/` needs a
   rebuild and `go test ./...`.

### Pre-flight

Already done (no sudo needed):

- Local-only images saved to `/mnt/models/_host-backup-20261016/local-images.tar` (2.5 GB):
  `llmstack-llama:latest`, `llmstack-llama:b9542-baseline`, `llama-vulkan-bleeding:mesa26`,
  `llmstack-llama-qwen4exp:6fcaa16`. All four are also reproducible from `containers/*/Containerfile`.
- `localhost/llmstack-vllm-rollback:v0.26.0` needs no backup: it shares image ID `3d7fe5e20f0d` with
  `docker.io/vllm/vllm-openai-rocm:v0.26.0`, so it is a retag — re-create with `podman tag` after a re-pull.
- The docker.io vLLM images (~137 GB) are re-pullable, slowly. The official ROCm 10.1 image is already pulled
  (75.4 GB on disk).
- Host state read 2026-10-16: Ubuntu 24.04.5, running 6.8.0-146, `rocm-core` 7.2.0, `amdgpu-dkms` 6.16.6 built
  for 6.8.0-137 and -146 only, four packages unconfigured (see BLOCKER). No release upgrade has been started and
  the superseded 24.04 and earlier 26.04 step lists were never run.

Still to do, with sudo, before step 1:

```bash
sudo mkdir -p /mnt/models/_host-backup-20261016/apt
sudo cp -a /etc/apt/sources.list.d/{rocm.list,amdgpu.list,amdgpu-proprietary.list} \
           /etc/apt/preferences.d/repo-radeon-pin-600 /mnt/models/_host-backup-20261016/apt/
sudo tar -C / -czf /mnt/models/_host-backup-20261016/etc.tar.gz etc
sudo dd if=/dev/nvme2n1p2 of=/mnt/models/_host-backup-20261016/boot.img    bs=4M status=progress
sudo dd if=/dev/nvme2n1p1 of=/mnt/models/_host-backup-20261016/bootefi.img bs=4M status=progress
sudo vgs                       # confirm VFree >= ~200G before step 1
```

### Steps

OS first, driver second — see "Why this order" below. Steps 2 and 3 are one sitting with no reboot between them.

**1. Snapshot the root LV.**

```bash
sudo lvcreate -s -n root-pre26 -L 200G /dev/ubuntu-vg/ubuntu-lv
```

`lsblk` implies roughly 800 GB unallocated (1.8 T partition, 1000 G LV), so 200 G of snapshot space is
available. Rollback is `sudo lvconvert --merge /dev/ubuntu-vg/root-pre26 && sudo reboot`, plus restoring
`boot.img`/`bootefi.img` from a live USB if the kernels no longer match the root.

**2. Purge the AMD 7.2 stack, clear the broken dpkg state, and do not reboot.**

```bash
sudo systemctl stop llama-swap 2>/dev/null; llmctl down          # free the GPUs first
sudo mv /etc/apt/sources.list.d/oibaf-ubuntu-graphics-drivers-noble.sources ~/oibaf.sources.disabled
sudo amdgpu-install --uninstall -y
sudo apt purge -y 'amdgpu*' 'rocm*' 'mesa-amdgpu*' 'libdrm-amdgpu*' 'libllvm*-amdgpu*' '*-amdgpu-mesa*'
sudo apt autoremove -y
sudo rm -f /etc/apt/sources.list.d/amdgpu*.list /etc/apt/sources.list.d/rocm*.list \
           /etc/apt/preferences.d/repo-radeon-pin-600
sudo dpkg --configure -a          # the 147 postinst now succeeds: no DKMS module to build
sudo apt --fix-broken install
```

Gate before continuing — all four must hold:

```bash
sudo dpkg --audit                                   # must print nothing (needs root!)
dpkg -l | awk '$1 !~ /^(ii|rc)$/ && NR>5'           # must print nothing
dkms status                                         # must be empty
ls /boot/initrd.img-6.8.0-147-generic               # should now exist
```

The console is still alive here because the running kernel 6.8.0-146 already has the driver loaded; a **reboot
now would land on a 6.8 kernel with no gfx1201 support and probably a dark console.** Keep going.

**3. Release upgrade, in the same sitting.**

```bash
sudo apt update && sudo apt full-upgrade -y
sudo do-release-upgrade
```

Keep local versions of config files we own when prompted. Accept the removal of the noble PPA and AMD sources.

**4. Reboot and verify the distro-only floor.**

```bash
uname -r                                       # 7.0.0-38-generic
lsb_release -ds                                # Ubuntu 26.04.1 LTS
ls /sys/class/drm/card*                        # card0..card3 on in-tree amdgpu
ls /lib/firmware/amdgpu/ | grep -c gc_12_0_1   # 11, from linux-firmware-amd-graphics
dkms status                                    # empty — no AMD packages at all yet
sudo dpkg --audit                              # nothing
```

This is the floor the 26.04 decision bought: graphics and all four cards working with no AMD packages installed.
If this step fails, roll back the snapshot — nothing AMD-specific has been introduced yet, so a failure here is
an Ubuntu problem, not a ROCm one.

**5. amdgpu 31.60 + ROCm 10.1 from the resolute repos.**

```bash
sudo apt install -y libatomic1 libquadmath0 "linux-headers-$(uname -r)" "linux-modules-extra-$(uname -r)"
cd /tmp
wget https://repo.radeon.com/amdgpu-install/31.60/ubuntu/resolute/amdgpu-install_31.60.316000-1_all.deb
sudo apt install ./amdgpu-install_31.60.316000-1_all.deb
sudo amdgpu-install --usecase=rocm,graphics --gfxversion=gfx1201
sudo reboot
```

`--gfxversion=gfx1201` is the deterministic form; `auto` also resolves correctly here (it dedupes by gfx target,
so four identical R9700s collapse to one entry) but hard-exits if discovery ever returns more than one target.

**6. Verify the full stack.**

```bash
uname -r                                       # 7.0.0-38-generic
dkms status                                    # amdgpu/31.60 (1:7.1.9.31600000) built for 7.0
amd-smi version && amd-smi list                # 4 GPUs, gfx1201
rocminfo | grep -cE '^\s*Name:\s+gfx1201$'     # expect 4 — plain `grep -c gfx1201` counts ~2 lines per GPU
groups                                         # render, video
```

`rocminfo` may not be on `PATH` in the 10.1 layout — try `/opt/rocm/bin/rocminfo`, or skip it, since
`amd-smi list` already proves enumeration.

### Why this order (OS first, then driver)

The user asked whether to update Linux first. Yes, and for three reasons:

1. **The driver has to match the final kernel.** Installing amdgpu 31.60 on noble first means installing a noble
   build, then having `do-release-upgrade` replace the kernel with 7.0 and disable the AMD repos, after which the
   resolute build has to be installed anyway. The driver work gets done twice and the DKMS-vs-new-kernel failure
   is walked into deliberately.
2. **That failure is not hypothetical.** The BLOCKER above is exactly it, at 6.8.0-147. A noble-first driver
   install would hit the same wall at kernel 7.0 during the upgrade, in the middle of the risky window.
3. **26.04 has a distro-only floor and noble does not.** After step 4 the box works with zero AMD packages, so
   ROCm can be installed calmly as a separate, reversible step. Driver-first has no such resting point.

The cost is that the OS and driver change together, so **S0′ vs S0 bundles OS, kernel, driver and mesa** and
cannot attribute between them. That is acceptable: the OS is a means to the supported driver, and neither
reading we actually need (production-still-works, and ROCm-10.1-vs-production) requires separating them.

### Rollback, precisely

- **Before step 2:** nothing to undo.
- **Between step 2 and step 4:** do not reboot. To abandon, reinstall the cached debs from
  `/home/xin/rocm-rollback-20261016/` (`amdgpu-dkms`, `amdgpu-dkms-firmware`; `linux-headers-6.8.0-146` is
  installed so DKMS has what it needs), confirm `dkms status` shows amdgpu built for 6.8.0-146, restore the apt
  sources from `/mnt/models/_host-backup-20261016/apt/`, and only then reboot — naming **6.8.0-146**, never the
  newest 6.8.
- **After step 3 (on 26.04):** `sudo lvconvert --merge /dev/ubuntu-vg/root-pre26 && sudo reboot`. The cached
  noble debs no longer apply on a 26.04 userspace, which is why the snapshot is the rollback mechanism once the
  release upgrade has run. Restore `boot.img`/`bootefi.img` from a live USB if the kernels and root disagree.

### Post-move validation, before any S2 benchmarking

The driver change cuts both ways: production `v0.26.0` carries ROCm **7.2.3** userspace and will now be running
on an amdgpu **31.60** driver — the inverse skew to the one B1 failed on. A boot check is not enough.

- `podman images` intact after the 5.x store migration; `podman tag` the rollback alias back if it was lost, and
  restore from `local-images.tar` if the local-only images did not survive.
- `llmctl hw`, `llmctl up`, then boot production 27B `v0.26.0` and Flash-Next `nightly-8cbd5d03…`.
- GGUF/Vulkan backends: `llmctl swap gemma4-26b-q8`, then `llmctl swap qwen3.8-flash-next` (llama.cpp fork).
  These carry their own RADV in the container, so what is being tested is whether the **31.60 kernel driver +
  `/dev/dri` + render-group plumbing** still satisfies a container RADV built for gfx1201 — not host mesa.
  Expect `vulkaninfo --summary` inside the container to list 4 gfx1201 devices as before.
- `cd tui && go test ./... && make build` on the new Go toolchain; confirm `llmctl`, `bench/canary_router.py` and
  `scripts/gpustat.py` still import and parse on Python 3.14 with amd-smi 27.x.
- **Re-run the full S0 suite on the unchanged production images as state S0′**, then
  `canary_compare.py bench/results/canary-rocm10-20261016/{fn-s0,fn-s0prime}`. This is the "production still
  works" gate and the thing that must pass before the pin is allowed to move.

Only then run S2 — on `rocm/vllm:rocm10.1.0_ubuntu24.04_py3.14-pytorch_2.13.0_vllm-0.29.0`, with
`nightly-rocm100-8cbd5d03…` as a secondary datapoint if the official image misbehaves. The official image being
`ubuntu24.04`-based is not a problem: the container ships its own ROCm userspace and only needs the host's kernel
driver and `/dev/kfd`.

**Confound to carry in the write-up:** the clean readings are **S0′ vs S0** (host effect: OS + kernel + driver,
image held constant) and **S2 vs S0′** (image effect on a supported host). Do not quote S2 vs S1 as "the ROCm 10
delta". If S2 uses the official 10.1 image its vLLM is 0.29.1.dev0 against our 0.26.0 pin, so a loss there is not
attributable to ROCm alone; the `nightly-rocm100` run (same vLLM commit as production Flash-Next) is the only
same-vLLM comparison available and is the one to use for attribution.
