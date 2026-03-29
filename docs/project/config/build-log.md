# Build Log

## Stage: Plan 1 — Foundation
**Status:** Complete
**Started:** 2026-03-28
**Completed:** 2026-03-28

### Completed
- Design spec written and approved
- Task 1: Project infrastructure (git_ops.py, workflow files)
- Task 2: Supabase schema with RLS on all 5 tables
- Task 3: FastAPI scaffold with health endpoint (tested)
- Task 4: FastAPI JWT auth middleware (tested, 4/4 tests passing)
- Task 5: Next.js PWA scaffold with Supabase client and auth proxy
- Task 6: Login/logout UI with Supabase server actions
- Task 7: Deploy configuration for Vercel and Railway

## Stage: Plan 2 — Bank Transactions
**Status:** Complete
**Started:** 2026-03-28
**Completed:** 2026-03-28

### Completed
- Task 1: Enable Banking webhook endpoint with HMAC-SHA256 signature verification, deduplication, and Supabase persistence (8/8 tests passing, commit eb9bad8)
- Task 2: Transaction list page — `/transactions` route with matched/unmatched status badges, server-side Supabase query, nav link in dashboard layout (build passes, commit 6cce223)

### Pending (manual)
- Run SQL migration in Supabase dashboard (002_bank_connections.sql)
- Deploy backend to Railway
- Deploy frontend to Vercel
- Add to phone home screen

---

## Stage: Plan 3 — Enable Banking Integration
**Status:** Complete
**Started:** 2026-03-28
**Completed:** 2026-03-29

### Completed
- Task 1: bank_connections Supabase migration (002_bank_connections.sql)
- Task 2: Enable Banking service — JWT RS256 + API client (5/5 tests passing)
- Task 3: Banking router — connect/sessions/sync endpoints (9/9 tests passing)
- Task 4: Connect Bank page + OAuth callback handler (frontend)
- Task 5: Sync button + updated Transactions page (frontend)
- Task 6: Pre-deploy checklist passed (43/43 tests, build clean)
- Task 7: Deployed — Railway + Vercel live
- Task 8: Callback URL registered in Enable Banking portal
- Task 9: End-to-end test passed — Revolut connected, transactions synced
- EPIC-4: Logging middleware — request timing, X-Request-ID, Supabase log writer
- Fixed: ASPSP names now fetched dynamically from Enable Banking API (no hardcoded list)
- Fixed: FX pairs (e.g. "Exchanged from CAD Main") were deduped as duplicates — changed unique key to (account_uid, external_id); migration 003_transactions_account_uid.sql
