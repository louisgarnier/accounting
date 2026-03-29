# Known Errors & Fixes

_Append here after fixing any bug. Format: date | area | error | fix | prevention rule_

| Date | Area | Error | Fix | Prevention |
|------|------|-------|-----|------------|
| 2026-03-28 | webhooks/tests | HMAC signature mismatch: `make_signature` used `json.dumps(separators=(",",":"))` (compact) but httpx `json=` kwarg sends standard spaced JSON, causing 401 on valid requests | Changed `make_signature` to use `json.dumps(payload)` (default separators matching httpx wire format) | When writing HMAC test helpers, use same JSON serializer as the HTTP client (`json.dumps` default = spaced, matches httpx/requests `json=` kwarg) |
| 2026-03-29 | banking/tests | `test_sync_saves_transactions_and_returns_count` was a false positive: single `return_value` on `.table().select().eq().execute()` mock was reused for both the connections query AND the dedup check — dedup always returned non-empty data, so every transaction was skipped (synced=0) but test only checked `"synced" in resp.json()` | Changed to `side_effect=[connections_result, dedup_result]` so each call gets distinct return data; tightened assertion to `resp.json()["synced"] == 1` | When a router calls the same DB mock chain more than once, always use `side_effect` with a list. Never assert key presence only — always assert the exact value. |
| 2026-03-29 | banking/tests | `test_sync_debit_amount_is_negative` silently passed when no rows were inserted because assertion was inside `if saved_rows:` guard | Removed guard; assert `len(saved_rows) == 1` unconditionally first, then check amount sign | Never wrap a test assertion in a conditional guard — it turns failures into silent passes |
