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

The host is the only machine. Rollback is an LVM snapshot of the root LV plus images of `/boot` and `/boot/efi`
(which live outside the LV), not package reinstallation — the cached 30.20 debs are `noble` builds and do not
apply after a release upgrade. If the GPUs do not enumerate, that is a console job, so this is never done
unattended.

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

## 9. B2 runbook: Ubuntu 26.04.1 + amdgpu 31.60 + ROCm 10.1

### Why 26.04.1 and not 24.04.5 + HWE 7.0

AMD's ROCm 10.1.0 table for Radeon AI PRO R9000 (RDNA 4, gfx1201) lists three supported rows — Ubuntu 26.04.1
kernel GA 7.0, 24.04.5 kernel HWE 7.0, 22.04.5 kernel HWE 6.8 — with amdgpu 31.60.0 or 31.50.0. The host is
already 24.04.5, so both of the first two rows are reachable. 26.04.1 is chosen because:

- **Kernel 7.0 is the distro GA kernel there**, not an HWE bolt-on. `linux-generic-hwe-24.04` tracks forward to
  newer kernels at each point release, and each roll is another chance for the out-of-tree DKMS driver to break.
- **It removes the Vulkan skew we otherwise could not test.** There is no `graphics/31.x` repo on repo.radeon.com
  (only `graphics/7.2`), so on 24.04 the RADV stack for the GGUF llama-server profiles would stay pinned at AMD's
  `mesa-amdgpu` 26.0.0 overlay while ROCm moved to 10.1. Ubuntu 26.04 ships `mesa-vulkan-drivers` **26.0.8** —
  newer than AMD's overlay — so the overlay is dropped entirely and the Vulkan path runs on distro RADV.
- One maintenance window instead of two; podman 5.x; LTS support to 2031.

Both halves publish for 26.04 (`resolute`), verified 2026-10-16: amdgpu `31.60/ubuntu/dists/resolute` serves
`amdgpu-dkms 1:7.1.9.31600000-2407772.26.04`, and `stable.repo.amd.com/rocm/core/packages/ubuntu2604` serves
`amdrocm10.1-gfx1201 10.1.0-3`. `do-release-upgrade -c` offers `26.04.1 LTS`.

### Hazards specific to this host

1. **No iGPU.** All four VGA controllers are `1002:7551` (R9700) and `card0` drives the DisplayPort console.
   Kernel 6.8's in-tree amdgpu predates gfx1201, so between purging `amdgpu-dkms` and booting kernel 7.0 there is
   no gfx1201 kernel driver. **Do not reboot between the purge and the release upgrade**, and have SSH available
   in case the local console goes dark.
2. **`/boot` and `/boot/efi` are outside the root LV** (`nvme2n1p2`, `nvme2n1p1`). A snapshot of root alone would
   roll back to a 24.04 root booted by 26.04 kernels. Image both partitions as well.
3. **The cached rollback debs are useless after the upgrade.** `/home/xin/rocm-rollback-20261016/` holds `noble`
   builds of amdgpu-dkms 30.20. After the move, the snapshot plus the `/boot` images are the only rollback.
4. **podman 4.9.3 → 5.x migrates the rootless store** (95 GB). Never run `podman system reset` as a fix — it
   wipes the store. The network backend is already `netavark`, so there is no CNI migration.

### Pre-flight (done, no sudo needed)

- Local-only images saved to `/mnt/models/_host-backup-20261016/local-images.tar` (2.5 GB): `llmstack-llama:latest`,
  `llmstack-llama:b9542-baseline`, `llama-vulkan-bleeding:mesa26`, `llmstack-llama-qwen4exp:6fcaa16`. All four are
  also reproducible from `containers/*/Containerfile`.
- `localhost/llmstack-vllm-rollback:v0.26.0` needs no backup: it shares image ID `3d7fe5e20f0d` with
  `docker.io/vllm/vllm-openai-rocm:v0.26.0`, so it is a retag — re-create with `podman tag` after a re-pull.
- The docker.io vLLM images (~137 GB) are re-pullable, slowly.

### Steps

**0. Verify snapshot room, then image what the snapshot cannot cover.**

```bash
sudo vgs                       # need VFree >= ~200G (lsblk implies ~800G: 1.8T partition, 1000G LV)
sudo dd if=/dev/nvme2n1p2 of=/mnt/models/_host-backup-20261016/boot.img    bs=4M status=progress
sudo dd if=/dev/nvme2n1p1 of=/mnt/models/_host-backup-20261016/bootefi.img bs=4M status=progress
sudo tar -C / -czf /mnt/models/_host-backup-20261016/etc.tar.gz etc
```

**1. LVM snapshot of root.**

```bash
sudo lvcreate -s -n root-pre26 -L 200G /dev/ubuntu-vg/ubuntu-lv
```

Rollback, if needed: `sudo lvconvert --merge /dev/ubuntu-vg/root-pre26 && sudo reboot`, then restore
`boot.img`/`bootefi.img` to their partitions from a live USB if the kernels no longer match.

**2. Purge the AMD 7.2 stack — and do not reboot afterwards.**

Required by AMD's own 10.1 instructions (uninstall ROCm 7.2.4 or older first), and necessary here because
noble-built `amdgpu-dkms 6.16.6` cannot build against kernel 7.0 and the `mesa-amdgpu`/`libllvm20.1-amdgpu`
overlays would fight Ubuntu's mesa during the upgrade.

```bash
sudo amdgpu-install --uninstall -y
sudo apt purge -y 'amdgpu*' 'rocm*' 'mesa-amdgpu*' 'libdrm-amdgpu*' 'libllvm*-amdgpu*' '*-amdgpu-mesa*'
sudo apt autoremove -y
sudo rm -f /etc/apt/sources.list.d/amdgpu*.list /etc/apt/sources.list.d/rocm*.list
dkms status                    # must be empty
```

**3. Release upgrade, in the same sitting.**

```bash
sudo apt update && sudo apt full-upgrade -y
sudo do-release-upgrade
```

Keep local versions of config files we own when prompted. Reboot lands on 26.04.1 + kernel 7.0, whose in-tree
amdgpu does support gfx1201, so console and cards should both return.

**4. amdgpu 31.60.**

```bash
cd /tmp && wget https://repo.radeon.com/amdgpu-install/31.60/ubuntu/resolute/amdgpu-install_31.60.316000-1_all.deb
sudo apt install ./amdgpu-install_31.60.316000-1_all.deb
sudo apt update && sudo apt install -y amdgpu-dkms
sudo reboot
```

**5. Verify the driver before anything else.**

```bash
uname -r                       # 7.0.x
dkms status                    # amdgpu/31.60 built for 7.0
amd-smi version && amd-smi list   # 4 GPUs, gfx1201
groups                         # render, video
```

**6. ROCm 10.1 userspace (optional — the containers carry their own).**

```bash
sudo apt install -y libatomic1 libquadmath0
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://stable.repo.amd.com/rocm/gpg/packages.gpg | sudo tee /etc/apt/keyrings/amdrocm.gpg >/dev/null
sudo tee /etc/apt/sources.list.d/amdrocm-stable.sources >/dev/null <<'EOF'
Types: deb
URIs: https://stable.repo.amd.com/rocm/core/packages/ubuntu2604/
Suites: stable
Components: main
Architectures: amd64
Signed-By: /etc/apt/keyrings/amdrocm.gpg
EOF
sudo apt update && sudo apt install -y amdrocm10.1-gfx1201
```

### Post-move validation, before any S2 benchmarking

The driver change cuts both ways: production `v0.26.0` carries ROCm **7.2.3** userspace and will now be running on
an amdgpu **31.60** driver — the inverse skew to the one B1 just failed on. A boot check is not enough.

- `podman images` intact after the 5.x store migration; `podman tag` the rollback alias back if it was lost.
- `llmctl hw`, `llmctl up`, then boot production 27B `v0.26.0` and Flash-Next `nightly-8cbd5d03…`.
- Vulkan GGUF path on distro RADV instead of AMD's overlay: `llmctl swap gemma4-26b-q8`.
- `cd tui && go test ./...`, and re-check the Python tooling (host Python moves 3.12 → newer; `python3-yaml` is a
  distro package so apt handles it, but confirm `llmctl` and `bench/canary_router.py` still import).
- **Re-run the full S0 suite on the unchanged production images as state S0′**, then
  `canary_compare.py bench/results/canary-rocm10-20261016/{fn-s0,fn-s0prime}`. This is the "production still
  works" gate and the thing that must pass before the pin is allowed to move.

Only then run S2 on `nightly-rocm100-8cbd5d03…`.

**Confound to carry in the write-up:** S2 vs S1 now mixes OS, kernel, driver and mesa. The clean readings are
**S0′ vs S0** (OS/kernel/driver effect, image held constant) and **S2 vs S0′** (image effect on the supported
host). Do not quote S2 vs S1 as "the ROCm 10 delta".
