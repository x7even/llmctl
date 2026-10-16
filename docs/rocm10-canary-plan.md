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

An earlier draft of this section recommended upgrading to Ubuntu 26.04.1. **That recommendation was based on a
false premise and is withdrawn.** The premise was "there is no `graphics/31.x` repo, so on 24.04 the Vulkan stack
would be stranded at AMD's 7.2 mesa overlay while ROCm moved to 10.1". AMD's graphics repo for the 31.60 era is
not numbered `31.x` — it is numbered on the ROCm release train as **`graphics/26.16`**, which is why a search for
`graphics/31.x` found nothing. Verified live 2026-10-16:

| Repo | Serves | mesa version |
|---|---|---|
| `repo.radeon.com/graphics/26.16/ubuntu` (noble **and** resolute) | AMD graphics/RADV overlay for 31.60 | `mesa-amdgpu-vulkan-drivers` **1:26.2.0.26160000** |
| Ubuntu 26.04 distro | distro RADV | `mesa-vulkan-drivers` **26.0.8** |

So the argument inverts: staying on 24.04 with `graphics/26.16` gives the GGUF/llama-server Vulkan path mesa
**26.2.0** — *newer* than what Ubuntu 26.04 ships, and matched by AMD to this driver. There is no Vulkan skew to
escape, and the release upgrade buys nothing for this task.

ROCm 10.1 itself is equally available on noble: `amdgpu-install` 31.60 configures
`repo.radeon.com/rocmradeon/apt/26.16 noble` (481 packages, all `amdrocm*` at **10.1.0-3**, including
`amdrocm10.1-gfx1201` and `amdrocm-rccl10.1-gfx1201`). That repo is never named in AMD's install prose — it was
established by extracting the `amdgpu-install` deb and reading the live index, so treat the mapping
"release 26.16 ⇒ ROCm 10.1.0-3" as an observed repository fact rather than an AMD statement.

24.04.5 + HWE 7.0 is a documented-supported row: AMD's 10.1.0 matrix for Radeon lists *only* HWE 7.0 for 24.04.5
(no GA 6.8 row for Radeon — the GA 6.8 row is Instinct-only), and `linux-generic-hwe-24.04` **7.0.0-38.38~24.04.4**
is in `noble-updates`, already confirmed available on this host.

Decisive advantages of staying:

- **Rollback becomes trivial.** The HWE metapackage does not remove the installed 6.8 images (6.8.0-137 and
  6.8.0-146 are both present), so recovery is selecting kernel 6.8 in GRUB. No LVM snapshot, no `/boot` imaging,
  no restore-from-backup, and no `do-release-downgrade` (which does not exist).
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
4. **Rollback target must stay installed.** Recovery is GRUB → kernel 6.8 with amdgpu-dkms 30.20 rebuilt from
   `/home/xin/rocm-rollback-20261016/` (noble debs, valid because we are not changing release). Do not
   `apt autoremove` the 6.8 images.
5. **Unchanged from the superseded plan:** the local-only container images are backed up (see pre-flight), and
   `podman system reset` must never be used — though with no release upgrade there is now no podman 5.x store
   migration at all.

### Pre-flight (done, no sudo needed)

- Local-only images saved to `/mnt/models/_host-backup-20261016/local-images.tar` (2.5 GB): `llmstack-llama:latest`,
  `llmstack-llama:b9542-baseline`, `llama-vulkan-bleeding:mesa26`, `llmstack-llama-qwen4exp:6fcaa16`. All four are
  also reproducible from `containers/*/Containerfile`.
- `localhost/llmstack-vllm-rollback:v0.26.0` needs no backup: it shares image ID `3d7fe5e20f0d` with
  `docker.io/vllm/vllm-openai-rocm:v0.26.0`, so it is a retag — re-create with `podman tag` after a re-pull.
- The docker.io vLLM images (~137 GB) are re-pullable, slowly.

### Steps

No release upgrade, no LVM snapshot. Kernel first, so the console never depends on a driver that is being removed.

**0. HWE 7.0 kernel, while the current 30.20 driver is still intact on 6.8.**

```bash
sudo apt update
sudo apt install --install-recommends -y linux-generic-hwe-24.04
sudo reboot                    # choose 7.0 (default); 6.8 stays in GRUB as the rollback
```

After the reboot: `uname -r` shows 7.0.x. The old amdgpu-dkms 30.20 will **not** have built for 7.0 — expected and
harmless, because kernel 7.0's in-tree amdgpu supports gfx1201 and drives both the console and the cards.
Confirm the GPUs still enumerate (`ls /sys/class/drm/card*`) before continuing. If anything is wrong here, reboot
into 6.8 and nothing has been lost.

**1. Remove the ROCm 7.2 / amdgpu 30.20 userspace and its apt sources.**

Required by AMD's own 10.1 instructions ("If you have ROCm 7.2.4 or older installed, please uninstall it before
proceeding"), and necessary to avoid the conffile/pin collision in hazard 2.

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
uname -r                          # 7.0.x
dkms status                       # amdgpu/31.60 (1:7.1.9.31600000) built for 7.0
amd-smi version && amd-smi list   # 4 GPUs, gfx1201
rocminfo | grep -c gfx1201        # expect 4
groups                            # render, video
glxinfo -B 2>/dev/null | grep -i mesa   # mesa 26.2.0 from graphics/26.16
```

Rollback from here: GRUB → kernel 6.8, then reinstall the cached 30.20 debs from
`/home/xin/rocm-rollback-20261016/` and restore the three old apt sources.

### Post-move validation, before any S2 benchmarking

The driver change cuts both ways: production `v0.26.0` carries ROCm **7.2.3** userspace and will now be running on
an amdgpu **31.60** driver — the inverse skew to the one B1 just failed on. A boot check is not enough.

- `podman images` intact (podman stays at 4.9.3, so no store migration — but check anyway); `podman tag` the
  rollback alias back if it was lost.
- `llmctl hw`, `llmctl up`, then boot production 27B `v0.26.0` and Flash-Next `nightly-8cbd5d03…`.
- Vulkan GGUF path on the new `graphics/26.16` mesa 26.2.0 overlay rather than 7.2's 26.0.0:
  `llmctl swap gemma4-26b-q8`, and confirm `llmctl swap qwen3.8-flash-next` (llama.cpp fork) still loads.
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
