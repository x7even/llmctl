# Code test results — qwen3.8-27b-code

Generated 2026-10-16 08:43:31  (temperature 0.6, top_p 0.95, max_tokens 81920, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | early stops (empty/cut) | import failures |
|---|---|---|---|---|---|---|---|---|
| expr_eval | think | 2 | 2/2 | 100.0% | 8047 | 0 | 0/0 | 0 |
| log_stats | think | 2 | 2/2 | 100.0% | 4219 | 0 | 0/0 | 0 |
| retry_decorator | think | 2 | 1/2 | 91.7% | 2023 | 0 | 0/0 | 0 |
| shopping_cart | think | 2 | 1/2 | 93.3% | 3789 | 0 | 0/0 | 0 |
| todo_repo | think | 2 | 2/2 | 100.0% | 3000 | 0 | 0/0 | 0 |
| ttl_cache | think | 2 | 2/2 | 100.0% | 3756 | 0 | 0/0 | 0 |

## Per-sample failures

- retry_decorator/think-s1 (10/12): test_calls_counter_accumulates, test_independent_decorated_functions
- shopping_cart/think-s0 (13/15): test_empty_cart, test_remove_partial_and_full
