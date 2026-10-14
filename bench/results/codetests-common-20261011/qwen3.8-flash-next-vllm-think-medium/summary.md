# Code test results — qwen3.8-flash-next-vllm

Generated 2026-10-11 10:51:28  (temperature 0.6, top_p 0.95, max_tokens 32000, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| log_stats | think | 8 | 5/8 | 96.6% | 3626 | 0 | 0 |
| retry_decorator | think | 8 | 8/8 | 100.0% | 1748 | 0 | 0 |
| shopping_cart | think | 8 | 8/8 | 100.0% | 2765 | 0 | 0 |
| todo_repo | think | 8 | 8/8 | 100.0% | 1894 | 0 | 0 |

## Per-sample failures

- log_stats/think-s1 (10/11): test_malformed_lines
- log_stats/think-s2 (10/11): test_malformed_lines
- log_stats/think-s4 (10/11): test_malformed_lines
