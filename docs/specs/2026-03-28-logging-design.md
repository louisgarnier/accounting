# Logging Design

**Status:** Draft
**Date:** 2026-03-28
**Scope:** Full-stack observability — frontend, API, backend, database

---

## Goal

Every request, error, and state change is captured in Supabase so Claude can query the full picture directly without requiring the user to share logs manually.

---

## Log Store: Supabase `logs` Table

Single source of truth. All layers write here. Queryable at any time.

### Schema

```sql
create table logs (
  id            uuid        default gen_random_uuid() primary key,
  created_at    timestamptz default now(),
  layer         text        not null,  -- 'frontend' | 'api' | 'backend' | 'database'
  level         text        not null,  -- 'info' | 'warn' | 'error'
  message       text        not null,
  request_id    text,                  -- UUID shared by frontend + backend for same request
  url           text,                  -- full URL called (API and frontend fetches)
  method        text,                  -- GET | POST | etc.
  status_code   integer,               -- HTTP status code
  duration_ms   integer,               -- elapsed time
  context       jsonb,                 -- arbitrary structured data (error body, row counts, etc.)
  user_id       uuid references auth.users(id)
);
```

### RLS

- **Backend** (service role key): full access, bypasses RLS
- **Frontend** (user session): insert only, own rows (`auth.uid() = user_id`)

### Local files (dev only)

When `LOG_DIR=../logs` is set in `backend/.env`, backend also writes to:
```
logs/
├── backend_YYYY-MM-DD.log
├── api_YYYY-MM-DD.log
├── database_YYYY-MM-DD.log
└── frontend_YYYY-MM-DD.log
```
Not used on Railway (no persistent filesystem).

---

## What Gets Logged

### Layer: `api` — every HTTP request/response

| Event | Level | Fields |
|-------|-------|--------|
| Request received | info | method, url, request_id |
| Response sent | info | method, url, status_code, duration_ms |
| Unhandled exception | error | url, message, context (stack trace) |

### Layer: `backend` — server events

| Event | Level | Fields |
|-------|-------|--------|
| Startup + env var presence | info | context: `{SUPABASE_URL: true, ENABLE_BANKING_APP_ID: true, ...}` (names only, never values) |
| Supabase connection check | info / error | message: "DB connection ok" or error detail |
| Enable Banking API error | error | url, status_code, context: response body |
| OAuth callback steps | info | message: "code received", "session created", "N accounts stored" |

### Layer: `database` — every Supabase operation in backend

| Event | Level | Fields |
|-------|-------|--------|
| Select | info | context: `{table, filter, rows_returned, duration_ms}` |
| Insert | info | context: `{table, rows_inserted, duration_ms}` |
| Delete | info | context: `{table, filter, rows_deleted, duration_ms}` |
| Operation error | error | context: `{table, operation, error}` |

### Layer: `frontend` — browser-side

| Event | Level | Fields |
|-------|-------|--------|
| App config on load | info | context: `{backend_url, supabase_url}` — exposes values so misconfiguration is visible |
| Fetch started | info | method, url, request_id |
| Fetch success | info | method, url, status_code, duration_ms, request_id |
| HTTP error | error | method, url, status_code, context: response body, request_id |
| Network error (TypeError) | error | message: "network error", url attempted, context: error message |
| OAuth callback received | info | context: `{has_code, has_error}` |

---

## Correlation: `request_id`

Frontend generates a UUID per fetch call. Passes it as `X-Request-ID` header.
Backend reads it from the header and includes it in all `api` and `database` log entries for that request.

**Query to trace one user action end-to-end:**
```sql
select layer, level, message, url, status_code, duration_ms, context, created_at
from logs
where request_id = '<uuid>'
order by created_at;
```

---

## Frontend Logger (`frontend/lib/logger.ts`)

Writes to Supabase directly via the user session client. Works even if the backend URL is wrong.

```
logger.info(message, context?)
logger.warn(message, context?)
logger.error(message, context?)
logger.fetch(method, url) → returns { request_id, done(status, body?) }
```

`logger.fetch` wraps every API call: captures start time, generates request_id, writes `fetch started`, then `done()` writes `fetch success` or `fetch error` with duration.

**Network error handling:** catches `TypeError` separately from HTTP errors, logs the attempted URL and error message as `layer: frontend, level: error`.

---

## Backend Logger (`backend/app/logger.py`)

Four named loggers: `backend_logger`, `api_logger`, `db_logger`.
Each writes to stdout (Railway captures) + optional file (if LOG_DIR set) + Supabase `logs` table via a non-blocking background task.

**Supabase writes are fire-and-forget** (via `asyncio.create_task` in async context, thread in sync context) — logging never blocks a request.

---

## Database Logger (`backend/app/db_logger.py`)

Thin wrapper around Supabase table operations:

```python
def db_select(table, query) → (data, error)
def db_insert(table, rows) → (data, error)
def db_delete(table, filter) → (data, error)
```

Each function times the operation, logs to `db_logger`, and returns the result. All routers use these instead of calling `get_db()` directly.

---

## API Middleware

FastAPI `@app.middleware("http")`:
1. Reads or generates `X-Request-ID`
2. Logs request received
3. Calls route handler
4. Logs response with `status_code` and `duration_ms`
5. On unhandled exception: logs full stack trace, returns 500

---

## Startup Checks (`backend/app/main.py`)

On startup:
1. Log all required env var names with `True/False` presence (never log values)
2. Attempt a lightweight Supabase query (`select 1 from logs limit 1`) — log success or error
3. Log `🚀 [Backend] started`

---

## OAuth Callback Logging

`/banking/callback` page (frontend) logs each step:
1. Page loaded — `{has_code: bool, has_error: bool}`
2. Calling `/api/banking/sessions` — fetch log via `logger.fetch`
3. Success — `{accounts_connected: N}`
4. Redirect to `/transactions?bank_connected=1`

`/api/banking/sessions` (backend) logs:
1. Code received (request_id from header)
2. Enable Banking session created
3. N accounts stored in `bank_connections`

---

## Files Changed

```
backend/
  app/
    logger.py          MODIFY — add db_logger, Supabase async write
    db_logger.py       NEW    — db_select / db_insert / db_delete wrappers
    main.py            MODIFY — startup checks, updated middleware
    routers/
      banking.py       MODIFY — use db_logger wrappers, log callback steps
      webhooks.py      MODIFY — use db_logger wrappers
  .env.example         MODIFY — add LOG_DIR=../logs

frontend/
  lib/
    logger.ts          NEW    — logger.info/warn/error/fetch
  app/(dashboard)/
    banking/
      connect/page.tsx MODIFY — use logger.fetch, log config on mount
      callback/page.tsx MODIFY — log each OAuth step
  components/
    SyncButton.tsx     MODIFY — use logger.fetch

supabase/
  migrations/
    20260328_logs.sql  NEW    — logs table + RLS
```

---

## Querying Logs (Claude's interface)

```sql
-- Last 20 errors across all layers
select created_at, layer, message, url, status_code, context
from logs where level = 'error'
order by created_at desc limit 20;

-- Trace one request end-to-end
select * from logs where request_id = '<uuid>' order by created_at;

-- Frontend config snapshots (spot misconfiguration)
select created_at, context from logs
where layer = 'frontend' and message = 'app config'
order by created_at desc limit 5;

-- All Enable Banking errors
select created_at, message, status_code, context
from logs where layer = 'backend' and level = 'error'
order by created_at desc limit 20;
```

---

## What This Fixes

| Past incident | How logs would have caught it |
|---------------|-------------------------------|
| NEXT_PUBLIC_BACKEND_URL not set | Frontend config log shows `backend_url: undefined` on first page load |
| Revolut country FR vs GB | Enable Banking error log shows `404: {"error": "aspsp not found"}` |
| Generic "Could not connect" | Frontend network error log shows exact URL attempted + TypeError message |
| Silent OAuth callback failure | Each callback step logged — know exactly which step failed |
