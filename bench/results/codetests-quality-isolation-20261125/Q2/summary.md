# Code test results — qwen3.8-27b-code

Generated 2026-11-25 19:21:10  (temperature 0.6, top_p 0.95, max_tokens 81920, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | early stops (empty/cut) | import failures |
|---|---|---|---|---|---|---|---|---|
| date_math | think | 12 | 5/12 | 80.4% | 29391 | 0 | 0/7 | 0 |
| json_strict | think | 12 | 0/12 | 39.9% | 27578 | 0 | 4/3 | 0 |

## Per-sample failures

- date_math/think-s1 (13/14): test_parse_rejects
- date_math/think-s3 (13/14): test_parse_rejects
- date_math/think-s6 (3/14): test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_parse_accepts, test_parse_rejects, test_format_date, test_diff_rule, test_diff_oracle_and_identity, test_validation_and_types, test_scale
- date_math/think-s7 (9/14): test_ordinal_weekday, test_iso_week_vs_stdlib, test_parse_accepts, test_parse_rejects, test_format_date
- date_math/think-s8 (12/14): test_parse_accepts, test_parse_rejects
- date_math/think-s9 (3/14): test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_parse_accepts, test_parse_rejects, test_format_date, test_diff_rule, test_diff_oracle_and_identity, test_validation_and_types, test_scale
- date_math/think-s11 (12/14): test_parse_accepts, test_parse_rejects
- json_strict/think-s0 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s1 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s2 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s3 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s4 (8/14): test_string_values, test_string_errors_pos, test_duplicate_keys, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s5 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s6 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s7 (1/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s8 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s9 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s10 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s11 (10/14): test_string_errors_pos, test_structure_whitespace_trailing_pos, test_differential_mutations, test_performance_scale
