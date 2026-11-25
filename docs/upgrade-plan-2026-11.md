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
| 1 | **Bring-up on `v0.34.0`.** Same flags, side port, router untouched. `qwen3.8-27b-code` first (the profile that failed in October), then one MoE (`qwen3.6-35b-128k-nomtp`), then `gemma4-26b-a4b` and Flash-Next. Two image arms: `v0.34.0` and `v0.34.0-rocm100`. Fix flag renames and startup failures. | Each profile starts, serves, passes tool-call, reasoning-field and needle checks |
| 2 | **Re-run.** The Phase 0 matrix, cell for cell, on the winning image arm. Quality gate before throughput (`bench/CLAUDE.md`). | Known before tuning: where 0.34 is ahead, level, behind |
| 3 | **Tune, re-run.** One variable at a time, matched pairs, fresh spawn per arm, under real serving load only. Candidates come from the Phase 2 gaps and from the release-notes review. Starting list: `GPU_MAX_HW_QUEUES` (1 vs 2 vs unset, since the band behaviour may differ on a new runtime), capture sizes, attention backend per profile, Model Runner V2 single-stream behaviour, KV pool and `--gpu-memory-utilization`. | Every `medium-256` cell within −5 % of Phase 0, depth cells no worse, quality gate passed. A cell that fails needs an explicit decision, not a relaxed gate |
| 4 | **Cut over.** Profile by profile: pin bump in `config/models.yaml`, root and `config/` `CLAUDE.md`, `scripts/`; new baselines; `docs/models.md` and `docs/benchmark-results-full.md` regenerated; rollback tag kept. | 30-min soak, long-context stress step, router check through :8080 |

Comparison rules (from `bench/CLAUDE.md`): same request count both sides, band classified on
every spawn, one fresh spawn per arm, image pin in every filename.

## Phase 0 — baseline (2026-11-25)

_Filled in when the run completes._

## Phase 1–4

_Not started._
