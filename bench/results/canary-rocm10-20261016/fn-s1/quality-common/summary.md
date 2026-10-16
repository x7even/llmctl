# Code test results — qwen3.8-flash-next-vllm

Generated 2026-10-16 18:12:32  (temperature 0.6, top_p 0.95, max_tokens 81920, reasoning_effort medium)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | early stops (empty/cut) | import failures |
|---|---|---|---|---|---|---|---|---|
| expr_eval | think | 2 | 1/2 | 94.4% | 7166 | 0 | 0/0 | 0 |
| log_stats | think | 2 | 2/2 | 100.0% | 3586 | 0 | 0/0 | 0 |
| retry_decorator | think | 2 | 2/2 | 100.0% | 1672 | 0 | 0/0 | 0 |
| shopping_cart | think | 2 | 2/2 | 100.0% | 3092 | 0 | 0/0 | 0 |
| todo_repo | think | 2 | 2/2 | 100.0% | 2242 | 0 | 0/0 | 0 |
| ttl_cache | think | 2 | 2/2 | 100.0% | 3646 | 0 | 0/0 | 0 |

## Per-sample failures

- expr_eval/think-s1 (16/18): test_decimal_literals, test_differential_fuzz
