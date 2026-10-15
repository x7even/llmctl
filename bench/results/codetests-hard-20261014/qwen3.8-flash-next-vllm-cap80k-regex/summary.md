# Code test results — qwen3.8-flash-next-vllm

Generated 2026-10-14 18:49:53  (temperature 0.6, top_p 0.95, max_tokens 81920, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| regex_engine | think | 4 | 0/4 | 50.0% | 69908 | 0 | 0 |

## Per-sample failures

- regex_engine/think-s0 (11/13): test_random_captures_diff, test_scale_memoisation
- regex_engine/think-s1 (10/13): test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff
- regex_engine/think-s2 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s3 (5/13): test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_scale_memoisation
