# Code test results — qwen3.8-27b-code

Generated 2026-11-25 18:37:21  (temperature 0.6, top_p 0.95, max_tokens 81920, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | early stops (empty/cut) | import failures |
|---|---|---|---|---|---|---|---|---|
| date_math | think | 12 | 5/12 | 64.9% | 26444 | 0 | 3/4 | 0 |
| json_strict | think | 12 | 2/12 | 44.6% | 27138 | 0 | 3/4 | 1 |

## Per-sample failures

- date_math/think-s1 (0/14): test_no_forbidden_imports, test_leap_and_month_lengths, test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_add_months_oracle, test_parse_accepts, test_parse_rejects, test_format_date, test_diff_rule, test_diff_oracle_and_identity, test_validation_and_types, test_scale
- date_math/think-s4 (11/14): test_iso_week_vs_stdlib, test_format_date, test_scale
- date_math/think-s5 (0/14): test_no_forbidden_imports, test_leap_and_month_lengths, test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_add_months_oracle, test_parse_accepts, test_parse_rejects, test_format_date, test_diff_rule, test_diff_oracle_and_identity, test_validation_and_types, test_scale
- date_math/think-s6 (3/14): test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_parse_accepts, test_parse_rejects, test_format_date, test_diff_rule, test_diff_oracle_and_identity, test_validation_and_types, test_scale
- date_math/think-s7 (12/14): test_parse_accepts, test_parse_rejects
- date_math/think-s9 (13/14): test_parse_rejects
- date_math/think-s11 (0/14): test_no_forbidden_imports, test_leap_and_month_lengths, test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_add_months_oracle, test_parse_accepts, test_parse_rejects, test_format_date, test_diff_rule, test_diff_oracle_and_identity, test_validation_and_types, test_scale
- json_strict/think-s0 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s2 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s3 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s4 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s5 (7/14): test_basic_values, test_string_errors_pos, test_duplicate_keys, test_depth_limit_ok, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s6 (0/14): test_basic_values, test_number_values, test_number_errors_pos, test_string_values, test_string_errors_pos, test_structure_whitespace_trailing_pos, test_duplicate_keys, test_depth_limit_ok, test_depth_limit_exceeded, test_error_api, test_no_json_module_no_eval, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s7 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s8 (8/14): test_string_values, test_string_errors_pos, test_duplicate_keys, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s10 (8/14): test_basic_values, test_string_errors_pos, test_duplicate_keys, test_differential_valid, test_differential_mutations, test_performance_scale
- json_strict/think-s11 (12/14): test_string_errors_pos, test_differential_mutations
