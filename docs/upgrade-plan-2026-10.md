# vLLM 0.26.0 → 0.31.0 canary — October 2026

**Outcome: HOLD at `v0.26.0`.** v0.31.0 boots, serves Qwen3.8-27B correctly and has a larger KV pool,
but it does not meet the upgrade gate (every `medium-256` cell within −5 % of the 0.26.0 baseline).
The stack stays pinned to `docker.io/vllm/vllm-openai-rocm:v0.26.0`. This document records what was
measured so the next attempt starts from facts instead of a re-run.

The gate, the method and the numbers below apply to `qwen3.8-27b-code` (FP8, MTP, TP=4, 131K context)
on 4× Radeon AI PRO R9700.

---

## Method

- Canary container from `docker.io/vllm/vllm-openai-rocm:v0.31.0`, byte-identical `vllm serve` flags to the
  production profile, on a side port, one model loaded at a time.
- Same-day control: a fresh 0.26.0 container with the production profile (a local retag of
  `docker.io/vllm/vllm-openai-rocm:v0.26.0`), benched immediately after.
- The two 0.31 runs differ in more than the runner: the "default" run set
  `VLLM_DISABLED_KERNELS=RowWiseTorchFP8ScaledMMLinearKernel` (an FP8 kernel mitigation tried first), the
  "MRV1" run set only `VLLM_USE_V2_MODEL_RUNNER=0`. The mitigation was found to have no effect on the
  regression, but the columns are not a single-variable A/B.
- `bench/concurrent_bench.py --prompt medium-256 --no-thinking --sweep 1,2,4,8,16 --requests 32`.
- Noise floor: two 0.26.0 controls run ~8 h apart (separate boots) agree within **±1.2 %** on every cell.
  Anything beyond ±2 % is a real difference.

## Results — decode tok/s, `medium-256`

| Cell | 0.26.0 control | 0.31.0 Model Runner V2 (+ FP8 kernel mitigation env) | Δ | 0.31.0 + `VLLM_USE_V2_MODEL_RUNNER=0` | Δ |
|---|---|---|---|---|---|
| serial | 66.5 | 36.2 | **−45.5 %** | 66.2 | −0.4 % |
| conc=1 | 65.6 | 35.9 | **−45.3 %** | 64.2 | −2.2 % |
| conc=2 | 113.1 | 119.4 | +5.6 % | 113.2 | +0.1 % |
| conc=4 | 194.2 | 210.0 | +8.1 % | 202.9 | +4.5 % |
| conc=8 | 365.3 | 333.0 | **−8.8 %** | 334.9 | **−8.3 %** |
| conc=16 | 545.9 | 513.3 | **−6.0 %** | 503.9 | **−7.7 %** |

Reading the table:

1. **Single-stream regression is Model Runner V2.** v0.31 makes the V2 model runner the default. With it, serial and
   conc=1 decode drops ~45 %. Falling back to the V1 runner with `VLLM_USE_V2_MODEL_RUNNER=0` restores serial and
   conc=1 to 0.26.0 level. (Disabling the FP8 RowWise kernel was tried first and had no effect.)
2. **High-concurrency regression is not the runner.** conc=8 and conc=16 are 6–9 % below 0.26.0 with *either*
   runner — well outside the 1.2 % noise floor. The cause was not isolated (candidates: attention/MTP
   path changes between 0.26 and 0.31; bisecting v0.28.0 / v0.30.0 would narrow it).
3. v0.31 is *faster* at conc=2–4 (the common 2–4-agent case), so the trade is workload-dependent — but the agreed
   gate is "no cell worse than −5 %", and it is not met.
4. The V1 runner (`VLLM_USE_V2_MODEL_RUNNER=0`) is removed in v0.32, so it is a stop-gap at best.

## Other 0.31.0 observations

- Cold boot, qwen3.8-27b-code, warm `.vllm-cache/` after the first compile: ~4m20s total (0.26.0: ~2–3 min).
- KV cache: 952 K tokens at 131 072 max-model-len.
- The chat reasoning field is `reasoning` (as since 0.24). `--default-chat-template-kwargs` exists in 0.31 but its
  behaviour was not exercised there (it was verified on 0.26.0 only).
- Not run on 0.31 (stopped once the gate failed): warm second start, tool-call test, MTP acceptance rate,
  ~100K needle test, 30-min soak, and the Qwen3.6-35B / Gemma 4 profiles.

## Decision and next steps

- Production stays on **v0.26.0**; nothing in `config/models.yaml` references 0.31.
- To retry: bisect the conc=8/16 regression (v0.28.0, v0.30.0, v0.31.0 with `VLLM_USE_V2_MODEL_RUNNER=0`) before
  spending time on the remaining validation gates. A profile that mostly serves 1–4 agents could reasonably
  accept the conc=8/16 cost; that needs an explicit decision, not a silently relaxed gate.
- Revisit when v0.32+ is released: MRV1 disappears, so the single-stream behaviour of V2 must be re-measured.
- Flash-Next on vLLM needs a newer image than 0.26.0 (a nightly build) and is evaluated separately.

## Raw data

All in `bench/baselines/` (`concurrent_bench.py` output, `medium-256`, 32 requests per level):

- `qwen3.8-27b-code-v0.26.0-sweep-nothink-20261010.json` — 0.26.0 control (compared against)
- `qwen3.8-27b-code-v0.31.0-sweep-nothink-20261010.json` — 0.31.0 Model Runner V2 with `VLLM_DISABLED_KERNELS=RowWiseTorchFP8ScaledMMLinearKernel`
- `qwen3.8-27b-code-v0.31.0-mrv1-sweep-nothink-20261010.json` — 0.31.0 with only `VLLM_USE_V2_MODEL_RUNNER=0`
- `qwen3.8-27b-code-v0.31.0-concurrency-sweep-nothink-20261009.json` — 0.31.0 wide concurrency sweep (1–64)

Compare any two with `python3 bench/concurrent_bench.py --compare OLD.json NEW.json`.
