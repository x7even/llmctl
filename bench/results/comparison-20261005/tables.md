## Concurrent bench (decode tok/s, 32 requests per level, `--no-thinking`)

`out` = mean completion tokens per request. A `⚠` marks levels where the two models' mean output length differs by more than 10%: tok/s is still comparable there, latency and wall time are not.

### short-64

| conc | Qwen3.6-27B tok/s | Qwen3.8-27B tok/s | Δ tok/s | Qwen3.6-27B out | Qwen3.8-27B out | Qwen3.6-27B p90 lat (s) | Qwen3.8-27B p90 lat (s) | errors |
|---|---|---|---|---|---|---|---|---|
| 1 | 33.4 | 33.5 | +0.1% | 57 | 61 | 1.9 | 2.1 | 0/0 |
| 2 | 59.5 | 58.3 | -2.0% | 55 | 62 ⚠ | 2.1 | 2.3 | 0/0 |
| 4 | 114.0 | 97.7 | -14.3% | 59 | 62 | 2.3 | 4.3 | 0/0 |
| 8 | 274.5 | 289.9 | +5.6% | 58 | 62 | 1.7 | 1.8 | 0/0 |
| 16 | 416.3 | 429.1 | +3.1% | 57 | 62 | 2.3 | 2.5 | 0/0 |

### medium-256

| conc | Qwen3.6-27B tok/s | Qwen3.8-27B tok/s | Δ tok/s | Qwen3.6-27B out | Qwen3.8-27B out | Qwen3.6-27B p90 lat (s) | Qwen3.8-27B p90 lat (s) | errors |
|---|---|---|---|---|---|---|---|---|
| 1 | 34.2 | 34.6 | +0.9% | 167 | 200 ⚠ | 5.3 | 6.5 | 0/0 |
| 2 | 64.8 | 64.3 | -0.7% | 169 | 199 ⚠ | 5.7 | 7.0 | 0/0 |
| 4 | 123.7 | 117.4 | -5.1% | 160 | 198 ⚠ | 5.6 | 7.2 | 0/0 |
| 8 | 315.0 | 312.1 | -0.9% | 164 | 199 ⚠ | 4.4 | 5.4 | 0/0 |
| 16 | 474.9 | 485.8 | +2.3% | 166 | 192 ⚠ | 5.6 | 6.7 | 0/0 |

### long-512

| conc | Qwen3.6-27B tok/s | Qwen3.8-27B tok/s | Δ tok/s | Qwen3.6-27B out | Qwen3.8-27B out | Qwen3.6-27B p90 lat (s) | Qwen3.8-27B p90 lat (s) | errors |
|---|---|---|---|---|---|---|---|---|
| 1 | 38.4 | 39.5 | +3.0% | 422 | 453 | 12.1 | 12.8 | 0/0 |
| 2 | 71.0 | 73.0 | +2.9% | 418 | 451 | 12.6 | 13.6 | 0/0 |
| 4 | 137.2 | 141.2 | +2.9% | 427 | 458 | 13.4 | 14.0 | 0/0 |
| 8 | 345.4 | 371.0 | +7.4% | 408 | 455 ⚠ | 9.4 | 10.1 | 0/0 |
| 16 | 549.8 | 540.7 | -1.7% | 428 | 442 | 12.7 | 13.0 | 0/0 |

### xlarge-2048

| conc | Qwen3.6-27B tok/s | Qwen3.8-27B tok/s | Δ tok/s | Qwen3.6-27B out | Qwen3.8-27B out | Qwen3.6-27B p90 lat (s) | Qwen3.8-27B p90 lat (s) | errors |
|---|---|---|---|---|---|---|---|---|
| 1 | 38.8 | 38.4 | -0.9% | 2048 | 2048 | 53.7 | 54.3 | 0/0 |
| 2 | 72.4 | 73.1 | +0.9% | 2048 | 2048 | 57.5 | 57.0 | 0/0 |
| 4 | 142.0 | 139.6 | -1.7% | 2048 | 2048 | 58.4 | 59.1 | 0/0 |
| 8 | 374.7 | 370.1 | -1.2% | 2048 | 2048 | 43.9 | 44.4 | 0/0 |
| 16 | 567.9 | 566.1 | -0.3% | 2048 | 2048 | 58.1 | 58.4 | 0/0 |

## Wide concurrency sweep (1000-token code prompt, 1000-token outputs)

The profile caps `--max-num-seqs` at 32, so levels above 32 queue.

| conc | requests | Qwen3.6-27B aggregate tok/s | Qwen3.8-27B aggregate tok/s | Δ | Qwen3.6-27B per-agent | Qwen3.8-27B per-agent | Qwen3.6-27B mean out | Qwen3.8-27B mean out | errors |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 32 | 49.3 | 49.2 | -0.2% | 49.3 | 49.2 | 1000 | 1000 | 0/0 |
| 2 | 32 | 93.3 | 92.3 | -1.1% | 46.7 | 46.1 | 1000 | 1000 | 0/0 |
| 4 | 32 | 182.2 | 179.5 | -1.5% | 45.6 | 44.9 | 1000 | 1000 | 0/0 |
| 8 | 32 | 503.4 | 496.4 | -1.4% | 62.9 | 62.0 | 1000 | 1000 | 0/0 |
| 16 | 32 | 765.6 | 752.3 | -1.7% | 47.9 | 47.0 | 1000 | 1000 | 0/0 |
| 24 | 48 | 910.4 | 901.2 | -1.0% | 37.9 | 37.5 | 1000 | 1000 | 0/0 |
| 32 | 64 | 1129.0 | 1113.1 | -1.4% | 35.3 | 34.8 | 1000 | 1000 | 0/0 |
| 40 | 80 | 1028.7 | 1023.0 | -0.6% | 25.7 | 25.6 | 1000 | 1000 | 0/0 |
| 48 | 96 | 1126.1 | 1111.8 | -1.3% | 23.5 | 23.2 | 1000 | 1000 | 0/0 |
| 56 | 112 | 1057.6 | 1047.7 | -0.9% | 18.9 | 18.7 | 1000 | 1000 | 0/0 |
| 64 | 128 | 1127.5 | 1114.6 | -1.1% | 17.6 | 17.4 | 1000 | 1000 | 0/0 |

## MTP speculative-decoding acceptance (vLLM counters, 2 draft tokens per step)

Deltas between driver snapshots, so each row covers only that phase. Counters reset when the container restarts.

| phase | model | draft tokens | accepted / drafted | mean accepted per step (max 2) |
|---|---|---|---|---|
| concurrent bench | Qwen3.6-27B | 376496 | 66.5% | 1.33 |
| concurrent bench | Qwen3.8-27B | 387048 | 66.2% | 1.32 |
| wide sweep | Qwen3.6-27B | 466520 | 97.5% | 1.95 |
| wide sweep | Qwen3.8-27B | 471670 | 95.9% | 1.92 |
| code tests | Qwen3.6-27B | 115430 | 86.7% | 1.73 |
| code tests | Qwen3.8-27B | 161652 | 75.0% | 1.50 |

## Code tests

Temperature 0.6, top_p 0.95, `max_tokens` 24000, 4 samples per task and mode. A sample that is cut off at the token limit has no code to grade, so it is counted as **truncated**, not as a wrong answer.

| task | mode | model | samples | full passes | graded samples | mean tests passed (graded only) | truncated | mean completion tok |
|---|---|---|---|---|---|---|---|---|
| expr_eval | think | Qwen3.6-27B | 4 | 0/4 | 0 | n/a | 4 | 24000 |
| expr_eval | nothink | Qwen3.6-27B | 4 | 2/4 | 4 | 84.7% | 0 | 2286 |
| ttl_cache | think | Qwen3.6-27B | 4 | 4/4 | 4 | 100.0% | 0 | 11942 |
| ttl_cache | nothink | Qwen3.6-27B | 4 | 4/4 | 4 | 100.0% | 0 | 1218 |
| expr_eval | think | Qwen3.8-27B | 4 | 0/4 | 0 | n/a | 4 | 24000 |
| expr_eval | nothink | Qwen3.8-27B | 4 | 1/4 | 4 | 38.9% | 0 | 2041 |
| ttl_cache | think | Qwen3.8-27B | 4 | 1/4 | 1 | 100.0% | 3 | 23341 |
| ttl_cache | nothink | Qwen3.8-27B | 4 | 4/4 | 4 | 100.0% | 0 | 1140 |

### Which tests failed (graded samples only)

- Qwen3.6-27B / expr_eval: `test_differential_fuzz` ×2, `test_decimal_literals` ×1, `test_floor_semantics_negative` ×1, `test_unary_vs_power` ×1, `test_stacked_unary` ×1, `test_unary_precedence_vs_mul` ×1, `test_whitespace` ×1, `test_nested_parens` ×1, `test_int_float_result_types` ×1, `test_zero_division` ×1
- Qwen3.8-27B / expr_eval: `test_basic_ints` ×3, `test_division_types` ×3, `test_floor_semantics_negative` ×3, `test_left_associativity` ×3, `test_unary_precedence_vs_mul` ×3, `test_int_float_result_types` ×3, `test_big_ints` ×3, `test_zero_division` ×3, `test_zero_ok` ×3, `test_differential_fuzz` ×3, `test_decimal_literals` ×2, `test_power_right_assoc` ×2, `test_unary_vs_power` ×2, `test_stacked_unary` ×2, `test_whitespace` ×2, `test_nested_parens` ×2, `test_malformed_raises_valueerror` ×2

### Every sample

| task | sample | model | passed | finish | completion tok | failed tests |
|---|---|---|---|---|---|---|
| expr_eval | think-s0 | Qwen3.6-27B | 0/18 | length | 24000 | (truncated, not graded) |
| expr_eval | think-s1 | Qwen3.6-27B | 0/18 | length | 24000 | (truncated, not graded) |
| expr_eval | think-s2 | Qwen3.6-27B | 0/18 | length | 24000 | (truncated, not graded) |
| expr_eval | think-s3 | Qwen3.6-27B | 0/18 | length | 24000 | (truncated, not graded) |
| expr_eval | nothink-s0 | Qwen3.6-27B | 16/18 | stop | 1925 | test_decimal_literals, test_differential_fuzz |
| expr_eval | nothink-s1 | Qwen3.6-27B | 9/18 | stop | 3335 | test_floor_semantics_negative, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_zero_division, test_differential_fuzz |
| expr_eval | nothink-s2 | Qwen3.6-27B | 18/18 | stop | 1733 |  |
| expr_eval | nothink-s3 | Qwen3.6-27B | 18/18 | stop | 2150 |  |
| ttl_cache | think-s0 | Qwen3.6-27B | 22/22 | stop | 11486 |  |
| ttl_cache | think-s1 | Qwen3.6-27B | 22/22 | stop | 11682 |  |
| ttl_cache | think-s2 | Qwen3.6-27B | 22/22 | stop | 12493 |  |
| ttl_cache | think-s3 | Qwen3.6-27B | 22/22 | stop | 12106 |  |
| ttl_cache | nothink-s0 | Qwen3.6-27B | 22/22 | stop | 1481 |  |
| ttl_cache | nothink-s1 | Qwen3.6-27B | 22/22 | stop | 1378 |  |
| ttl_cache | nothink-s2 | Qwen3.6-27B | 22/22 | stop | 895 |  |
| ttl_cache | nothink-s3 | Qwen3.6-27B | 22/22 | stop | 1119 |  |
| expr_eval | think-s0 | Qwen3.8-27B | 0/18 | length | 24000 | (truncated, not graded) |
| expr_eval | think-s1 | Qwen3.8-27B | 0/18 | length | 24000 | (truncated, not graded) |
| expr_eval | think-s2 | Qwen3.8-27B | 0/18 | length | 24000 | (truncated, not graded) |
| expr_eval | think-s3 | Qwen3.8-27B | 0/18 | length | 24000 | (truncated, not graded) |
| expr_eval | nothink-s0 | Qwen3.8-27B | 8/18 | stop | 1760 | test_basic_ints, test_division_types, test_floor_semantics_negative, test_left_associativity, test_unary_precedence_vs_mul, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_differential_fuzz |
| expr_eval | nothink-s1 | Qwen3.8-27B | 1/18 | stop | 2561 | test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_differential_fuzz |
| expr_eval | nothink-s2 | Qwen3.8-27B | 1/18 | stop | 1812 | test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_differential_fuzz |
| expr_eval | nothink-s3 | Qwen3.8-27B | 18/18 | stop | 2032 |  |
| ttl_cache | think-s0 | Qwen3.8-27B | 0/22 | length | 24000 | (truncated, not graded) |
| ttl_cache | think-s1 | Qwen3.8-27B | 22/22 | stop | 21364 |  |
| ttl_cache | think-s2 | Qwen3.8-27B | 0/22 | length | 24000 | (truncated, not graded) |
| ttl_cache | think-s3 | Qwen3.8-27B | 0/22 | length | 24000 | (truncated, not graded) |
| ttl_cache | nothink-s0 | Qwen3.8-27B | 22/22 | stop | 1254 |  |
| ttl_cache | nothink-s1 | Qwen3.8-27B | 22/22 | stop | 1081 |  |
| ttl_cache | nothink-s2 | Qwen3.8-27B | 22/22 | stop | 1136 |  |
| ttl_cache | nothink-s3 | Qwen3.8-27B | 22/22 | stop | 1088 |  |

## Run conditions (from the driver snapshots)

- Qwen3.6-27B start (2026-10-05 09:20:55): containers = `llmstack-vllm-qwen3.6-27b-code Up 5 minutes`; :8080 running = `{"running":[]}`
- Qwen3.6-27B end (2026-10-05 11:23:09): containers = `llmstack-vllm-qwen3.6-27b-code Up 2 hours`; :8080 running = `{"running":[]}`
- Qwen3.8-27B start (2026-10-05 11:26:03): containers = `llmstack-vllm-qwen3.8-27b-code Up 2 minutes`; :8080 running = `{"running":[]}`
- Qwen3.8-27B end (2026-10-05 13:35:10): containers = `llmstack-vllm-qwen3.8-27b-code Up 2 hours`; :8080 running = `{"running":[]}`

