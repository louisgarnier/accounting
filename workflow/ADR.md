# Architecture Decision Records

## ADR-001 — Tech Stack
**Date:** 2026-03-28
**Decision:** Next.js PWA (Vercel) + FastAPI (Railway) + Supabase
**Reason:** Supabase handles OAuth, RLS, and file storage out of the box. FastAPI handles OCR and integrations where Python has the best library support. Next.js is the strongest frontend choice for this use case.
**Status:** Accepted
