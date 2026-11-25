# vLLM 0.26.0 → 0.34.0 upgrade — November 2026

**Status: in progress.** Phase 0 (fresh baseline of the stack as it runs today) started
2026-11-25. Nothing in `config/models.yaml` references 0.34 yet.

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

## Phase 0 — baseline (2026-11-25)

_Filled in when the run completes._

## Phase 1–4

_Not started._
