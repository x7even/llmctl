# Code test results — qwen3.6-27b-code

Generated 2026-10-05 11:23:09  (temperature 0.6, top_p 0.95, max_tokens 24000)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| expr_eval | nothink | 4 | 2/4 | 84.7% | 2286 | 0 | 0 |
| expr_eval | think | 4 | 0/4 | 0.0% | 24000 | 4 | 0 |
| ttl_cache | nothink | 4 | 4/4 | 100.0% | 1218 | 0 | 0 |
| ttl_cache | think | 4 | 4/4 | 100.0% | 11942 | 0 | 0 |

## Per-sample failures

- expr_eval/nothink-s0 (16/18): test_decimal_literals, test_differential_fuzz
- expr_eval/nothink-s1 (9/18): test_floor_semantics_negative, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_zero_division, test_differential_fuzz
- expr_eval/think-s0 (0/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_not_using_eval, test_differential_fuzz
- expr_eval/think-s1 (0/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_not_using_eval, test_differential_fuzz
- expr_eval/think-s2 (0/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_not_using_eval, test_differential_fuzz
- expr_eval/think-s3 (0/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_not_using_eval, test_differential_fuzz
