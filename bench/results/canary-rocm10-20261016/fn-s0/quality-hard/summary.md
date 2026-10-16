# Code test results — qwen3.8-flash-next-vllm

Generated 2026-10-16 12:25:47  (temperature 0.6, top_p 0.95, max_tokens 81920, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | early stops (empty/cut) | import failures |
|---|---|---|---|---|---|---|---|---|
| cron_next | think | 8 | 7/8 | 98.1% | 16921 | 0 | 0/0 | 0 |
| date_math | think | 8 | 2/8 | 68.8% | 36772 | 0 | 0/0 | 1 |
| json_strict | think | 8 | 4/8 | 89.3% | 32891 | 0 | 0/0 | 0 |
| mini_scheme | think | 8 | 0/8 | 42.0% | 45285 | 0 | 0/0 | 0 |
| regex_engine | think | 8 | 0/8 | 21.2% | 61064 | 0 | 2/1 | 1 |

## Per-sample failures

- cron_next/think-s1 (11/13): test_random_expressions_and_chains_vs_oracle, test_random_day_logic_across_centuries_vs_oracle
- date_math/think-s0 (10/14): test_ordinal_weekday, test_iso_week_vs_stdlib, test_parse_accepts, test_format_date
- date_math/think-s3 (12/14): test_parse_accepts, test_parse_rejects
- date_math/think-s4 (11/14): test_diff_rule, test_diff_oracle_and_identity, test_scale
- date_math/think-s5 (0/14): test_no_forbidden_imports, test_leap_and_month_lengths, test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_add_months_oracle, test_parse_accepts, test_parse_rejects, test_format_date, test_diff_rule, test_diff_oracle_and_identity, test_validation_and_types, test_scale
- date_math/think-s6 (3/14): test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_parse_accepts, test_parse_rejects, test_format_date, test_diff_rule, test_diff_oracle_and_identity, test_validation_and_types, test_scale
- date_math/think-s7 (13/14): test_validation_and_types
- json_strict/think-s1 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s3 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s5 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s6 (8/14): test_basic_values, test_string_values, test_string_errors_pos, test_differential_valid, test_differential_mutations, test_performance_scale
- mini_scheme/think-s0 (9/14): test_lexical_syntax_and_display, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_deep_recursion_and_long_lists
- mini_scheme/think-s1 (3/14): test_lexical_syntax_and_display, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_randomized_differential
- mini_scheme/think-s2 (12/14): test_lexical_syntax_and_display, test_error_handling
- mini_scheme/think-s3 (12/14): test_lexical_syntax_and_display, test_error_handling
- mini_scheme/think-s4 (0/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
- mini_scheme/think-s5 (0/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
- mini_scheme/think-s6 (11/14): test_lexical_syntax_and_display, test_lists_apply_and_shadowing, test_error_handling
- mini_scheme/think-s7 (0/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
- regex_engine/think-s0 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s1 (5/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_invalid_patterns, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity
- regex_engine/think-s2 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s3 (8/13): test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_scale_memoisation
- regex_engine/think-s4 (1/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s5 (1/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s6 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s7 (7/13): test_priority_and_laziness, test_empty_iteration_loops, test_invalid_patterns, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff
