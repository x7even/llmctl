# Code test results — qwen3.8-flash-next-vllm

Generated 2026-10-16 18:07:26  (temperature 0.6, top_p 0.95, max_tokens 81920, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | early stops (empty/cut) | import failures |
|---|---|---|---|---|---|---|---|---|
| cron_next | think | 8 | 7/8 | 89.4% | 16783 | 0 | 0/0 | 0 |
| date_math | think | 8 | 3/8 | 83.0% | 39238 | 0 | 0/0 | 0 |
| json_strict | think | 8 | 3/8 | 80.4% | 27932 | 0 | 1/0 | 0 |
| mini_scheme | think | 8 | 0/8 | 60.7% | 45517 | 0 | 0/0 | 0 |
| regex_engine | think | 8 | 0/8 | 7.7% | 62722 | 0 | 4/0 | 0 |

## Per-sample failures

- cron_next/think-s4 (2/13): test_basic_rollovers_and_strictness, test_field_syntax_steps_and_lists, test_names_case_insensitive_and_mixed, test_day_of_week_zero_and_seven_are_sunday, test_dom_dow_or_vs_and_rule, test_month_lengths_and_leap_years, test_search_horizon_and_lookup_error, test_validation_fuzz_against_independent_checker, test_random_expressions_and_chains_vs_oracle, test_random_day_logic_across_centuries_vs_oracle, test_performance_sparse_expressions
- date_math/think-s0 (11/14): test_parse_accepts, test_parse_rejects, test_format_date
- date_math/think-s1 (10/14): test_ordinal_weekday, test_iso_week_vs_stdlib, test_parse_accepts, test_format_date
- date_math/think-s2 (6/14): test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_parse_accepts, test_format_date, test_diff_oracle_and_identity, test_scale
- date_math/think-s5 (13/14): test_parse_rejects
- date_math/think-s7 (11/14): test_add_months_oracle, test_diff_rule, test_diff_oracle_and_identity
- json_strict/think-s1 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s2 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s3 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s5 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s7 (12/14): test_string_errors_pos, test_differential_mutations
- mini_scheme/think-s0 (8/14): test_integer_arithmetic, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists
- mini_scheme/think-s1 (10/14): test_integer_arithmetic, test_lists_apply_and_shadowing, test_error_handling, test_randomized_differential
- mini_scheme/think-s2 (0/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
- mini_scheme/think-s3 (6/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_lists_apply_and_shadowing, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_randomized_differential
- mini_scheme/think-s4 (10/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_error_handling, test_randomized_differential
- mini_scheme/think-s5 (13/14): test_lexical_syntax_and_display
- mini_scheme/think-s6 (9/14): test_lexical_syntax_and_display, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling
- mini_scheme/think-s7 (12/14): test_lexical_syntax_and_display, test_error_handling
- regex_engine/think-s0 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s1 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s2 (4/13): test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s3 (3/13): test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation
- regex_engine/think-s4 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s5 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s6 (1/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
- regex_engine/think-s7 (0/13): test_api_and_examples, test_classes_escapes_anchors, test_priority_and_laziness, test_capture_semantics, test_empty_iteration_loops, test_invalid_patterns, test_strict_dialect_rejections, test_random_captures_diff, test_random_empty_loops_diff, test_random_classes_anchors_diff, test_random_syntax_validity, test_scale_memoisation, test_long_input_no_recursion
