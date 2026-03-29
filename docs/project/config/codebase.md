# Codebase Map

## Structure
- `frontend/` — Next.js PWA (Vercel)
- `backend/` — FastAPI Python (Railway)
- `supabase/` — Database migrations
- `scripts/` — Dev tooling
- `workflow/` — ADR.md, ERRORS.md
- `docs/` — Specs, plans, config
- `logs/` — Runtime logs (gitignored)

## Modules
- `backend/app/main.py` — FastAPI app entry point, CORS + logging middleware
- `backend/app/config.py` — Environment config (SUPABASE_URL, SUPABASE_SERVICE_KEY, FRONTEND_URL, ENABLE_BANKING_APP_ID, ENABLE_BANKING_PRIVATE_KEY)
- `backend/app/auth.py` — JWT bearer auth via Supabase admin client
- `backend/app/database.py` — Supabase DB client (thread-safe singleton)
- `backend/app/logger.py` — backend_logger, fire-and-forget Supabase log writer
- `backend/app/routers/health.py` — GET /health → {"status": "ok"}
- `backend/app/routers/banking.py` — GET /api/banking/aspsps, POST /api/banking/connect, POST /api/banking/sessions, POST /api/banking/sync
- `backend/app/routers/webhooks.py` — POST /api/webhooks/enable-banking (HMAC-verified)
- `backend/app/services/enable_banking.py` — RS256 JWT signing, Enable Banking API client (get_aspsps, start_auth, create_session, fetch_transactions)
- `backend/tests/conftest.py` — Sets dummy env vars for test isolation
- `backend/Dockerfile` — python:3.11-slim, uvicorn on port 8000
- `backend/.env.example` — Template for required env vars
- `frontend/app/(dashboard)/banking/connect/page.tsx` — Bank selection UI (fetches ASPSP list dynamically)
- `frontend/app/(dashboard)/banking/callback/page.tsx` — OAuth callback, exchanges code via /api/banking/sessions
- `frontend/app/(dashboard)/transactions/page.tsx` — Transaction list with Connect Bank / Sync buttons
- `frontend/components/SyncButton.tsx` — Sync button with loading state
- `supabase/migrations/001_initial_schema.sql` — transactions, documents, matches, categories tables + RLS
- `supabase/migrations/002_bank_connections.sql` — bank_connections table + RLS
- `supabase/migrations/003_transactions_account_uid.sql` — adds account_uid column, changes unique key to (account_uid, external_id)
