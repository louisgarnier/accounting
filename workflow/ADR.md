# Architecture Decision Records

## ADR-002 — Enable Banking ASPSP list fetched dynamically
**Date:** 2026-03-29
**Decision:** Frontend fetches available banks from `GET /api/banking/aspsps?country=XX` (which proxies Enable Banking's `/aspsps` endpoint) rather than a hardcoded list.
**Reason:** Enable Banking returns 422 if the ASPSP name doesn't match exactly. Names can change and vary by region. Hardcoding caused "Revolut" to fail (wrong exact name).
**Status:** Accepted

## ADR-003 — Transaction dedup keyed on (account_uid, external_id)
**Date:** 2026-03-29
**Decision:** Unique constraint on transactions table is `(account_uid, external_id)`, not just `external_id`.
**Reason:** Revolut FX exchange trades produce two transactions with the same `transaction_id` — one on each account (e.g. CAD account and EUR account). A global unique constraint on `external_id` dropped the second leg as a duplicate.
**Status:** Accepted

## ADR-001 — Tech Stack
**Date:** 2026-03-28
**Decision:** Next.js PWA (Vercel) + FastAPI (Railway) + Supabase
**Reason:** Supabase handles OAuth, RLS, and file storage out of the box. FastAPI handles OCR and integrations where Python has the best library support. Next.js is the strongest frontend choice for this use case.
**Status:** Accepted
