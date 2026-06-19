# bench/ — benchmarking methodology

---

## Scripts

| Script | Purpose |
|--------|---------|
| `concurrent_bench.py` | Main benchmark: sweep concurrency levels, collect tok/s, TTFT, VRAM |
| `opt_probe.py` | Targeted probe for optimization impact (before/after comparison) |

---

## Standard invocation

### Full sweep (save as baseline)

```bash
python3 bench/concurrent_bench.py \
  --model qwen3.6-35b-code \
  --url http://127.0.0.1:8080/v1/chat/completions \
  --sweep 1,2,4,8,16 \
  --prompt all \
  --no-thinking \
  --requests 16 \
  --save bench/baselines/qwen3.6-35b-code-v0.22.1-nothink.json
```

### Quick sanity check

```bash
python3 bench/concurrent_bench.py \
  --model qwen3.6-35b-code \
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
qwen3.6-35b-code-v0.22.1-nothink.json     ← good
qwen3.6-35b-code.json                      ← ambiguous
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

**Expected baselines for `qwen3.6-35b-code` (medium-256, vLLM 0.22.1, no-thinking, MTP, 32 req/level):**

| conc | tok/s | TTFT (ms) |
|------|-------|----------|
| 1    | 52    | ~200 |
| 2    | 94    | ~250 |
| 4    | 155   | ~500 |
| 8    | 259   | ~1500 |
| 16   | 478   | ~3500 |

If conc=8 drops below ~200 tok/s, something is wrong — check VRAM, container
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
qwen3.6-35b-code-v0.22.1-nothink.json      ← main baseline
qwen3.6-35b-code-v0.20.0-nothink.json      ← old version for comparison
qwen3.6-35b-awq-v0.20.0-nothink.json       ← different quant
qwen3.6-27b-fp8-v0.22.1.json               ← FP8 dense
```

Commit new baselines alongside the config or code change that motivated them.
Commit message should include the headline numbers, e.g.:
```
bench: add qwen3.6-35b-code vLLM 0.22.1 baseline (conc=8: 261 tok/s)
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
