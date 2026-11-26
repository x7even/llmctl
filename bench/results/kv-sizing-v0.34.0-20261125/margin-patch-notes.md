# [ROCm] Make the extensible KV cache margin floor and non-torch reserve configurable

Draft PR notes for `margin-patch.diff` (unified diff against vLLM 0.34.0
`vllm/envs.py` and `vllm/v1/worker/extensible_kv_cache.py`, as shipped in
`docker.io/vllm/vllm-openai-rocm:v0.34.0`). Not submitted.

## What the patch does

It adds two opt-in environment variables. Defaults are unchanged.

| Variable | Overrides | Default (ROCm / other) |
|---|---|---|
| `VLLM_KV_CACHE_MARGIN_FLOOR_MB` | `KV_CACHE_MARGIN_FLOOR_BYTES` | 3 GiB / 1 GiB |
| `VLLM_KV_CACHE_NON_TORCH_RESERVE_MB` | `KV_CACHE_NON_TORCH_RESERVE_BYTES` | 1 GiB / 512 MiB |

It also fails at import if the reserve is set above the floor, since the
reserve is carved out of the margin.

I chose not to change the ROCm default. The evidence below comes from one GPU
(gfx1201), one model and one TP size. That justifies a knob, not a new default
for MI300/MI355.

## Why

On a 32 GiB card the 3 GiB ROCm floor is the binding term in the sizing
formula. At 0.75x the measured transient, the fractional margin comes to less
than 3 GiB. So the floor alone sets how much KV the card gets:

- At the default floor, 0.34.0 sizes the pool at 81.2% of what 0.26.0 gave on
  the same hardware and model (891,289 vs 1,097,728 tokens).
- `--gpu-memory-utilization` cannot get that memory back. Removing GMU gives a
  byte-identical pool, because the margin binds and GMU does not.
- The only other way to raise the pool is `--kv-cache-memory-bytes`. That turns
  off extensible sizing, the torch cap and the reserve all at once.

The source comment justifies the larger ROCm floor this way: "ROCr also maps
kernel scratch outside the allocator when a kernel first needs it". The
measurements below found no such growth on gfx1201 under any workload tried.

## Setup

- 4x AMD Radeon AI PRO R9700 (gfx1201, 32 GiB, 31.86 GiB reported), TP4, ROCm 7.2 host.
- Image `vllm/vllm-openai-rocm:v0.34.0`.
- Model: Qwen3.8-27B-FP8, a GDN hybrid with MTP speculative decoding.
- `--max-model-len 131072`, explicit CUDA-graph capture sizes `[1,2,4,8,16,32]`.
- `GPU_MAX_HW_QUEUES=1`, KV dtype unchanged.
- Each arm was one fresh spawn, and every spawn was in the fast decode band
  before and after its workload.

**Memory tracing:**
- Host: amdgpu sysfs `mem_info_vram_used` per card, every 2 s.
- In-process: a `sitecustomize` thread in each worker reading
  `torch.cuda.memory_stats()` every 2 s (allocated, reserved, peaks,
  `num_alloc_retries`, `num_ooms`).
- Non-torch is computed as `used - torch reserved - extensible KV committed`.
- Only samples where torch reserved was unchanged across the bracketing
  samples are counted, because the two samplers are not synchronised. The raw
  maximum is kept as an upper bound.
- Cross-check: peak growth of device used minus peak growth of torch reserved.

**Workload, run in order on every arm:**
1. medium-256 sweep at serial / conc 8 / conc 32, 128 requests per level.
2. Prewarmed depth cells: 129,984x1, 65,536x4 and 16,384x8.
3. Pool fill: 12x120K-token prompts staggered by 0.5 s, plus 32 short requests
   at t=20 s. KV usage reached 0.99-1.00 and there were preemptions.
4. A thinking request with a tool call, then 4 streams x 8,192 generated tokens.
5. A 15-minute soak at conc 8, alternating short prompts with 16K-64K prompts.

## Results

Pool size is shown as tokens and as a percentage of 0.26.0's 1,097,728. Min
free is the lowest device free reading on any card during the whole workload.

| Arm | Floor / reserve | Pool tokens | KV GiB/card | Torch cap | Peak used | Min free | Non-torch growth | Torch reserved growth | Alloc retries | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| K0 GMU 0.95 | 3 / 1 GiB | 891,289 (81.2%) | 15.61 | 13.08 GiB | 89.6% | 3.30 GiB | +0.011 GiB | +3.09 GiB | 0 | pass |
| K1 no GMU | 3 / 1 GiB | 891,289 (81.2%) | 15.61 | 13.08 GiB | 90.0% | 3.20 GiB | +0.013 GiB | +3.20 GiB | 0 | pass |
| floor 2 GiB | 2 / 1 GiB | 948,344 (86.4%) | 16.60 | 12.08 GiB | 93.1% | 2.19 GiB | +0.011 GiB | +3.20 GiB | 0 | pass |
| floor 1 GiB | 1 / 1 GiB | 1,005,399 (91.6%) | 17.60 | 11.08 GiB | 93.0% | 2.22 GiB | +0.013 GiB | +1.96 GiB (capped) | 1 | pass |
| floor 1 / reserve 0.5 (NVIDIA values) | 1 / 0.5 GiB | 1,005,399 (91.6%) | 17.60 | 11.59 GiB | 94.8% | 1.67 GiB | +0.015 GiB | +2.62 GiB (capped) | 1 | pass |
| K2 `--kv-cache-memory-bytes` 19.17 GiB (extensible off, no cap) | none | 1,095,607 (99.8%) | 19.17 | none | 99.9% | **0.046 GiB** | +0.011 GiB | +2.89 GiB | 1 (TP0-2) | **fail**: device-level allocator OOM in pool fill |
| K2 `--kv-cache-memory-bytes` 18.67 GiB | none | 1,067,080 (97.2%) | 18.67 | none | 98.7% | 0.40 GiB | +0.020 GiB | +2.83 GiB | 0 | pass (see the pool-fill caveat) |

A pass means all of the following held:
- No OOM and no worker death.
- 0 request errors across all steps.
- 0 server error lines, after excluding benign `triton_bundler` cache warnings
  that appear on every arm.
- `num_ooms` was 0.
- Throughput was within noise of the 3 GiB arm.

**Throughput:**

| Arm | Serial | Conc 8 | Conc 32 | 130Kx1 | 64Kx4 | 16Kx8 | Long gen 4x8K |
|---|---|---|---|---|---|---|---|
| K0 | 77.4 | 453.6 | 996.2 | 76.0 | 170.0 | 328.4 | 366.0 |
| K1 | 76.8 | 453.0 | 983.3 | 71.3 | 171.7 | 317.2 | 365.4 |
| floor 2 | 76.8 | 453.1 | 970.7 | 79.1 | 167.2 | 312.2 | 340.2 |
| floor 1 | 76.8 | 453.2 | 1006.7 | 75.1 | 164.6 | 318.0 | 363.5 |
| NVIDIA values | 76.9 | 453.1 | 994.3 | 72.0 | 166.3 | 320.6 | 363.8 |
| K2 19.17 | 77.0 | 453.7 | 996.3 | 77.6 | 168.2 | 314.8 | 368.8 |
| K2 18.67 | 77.0 | 453.6 | 1007.8 | 73.4 | 172.5 | 309.0 | 375.3 |

The depth-cell spread between arms follows MTP acceptance per step (2.12-2.35)
rather than the memory setting: decode step rate is flat. Conc 32 spans
971-1007 across five spawns, which is spawn-to-spawn noise.

### The `--kv-cache-memory-bytes` arm (stock 0.34.0, no patch)

This is the only way to grow the pool on an unpatched 0.34.0, and it works
differently from the extensible path:
- It skips profiling and turns off extensible sizing, so there is no torch cap,
  no margin and no reserve.
- The KV tensor lives inside torch's reservation, and nothing stops the
  caching allocator from growing into the last free byte.

**At 19.17 GiB/card** (K0's tightest "fully utilize" figure, 99.8% of the
0.26.0 pool) the card had 2.76 GiB free at idle. Pool fill then took it to zero:
- TP0-2 each logged `HIPCachingAllocator.cpp:3934] memory allocation failed
  with OOM ... trying to allocate 335544320 bytes (free: 0, total:
  34208743424)`.
- They survived because the allocator flushed its cache and retried, so
  `num_ooms` stayed 0 and there were no request errors.
- TP3 grew to 30.96 GiB reserved without a retry and ran at 0.046 GiB free for
  the rest of the run.
- This is classed as a fail. Any non-torch allocation at that moment (RCCL,
  ROCr scratch) would have had nothing.

**One 0.5 GiB step lower (18.67 GiB)**, the arm passed:
- 97.2% of the 0.26.0 pool, min free 0.40 GiB, no allocator OOM line, 0 retries.
- Torch reserved still grew by 2.83 GiB, nearly all of the 3.26 GiB that was
  free at idle.
- Its 400 MB of headroom is set by one workload's fragmentation, and nothing
  enforces it.
- Caveat: on this larger pool, the standard 12x120K fill admitted only 8
  long prompts, so it peaked at 0.895 KV usage.
- A supplementary fresh spawn (`K2-18.67-fill128k`, pool fill only, 128K
  prompts) reached 0.984 KV usage, 20 s at or above 95%. It had min free
  0.82 GiB, 0 errors and no allocator OOM.
- Torch reservation growth differed between the two fills (+2.83 vs +2.41
  GiB). The headroom this path needs depends on the workload.


1. **Non-torch memory grew by at most 0.015 GiB after startup on any card in
   any arm.** That covers all five workload steps: 130K prefill, 120K-prompt
   pool fill to 100% with preemption, long generation, and a 15-minute soak.
   - The raw, unaligned maximum was 1.41 GiB. That came from sampler skew while
     torch was growing; the aligned samples and the used-minus-reserved
     peak-growth cross-check agree on about 0.01 GiB.
   - For comparison, the ROCm defaults keep 3 GiB as the floor and 1 GiB as the
     non-torch reserve. The source comment cites MI355 growth of up to 0.17 GiB.
2. **What actually consumes the margin is the torch caching allocator's
   reservation growth.** Reserved grew by 3.1-3.2 GiB when uncapped, while live
   allocations peaked only about 1 GiB above idle. Startup deducted 2.25 GiB
   for this ("2.25 GiB of torch reservation growth"), so serving fragmented
   about 0.9 GiB beyond what warmup predicted.
3. **The torch cap absorbs that growth when the margin is smaller.** With the
   floor at 1 GiB, reserved stopped at the cap (11.08 GiB; peak 10.78-11.44
   GiB). The allocator logged exactly one `num_alloc_retries` (it freed cached
   blocks and retried), and there were no OOMs, no errors and no throughput
   change.
4. Without a cap (`--kv-cache-memory-bytes`), torch's reservation grows to fill
   whatever is free: +2.4 to +2.9 GiB, against about +0.75 GiB of live
   allocation. At 19.17 GiB/card that exhausted the device.
5. Even at a 1 GiB floor with a 0.5 GiB reserve, at least 1.67 GiB of device
   memory stayed free at all times on every card.
6. Both GMU arms (0.95 and unset) produced identical pools, so GMU has no
   effect while the margin binds.

## What is inferred, not measured

- "ROCr maps kernel scratch lazily" did not show up as non-torch growth here.
  The likely reason is that scratch for every kernel shape this model uses was
  already mapped by profiling and CUDA-graph capture, which happen before the
  measurement baseline. A model or workload that reaches new kernel shapes
  after startup could still grow it. Examples would be LoRA, new
  multimodal encoders, or a capture-size list that does not cover the
  batch sizes served.
- A single allocator retry is cheap here. Under a workload that sits at the
  cap, repeated retries (cache flushes) could cost latency. This was not
  measured beyond the 15-minute soak, which ran at 35% KV usage.
- Nothing here bears on MI300/MI355 or on other models. That is why the patch
  is a knob and leaves the default alone.

## Patch status

The diff was dry-run applied (`patch -p1 --dry-run`) to the 0.34.0 files and
AST-checked. It was **not** run in a container. The arms used copies of
`extensible_kv_cache.py` with the constants edited in place, which exercise
the same values the env vars would set.

## Smallest margin that passed

The smallest margin tested passed: floor 1 GiB with non-torch reserve 0.5 GiB,
which are the NVIDIA defaults. It raised the pool by 12.8% over the ROCm
default (1,005,399 vs 891,289 tokens), with 0 errors and throughput unchanged.
A 2 GiB floor is the setting that passed without a single allocator retry.
