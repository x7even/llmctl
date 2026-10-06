# Code test results — qwen3.8-27b-code

Generated 2026-10-05 18:10:39  (temperature 0.6, top_p 0.95, max_tokens 24000)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| expr_eval | nothink | 16 | 5/16 | 64.2% | 2353 | 0 | 0 |
| ttl_cache | nothink | 16 | 16/16 | 100.0% | 1045 | 0 | 0 |

## Per-sample failures

- expr_eval/nothink-s0 (2/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_differential_fuzz
- expr_eval/nothink-s1 (1/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_malformed_raises_valueerror, test_differential_fuzz
- expr_eval/nothink-s2 (8/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_left_associativity, test_unary_precedence_vs_mul, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_differential_fuzz
- expr_eval/nothink-s4 (15/18): test_unary_vs_power, test_unary_precedence_vs_mul, test_differential_fuzz
- expr_eval/nothink-s5 (16/18): test_decimal_literals, test_differential_fuzz
- expr_eval/nothink-s6 (2/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_differential_fuzz
- expr_eval/nothink-s7 (16/18): test_decimal_literals, test_differential_fuzz
- expr_eval/nothink-s9 (14/18): test_power_right_assoc, test_unary_vs_power, test_unary_precedence_vs_mul, test_differential_fuzz
- expr_eval/nothink-s13 (2/18): test_basic_ints, test_division_types, test_floor_semantics_negative, test_decimal_literals, test_left_associativity, test_power_right_assoc, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_differential_fuzz
- expr_eval/nothink-s14 (11/18): test_floor_semantics_negative, test_unary_vs_power, test_stacked_unary, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_differential_fuzz
- expr_eval/nothink-s15 (8/18): test_power_right_assoc, test_unary_vs_power, test_unary_precedence_vs_mul, test_whitespace, test_nested_parens, test_int_float_result_types, test_big_ints, test_zero_division, test_zero_ok, test_differential_fuzz
