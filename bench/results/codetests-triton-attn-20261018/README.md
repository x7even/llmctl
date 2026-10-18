# Quality gate for `--attention-backend TRITON_ATTN` on `qwen3.8-27b-think`

Does switching the attention backend change what the model *says*? The depth benchmarks
answer how fast it decodes at 131K; this answers whether the output is still worth having.
See `docs/rdna4-long-context.md` for the fix itself.

## What was run

`a3-nomtp-triton` is the 27B FP8 checkpoint served with no MTP and
`--attention-backend TRITON_ATTN` — flag-for-flag the committed `qwen3.8-27b-think` profile.

```
--modes think --reasoning-effort medium --samples 4
--max-tokens 81920 --temperature 0.6 --top-p 0.95
--tasks date_math,json_strict
```

**The `summary.md` header is wrong about two of those.** It was regenerated with `regrade`,
which stamps its own defaults (`max_tokens 24000`, `reasoning_effort template default`) rather
than the values the generation actually used. The block above is what the model was served;
the grades themselves are from the saved responses and are unaffected.

## Baseline

`bench/results/codetests-hard-20261014/qwen3.8-27b-think-cap80k/` — the same profile before
the flag, with the same sampling config, measured 2026-10-14. That is what makes this an
apples-to-apples pair.

| task | before | with TRITON_ATTN |
|---|---|---|
| date_math | 54/56 (96.4%) | 45/56 (80.4%) |
| json_strict | 38/56 (67.9%) | 52/56 (92.9%) |
| **pooled** | **92/112 (82.1%)** | **97/112 (86.6%)** |

## Reading it

No regression. The two tasks move in opposite directions, and each arm has exactly one
catastrophic sample on a *different* task — baseline `json_strict/think-s3` at 0/14, here
`date_math/think-s0` at 3/14. At 4 samples that is noise, not signal.

Two things raise confidence beyond the pooled number:

- **The bad sample is not degenerate.** `date_math/think-s0` was read directly: coherent,
  well-structured Python that terminates cleanly, 400 unique words in 1876, no repetition
  loop, no broken tokens. Ordinary wrong logic. A split-KV kernel mis-combining its softmax
  segments at ~25K depth would not look like this.
- **The surviving failures match the baseline's signature.** Both `json_strict` misses here
  (s1, s3) fail exactly `test_string_errors_pos` and `test_differential_mutations` — the same
  two tests the baseline's s1 and s2 failed. Same model, same weak spots.

## Why only two tasks

`mini_scheme` and `regex_engine` score **0%** in the baseline, so a 0% from this arm would be
uninformative either way, and they are the longest generations in the suite. The gate was
stopped after `date_math` and `json_strict` rather than spend an hour of GPU proving a floor
is still a floor. Long-context coherence is covered properly by `bench/needle_check.py`
(5 needle positions × 3 depths to 131K, 15/15 on both backends), which is the test designed
for this failure mode.
