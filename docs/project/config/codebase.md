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
- `backend/app/main.py` — FastAPI app entry point, CORS middleware
- `backend/app/config.py` — Environment config (SUPABASE_URL, SUPABASE_SERVICE_KEY, FRONTEND_URL)
- `backend/app/routers/health.py` — GET /health → {"status": "ok"}
- `backend/tests/conftest.py` — Sets dummy env vars for test isolation
- `backend/Dockerfile` — python:3.11-slim, uvicorn on port 8000
- `backend/.env.example` — Template for required env vars
