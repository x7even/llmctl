# Harder code tasks: what they showed (2026-10)

Five tasks were added to `bench/codetests/` because the original four are saturated: `regex_engine`,
`json_strict`, `cron_next`, `mini_scheme`, `date_math`. Each has a reference solution and a negative
control (`run_codetests.py validate`). The question was whether Flash-Next's 4-bit weights
(W4A16 experts + FP8 PLE) cost real quality against the 27B (FP8).

Runs: `think` mode, `reasoning_effort=medium`, temperature 0.6, 4 samples per cell (8 at the 32K cap).
Four samples per cell is a small sample: read differences under ~15 points as noise. Per-sample
data is under `bench/results/codetests-hard-20261014/`.

## 1. The 32K cap, not the quantisation, produced Flash-Next's zeros

| Flash-Next, mean tests passed | cap 32,768 | cap 81,920 |
|---|---|---|
| date_math | 0% (8/8 truncated) | 91.1% |
| json_strict | 42.9% | 66.1% |
| mini_scheme | 0% (8/8 truncated) | 53.6% |
| regex_engine | 0% (8/8 truncated) | 50.0% |

At 81,920, 0 of 16 samples truncated; samples use 34-70K tokens. Hard code needs a cap of 64K or more
on this model. The reasoning is long, not looping.

## 2. Equal room, 27B vs Flash-Next (cap 81,920)

| mean tests passed (full passes) | Flash-Next W4A16 | 27B FP8, no MTP |
|---|---|---|
| date_math | 91.1% (2/4) | 96.4% (3/4) |
| json_strict | 66.1% (0/4) | 67.9% (1/4) |
| mini_scheme | 53.6% (0/4) | 0.0% (0/4) |
| regex_engine | 50.0% (0/4) | 0.0% (0/4) |

Where the 27B produced an answer it was as good as Flash-Next or better. The 27B zeros come from
**empty replies** (below), not wrong code: 6 of 16 samples. No quality loss from the 4-bit weights is
visible here, but 4 samples per cell cannot rule out a small one.

## 3. 27B ends generation early (finish=stop, empty content)

The 27B (with or without MTP) sometimes emits end-of-sequence in the middle of its reasoning:
`finish_reason=stop`, `content` empty, no `</think>`. 12/40 samples at the 32K cap with MTP, 6/16 without
MTP at 81,920. It rises with temperature (10/16 at 1.0, 2-3/16 at 0.6) and was not seen on Flash-Next.
Not caused by MTP. A client that gets `stop` with empty content and no `</think>` should retry or
continue.

Diagnostic (27B no-MTP, `skip_special_tokens=false`): the first three `regex_engine` samples that
finished (19K-26K tokens, cap 32,768, temperature 0.6) each ended with the model emitting `<|im_end|>`
in the middle of a reasoning sentence (previous tokens `?!`, `|`, `{}`), so it is a premature turn-end
token, not a stop string or the length limit. The run hit its time limit before the remaining nine
samples and the per-token probabilities were saved, so how likely `<|im_end|>` was at those positions
is still unmeasured. A sampling-side mitigation (suppressing `<|im_end|>` while inside `<think>`) is
untested.

## 4. Things that did not help

- **Recommended sampling recipe (temperature 1.0 etc.):** worse for both models, more truncation and
  more 27B early stops.
- **`thinking_token_budget`** (request-only vLLM parameter; works on both models): a 24,576 budget
  under a 32,768 cap was no better than the plain 32K cap and truncated every `mini_scheme` sample,
  because its answers run about 10K tokens and the budget leaves too little room for them. A budget is
  only useful if cap minus budget covers the answer. A 40,960 budget under a 65,536 cap was queued but
  not completed.

## 5. Context and caps follow the hardware

`--max-model-len -1` makes vLLM choose the largest context that fits the KV memory it actually has.
Measured with the shipped profiles on this rig (auto-fit message in the container log):

| profile | cards | auto-fit max_model_len | KV pool (tokens) | load / serial tok/s |
|---|---|---|---|---|
| qwen3.8-flash-next-vllm | 4 (TP4+EP) | 262,144 (native) | 550,959 | 125 s / 56.6 |
| qwen3.8-27b-code | 4 (TP4) | 262,144 (native) | 1,057,057 | 165 s / 68.7 |
| qwen3.8-27b-code | 2 (TP2) | 262,144 (native) | 264,457 | 220 s / 33.4 |

Every valid TP size fits the native context, so the shipped 27B value of 131,072 is a policy choice
(decode slows steeply with depth), not a memory limit. At TP2 a 262,144 context leaves room for only
one full-length request in the pool; 131,072 allows two. Flash-Next vLLM needs all four cards (see
`docs/gpu-counts.md`), so smaller rigs are covered by the GGUF profile, whose shipped `--ctx-size` was
measured on 2 and 3 cards.

## 6. Ceiling check: a 200,000-token cap buys nothing over 81,920

Flash-Next, medium effort, cap 200,000, 3 samples each: all 6 samples stopped on their own, at 37K to
79K completion tokens, none truncated. Mean tests passed were 35.7% on `mini_scheme` and 15.4% on
`regex_engine` (3 samples, so within noise of the 81,920 run's 54% and 50%; the large per-sample spread,
e.g. `mini_scheme` 1/14, 13/14, 1/14, is the real signal). The model does not need more than about 80K
tokens on these tasks, and extra room does not turn failures into passes. Results:
`bench/results/codetests-hard-20261014/qwen3.8-flash-next-vllm-ceiling200k-medium/`.

Practical reading: a 64K-96K generation cap is enough for hard code on Flash-Next. The 262,144 context
is for long inputs, not longer answers.
