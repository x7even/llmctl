# vLLM 0.26.0 → 0.34.0 upgrade — November 2026

**Status: switched; KV margin patch adopted on three profiles; open items listed at the end of
Phase 4.** Phase 0 (fresh baseline of the stack as it ran) finished 2026-11-25. Phase 1
(bring-up on `v0.34.0`): `qwen3.8-27b-code` starts and is faster everywhere, and a 12-sample
quality re-check found no regression. Phase 2: every other profile passes on 0.34. Phase 3c:
the KV margin backport (1 GiB floor) is adopted on `qwen3.8-27b-code`,
`qwen3.8-flash-next-vllm` and `qwen3.6-35b-code`. Phase 4: every vLLM profile pins `v0.34.0`,
and the live switch was done on 2026-11-27.

**Policy (user, 2026-11-27): v0.34.0 is the minimum.** "At this point I don't think we should
ever be using anything but 0.34 and above." Every new profile, canary and benchmark runs on
v0.34.0 or newer. v0.26.0 and the old Flash-Next nightly are emergency rollback only. The 0.26
figures in this document are history.

Why now: the stack has been pinned to `v0.26.0` since the October 0.31.0 canary failed its gate
(`docs/upgrade-plan-2026-10.md`). Eight releases have shipped since. New model support
(Inkling 2 Mini, parked in PR #37) needs vLLM ≥ 0.35, so staying on 0.26 blocks it. The old
single-stream workaround (`VLLM_USE_V2_MODEL_RUNNER=0`) was removed in 0.32, so this attempt has
to make Model Runner V2 work on gfx1201 or find out why it does not.

## Method

Each phase is a gate. Production profiles stay on their current pins until Phase 4.

| Phase | What | Gate |
|---|---|---|
| 0 | **Fresh baseline, live config.** All seven published vLLM profiles, one fresh spawn each: provenance, `llmband`, `medium-256` sweep (`--requests 128 --serial-n 8`, conc 1–32), prewarmed depth cells, hard-code quality on two profiles, tool-call and reasoning response shapes. | Complete data set under `bench/baselines/*-live-20261125.json` |
| 1 | **Bring-up on `v0.34.0`.** Same flags, side port, router untouched. `qwen3.8-27b-code` first (the profile that failed in October), then one MoE (`qwen3.6-35b-128k-nomtp`), then `gemma4-26b-a4b` and Flash-Next. One image (`v0.34.0`; the `-rocm100` tag is the same digest). Fix flag renames and startup failures. | Each profile starts, serves, passes tool-call, reasoning-field and needle checks |
| 2 | **Re-run.** The Phase 0 matrix, cell for cell, on the winning image arm. Quality gate before throughput (`bench/CLAUDE.md`). | Known before tuning: where 0.34 is ahead, level, behind |
| 3 | **Tune, re-run.** One variable at a time, matched pairs, fresh spawn per arm, under real serving load only. Candidates come from the Phase 2 gaps and from the release-notes review. Starting list: `GPU_MAX_HW_QUEUES` (1 vs 2 vs unset, since the band behaviour may differ on a new runtime), capture sizes, attention backend per profile, Model Runner V2 single-stream behaviour, KV pool and `--gpu-memory-utilization`. | Every `medium-256` cell within −5 % of Phase 0, depth cells no worse, quality gate passed. A cell that fails needs an explicit decision, not a relaxed gate |
| 4 | **Cut over.** Profile by profile: pin bump in `config/models.yaml`, root and `config/` `CLAUDE.md`, `scripts/`; new baselines; `docs/models.md` and `docs/benchmark-results-full.md` regenerated; rollback tag kept. | 30-min soak, long-context stress step, router check through :8080 |

Comparison rules (from `bench/CLAUDE.md`): same request count both sides, band classified on
every spawn, one fresh spawn per arm, image pin in every filename.

## What changed between 0.26 and 0.34 (release review, 2026-11-25)

From release notes, PRs and source at the `v0.34.0` tag. Items marked *(untested)* are
hypotheses until Phase 1–3 measure them here.

- **One image.** `v0.34.0` and `v0.34.0-rocm100` are the same digest: ROCm 10.0 userspace, torch
  2.13, Triton 3.8, Python 3.12, built for gfx1201. There is no ROCm 7.2 build of 0.34;
  `v0.33.0-rocm72` is the last one. So there is one image arm, not two.
- **Model Runner V1 is gone** (#63373). `VLLM_USE_V2_MODEL_RUNNER=0` fails at startup.
- **October's 45 % single-stream loss was probably the slow decode band, not the runner itself**
  *(untested)*. The 0.31 canary ran on 2026-10-10 without `GPU_MAX_HW_QUEUES=1` (found
  2026-10-18). Its V2 reading, 36.2 tok/s, is the slow-band figure for this profile (35.6); the
  0.26 control read 66.5, the fast figure. vllm#58639 measures the mechanism on an R9700: V2's
  extra HIP streams add ~17 µs per kernel dispatch under the default queue limit, and
  `GPU_MAX_HW_QUEUES=1` or `2` removes it. Every profile now carries the flag.
- **TRITON_ATTN is the default attention backend on gfx1201** (#60418), so the MTP profiles
  would silently leave ROCM_ATTN. Its split-KV path now admits MTP verify (query length ≤ 8,
  #56148), so "MTP closes the 3D path" in `CLAUDE.md` is stale on 0.34 and MTP + depth may no
  longer be a trade *(untested)*. On gfx1201 the 3D threshold is halved for single-token decode
  with 16-bit KV, so it may close above ~16 sequences, not 32 *(untested)*.
- **Extensible KV cache is on by default** (#56492) and has an open R9700 report of −44 %
  single-stream decode (#69742). Test `--no-enable-extensible-kv-cache`.
- **Capture sizes.** `--cudagraph-capture-sizes` is deprecated under V2; decode capture is by
  request count and appears capped at `max size // (K+1)`, i.e. 10 requests on the MTP profiles.
  At 0.31 this left conc 8/16 without full decode graphs, a candidate for October's 6–9 % loss
  *(untested)*. Lever: `--compilation-config` with `decode_cudagraph_capture_request_sizes`.
- **Breaking details:** `reasoning_content` is removed (only `reasoning`; `bench/depth_bench.py`
  reads the old name), `CUDA_VISIBLE_DEVICES` no longer works on ROCm, NUMA binding and
  `--block-size 64` are new defaults, `max_tokens` is no longer reserved from the context, Qwen3
  tool calls stream incrementally (re-test `llmproxy`), the compile cache key changed so the
  first start is a cold compile.
- **Other levers** *(all untested)*: `ROCM_SEGMENTED_ATTN` (opt-in, head size 256),
  `VLLM_DISABLE_SHARED_EXPERTS_STREAM=1` on MoE, `draft_lm_head_quantization`,
  `--max-num-active-seqs`.

Phase 1 arms on `qwen3.8-27b-code`, in this order, one variable each: as-shipped flags →
`--no-enable-extensible-kv-cache` → explicit `--attention-backend ROCM_ATTN` → decode capture
sizes to 32 → `GPU_MAX_HW_QUEUES` 1 / 2 / unset.

## Phase 0 — baseline (2026-11-25) — done

Live config (main checkout, uncommitted changes included: `qwen3.8-27b-think` at 262,144 with
the CPU KV-offload connector, Flash-Next at `--gpu-memory-utilization 0.95`). One fresh spawn
per profile, `GPU_MAX_HW_QUEUES=1` confirmed in every container. Six profiles on `v0.26.0`,
Flash-Next on `nightly-8cbd5d0` (vLLM 0.31.1rc1).

### `medium-256`, no thinking, `--requests 128 --serial-n 8`, decode tok/s

| Profile | serial | c1 | c2 | c4 | c8 | c16 | c32 |
|---|---|---|---|---|---|---|---|
| qwen3.8-27b-code | 67.9 | 66.0 | 116.0 | 204.8 | 367.0 | 578.7 | 865.3 |
| qwen3.8-27b-think | 44.5 | 45.9 | 82.3 | 154.4 | 276.2 | 482.0 | 759.0 |
| qwen3.6-27b-code | 68.2 | 67.3 | 116.3 | 206.5 | 368.3 | 585.8 | 867.9 |
| qwen3.6-35b-code | 109.6 | 118.2 | 193.1 | 309.8 | 305.3 | 575.7 | 1047.1 |
| qwen3.6-35b-128k-nomtp | 92.1 | 91.9 | 153.6 | 272.5 | 466.7 | 752.1 | 1194.9 |
| gemma4-26b-a4b | 129.6 | 129.5 | 210.0 | 348.1 | 539.1 | 891.7 | 1434.9 |
| qwen3.8-flash-next-vllm | 55.1 | 55.4 | 98.5 | 164.5 | 206.0 | 245.0 | 454.8 |

Against the published 2026-10-19 table every comparable cell is within −3.9 % to +6.0 %: the
stack is where it was. The −3.9 % is `27b-think` serial, whose cell had a latency tail (p90/mean
1.44); its c1 cell matches.

### Depth, prewarmed, no arrivals, aggregate decode tok/s

| Profile | 2K×1 | 16K×1 | 64K×1 | 130K×1 | 258K×1 | 16K×8 | 64K×4 |
|---|---|---|---|---|---|---|---|
| qwen3.8-27b-code | 63.0 | 26.4 | 9.4 | 5.0 | — | 113.5 | 26.3 |
| qwen3.8-27b-think | 47.6 | 45.4 | 39.5 | 33.5 | 26.0 | 192.6 | 108.1 |
| qwen3.6-35b-code | 112.3 | 41.8 | 13.1 | 7.3 | — | 231.3 | 46.3 |
| qwen3.6-35b-128k-nomtp | 95.5 | 90.3 | 75.6 | 62.0 | — | 381.9 | 216.0 |
| gemma4-26b-a4b | 119.6 | 76.8 | 46.9 | 34.7 | 23.1 | 326.4 | 3.6 ¹ |
| qwen3.8-flash-next-vllm | 56.7 | 56.7 | 56.6 | 56.6 | 56.2 | 162.9 | 147.5 |

¹ Not a steady-state figure: TTFT 113.7 s, reproduced on a re-run. The prewarm evidently does not
hold 4×64K in gemma4's 469K-token pool (cause inferred).

The two MTP profiles are the ones that collapse with depth (63 → 5 and 112 → 7 tok/s). That is
the cell block to watch on 0.34, where the split-KV path may accept MTP.

### Other reference points

- **KV pool (tokens):** 27b-code 1,097,728; 27b-think 1,150,051; 3.6-27b-code 1,096,983;
  35b-code 1,339,213; nomtp 1,538,425; gemma4 469,454; Flash-Next 589,824.
- **Swap wall time:** 104–178 s.
- **Band:** 27b-code `llmband` fast before and after; the others have no stored band baseline
  (exit 2) and are fast by comparison with their published rows.
- **Quality** (hard tasks, think, medium effort, 4 samples, 81,920 cap; mean tests passed):
  27b-code date_math 85.7 %, json_strict 78.6 %, mini_scheme 0 %, regex_engine 0 %, with 9 of 16
  samples ending early. nomtp date_math 23.2 %, the rest 0 %, 11 of 16 samples running to the
  cap. Only date_math and json_strict on 27b-code have room to show a drop; the gate on 0.34
  reads those two plus the early-stop and cap counts.
- **Response shape:** thinking is in `reasoning` already; tool calls well-formed.
- **Open observations, not chased:** nomtp 16K×8 reads 381.9 against 439.8 documented (−13 %)
  and 64K×4 216.0 against 231.1; `qwen3.6-35b-code` c8 is no faster than c4 (as published); the
  card-3 slot link is still at Gen4.

Data: `bench/baselines/*-live-20261125.json`, `bench/baselines/depth/*-live-20261125.json`,
`bench/results/baseline-live-20261125/`, `bench/results/codetests-baseline-live-20261125/`.

## Phase 1 — bring-up, `qwen3.8-27b-code` on `v0.34.0` (2026-11-25)

Side port, fresh compile caches, router stopped. Every arm is a fresh spawn; the sweep was run
twice per spawn. **The production argv starts unchanged** (only image, name and port differ).
Cold start 217 s, warm 70–147 s, 202 s when an arm forces a recompile.

### `medium-256`, decode tok/s (first sweep; the repeat agrees within ~2 %)

| Arm | serial | c1 | c2 | c4 | c8 | c16 | c32 |
|---|---|---|---|---|---|---|---|
| 0.26.0 baseline | 67.9 | 66.0 | 116.0 | 204.8 | 367.0 | 578.7 | 865.3 |
| A0 shipped flags | 75.7 | 76.2 | 137.0 | 249.8 | 437.0 | 711.6 | 982.5 |
| A1 extensible KV off | 76.8 | 76.2 | 137.5 | 250.1 | 437.1 | 715.4 | 974.3 |
| A2 `ROCM_ATTN` forced | 68.1 | 67.1 | 123.8 | 227.1 | 389.1 | 604.5 | 829.2 |
| A3 decode capture to 32 | 75.4 | 76.3 | 137.0 | 256.8 | 455.9 | 714.6 | 991.2 |
| A4 `GPU_MAX_HW_QUEUES=2` | 43.7 | 43.6 | 81.3 | 152.2 | 270.5 | 466.5 | 713.5 |
| A4 queue flag unset | 45.2 | 45.2 | 82.0 | 152.5 | 274.6 | 470.2 | 719.3 |
| **A5 = A1 + A3** | 76.9 | 76.3 | 137.7 | 257.0 | 456.0 | 720.9 | 1006.2 |

A5 against the baseline: +13 % serial, +19 % c2, +25 % c4, +24 % c8, +25 % c16, +16 % c32.

### Depth, prewarmed, aggregate decode tok/s

| Arm | 2K×1 | 16K×1 | 64K×1 | 130K×1 | 16K×8 | 64K×4 |
|---|---|---|---|---|---|---|
| 0.26.0 baseline | 63.0 | 26.4 | 9.4 | 5.0 | 113.5 | 26.3 |
| A0 | 87.9 | 86.2 | 81.0 | 73.4 | 305.6 | 165.4 |
| A1 | 91.2 | 84.6 | 84.0 | 74.6 | 310.9 | 171.1 |
| A2 `ROCM_ATTN` | 47.8 | 14.9 | 5.0 | 2.5 | 72.3 | 14.8 |
| A5 | 79.5 | 87.8 | 78.3 | 77.4 | 313.9 | 168.2 |

Needle retrieval 15/15 on A0 and A5.

### What the hypotheses turned out to be

- **Model Runner V2 with `GPU_MAX_HW_QUEUES=1` is fast** (measured): 39.4–39.9 steps/s,
  `mem_busy` 49–50 %, against the 0.26 band baseline of 36.3 at 46 %. Without it, or with `2`,
  the spawn is in the slow band: 22–23 steps/s, `mem_busy` 28–29 %, −35 % serial (one spawn
  each). `2` is not enough here, contrary to vllm#58639. That October's loss was this band is
  consistent with these figures, still inferred.
- **TRITON_ATTN is auto-selected and works with MTP at depth** (measured): 73 tok/s at 130K
  against 2.5 with `ROCM_ATTN` forced on the same image. MTP and depth are no longer a trade on
  this profile. `ROCM_ATTN` is also slower at every short-prompt level. Not tested: depth above 8
  streams.
- **Extensible KV cache costs no throughput** (measured; #69742's −44 % did not reproduce) but
  costs pool: 880,495 tokens on, 1,005,399 off, against 1,097,728 on 0.26. Turn it off.
- **Decode capture** (measured): the shipped `--cudagraph-capture-sizes 1 2 4 8 16 32` resolves
  to decode request sizes {1,2,3,6} under MTP, not 10 as estimated above. Explicit
  `--compilation-config '{"prefill_cudagraph_capture_token_sizes":[1,2,4,8,16,32],"decode_cudagraph_capture_request_sizes":[1,2,4,8,16,32]}'`
  (legacy flag removed) is worth +3.9 % at c8 and +2 % at c4, nothing at c32. Mandatory item 2
  in `CLAUDE.md` needs rewriting at cut-over.
- **Response shape:** `reasoning_content` is gone, thinking is in `reasoning`; tool calls
  well-formed. `bench/depth_bench.py` now reads either.

### Quality gate — first reading (superseded below)

Hard tasks, think, medium effort, 81,920 cap; 0.34 is two runs of 4 samples, 0.26 is one.

| Task | 0.26.0 (n=4) | 0.34.0 A5 run 1 | run 2 | pooled (n=8) |
|---|---|---|---|---|
| date_math | 85.7 % | 58.9 % | 92.9 % | 75.9 % |
| json_strict | 78.6 % | 35.7 % | 64.3 % | 50.0 % |
| mini_scheme | 0 % | 0 % | 0 % | 0 % |
| regex_engine | 0 % | 0 % | 0 % | 0 % |

Early-ended samples: 23 of 32 on 0.34 against 9 of 16 on 0.26; empty replies 14 of 32 against
5 of 16. Same signature as the known 27B early stop (reasoning ends mid-sentence, no answer),
more often. The two 0.34 runs differ by 30 points on both tasks, so n=4 per side is a weak
comparison, and the 0.26 side has only n=4. Not yet separated: the image, TRITON_ATTN under
MTP verify, the A5 capture change, extensible KV off. Next: the same suite at equal n on 0.26,
0.34 A0, and 0.34 with `ROCM_ATTN`.

Data: `bench/baselines/qwen3.8-27b-code-v0.34.0-*-20261125*.json`,
`bench/baselines/depth/qwen3.8-27b-code-v0.34.0-*`, `bench/results/canary-v0.34.0-20261125/`,
`bench/results/codetests-canary-v0.34.0-20261125/`.

### Quality re-check at 12 samples per task — no regression found

Fresh spawn per arm, same suite, `date_math` and `json_strict` only (the other two score 0 on
both versions). The run was stopped during the fourth arm once the picture was clear.

| Arm | date_math | json_strict | empty replies |
|---|---|---|---|
| Q0 0.26.0 production | 64.9 % | 44.6 % | 6 of 24 |
| Q1 0.34.0 shipped flags | 78.6 % | 53.0 % | 3 of 24 |
| Q2 0.34.0 A5 | 80.4 % | 39.9 % | 4 of 24 |
| Q3 0.34.0 `ROCM_ATTN` (partial) | 80.4 % | 34.3 % (5 samples) | 4 of 17 |

The 0.26.0 figures the gate was failing against (85.7 % / 78.6 %) were a favourable draw of
four: at twelve samples the same configuration scores 64.9 % / 44.6 %. Single samples range
from 0 to 14 of 14 on every arm, so differences of 10–15 points between arms are noise at this
size. 0.34 does not end replies early more often. No significance tests were run. **Lesson for
`bench/CLAUDE.md`: four samples per task cannot gate this suite.** Decision (user, 2026-11-25):
proceed to transition and tuning.

Data: `bench/results/codetests-quality-isolation-20261125/`.

## Phase 3a — KV pool sizing on 0.34.0 (`qwen3.8-27b-code`, 2026-11-25/26)

0.34's default ("extensible") KV sizing leaves ~19 % of each card unused. Every arm ran the same
stress: sweep, deep-context cells, a pool fill to ≥95 % with distinct ~120K prompts plus a
32-request burst, 4×8,192-token generations, a 15-minute mixed soak; memory sampled every 2 s.
One spawn per arm. Throughput was within noise of A5 on all of them.

| Arm | Pool (tokens) | vs 0.26.0 | Min free VRAM | Result |
|---|---|---|---|---|
| default, `--gpu-memory-utilization 0.95` | 891,289 | 81.2 % | 3.30 GiB | pass |
| flag removed | 891,289 | 81.2 % | 3.20 GiB | pass, identical |
| margin floor 2 GiB (patched) | 948,344 | 86.4 % | 2.19 GiB | pass, no allocator retries |
| margin floor 1 GiB (patched) | 1,005,399 | 91.6 % | 2.22 GiB | pass, one retry |
| floor 1 GiB, reserve 0.5 GiB (NVIDIA values) | 1,005,399 | 91.6 % | 1.67 GiB | pass, one retry |
| fixed `--kv-cache-memory-bytes` 18.67 GiB | 1,067,080 | 97.2 % | 0.40 GiB | pass |
| fixed 19.17 GiB | 1,095,607 | 99.8 % | 0.05 GiB | **fail**: allocator OOM on three ranks during the fill, recovered by flushing |

- **The cap we pass is not the limit**: removing `--gpu-memory-utilization` changes nothing.
- **Memory outside PyTorch's allocator grew by at most 0.02 GiB** on any card in any arm. The
  3 GiB ROCm floor's stated purpose (runtime scratch mapped outside the allocator) is not what
  consumes memory here.
- **What does consume it is the allocator's own reservation**, which grows 2.4–3.2 GiB under
  load while live allocations grow only ~0.75–1 GiB. With the extensible path a per-process
  cap bounds that growth; with a fixed KV size nothing does, which is why 19.17 GiB ran dry.
  So some margin is genuinely needed; 3 GiB is more than this workload used.
- Pass and fail on the fixed-size path are 0.5 GiB apart on one spawn each: do not deploy 18.67.
- Offload connectors (from source, not run): the CPU offload connectors keep extensible sizing
  and add no meaningful VRAM; their cost is pinned host RAM.

Draft upstream patch (opt-in env vars for the floor and reserve, defaults unchanged):
`bench/results/kv-sizing-v0.34.0-20261125/margin-patch.diff` with evidence in
`margin-patch-notes.md`. Dry-run applied only; not filed. Open lever, untested: allocator
settings that reduce reservation growth.

## Phase 2 — remaining profiles on 0.34.0 (2026-11-26) — done (all pass), resumed after the drive swap

**Was blocked on hardware; resumed the same day.** The model drive (`nvme1`, `/mnt/models`) stopped responding at
02:38 UTC while `qwen3.6-35b-code` was loading: read timeouts, failed controller reset, device
disabled, ext4 shut down. Kernel excerpt in
`bench/results/canary-v0.34.0-20261126/qwen3.6-35b-code/kernel-nvme1-failure.log` (local to the
rig: `*.log` is gitignored, so it is not in the repo). The kernel
log is clean up to that point, so the two profiles below were measured on a healthy drive.
At the time these five were not run: `qwen3.6-35b-code`, `qwen3.6-27b-code`, `qwen3.8-27b-think` and both
Flash-Next profiles. All five were run after the drive swap; see the subsection below.

Both completed profiles started on 0.34.0 with the live argv unchanged (image only), one spawn
each, `medium-256` sweep as Phase 0, decode tok/s 0.26.0 → 0.34.0:

| Profile | serial | c8 | c16 | c32 |
|---|---|---|---|---|
| qwen3.6-35b-128k-nomtp | 92.1 → 103.3 (+12 %) | 466.7 → 476.7 (+2 %) | 752.1 → 755.4 (0 %) | 1194.9 → 1220.5 (+2 %) |
| gemma4-26b-a4b | 129.6 → 127.1 (−2 %) | 539.1 → 565.8 (+5 %) | 891.7 → 881.9 (−1 %) | 1434.9 → 1546.2 (+8 %) |

Depth, prewarmed, aggregate tok/s:

| Profile | 2K | 16K | 64K | 130K | 16K×8 | 64K×4 |
|---|---|---|---|---|---|---|
| nomtp | 95.5 → 107.5 | 90.3 → 103.6 | 75.6 → 95.0 | 62.0 → 86.4 (+39 %) | 381.9 → 435.1 | 216.0 → 227.2 |
| gemma4 | 119.6 → 121.0 | 76.8 → 81.8 | 46.9 → 48.5 | 34.7 → 34.5 | 326.4 → 312.8 | 3.6 → 136.4 † |

† Phase 0's 64K×4 cell on gemma4 was a stall (TTFT 113.7 s) that did not reproduce; not a speedup.

- KV pools shrink as on the 27B: nomtp 1,538,425 → 1,338,166 (−13 %), gemma4 469,454 → 373,839 (−20 %).
- The legacy capture-size flag resolves decode sizes to 1..32 on both (no MTP), so only MTP
  profiles need the explicit `--compilation-config`.
- Backend unchanged on both (TRITON_ATTN). Needle 15/15 on nomtp. Smoke passed; `reasoning`
  replaces `reasoning_content`. gemma4 with `enable_thinking` returns raw thought text in
  `content` (no reasoning parser in the live argv; not checked against 0.26).
- Startup 192 s each (first compile on the canary cache).

Driver scripts: `~/.local/share/llmstack/canary-034/drivers/` (copied off tmpfs).

### Resumed on the replacement drive (2026-11-26, from ~20:15 UTC)

The drive was replaced and every model re-downloaded to it on 2026-11-26. Weights are the same
upstream revisions; for the three Qwen FP8 checkpoints `chat_template.jinja` and
`tokenizer_config.json` were put back to their pre-2026-11-07 versions (the 2026-11-07 upstream
commits changed only those two files), so the prompts match the Phase 0 baselines. Revisions and
the kept upstream copies: `/mnt/models/llm/PROVENANCE.txt`. The two profiles above were measured
on the old drive before it failed; everything below is on the new one. Kernel log checked for
NVMe errors after every profile: none.

Same recipe as above: one fresh spawn per profile on `v0.34.0`, side port, `llmband` before and
after the sweep, `medium-256` sweep at `--requests 128 --serial-n 8`, the three prewarmed depth
cells, needle 3 depths × 5 positions, smoke (plain, thinking, tool call). **Every figure is one
spawn per arm** (one 0.26.0 spawn in Phase 0, one 0.34.0 spawn here); differences of a few
percent are not results. MTP profiles run in the `tuned` form: the legacy
`--cudagraph-capture-sizes 1 2 4 8 16 32` replaced by the Phase 1 `--compilation-config`
(prefill token sizes and decode request sizes both `[1,2,4,8,16,32]`). So an MTP row differs
from its 0.26 row in two things, the image and the capture change; Phase 1 put the capture
change alone at about +4 % at c8 and +2 % at c4. Extensible KV left at its default, as for the
two profiles above.

#### `qwen3.6-35b-code` (MTP, 3B-active MoE) — pass

Fresh spawn (`spawn2`; `spawn1` is the one that died with the drive). Argv: live profile, image
and capture change only.

| | serial | c8 | c16 | c32 |
|---|---|---|---|---|
| 0.26.0 | 109.6 | 305.3 | 575.7 | 1047.1 |
| 0.34.0 tuned | 150.2 (+37 %) | 671.4 (+120 %) | 986.9 (+71 %) | 1562.9 (+49 %) |

c1 118.2 → 148.6, c2 193.1 → 230.2, c4 309.8 → 399.4. The 0.26 profile's c8 was no faster than
its c4 (Phase 0, and as published); on 0.34 the curve is monotonic, so most of the c8 figure is
that dip disappearing rather than a 2.2x speedup in general.

Depth, prewarmed, aggregate tok/s:

| 2K | 16K | 64K | 130K | 16K×8 | 64K×4 |
|---|---|---|---|---|---|
| 112.3 → 167.1 | 41.8 → 161.6 | 13.1 → 143.0 | 7.3 → 140.4 (19x) | 231.3 → 608.7 | 46.3 → 297.7 |

This is the Phase 1 finding on a second MTP profile: on 0.26 the MTP profile collapsed with
depth (ROCM_ATTN, split-KV path closed by MTP); on 0.34 TRITON_ATTN is auto-selected
(`Overriding with TRITON_ATTN out of potential backends: ['TRITON_ATTN', 'ROCM_ATTN']`) and
decay across the window is 1.19x. 130K TTFT 0.81 → 0.33 s (prewarmed). Accepted tokens per
step are unchanged (2.15 → 2.15 at 2K and 130K), so none of this is MTP acceptance.

- KV pool 1,339,213 → 1,087,351 tokens (−19 %), extensible sizing as on the others.
- Resolved capture sizes (startinfo): decode request sizes `[1, 2, 4, 8, 16, 32]`, prefill
  token sizes `[1, 2, 4, 8, 16, 32]`, `FULL_AND_PIECEWISE`; same capture-progress shape as
  Phase 1 A5 (decode FULL 15 graphs).
- Startup 212 s (first compile of this model on the canary cache).
- `llmband` exit 2 before and after (no stored baseline); 126 steps / 256 tokens in 1.59 s,
  i.e. ~79 steps/s.
- Needle 15/15 (16K, 64K, 130,752). Smoke passed: `reasoning` field, tool call well-formed.
- 0 preemptions over the run; MTP acceptance 52 % of draft tokens.

#### `qwen3.6-27b-code` (MTP, dense 27B, previous generation) — pass

One spawn, tuned capture sizes, otherwise the live argv.

| | serial | c8 | c16 | c32 |
|---|---|---|---|---|
| 0.26.0 | 68.2 | 368.3 | 585.8 | 867.9 |
| 0.34.0 tuned | 75.1 (+10 %) | 448.9 (+22 %) | 714.2 (+22 %) | 1011.4 (+17 %) |

c1 67.3 → 76.3, c2 116.3 → 139.5, c4 206.5 → 256.7. Within ~2 % of Phase 1's A5 on
`qwen3.8-27b-code` (76.9 / 456.0 / 720.9 / 1006.2) at every level, as the two shared a row on
0.26 too.

Depth, prewarmed, aggregate tok/s (0.34.0 only — Phase 0 ran no depth cells on this profile):

| 2K | 16K | 64K | 130K | 16K×8 | 64K×4 |
|---|---|---|---|---|---|
| 91.1 | 84.7 | 81.0 | 72.3 | 335.1 | 174.1 |

No 0.26 reference on the same method, so no ratio is quoted; the shape (1.26x decay across the
window) matches Phase 1's 27B on 0.34, where the 0.26 reference fell from 63.0 to 5.0.

- KV pool 1,096,983 → 876,640 tokens (−20 %).
- Backend TRITON_ATTN by auto-selection under MTP (same log line as above). Resolved capture
  sizes as on the 35B: decode and prefill `[1, 2, 4, 8, 16, 32]`.
- Startup 202 s (first compile of this model on the canary cache).
- `llmband` exit 2 before and after (no stored baseline); 118 steps in 2.97 s and 3.00 s, i.e.
  ~40 steps/s, the same as Phase 1's fast 27B (39.4–39.9).
- Needle 15/15. Smoke passed. 0 preemptions; acceptance 53 % of draft tokens.

#### `qwen3.8-27b-think` (no MTP, TRITON_ATTN, 262K + CPU KV offload) — pass

Live argv unchanged apart from image, name and port (legacy capture flag kept: no MTP). That
includes the uncommitted live settings: `--max-model-len 262144` and
`SimpleCPUOffloadConnector` with `cpu_bytes_to_use` 96 GiB. The connector's options are the
same on 0.34 (read in the image source); it came up eager, 24.00 GB pinned per rank, 1,890 CPU
blocks.

| | serial | c8 | c16 | c32 |
|---|---|---|---|---|
| 0.26.0 | 44.5 | 276.2 | 482.0 | 759.0 |
| 0.34.0 | 49.9 (+12 %) | 297.9 (+8 %) | 520.1 (+8 %) | 857.6 (+13 %) |

c1 45.9 → 49.7, c2 82.3 → 87.8, c4 154.4 → 166.1. Phase 0 noted a latency tail on the 0.26
serial cell (p90/mean 1.44); against its c1 cell the single-stream gain is +8 %.

Depth, prewarmed, aggregate tok/s:

| 2K | 16K | 64K | 130K | 258K | 16K×8 | 64K×4 |
|---|---|---|---|---|---|---|
| 47.6 → 50.5 | 45.4 → 49.6 | 39.5 → 46.8 | 33.5 → 43.6 (+30 %) | 26.0 → 38.4 (+48 %) | 192.6 → 219.6 | 108.1 → 111.3 |

The deeper the prompt the larger the gain; decay across the window 1.83x → 1.32x. Prewarmed
TTFT at 16K×8 1.55 → 1.06 s.

- KV pool 1,150,051 → 969,607 tokens (−16 %). CPU offload pool on top, unchanged in size.
  Exercised only lightly: 99 offload stores over the run, no preemptions. No test here forces
  KV out to the CPU pool and back, so its recall path is not checked by this run.
- Backend `Using TRITON_ATTN backend (selected via --attention-backend)` (the flag is in the
  argv). Resolved capture sizes `[1, 2, 4, 8, 16, 32]` for both prefill and decode, as expected
  without MTP.
- Startup 197 s. Host MemFree fell from 19 GiB to 1.2 GiB at startup (page cache from the
  re-download giving way to the 96 GiB pinned pool); the spawn read fast regardless.
- `llmband` exit 2 before and after (no stored baseline): 256 steps in 4.99 s and 5.03 s,
  ~51 steps/s, against a 0.26 serial of 44.5 tok/s, so not a slow draw (inferred).
- Needle 15/15 (16K, 64K, 131,072). Smoke passed.

#### `qwen3.8-flash-next-vllm` (W4A16 + FP8 PLE, TP4+EP, vision on) — pass

The old pin is `nightly-8cbd5d0` (vLLM 0.31.1rc1.dev173), not 0.26. The live argv is unchanged
apart from image, name and port; `llm-prestart` ran first with the live arguments (MemFree
114.6 GiB, no drop needed).

**PLE offload needed no flag.** The live argv carries no `VLLM_PLE_CPU_OFFLOAD`, and no 0.34
source reads that name. 0.34's `EngramConfig` defaults to `cpu_offload=True`, and the log
confirms it took effect:
- `Resolved Engram configuration: EngramConfig(cpu_offload=True, ...)`.
- Each rank logs `Initialized AMD PLE embedding ... weight_device=cpu, pinned=True`.
- Model load is 19.01 GiB per GPU.
- Host MemFree fell from 114.6 GiB to 1.2 GiB at startup.

So `--engram-config` was not needed and was not added.

| | serial | c8 | c16 | c32 |
|---|---|---|---|---|
| nightly-8cbd5d0 | 55.1 | 206.0 | 245.0 | 454.8 |
| 0.34.0 | 60.8 (+10 %) | 244.9 (+19 %) | 242.8 (−1 %) | 461.6 (+1.5 %) |

c1 55.4 → 60.7, c2 98.5 → 105.5, c4 164.5 → 168.6. c16 still sits level with c8 (p90 12.2 s),
the same plateau as on the nightly. The c8 gain is one spawn per arm, and Flash-Next's c8 has
spread widely across spawns before: 140–182 unflagged, and 204.1 / 204.3 flagged, in the
2026-10 readings. The c16 and c32 cells are
inside the earlier spawn-to-spawn spread, so they show no change, not a gain.

Depth, prewarmed, aggregate tok/s:

| 2K | 16K | 64K | 130K | 258K | 16K×8 | 64K×4 |
|---|---|---|---|---|---|---|
| 56.7 → 62.0 | 56.7 → 61.7 | 56.6 → 61.7 | 56.6 → 61.7 | 56.2 → 61.4 | 162.9 → 169.9 | 147.5 → 144.5 |

The single-stream rate is still flat across the window, now about 9 % higher. The concurrent
depth cells did not move.

- **KV pool 589,824 → 377,487 tokens (−36 %)**, the largest drop of any profile. Auto-fit still
  picks `max_model_len` 262,144, but at 1.44x concurrency for a full-length request. The
  extended KV is 4.74 GiB per GPU, and the log reports 9.77 GiB still free after warmup on
  rank 0. Idle VRAM after startup is ~26.7 GB per GPU. No preemptions occurred in this run, but
  this pool is tighter for many concurrent long requests, and nothing here tests that. It is the
  Phase 3 tuning candidate (`--kv-cache-memory-bytes` or the extensible-KV floor), not a fail.
- Capture sizes resolved to `[1, 2, 4, 8]` for prefill and decode, which is what the live
  `--cudagraph-capture-sizes 1 2 4 8` asks for. There is no MTP, so the legacy flag is honest
  here.
- The log names no attention backend for the full-attention layers, as on the nightly. GDN uses
  the Triton/FLA prefill kernel, MoE uses `TRITON WNA16`, and ViT uses Torch SDPA.
- Startup 212 s.
- `llmband` exit 2 before and after the sweep. `config/band-baselines.json` is gitignored and
  only holds `qwen3.8-27b-code`, so no other profile has a baseline. The probe read 256 steps in
  4.01 s and 4.03 s (~64 steps/s). The fast reference in CLAUDE.md is 57.8, so this was not a
  slow draw (inferred).
- Smoke passed, including the image request: all four shapes were named correctly in 2.1 s,
  from 819 prompt tokens. Needle 15/15. 0 preemptions.

#### `qwen3.8-flash-next-vllm-text` — smoke only, pass

The live argv (`--language-model-only`, `GPU_MAX_HW_QUEUES=1`, confirmed in provenance) is
unchanged apart from image, name and port. Startup took 171 s. PLE offload behaved as above
(`weight_device=cpu, pinned=True`). The KV pool is 402,491 tokens, versus 377,487 with the
vision tower on. The plain, reasoning and tool-call smoke tests passed. No sweep was run, by
design.

## Phase 3b — margin: upstream is already on it

The 3 GiB ROCm floor is a three-week-old stopgap (vllm #65418, MI355 CI OOMs). Open upstream:
#69471 (floor back to 2 GiB; one Gemma 4 MTP test still fails 5/20 at 2 GiB) and #69994
(expandable segments under the torch cap, ROCm; TP>1 untested there). Consequences: do not file
the env-var patch as drafted; one spawn per arm cannot clear a floor when failures are
intermittent; next test is expandable segments at floors 3/2/1 GiB, several spawns each.

## Phase 3c — margin tuning with repeated spawns (2026-11-27)

**Result: with #69994 backported, a 1 GiB floor recovers part of the lost KV pool. It leaves
about as much free VRAM as the stock config that ships now.** No arm failed in 15 spawns.

| Profile | Stock pool, % of 0.26 | Floor 1 GiB + #69994, % of 0.26 |
|---|---|---|
| `qwen3.8-27b-code` | 81.2 % | 91.6 % |
| `qwen3.6-35b-code` | 81.3 % | 90.9 % |
| Flash-Next | 67 % | 94 % |

That is about half the loss on the 27B and the 35B, and most of it on Flash-Next.

Nothing is deployed: `config/models.yaml` is unchanged. The proposed lines are at the end of this
section.

### Step 0 — does expandable segments work on this torch?

The image ships torch 2.13.0+rocm10.0.0 (HIP 7.15). I ran the PR's own scenario in the image on
one GPU, with a 700 MiB cap set by `set_per_process_memory_fraction`, as 0.34 does. Script and
output: `mech_test.py` and `mechanism-step0.txt`.

| Mode | Result |
|---|---|
| stock | **OOM**: "Tried to allocate 300 MiB … 700 MiB allowed; 320 MiB allocated, 280 MiB reserved but unallocated" (1 retry, 1 OOM) |
| runtime toggle under the cap (what #69994 does) | pass, `expandable_segments` live |
| `PYTORCH_ALLOC_CONF=expandable_segments:True` | pass |
| `PYTORCH_CUDA_ALLOC_CONF=…` | pass |
| `PYTORCH_HIP_ALLOC_CONF=…` | pass |

So all three env names work on this build, and so does the runtime toggle. The stock failure is
exactly the one the PR describes: the cap counts memory that is reserved but unusable.

**Every E arm below used the bind-mounted backport, not env-only.** The mounted file is
`extensible_kv_cache.py` with the PR #69994 hunk (head `a150a16`, kept exactly in
`config/patches/vllm-v0.34.0/pr69994-extensible-kv-cache-expandable-segments.diff`), the floor
constant changed, and two log lines. Each spawn was gated on 4 floor lines and 4
`expandable_segments live=True env=''` lines, one per rank. Every E spawn passed the gate.
Env-only was not used because it would turn expandable segments on for the whole process,
not just while the cap is set, which is a different configuration from the PR.

### Step 1 — `qwen3.8-27b-code`, three fresh spawns per arm

Every spawn ran:
- a pool fill: 12 distinct ~120K prompts plus a 32-request burst, to ≥88 % KV usage;
- tool-call and reasoning checks;
- 4×8,192-token generations;
- a 10-minute mixed soak at concurrency 8.

Spawn 1 of each arm also ran the `medium-256` sweep and three depth cells. Host and torch memory
were sampled every 2 s. `llmband` read **fast** on every spawn.

| Arm | Spawns | Result | Pool (tokens) | % of 0.26.0 (1,097,728) | Min free VRAM, worst card | Torch reserved growth under load | Cap − peak reserved | Retries / OOMs | Request errors | Soak TTFT p99 s | serial / c8 / c32 tok/s (spawn 1) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S3 stock (floor 3) | 3 | 3 pass | 891,289 | 81.2 % | 3.27 GiB | +3.10 GiB | 1.15 GiB | 0 / 0 | 0 | 40.4 / 40.6 / 37.2 | 75.9 / 451.2 / 1018.6 |
| E2 backport, floor 2 | 3 | 3 pass | 948,344 | 86.4 % | 4.17 GiB | +1.20 GiB | 2.05 GiB | 0 / 0 | 0 | 27.9 / 44.7 / 54.1 | 75.1 / 455.3 / 1002.4 |
| E1 backport, floor 1 | 3 | 3 pass | 1,005,399 | 91.6 % | 3.18 GiB | +1.20 GiB | 1.06 GiB | 0 / 0 | 0 | 44.5 / 43.3 / 32.4 | 75.0 / 452.2 / 982.3 |
| *F1 floor 1, no expandable (Phase 3a, 1 spawn)* | 1 | pass | 1,005,399 | 91.6 % | 2.22 GiB | +2.4–3.2 GiB | — | 1 / 0 | 0 | — | — |

- **Expandable segments cut the allocator's growth under load from +3.10 to +1.20 GiB per
  rank.** Live allocations grow the same ~0.6–0.75 GiB in every arm. The figures repeat to
  0.01 GiB across all three spawns of each arm, so this is not noise.
- With that growth gone, E2 ends with **more** free VRAM than stock (4.17 vs 3.27 GiB) on a
  6 % larger pool. E1 ends level with stock (3.18 vs 3.27 GiB) on a 12.8 % larger pool, with
  the same headroom under the cap (1.06 vs 1.15 GiB).
- Without expandable segments (F1, Phase 3a), floor 1 left 2.22 GiB free and hit an allocator
  retry. Expandable segments are what make floor 1 sound; the floor alone is not.
- Memory outside torch's allocator did not grow on any spawn, as in Phase 3a.
- Preemptions (0–12 per spawn) all came from the pool fill, which is built to cause them, and
  appeared in every arm.
- The soak's longest token gap was 5.16–5.25 s on every spawn: chunked-prefill pauses, not
  arm-specific. Gaps over 5 s per spawn: S3 28 / 18 / 32, E2 21 / 12 / 18, E1 5 / 13 / 13.
- Throughput is unchanged. The sweep cells are inside spawn-to-spawn spread. Prewarmed depth
  cells (S3 / E2 / E1): 130K×1 74.7 / 80.2 / 70.8; 64K×4 170.7 / 169.7 / 170.9; 16K×8
  309.2 / 323.8 / 309.4 tok/s.
- Startup was 70–71 s on every spawn.

**Arms not run:**
- **E3** (expandable segments, floor 3) is dominated: the pool is fixed by the floor, so it
  would give S3's pool with E2's slack. It answers no sizing question.
- **F1** was not re-run. Phase 3a's single spawn above stands in for it, and it is already the
  worse of the two floor-1 options.
- **Fixed 18.67 GiB with expandable segments** was cut for budget. Note that the backport is
  inert on the fixed `--kv-cache-memory-bytes` path, which sets no cap, so that arm would have
  needed env-wide `PYTORCH_ALLOC_CONF`.

### Step 2 — E1 against stock on Flash-Next and the 35B

Argv was built from the live config, as `gen_argv.py` does. Flash-Next ran `llm-prestart` with
its live arguments first. Flash-Next pools are compared with its 0.26-era nightly pool of
589,824; the 35B with 0.26.0's 1,339,213.

| Profile / arm | Spawns | Result | Pool (tokens) | % of 0.26 | Min free VRAM | Reserved growth | Cap − peak reserved | Retries / OOMs | Request errors | Preemptions | Soak TTFT p99 s | serial / c8 / c32 (spawn 1) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Flash-Next S3 | 2 | 2 pass | 393,619 / 395,232 | 66.7 / 67.0 % | 2.88 GiB | +2.60 GiB | 1.39 GiB | 0 / 0 | 0 | 13 / 12 | 51.4 / 60.6 | 60.6 / 247.6 / 446.5 |
| Flash-Next E1 | 2 | 2 pass | 553,325 / 554,132 | 93.8 / 93.9 % | 2.40 GiB | +1.06 GiB | 0.92 GiB | 0 / 0 | 0 | 17 / 17 | 64.2 / 51.3 | 60.6 / 246.3 / 470.4 |
| 35B-code S3 | 1 | pass | 1,088,989 | 81.3 % | 3.28 GiB | +3.29 GiB | 1.36 GiB | 0 / 0 | 0 | 0 | 9.8 | — |
| 35B-code E1 | 1 | pass | 1,217,331 | 90.9 % | 3.89 GiB | +1.40 GiB | 2.06 GiB | 0 / 0 | 0 | 10 | 9.1 | — |

- **Flash-Next gets back 160K tokens, +40 %.** That is most of its 36 % loss. Its full-length
  (262K) concurrency goes from 1.50x to 2.11x.
- The Flash-Next stock pool read 393–395K here, against 377,487 in Phase 2. That spawn was
  taken on a different day, after a different page-cache state.
- On Flash-Next, E1 leaves 0.5 GiB less free VRAM than stock (2.40 vs 2.88 GiB). This is the
  one place E1 is tighter than the shipped config. Torch's headroom under the cap is still
  0.92 GiB, with no retries.
- `llmband` returned undecided (exit 2) on every Step 2 spawn, because these profiles have no
  baseline. Neither arm looks like a slow draw, but that is inferred:
  - Flash-Next serial was 60.6 on both arms, against 60.8 in Phase 2.
  - The 35B long generations ran at 584.6 and 590.1 tok/s.
- The soak request counts differ between spawns (58–88 on Flash-Next) because the long/short
  mix is random. Stock spawn 2 (25.3 tok/s) was as slow as E1 spawn 1 (24.1), so this is mix,
  not arm.
- **35B: +128K tokens (+11.8 %), and E1 leaves *more* free VRAM than stock** (3.89 vs 3.28
  GiB).
  - The extended KV went from 12.05 to 13.47 GiB on rank 0, a gain of 1.42 GiB, not the full
    2 GiB. The torch cap fell 1.19 GiB (16.51 → 15.32 GiB).
  - Both spawns logged 2.67 GiB of torch reservation growth at warmup. 0.75 × 2.67 ≈ 2.0 GiB,
    so at floor 1 the 35B's margin is probably set by that term, not by the floor. This is
    inferred from the log figures: the log does not print the margin itself.
  - Meanwhile expandable segments removed 1.9 GiB of reserved growth, more than the pool took.
  - One spawn per arm; the rest was cut for budget. The S3 fill
  happened to preempt nothing and E1's preempted 10 times, with KV usage at ~1.0 on both; the
  burst's timing decides that.

### Recommendation

**Adopted 2026-11-27** on the three profiles below (`config/models.yaml`; the tests in
`tests/test_configure.py` pin the set). The text below is the recommendation as written.

**Adopt the backport with a 1 GiB floor on `qwen3.8-27b-code`, `qwen3.8-flash-next-vllm` and
`qwen3.6-35b-code`.** On each it recovers 10–27 points of the 0.26 pool.
No spawn had a failure or an allocator
retry, and throughput did not change where it was measured: the 27B and Flash-Next sweeps and
the 27B depth cells. The 35B was not swept. One memory cost: on Flash-Next it leaves 0.5 GiB
less free VRAM than stock.

**Confidence: moderate.** Memory behaviour repeats almost exactly from spawn to spawn, and every
arm stays well clear of the cap. The thin part is the number of spawns. E1 ran
on six spawns (3 on the 27B, 2 on Flash-Next, 1 on the 35B) with no failure.
- Upstream saw 4–5 failures in 20 starts. Zero failures in six spawns cannot rule out a 1-in-5
  failure rate: at that rate, about 1 run in 4 would still show zero.
- Upstream's failures (#69471) were a Gemma 4 MTP test in upstream CI, at floor 2 without
  expandable segments. That is a different model and allocator mode from this test.

**Safer alternative: E2 (floor 2).** On the 27B it is strictly safer than stock on every
measure (more free VRAM, twice the cap headroom) and still gives back +6.4 %. Take it if the
1 GiB floor ever produces an OOM.

Proposed change per profile (one extra mount; argv otherwise unchanged; `GPU_MAX_HW_QUEUES=1`
and capture sizes untouched; no KV dtype change):

```yaml
-v __LLMSTACK_DIR__/config/patches/vllm-v0.34.0/extensible_kv_cache.py:/usr/local/lib/python3.12/dist-packages/vllm/v1/worker/extensible_kv_cache.py:ro
```

- `config/patches/vllm-v0.34.0/extensible_kv_cache.py` is the 0.34.0 file plus the #69994 hunk
  plus `KV_CACHE_MARGIN_FLOOR_BYTES = 1 << 30`. It is the canary file minus its two log lines.
  The full diff against 0.34.0 is `extensible_kv_cache-pr69994-floor1.diff`.
- The mount is pinned to the 0.34.0 file. Drop it on the next image bump: #69994 or #69471 may
  have landed by then, and an old file shadowing new code would be worse than either.
- Do not set `PYTORCH_ALLOC_CONF` alongside it. The backport defers to any `expandable_segments`
  value set in env, which would change what was tested.

**Not tested:**
- The gemma4 profiles. These are where upstream's failures are; leave them on stock until they
  have their own spawns.
- `qwen3.8-27b-think`, `-fast`, `qwen3.6-27b-code`, `qwen3.6-35b-128k-nomtp`, and the
  Flash-Next `-text` clone.
- The fixed-KV path with expandable segments.
- Workloads longer than the 10-minute soak, and request mixes other than this harness's.
- A second 35B spawn per arm (cut for budget).
- Repeated cold starts at the rate upstream used (20 per arm).

Data: `bench/results/kv-margin-v0.34.0-20261127/`. Each spawn directory has:
- `spawnsum.json`;
- the torch and host memory traces;
- `argv-changes.txt`, the argv diff against the live config. The raw `argv.bin` is not
  committed, because it contains absolute paths;
- provenance and the stress outputs.

Logs are gitignored.

## Phase 4 — transition (2026-11-27)

**Transition (branch `vllm-upgrade-2026-11`).** What the transition commit changed:

- `config/models.yaml`: every vLLM profile pins `docker.io/vllm/vllm-openai-rocm:v0.34.0`,
  both Flash-Next profiles included (from `nightly-8cbd5d03006c33185f402249ff2b448efd594986`),
  and so does the template at the bottom.
- The four MTP profiles (`qwen3.8-27b-code`, `qwen3.8-27b-fast`, `qwen3.6-27b-code`,
  `qwen3.6-35b-code`) replace `--cudagraph-capture-sizes 1 2 4 8 16 32` with
  `--compilation-config '{"prefill_cudagraph_capture_token_sizes":[1,2,4,8,16,32],"decode_cudagraph_capture_request_sizes":[1,2,4,8,16,32]}'`.
  Under MTP on Model Runner V2 the legacy flag resolves decode capture to request sizes
  {1,2,3,6}. The explicit form was worth +3.9% at c8 and +2% at c4 in Phase 1 (A5). The no-MTP
  profiles keep the legacy flag, and Flash-Next keeps `1 2 4 8`.
- No other flag changed. `GPU_MAX_HW_QUEUES=1` stays on every profile; it is still required on
  0.34 (unset or `=2` gives the slow band, −35% serial). Extensible KV stays at its default.
- Other live pins moved to `v0.34.0`: `scripts/pcie-link-check`, `scripts/tune-dense-fp8`, and
  `scripts/tunableop-tune` (which also takes the `--compilation-config` form, since it runs the MTP
  27B). The test fixtures moved too.
- `scripts/llmkv` reads the 0.34 `decode_cudagraph_capture_request_sizes` config dump. Before
  this it returned `[]` for a 0.34 log.
- `bin/llmproxy` no longer drops a stripped tool-call chunk that also carries `reasoning` or
  `reasoning_content`.
- Docs: root `CLAUDE.md`, `config/CLAUDE.md`, `bench/CLAUDE.md`, `README.md`, `docs/models.md` and
  `docs/rdna4-long-context.md` now describe the 0.34 pin, both capture forms, the `reasoning` field,
  the smaller KV pools and TRITON_ATTN with MTP.
- **Not canaried on 0.34.** `qwen3.8-27b-fast` has the same weights and flags as `-code` apart
  from template defaults. `qwen3.6-35b-fast` carries `--kv-cache-dtype fp8`, which was left as is.
  `gemma4-26b-fp8` lacked `GPU_MAX_HW_QUEUES=1` at the transition; it gained it on 2026-11-27
  (unmeasured on that profile). Smoke-test all three.
- **Rollback (emergency only, per the 0.34-minimum policy).** Re-pin
  `docker.io/vllm/vllm-openai-rocm:v0.26.0`, which is still local and is the same image as
  `localhost/llmstack-vllm-rollback:v0.26.0`. **Remove the KV margin patch mount** from the three
  patched profiles (it would shadow a different module on 0.26). Restore the legacy capture flag
  on the four MTP profiles, and Flash-Next's nightly pin. The 0.34 compile-cache key differs, so
  the first 0.34 start is a cold compile (171-217 s measured; warm starts 70-147 s).
- **KV margin patch fallbacks, in order:** floor 2 (set `KV_CACHE_MARGIN_FLOOR_BYTES = 2 << 30`
  in the patch file; E2 measured 948,344 tokens on the 27B), then stock (remove the mount). Both
  stay on v0.34.0.

**Live switch: done 2026-11-27.** The live config moved to v0.34.0, with a backup of the
previous live config kept. The default model (`qwen3.8-27b-code`) was verified through the
router:
- `llmband`: fast band, 40.03 steps/s against a 36.31 baseline.
- `medium-256`: serial 77.1, conc=8 450.7, conc=32 1009.9 tok/s.
- KV pool 891,289 tokens. That is stock sizing: the live check ran **before** the KV margin
  patch was added. The patched pools above were measured with the canary file (the shipped file
  minus two log lines). The shipped file itself has not booted yet.

**Then (same day):** the KV margin patch mount went onto `qwen3.8-27b-code`,
`qwen3.8-flash-next-vllm` and `qwen3.6-35b-code`, and `-e GPU_MAX_HW_QUEUES=1` went onto
`gemma4-26b-fp8`. Tests now check that every vLLM profile carries the flag, and that a mounted
patch sits on the image its directory names.

### Open items

- **The shipped patch file has booted only as its canary twin.** First start of each patched
  profile: check the pool against Phase 3c (27B 1,005,399; Flash-Next ~553K; 35B 1,217,331).
- **Profiles the patch was not tested on** stay stock: `qwen3.8-27b-think`, `qwen3.8-27b-fast`,
  `qwen3.6-27b-code`, `qwen3.6-35b-128k-nomtp`, `qwen3.6-35b-fast`, `qwen3.8-flash-next-vllm-text`,
  and both gemma4 vLLM profiles (where upstream's failures were).
- **The patch's thin evidence.** 6 clean floor-1 spawns (15 across all arms) cannot rule out an
  intermittent failure; the 35B had one spawn per arm and no throughput sweep.
- **Not canaried on 0.34:** `qwen3.8-27b-fast`, `qwen3.6-35b-fast`, `gemma4-26b-fp8`.
- **Upstream contribution not filed.** The R9700 measurements behind the floor and #69994 were
  not posted upstream.
- **35B routing by depth not re-decided.** On 0.34 `qwen3.6-35b-code` (MTP, TRITON_ATTN)
  read 140.4 tok/s at 130K against 86.4 for `qwen3.6-35b-128k-nomtp`.
- **The `--max-num-seqs` 3D-path threshold has not been re-read for 0.34** (it was 32 on 0.26;
  it may be lower, around 16, untested).
