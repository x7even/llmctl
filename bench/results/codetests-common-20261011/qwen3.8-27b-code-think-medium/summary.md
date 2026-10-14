# Code test results — qwen3.8-27b-code

Generated 2026-10-11 10:58:40  (temperature 0.6, top_p 0.95, max_tokens 32000, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| log_stats | think | 8 | 5/8 | 96.6% | 4247 | 0 | 0 |
| retry_decorator | think | 8 | 8/8 | 100.0% | 1724 | 0 | 0 |
| shopping_cart | think | 8 | 4/8 | 93.3% | 3567 | 0 | 0 |
| todo_repo | think | 8 | 8/8 | 100.0% | 2567 | 0 | 0 |

## Per-sample failures

- log_stats/think-s0 (10/11): test_malformed_lines
- log_stats/think-s5 (10/11): test_malformed_lines
- log_stats/think-s6 (10/11): test_malformed_lines
- shopping_cart/think-s1 (13/15): test_empty_cart, test_remove_partial_and_full
- shopping_cart/think-s4 (13/15): test_empty_cart, test_remove_partial_and_full
- shopping_cart/think-s5 (13/15): test_empty_cart, test_remove_partial_and_full
- shopping_cart/think-s6 (13/15): test_empty_cart, test_remove_partial_and_full
