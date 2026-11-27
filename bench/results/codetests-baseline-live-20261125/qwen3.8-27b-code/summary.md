# Code test results — qwen3.8-27b-code

Generated 2026-11-25 09:00:40  (temperature 0.6, top_p 0.95, max_tokens 81920, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | early stops (empty/cut) | import failures |
|---|---|---|---|---|---|---|---|---|
| date_math | think | 4 | 1/4 | 85.7% | 27086 | 0 | 0/1 | 0 |
| json_strict | think | 4 | 0/4 | 78.6% | 29820 | 0 | 0/2 | 0 |
| mini_scheme | think | 4 | 0/4 | 0.0% | 39778 | 0 | 2/1 | 0 |
| regex_engine | think | 4 | 0/4 | 0.0% | 36498 | 0 | 3/0 | 0 |

## Per-sample failures

- date_math/think-s1 (12/14): test_parse_accepts, test_parse_rejects
- date_math/think-s2 (11/14): test_parse_accepts, test_parse_rejects, test_format_date
- date_math/think-s3 (11/14): test_parse_accepts, test_parse_rejects, test_format_date
- json_strict/think-s0 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s1 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s2 (8/14): test_string_values, test_string_errors_pos, test_duplicate_keys, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s3 (12/14): test_string_errors_pos, test_differential_mutations
- mini_scheme/think-s0 (0/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
- mini_scheme/think-s1 (0/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
- mini_scheme/think-s2 (0/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
- mini_scheme/think-s3 (0/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
- regex_engine/think-s0 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s1 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s2 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s3 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
