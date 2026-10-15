# Code test results — qwen3.8-flash-next-vllm

Generated 2026-10-15 06:39:29  (temperature 0.6, top_p 0.95, max_tokens 200000, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| mini_scheme | think | 3 | 0/3 | 35.7% | 45043 | 0 | 0 |
| regex_engine | think | 3 | 0/3 | 15.4% | 70440 | 0 | 0 |

## Per-sample failures

- mini_scheme/think-s0 (1/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
- mini_scheme/think-s1 (13/14): test_lexical_syntax_and_display
- mini_scheme/think-s2 (1/14): test_lexical_syntax_and_display, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
- regex_engine/think-s0 (5/13): test_classes_escapes_anchors, test_priority_and_laziness, test_empty_iteration_loops, test_invalid_patterns, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_scale_memoisation
- regex_engine/think-s1 (1/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s2 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
