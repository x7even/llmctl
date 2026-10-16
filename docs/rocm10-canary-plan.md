# ROCm 10.x canary plan (target: v0.5.0)

Status: plan for review, written 2026-10-16. Nothing here has been run on the host except the
`amd-smi` probes in section 2. The production pin stays `docker.io/vllm/vllm-openai-rocm:v0.26.0`
(Flash-Next: the pinned nightly) until a canary passes every gate in section 6.

## 1. What "ROCm 10 support" means here

The host runs ROCm 7.2.0 (amdgpu 6.16.6, `rocm-smi` 4.0.0, `amd-smi` 26.2.1). Every model runs in a
container that carries its own ROCm userspace (the vLLM images are built on ROCm 7.2.3), so the host
only supplies the kernel driver (amdgpu/KFD) and the monitoring tools. That splits the work in two:

| Track | What changes | Host risk | Needed for |
|-------|--------------|-----------|------------|
| A. Tooling | `rocm-smi` is deprecated; move the repo to `amd-smi` with `rocm-smi` as fallback | none | any host move |
| B. Runtime | a vLLM image built on ROCm 10.x, then (only if it helps) the host driver | high: one box, no spare | ROCm 10 itself |

State of the world when this was written (2026-10-15 research, re-verify at step B0): ROCm 10.1.0 was
released 2026-10-05 and is the latest; no official `vllm/vllm-openai-rocm` image is built on ROCm 10.x.

## 2. Track A: tooling (do first, no host change, ships on its own)

`rocm-smi` call sites to migrate (from `grep -rn rocm-smi`, 2026-10-16):

| File | Use | Notes |
|------|-----|-------|
| `bin/llmctl:502` | `llmctl status` GPU VRAM block | `--showmeminfo vram`, prints "GPU" / "VRAM" lines |
| `tui/data.go:195-200` | llmpanel GPU panel, every 3 s | VRAM, utilisation, temperature |
| `scripts/llmhw.py:80-97` | GPU count / VRAM fallback when sysfs has no VRAM info | sysfs stays primary |
| `scripts/configure:324` | error message only | wording |
| `bench/concurrent_bench.py:59`, `bench/opt_probe.py:44` | peak VRAM sampler | bytes today |
| `tests/smoke.sh:118-122` | VRAM snapshot | |
| docs | README, tui/README.md, tui/CLAUDE.md, docs/llmctl.md, docs/gpu-counts.md | wording |

`amd-smi` already does everything these need, probed on this host:

- `amd-smi metric --mem-usage --json` gives per-GPU `mem_usage.{total_vram,used_vram,free_vram}` as
  `{"value": N, "unit": "MB"}`. The unit is MiB in practice (32624 = 31.86 GiB), whereas `rocm-smi` prints bytes.
- `amd-smi metric --usage --temperature --json` gives utilisation (`usage.gfx_activity`) and temperature.
- `amd-smi list --json` gives one entry per GPU (count, BDF, UUID); `amd-smi static --vram --json` gives size.
- Cost is the same as today: about 64 ms per call vs 55 ms for `rocm-smi`, so the TUI's 3 s poll is unaffected.

Design: one small helper per language, same contract (`gpus() -> [{index, vram_total_b, vram_used_b,
util_pct, temp_c}]`): try `amd-smi ... --json`, fall back to parsing `rocm-smi`, return an empty
list when neither exists (callers already show "unavailable"). Convert MB to bytes once, in the helper.
Python gets it in `scripts/llmhw.py` (already the shared module for `llmctl`/`configure`), Go gets a port in
`tui/` with a parity fixture like `tests/fixtures/llmhw_cases.json`. Unit tests feed canned JSON and
canned `rocm-smi` text through an injectable runner (the existing pattern in `tests/test_llmhw.py`).

Exit criterion: `llmctl status`, `llmpanel`, `scripts/configure`, both bench samplers and `tests/smoke.sh`
work with only `amd-smi` present and with only `rocm-smi` present. Release as v0.4.7 if it lands before
Track B starts.

## 3. Track B: runtime, in phases that each stop cheaply

**B0. Re-verify the premise (30 min, no risk).** Check for an official or community vLLM image on ROCm 10.x,
a PyTorch ROCm 10.x build, and R9700 (gfx1201) support in the 10.1 release notes. If none exists, stop: moving the
host driver buys nothing and the plan ends with a note in `docs/upgrade-plan-2026-10.md`.

**B1. Container-only trial (zero host risk).** If an image exists, pull it under a pinned tag, run it on the
current host driver through the throwaway-router pattern (own port :8099, own container names, shipped profile
untouched; see `bench/CLAUDE.md` canary checklist). This answers "does ROCm 10 userspace run on the 7.2 driver"
and gives all the gate numbers without touching the host. Order: Qwen3.8-27B FP8 TP4 first (smallest surprise),
then Flash-Next (nightly-only features, pinned host RAM, so the likeliest to break).

**B2. Host driver move (only if B1 shows a gain worth the risk).** The host is the only machine, so before any
change: record `dpkg -l | grep -E 'rocm|amdgpu|hsa'` and the kernel version into the plan, keep the old
package repo pinned and cached, and confirm the previous driver can be reinstalled offline. Install the new
driver, reboot, re-run `llmctl hw`, then repeat the B1 gates on the shipped images and the canary image.
Rollback is reinstalling the recorded versions; if the GPUs do not enumerate, that is a console job, so do
this with the user present, not unattended.

**B3. Cut over.** Change the pins in one PR (models.yaml, `config/CLAUDE.md`, root `CLAUDE.md`, `scripts/`),
keep `localhost/llmstack-vllm-rollback:v0.26.0` until the next release, tag v0.5.0.

## 4. Why the order matters

Rollback is what a failed canary leans on, and v0.4.6 just repaired the rollback anchors. Track A removes the
last tooling dependency on a deprecated binary, so a host move cannot break `llmctl status` or `llmpanel`
mid-experiment. B1 before B2 means the expensive, one-way step is only taken with measurements in hand.

## 5. Known risks to test, not assume

- Container ROCm userspace vs host driver skew in either direction (7.2.3 userspace on a 10.x driver after B2;
  10.x userspace on the 7.2 driver in B1). Symptom to watch: HIP init errors, or silent slowdowns.
- Pinned-host-RAM behaviour for Flash-Next: PLE pinning goes through the HIP pinned-host allocator, so a
  runtime change can move the half-speed behaviour (`docs/flash-next-half-speed.md`). Re-run the serial
  speed check with a full page cache.
- Kernel-side counters and `rocm-smi` flags that disappear: do not use `VmLck`/`Mlocked` to judge pinning.
- Cold-start and compile cache: `.vllm-cache/` and `.triton-cache/` are keyed on image and ROCm, so first boot
  recompiles; budget the 2-3 minute warm start plus a longer first boot.

## 6. Gates (all must pass, same settings as the baseline)

1. **Quality gate** (`bench/CLAUDE.md`): hard code tasks `mini_scheme`, `regex_engine`, `json_strict`,
   `date_math`, reasoning effort medium, cap >= 64K, same samples as the shipped baseline. Fail on a drop beyond
   noise or on early stops ("early stops (empty/cut)" column).
2. **Throughput gate:** `concurrent_bench.py`, `medium-256`, `--no-thinking`, no more than -5% against the
   shipped baseline at serial, conc=8 and conc=16 (the gate that held back the v0.31.0 canary).
3. **Long-context stress:** 7 concurrent unique ~100K-token prompts all finish, no timeouts, at the profile's real
   `--gpu-memory-utilization`; plus decode speed at 1K and ~100K depth (the 27B falls from 83 to 3 tok/s with depth
   on v0.26.0, Flash-Next stays flat at ~55).
4. **Flash-Next health:** ~55 tok/s serial after a cold start with a warm page cache, and again after `llm-prestart`
   with a full page cache (must not start at half speed).
5. **Tool calls and reasoning:** the existing tool-call smoke check and `tests/smoke.sh` on both backends.
6. **Run the checkpoint's or image's own published recipe verbatim** when a candidate fails, to separate config
   from image/kernel faults before ruling it out.

## 7. Decision points for the user

- After B0: continue only if an image exists.
- After B1: is the measured gain big enough to justify a host driver change on the only machine?
- B2 needs the user at the console in case the driver move needs recovery.
