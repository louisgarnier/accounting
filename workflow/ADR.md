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

---

## Planning Lessons — Requirements gaps found during Plan 3

These are specification gaps that caused real bugs or delays. Use as a checklist when writing future plans.

### Category A — External API contracts

| # | Gap | What should be in the spec |
|---|-----|---------------------------|
| A1 | ASPSP names were hardcoded as free-text strings — Enable Banking returned 422 | "ASPSP names are enum values owned by the API. Always fetch from `GET /aspsps` — never hardcode." |
| A2 | Enable Banking transaction dedup assumed one global ID per transaction — FX pairs across accounts share the same `transaction_id` | "FX exchanges produce one transaction per account with the same ID. Dedup must be scoped to `(account_uid, external_id)`." |
| A3 | Transaction history window was never defined | "Specify: how far back on first sync, how far back on subsequent syncs, whether user can control it." |

### Category B — Infrastructure & secrets

| # | Gap | What should be in the spec |
|---|-----|---------------------------|
| B1 | PEM key format on Railway was unspecified — Railway strips newlines, breaking RS256 signing | "Specify exact storage format: raw base64 body only (no headers, no newlines). Document that code must wrap it into valid PEM at runtime." |
| B2 | `PyJWT[cryptography]` extra not reliably installed by Railway | "Always pin transitive deps explicitly (`cryptography==X.Y.Z`). Never rely on extras to pull in critical packages." |
| B3 | Railway env var formatting issues (line breaks, trailing quotes, trailing spaces) were not anticipated | "After adding any secret to Railway, verify in Raw Editor that there are no trailing characters or embedded newlines." |

### Category C — Framework behaviour

| # | Gap | What should be in the spec |
|---|-----|---------------------------|
| C1 | CORS middleware ordering was left implicit — logging middleware was outermost, so error responses had no CORS headers | "State explicitly in the plan: CORS must be the outermost middleware layer. Register it last, after all `@app.middleware` decorators." |
| C2 | `create_client()` outside try/except caused unhandled exceptions → 500 instead of 401 | "Every external client call at a system boundary must be inside the error handler. No exceptions." |

### Category D — Test design

| # | Gap | What should be in the spec |
|---|-----|---------------------------|
| D1 | Mock chain collision: single `return_value` reused across multiple DB calls in the same route — tests passed when logic was broken | "State the multi-call mock rule in the plan's testing section before any test is written: use `side_effect=[...]` whenever the same chain is called more than once." |
| D2 | Assertion wrapped in `if saved_rows:` guard — test silently passed when nothing was inserted | "Never wrap assertions in conditional guards. Assert unconditionally — a missing row is a test failure, not a no-op." |

### Meta-lesson

Most of these gaps are at **integration seams** — where two systems meet (Railway + PEM, Enable Banking + ASPSP names, Revolut + FX model). Future plans should include an **"Integration assumptions to verify"** section per external dependency, listing format contracts, known edge cases, and how to validate before coding.

---

## ADR-001 — Tech Stack
**Date:** 2026-03-28
**Decision:** Next.js PWA (Vercel) + FastAPI (Railway) + Supabase
**Reason:** Supabase handles OAuth, RLS, and file storage out of the box. FastAPI handles OCR and integrations where Python has the best library support. Next.js is the strongest frontend choice for this use case.
**Status:** Accepted
