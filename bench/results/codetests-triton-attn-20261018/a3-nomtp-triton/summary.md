# Code test results — a3-nomtp-triton

Generated 2026-10-18 13:29:21  (temperature 0.6, top_p 0.95, max_tokens 24000, reasoning_effort template default)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | early stops (empty/cut) | import failures |
|---|---|---|---|---|---|---|---|---|
| date_math | think | 4 | 3/4 | 80.4% | 31094 | 0 | 0/2 | 0 |
| json_strict | think | 4 | 2/4 | 92.9% | 28586 | 0 | 0/2 | 0 |

## Per-sample failures

- date_math/think-s0 (3/14): test_ordinal_weekday, test_iso_week_vs_stdlib, test_from_iso_week_rules, test_add_days, test_parse_accepts, test_parse_rejects, test_format_date, test_diff_rule, test_diff_oracle_and_identity, test_validation_and_types, test_scale
- json_strict/think-s1 (12/14): test_string_errors_pos, test_differential_mutations
- json_strict/think-s3 (12/14): test_string_errors_pos, test_differential_mutations
