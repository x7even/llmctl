# vLLM 0.26.0 → 0.34.0 upgrade — November 2026

**Status: in progress.** Phase 0 (fresh baseline of the stack as it runs today) finished
2026-11-25. Phase 1 (bring-up on `v0.34.0`): `qwen3.8-27b-code` starts and is faster everywhere, and a
12-sample quality re-check found no regression. Tuning and the other profiles are next. Nothing in `config/models.yaml` references 0.34 yet.

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

## Phase 2–4

_In progress: KV pool sizing on 0.34, then bring-up of the remaining profiles._
