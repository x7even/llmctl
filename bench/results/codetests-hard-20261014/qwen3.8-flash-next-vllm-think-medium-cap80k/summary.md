# Code test results — qwen3.8-flash-next-vllm

Generated 2026-10-14 08:41:13  (temperature 0.6, top_p 0.95, max_tokens 81920, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| date_math | think | 4 | 2/4 | 91.1% | 44820 | 0 | 0 |
| json_strict | think | 4 | 0/4 | 66.1% | 33869 | 0 | 0 |
| mini_scheme | think | 4 | 0/4 | 53.6% | 43489 | 0 | 0 |

## Per-sample failures

- date_math/think-s2 (11/14): test_parse_accepts, test_parse_rejects, test_format_date
- date_math/think-s3 (12/14): test_parse_rejects, test_validation_and_types
- json_strict/think-s0 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s1 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s2 (1/14): test_basic_values, test_number_values, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s3 (12/14): test_string_errors_pos, test_differential_mutations
- mini_scheme/think-s0 (9/14): test_integer_arithmetic, test_truthiness_equality_and_predicates, test_closures_and_mutation, test_error_handling, test_randomized_differential
- mini_scheme/think-s1 (12/14): test_lexical_syntax_and_display, test_randomized_differential
- mini_scheme/think-s2 (9/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_lists_apply_and_shadowing, test_error_handling, test_randomized_differential
- mini_scheme/think-s3 (0/14): test_lexical_syntax_and_display, test_integer_arithmetic, test_truthiness_equality_and_predicates, test_lists_apply_and_shadowing, test_closures_and_mutation, test_binding_forms_and_internal_defines, test_evaluation_order, test_error_handling, test_tail_calls_long_loops, test_tail_calls_in_conditionals, test_tail_calls_in_binding_forms_and_apply, test_deep_recursion_and_long_lists, test_classic_programs, test_randomized_differential
