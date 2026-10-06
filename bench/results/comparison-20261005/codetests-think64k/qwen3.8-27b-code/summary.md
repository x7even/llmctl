# Code test results — qwen3.8-27b-code

Generated 2026-10-05 19:06:37  (temperature 0.6, top_p 0.95, max_tokens 24000)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| ttl_cache | think | 3 | 2/3 | 66.7% | 34292 | 0 | 0 |

## Per-sample failures

- ttl_cache/think-s1 (0/22): test_basic_put_get, test_validation, test_expiry_boundary_inclusive, test_per_entry_ttl, test_infinite_ttl, test_get_does_not_extend_ttl, test_overwrite_resets_ttl_and_value, test_overwrite_uses_new_ttl_or_default, test_lru_eviction_order, test_get_refreshes_recency, test_peek_does_not_refresh, test_contains_does_not_refresh, test_overwrite_refreshes_and_never_evicts, test_expired_purged_before_lru_eviction, test_expired_slot_reclaimed_prefers_expired_over_lru, test_len_excludes_expired, test_delete_semantics, test_overwrite_expired_key_counts_as_new_insert, test_none_value_is_a_hit, test_hashable_keys, test_capacity_one, test_model_based_random
