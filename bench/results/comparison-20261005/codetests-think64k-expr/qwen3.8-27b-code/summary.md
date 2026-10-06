# Code test results — qwen3.8-27b-code

Generated 2026-10-05 20:24:38  (temperature 0.6, top_p 0.95, max_tokens 24000)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| expr_eval | think | 4 | 0/4 | 0.0% | 64000 | 4 | 0 |

## Per-sample failures

- expr_eval/think-s0 (0/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_not_using_eval, test_differential_fuzz
- expr_eval/think-s1 (0/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_not_using_eval, test_differential_fuzz
- expr_eval/think-s2 (0/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_not_using_eval, test_differential_fuzz
- expr_eval/think-s3 (0/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_not_using_eval, test_differential_fuzz
