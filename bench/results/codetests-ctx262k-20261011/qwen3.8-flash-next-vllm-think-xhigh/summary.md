# Code test results — qwen3.8-flash-next-vllm

Generated 2026-10-11 23:54:27  (temperature 0.6, top_p 0.95, max_tokens 256000, reasoning_effort template default)

| task | mode | samples | full passes | mean tests passed | mean completion tok | truncated | import failures |
|---|---|---|---|---|---|---|---|
| log_stats | think | 2 | 1/2 | 50.0% | 178062 | 1 | 0 |
| retry_decorator | think | 2 | 1/2 | 50.0% | 148945 | 1 | 0 |
| shopping_cart | think | 2 | 0/2 | 0.0% | 256000 | 2 | 0 |
| todo_repo | think | 2 | 1/2 | 50.0% | 172976 | 1 | 0 |

## Per-sample failures

- log_stats/think-s0 (0/11): test_totals, test_status_counts, test_error_rate, test_top_paths, test_query_string_stripped, test_requests_per_hour, test_malformed_lines, test_empty_input, test_fewer_than_three_paths, test_accepts_generator_and_newlines, test_return_keys
- retry_decorator/think-s1 (0/12): test_success_first_try, test_retries_then_succeeds, test_exhausts_and_raises_last, test_backoff_sequence, test_unlisted_exception_propagates_immediately, test_listed_tuple_of_exceptions, test_default_exceptions_cover_exception_subclasses, test_max_attempts_one, test_parameter_validation, test_preserves_metadata, test_calls_counter_accumulates, test_independent_decorated_functions
- shopping_cart/think-s0 (0/15): test_empty_cart, test_add_and_subtotal, test_add_same_sku_accumulates, test_add_validation, test_remove_partial_and_full, test_remove_validation, test_remove_exact_quantity_removes_line, test_coupon_save10, test_coupon_fiveoff_capped, test_coupon_replaces_previous_and_validation, test_tax, test_tax_applied_after_discount_with_rounding, test_half_up_rounding, test_tax_rate_validation, test_summary_keys_and_types
- shopping_cart/think-s1 (0/15): test_empty_cart, test_add_and_subtotal, test_add_same_sku_accumulates, test_add_validation, test_remove_partial_and_full, test_remove_validation, test_remove_exact_quantity_removes_line, test_coupon_save10, test_coupon_fiveoff_capped, test_coupon_replaces_previous_and_validation, test_tax, test_tax_applied_after_discount_with_rounding, test_half_up_rounding, test_tax_rate_validation, test_summary_keys_and_types
- todo_repo/think-s0 (0/11): test_add_and_get, test_title_stripped_and_validated, test_priority_validation, test_special_characters_roundtrip, test_list_order_by_priority_then_id, test_list_filter_by_done, test_mark_done, test_delete_and_no_id_reuse, test_count, test_persistence_across_instances, test_empty_repo
