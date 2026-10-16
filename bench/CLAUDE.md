# bench/ — benchmarking methodology

---

## Scripts

| Script | Purpose |
|--------|---------|
| `concurrent_bench.py` | Main benchmark: sweep concurrency levels, collect tok/s, TTFT, VRAM |
| `opt_probe.py` | Targeted probe for optimization impact (before/after comparison) |
| `codetests/run_codetests.py` | Code-correctness suite: model writes code, hidden tests grade it (`validate` / `run` / `regrade`) |
| `canary_suite.py` | Whole canary in one resumable run: env, speed, depth, tools, ~100K stress, quality (hours) |
| `canary_compare.py` | Diffs `canary_suite.py` result directories (first = baseline) and prints the per-gate verdict |
| `canary_router.py` | Throwaway llama-swap router on :8099 for one shipped vLLM profile with a different image, suffixed container name and separate cache dirs (`up` / `down` / `config`) |

---

## Code-correctness tests (`codetests/`)

Throughput numbers say nothing about whether a model still writes correct code under a new quantisation, image
or sampling setting. `codetests/` has 11 tasks, each with a prompt, a hidden test file and a reference solution.
Six are the original set (saturated: current models pass nearly all); five are harder (`regex_engine`,
`json_strict`, `cron_next`, `mini_scheme`, `date_math`).

```bash
python3 bench/codetests/run_codetests.py validate     # reference solutions must score 100%, controls 0%
python3 bench/codetests/run_codetests.py run --url http://127.0.0.1:8080/v1/chat/completions \
  --model qwen3.8-flash-next-vllm --modes think --reasoning-effort medium --samples 4 \
  --max-tokens 81920 --timeout 7200 --tasks regex_engine,mini_scheme,date_math,json_strict \
  --out bench/results/codetests-<topic>-$(date +%Y%m%d)/<profile>
```

Rules learned the hard way (details in `docs/hard-code-tasks.md`):
- Use a generation cap of 64K-96K for the hard tasks; at 32K Flash-Next truncates and the zeros measure the cap.
- 4 samples per cell is small: read differences under ~15 points as noise.
- A `finish_reason=stop` with empty content is a premature end-of-turn from the model, not a test failure; count
  it separately (the 27B does this at a rate that rises with temperature). The runner now does: the summary's
  "early stops (empty/cut)" column counts replies that were empty or ended inside an unterminated code fence,
  and each row carries `early_stop`. `regrade` fills it in for older saved runs.
- `--thinking-budget` only helps if cap minus budget still covers the answer.
- Save per-sample results (the runner does) so every score can be audited or re-graded with `regrade`.

### Quality gate for canaries (new checkpoint, image, kernel or quantisation)

Speed is not a result if output quality drops. Before a canary gets throughput numbers, a tool-call check or
a profile, run the hard code tasks (`mini_scheme`, `regex_engine`, plus `json_strict` and `date_math`) against
the current profile as a baseline and against the candidate under identical settings (same reasoning effort,
cap of at least 64K, same samples per cell, exact all-reduce where an image offers a lossy one). Stop the canary
when either holds:
- a task's mean tests passed falls by more than the noise (15 points at 4 samples, ~10 at 8), or
- more than a handful of samples end early (the "early stops" column), or run to the cap with empty content.

Before blaming the model, also run the checkpoint's own published recipe verbatim (its flags, sampling and
env). If that fails the same way, the cause is the checkpoint or the image, not our config. Precedent:
the 2026-10-15 MXFP4 Flash-Next canary was ~2x faster but scored 5-14% vs 50-54% on the two hardest tasks,
with the model's own recipe failing the same way, so it was not adopted.

### Full canary suite (`canary_suite.py` / `canary_compare.py`)

For a change that could move both speed and quality (new image, ROCm, driver, kernel), run the whole suite
against the current state and the new state under identical conditions, then diff:

```bash
python3 bench/canary_suite.py --base http://127.0.0.1:8099 --model qwen3.8-27b-code \
  --label "S1 nightly-rocm100 (ROCm 10.0)" --container <container-name> --out bench/results/<topic>/27b-s1
python3 bench/canary_compare.py bench/results/<topic>/27b-s0 bench/results/<topic>/27b-s1 --md compare.md
```

Stages (`--stages env,speed,...`; finished stages are skipped on rerun, `--force` redoes them): `env` records
kernel, driver, image and in-container ROCm/vLLM/torch; `speed` is the standard all-prompts sweep; `depth` is
streamed decode and prefill tok/s at 1K-200K with unique prompts; `tools` runs 8 tool-call cases streaming and
not; `stress` is 7 concurrent ~100K prompts with preemption count and peak VRAM; `quality` is the hard code tasks
at 8 samples plus the common tasks. Use a frozen copy of the harness for every state of one comparison, and run
the baseline from the same session as the candidate. Gate thresholds live at the top of `canary_compare.py`.
GPU stats come from `scripts/gpustat.py` (amd-smi first, rocm-smi fallback). `canary_router.py up --profile <p>
--image <img> --suffix <s> --cache-dir <dir>` builds the throwaway router for the candidate state from `config/models.yaml`
so every flag stays identical to the shipped profile; unload production first, the GPUs are shared.

### Canary checklist

1. Baseline the shipped profile on the same prompts and settings first.
2. Run the quality gate above before any throughput work.
3. Run the model card's own recipe verbatim, as a config-vs-model check.
4. Long-context stress: ~7 concurrent unique ~100K-token prompts (~690K tokens total) must all finish, with
   no timeouts, under the profile's real `--gpu-memory-utilization`. This is what separates 0.95 from 0.97.
5. Keep throwaway routers and containers on a separate port and name, and leave the shipped profile untouched
   until every step passes.

---

## Standard invocation

### Full sweep (save as baseline)

```bash
python3 bench/concurrent_bench.py \
  --model qwen3.8-27b-code \
  --url http://127.0.0.1:8080/v1/chat/completions \
  --sweep 1,2,4,8,16 \
  --prompt all \
  --no-thinking \
  --requests 16 \
  --save bench/baselines/qwen3.8-27b-code-v0.26.0-nothink.json
```

### Quick sanity check

```bash
python3 bench/concurrent_bench.py \
  --model qwen3.8-27b-code \
  --no-thinking
```

### Compare two baselines

```bash
python3 bench/concurrent_bench.py \
  --compare bench/baselines/old.json bench/baselines/new.json
```

---

## Rules for clean comparisons

### Always use `--no-thinking`

Thinking models generate many reasoning tokens that inflate tok/s numbers.
Without `--no-thinking`, Qwen3.6 emits a `<think>...</think>` block before
the actual answer. This:
- Inflates "output tokens" counted toward tok/s
- Makes the number useless for comparing models/configs against each other
- Was the root cause of the misleading v0.20.0 "485 tok/s" benchmark (thinking ON)

**For Qwen3 and other models where thinking is explicitly suppressible:**
every baseline file in `bench/baselines/` must be no-thinking.
The filename should include `-nothink` or `-no-thinking` if there is any ambiguity.

**Gemma 4 IT dual-baseline convention:**

Gemma 4 IT activates thinking by default, but `chat_template_kwargs: {enable_thinking: false}`
is confirmed effective at suppressing `<think>` output (spot-checked 2026-06-18 on all
three Gemma 4 profiles — responses to "What is 2+2?" were direct answers with no think
block, 0 errors across all prompt sizes).

However, no-thinking does NOT improve throughput for Gemma 4 models — measured differences
are within session-to-session noise (~0–6%). This means the original thinking-on baselines
remain the best representation of real-world default behaviour.

For Gemma 4 models, keep **both** baselines:

- **thinking-on baseline** (date only): reflects default real-world behaviour; the numbers
  used in comparison tables and the README.
  Example: `gemma4-26b-q8-20260613.json`

- **no-thinking baseline** (-nothink suffix): clean apples-to-apples comparison against
  Qwen3 and other no-thinking models.
  Example: `gemma4-26b-q8-nothink-20260618.json`

When comparing Gemma 4 against other models, use the no-thinking baseline for fairness.
When reporting Gemma 4 headline numbers in user-facing docs, the thinking-on baseline is
appropriate since that is what users get by default.

### Do NOT cap `max_tokens` at 256

Setting `--max-tokens 256` causes thinking models to hit the limit mid-think
and truncate, returning zero actual content tokens. The metric looks the same
(256 tokens output) but the quality is garbage and the number is meaningless.
Let the model generate freely.

### Use `--requests 16` minimum per concurrency level

Fewer requests means the measurement is noisy. 16 requests at each concurrency
level gives stable statistics. 32 is better for publication-quality comparisons.

### Note what's different in the filename

```
qwen3.8-27b-code-v0.26.0-nothink.json     ← good
qwen3.8-27b-code.json                      ← ambiguous
```

---

## Prompt sizes

| Key | Prompt length | Typical use |
|-----|--------------|-------------|
| `short-64` | ~64 tokens | Quick command/question |
| `medium-256` | ~256 tokens | Normal coding task |
| `long-512` | ~512 tokens | Complex function/class |
| `xlarge-2048` | ~2048 tokens | Multi-file analysis |

`--prompt all` runs all four. `--prompt medium-256` runs one.
`medium-256` is the standard comparison prompt — use it for headline numbers.

---

## Interpreting results

| Metric | What it means | Target |
|--------|-------------|--------|
| `tok/s` (decode) | Output tokens per second across all concurrent requests | Higher is better |
| TTFT | Time to first token (ms) | Lower is better; ≤2000 ms at conc=8 is good |
| P90 latency | 90th percentile request latency (s) | Depends on use case |
| conc=1 | Serial throughput — effective speed per single request | |
| conc=8 | Primary throughput metric — typical concurrent agent load | |
| conc=16 | Peak concurrent load | |

**MTP effect:** Multi-Token Prediction boosts tok/s mainly at conc ≥ 4. At conc=1,
MTP overhead can slightly reduce serial tok/s if the draft hit rate is low.

**Expected baselines for `qwen3.8-27b-code` (medium-256, vLLM 0.26.0, no-thinking, MTP, 32 req/level):**

| conc | tok/s |
|------|-------|
| 1    | 66    |
| 2    | 113   |
| 4    | 194   |
| 8    | 361   |
| 16   | 549   |

If conc=8 drops below ~300 tok/s, something is wrong — check VRAM, container
restart, or whether CUDA graph capture ran correctly.

**Important:** conc=8 and conc=16 numbers are only meaningful with `--requests 32`
(the default). Using `--requests-per-level 3` with `--sweep` never fills the
concurrency slots and shows false plateaus at conc≥4.

---

## Baseline file naming convention

```
bench/baselines/<profile-id>-<version>[-<variant>].json
```

Examples:
```
qwen3.8-27b-code-v0.26.0-nothink.json      ← main baseline
qwen3.6-35b-code-v0.22.1-nothink.json      ← previous-generation reference
qwen3.6-35b-awq-v0.20.0-nothink.json       ← archived profile, kept for history
```

Commit new baselines alongside the config or code change that motivated them.
Commit message should include the headline numbers, e.g.:
```
bench: add qwen3.8-27b-code vLLM 0.26.0 baseline (conc=8: 361 tok/s)
```

---

## When to benchmark

- After adding a new profile (establish baseline)
- After changing `--max-num-seqs`, `--gpu-memory-utilization`, or `--cudagraph-capture-sizes`
- After upgrading vLLM (compare against previous version baseline)
- After enabling/disabling MTP (the delta reveals its real contribution)
- When investigating a user-reported slowness

Do NOT benchmark during a vLLM cold start (first boot) — CUDA graph capture and FP8 KV
calibration are running concurrently and will skew results. Wait for
"Application startup complete." in the container log before starting a benchmark.
