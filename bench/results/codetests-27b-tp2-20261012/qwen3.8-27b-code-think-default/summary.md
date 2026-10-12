# Code test results — qwen3.8-27b-code

Generated 2026-10-12 05:51:25  (temperature 0.6, top_p 0.95, max_tokens 32000, reasoning_effort template default)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| log_stats | think | 4 | 2/4 | 77.3% | 3945 | 0 | 0 |
| retry_decorator | think | 4 | 3/4 | 95.8% | 1801 | 0 | 0 |
| shopping_cart | think | 4 | 2/4 | 91.7% | 3306 | 0 | 0 |
| todo_repo | think | 4 | 4/4 | 100.0% | 2268 | 0 | 0 |

## Per-sample failures

- log_stats/think-s0 (10/11): test_malformed_lines
- log_stats/think-s2 (2/11): test_totals, test_status_counts, test_error_rate, test_top_paths, test_query_string_stripped, test_requests_per_hour, test_malformed_lines, test_fewer_than_three_paths, test_accepts_generator_and_newlines
- retry_decorator/think-s3 (10/12): test_calls_counter_accumulates, test_independent_decorated_functions
- shopping_cart/think-s0 (13/15): test_empty_cart, test_remove_partial_and_full
- shopping_cart/think-s3 (12/15): test_empty_cart, test_remove_partial_and_full, test_tax_applied_after_discount_with_rounding
