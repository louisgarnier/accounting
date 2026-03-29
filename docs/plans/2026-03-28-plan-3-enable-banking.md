# Enable Banking Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user connect their bank account via Enable Banking and sync transactions with one button tap.

**Architecture:** FastAPI handles all Enable Banking API calls (JWT auth, bank connect flow, session exchange, transaction fetch) since the RSA private key lives in Railway env vars. The frontend drives the flow: Connect Bank page → Enable Banking authorization → callback page exchanges the code via FastAPI → Sync button on the transactions page calls FastAPI to pull fresh transactions. A new `bank_connections` Supabase table stores account UIDs and session IDs.

**Tech Stack:** PyJWT[cryptography] (RS256 JWT signing), httpx (Enable Banking HTTP calls), FastAPI, Next.js 16.2.1 server + client components, Supabase PostgreSQL

---

## Credentials & Context

- **Enable Banking App ID:** `4ab7c74d-943b-45d7-be5b-343e8744eb92`
- **Private key env var:** `ENABLE_BANKING_PRIVATE_KEY` (already in Railway, full PEM including `-----BEGIN/END PRIVATE KEY-----`)
- **Railway backend URL:** `https://accounting-production-d529.up.railway.app`
- **Vercel frontend URL:** `https://accounting-flax-pi.vercel.app`
- **Callback URL:** `https://accounting-flax-pi.vercel.app/banking/callback`

## Enable Banking API Quick Reference

- **Base URL:** `https://api.enablebanking.com`
- **Auth:** `Authorization: Bearer <JWT>` on every request
- **JWT header:** `{"typ":"JWT","alg":"RS256","kid":"<app_id>"}`
- **JWT payload:** `{"iss":"enablebanking.com","aud":"api.enablebanking.com","iat":<now>,"exp":<now+3600>}`
- **POST /auth** → `{url, authorization_id}` — start bank connection, get redirect URL
- **POST /sessions** → `{session_id, accounts:[{uid,...}], aspsp:{name}}` — exchange auth code for session
- **GET /accounts/{uid}/transactions?date_from=YYYY-MM-DD** → `{transactions:[...], continuation_key}` — paginated

## Critical Testing Pattern — Multi-Call DB Mocks

> **Read this before writing any test that calls a sync endpoint.**

When a router calls the DB chain `.table().select().eq().execute()` more than once (e.g. connections query + dedup check), a single `return_value` on the mock will return the **same data for every call**. This causes silent false positives.

**Wrong — both queries return the same data:**
```python
mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[...])
```

**Correct — each call gets its own return value:**
```python
mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
    MagicMock(data=[{"account_uid": "acc-uid-1", "institution_name": "BNP Paribas"}]),  # 1st call: connections
    MagicMock(data=[]),   # 2nd call: dedup check (not seen before)
]
```

Always use `side_effect` with a list when the same mock chain is called more than once.
Always assert the **exact count** (`resp.json()["synced"] == 1`), never just check key presence (`"synced" in resp.json()`).
Never use `if saved_rows:` as a guard before an assertion — remove the guard and assert unconditionally.

## File Structure

**Created:**
- `supabase/migrations/002_bank_connections.sql` — bank_connections table + RLS
- `backend/app/services/__init__.py`
- `backend/app/services/enable_banking.py` — JWT generation + Enable Banking API calls
- `backend/app/routers/banking.py` — FastAPI routes: connect, sessions, sync
- `backend/tests/test_enable_banking_service.py` — service unit tests (5 tests)
- `backend/tests/test_banking_router.py` — router integration tests (7 tests)
- `frontend/app/(dashboard)/banking/connect/page.tsx` — bank selection UI
- `frontend/app/(dashboard)/banking/callback/page.tsx` — OAuth callback handler
- `frontend/components/SyncButton.tsx` — sync button with loading state

**Modified:**
- `backend/requirements.txt` — added `PyJWT[cryptography]==2.9.0`
- `backend/app/config.py` — added `ENABLE_BANKING_APP_ID`, `ENABLE_BANKING_PRIVATE_KEY`
- `backend/app/main.py` — registered banking router
- `backend/tests/conftest.py` — added new env vars
- `frontend/app/(dashboard)/transactions/page.tsx` — connect/sync UI + flash messages

---

### Task 0: Local dev setup ✅ REQUIRED BEFORE ANYTHING ELSE

Without this, you cannot run scripts, query logs, or debug locally.

**Files:**
- Create: `backend/.env` (git-ignored, never commit)

- [ ] **Step 1: Copy the example and fill in real values**

```bash
cp backend/.env.example backend/.env
```

Then open `backend/.env` and fill in:
- `SUPABASE_URL` — Supabase Dashboard → Settings → API → Project URL
- `SUPABASE_SERVICE_KEY` — Supabase Dashboard → Settings → API → service_role key (not anon)
- `APP_USER_ID` — your Supabase user UUID (Auth → Users → your account)
- `ENABLE_BANKING_WEBHOOK_SECRET` — Enable Banking portal → your app → webhook secret
- `ENABLE_BANKING_APP_ID` — `4ab7c74d-943b-45d7-be5b-343e8744eb92`
- `ENABLE_BANKING_PRIVATE_KEY` — full PEM, same value as Railway env var

- [ ] **Step 2: Verify it works**

```bash
cd backend && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
from supabase import create_client
db = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
rows = db.table('logs').select('id').limit(1).execute()
print('OK — Supabase connected, logs table accessible')
"
```

Expected: `OK — Supabase connected, logs table accessible`

- [ ] **Step 3: Confirm .env is git-ignored**

```bash
grep -q ".env" backend/.gitignore && echo "OK — .env is ignored" || echo "ADD .env TO .gitignore NOW"
```

If it prints the warning, run:
```bash
echo ".env" >> backend/.gitignore
```

---

## Log query cheatsheet

Run these any time you need to see what's happening in production:

```bash
# All errors in the last hour
cd backend && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
from supabase import create_client
db = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
rows = db.table('logs').select('created_at,layer,message,context').eq('level','error').order('created_at', desc=True).limit(30).execute()
for r in rows.data:
    print(r['created_at'][:19], r['layer'], '|', r['message'])
    if r.get('context'): print('  ', r['context'])
"

# All banking-related logs (info + error)
cd backend && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
from supabase import create_client
db = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
rows = db.table('logs').select('created_at,level,layer,message,context').ilike('message','%banking%').order('created_at', desc=True).limit(30).execute()
for r in rows.data:
    print(r['created_at'][:19], r['level'].upper(), '|', r['message'])
    if r.get('context'): print('  ', r['context'])
"
```

---

### Task 1: Supabase migration — bank_connections table ✅ DONE

Migration file at `supabase/migrations/002_bank_connections.sql`.

- [x] Write migration file
- [ ] **Run in Supabase Dashboard → SQL Editor → New Query, paste, click Run**

  Expected: "Success. No rows returned."

- [ ] **Verify in Supabase Table Editor** — `bank_connections` appears alongside the other tables.

- [ ] **Commit**

  ```bash
  python3 scripts/git_ops.py add supabase/migrations/002_bank_connections.sql
  python3 scripts/git_ops.py commit "[EPIC-3] feat: add bank_connections table migration"
  ```

---

### Task 2: Backend — Enable Banking service ✅ DONE

Files: `backend/app/services/enable_banking.py`, `backend/tests/test_enable_banking_service.py`

Verify still passing:
```bash
cd backend && pytest tests/test_enable_banking_service.py -v
```
Expected: `5 passed`

---

### Task 3: Backend — Banking router ✅ DONE

Files: `backend/app/routers/banking.py`, `backend/tests/test_banking_router.py`

Verify still passing:
```bash
cd backend && pytest tests/test_banking_router.py -v
```
Expected: `7 passed`

Full suite:
```bash
cd backend && pytest -v
```
Expected: `41 passed`

- [ ] **Commit all uncommitted backend work**

  ```bash
  python3 scripts/git_ops.py add backend/app/services/__init__.py backend/app/services/enable_banking.py backend/app/routers/banking.py backend/app/main.py backend/tests/test_enable_banking_service.py backend/tests/test_banking_router.py backend/app/config.py backend/requirements.txt backend/tests/conftest.py
  python3 scripts/git_ops.py commit "[EPIC-3] feat: Enable Banking service, router, and tests (41 passing)"
  ```

---

### Task 4: Frontend — Connect Bank page + Callback page ✅ DONE

Files: `frontend/app/(dashboard)/banking/connect/page.tsx`, `frontend/app/(dashboard)/banking/callback/page.tsx`

Verify build still passes:
```bash
cd frontend && npm run build
```
Expected: `✓ Compiled successfully` with routes `/banking/connect` and `/banking/callback` listed.

- [ ] **Commit frontend pages**

  ```bash
  python3 scripts/git_ops.py add "frontend/app/(dashboard)/banking/connect/page.tsx" "frontend/app/(dashboard)/banking/callback/page.tsx"
  python3 scripts/git_ops.py commit "[EPIC-3] feat: add connect bank page and OAuth callback handler"
  ```

---

### Task 5: Frontend — Sync button + updated Transactions page ✅ DONE

Files: `frontend/components/SyncButton.tsx`, `frontend/app/(dashboard)/transactions/page.tsx`

Verify build still passes:
```bash
cd frontend && npm run build
```
Expected: `✓ Compiled successfully`

- [ ] **Commit**

  ```bash
  python3 scripts/git_ops.py add "frontend/components/SyncButton.tsx" "frontend/app/(dashboard)/transactions/page.tsx"
  python3 scripts/git_ops.py commit "[EPIC-3] feat: add sync button and connect bank UI to transactions page"
  ```

---

### Task 6: Pre-deploy checklist

Before pushing, complete these one at a time. Each step has an expected outcome — stop and fix if the outcome doesn't match.

- [ ] **Step 1: Run full backend test suite**

  ```bash
  cd backend && pytest -v
  ```
  Expected: `41 passed, 0 failed`
  If any fail: fix before continuing.

- [ ] **Step 2: Run frontend build**

  ```bash
  cd frontend && npm run build 2>&1
  ```
  Expected: `✓ Compiled successfully` — no TypeScript errors, no missing imports.
  If build fails: read the error, fix the specific file, re-run build.

- [ ] **Step 3: Check git status — nothing untracked that should be committed**

  ```bash
  python3 scripts/git_ops.py status
  ```
  Expected: clean or only the plan file untracked.
  Commit anything missing using the pattern from Tasks 3–5.

- [ ] **Step 4: Commit the plan file**

  ```bash
  python3 scripts/git_ops.py add docs/plans/2026-03-28-plan-3-enable-banking.md docs/project/config/build-log.md workflow/ERRORS.md workflow/ADR.md
  python3 scripts/git_ops.py commit "[EPIC-3] docs: add plan, update build log and workflow docs"
  ```

---

### Task 7: Deploy

- [ ] **Step 1: Push to GitHub**

  ```bash
  python3 scripts/git_ops.py push
  ```

  Railway and Vercel auto-deploy on push to main.

- [ ] **Step 2: Watch Railway build log**

  Go to Railway Dashboard → your service → Deployments → click the latest deployment → View Logs.

  Watch for:
  - `Collecting PyJWT[cryptography]` — must appear (new dep)
  - `Successfully installed PyJWT` — install succeeded
  - `🚀 [Backend] starting` — app booted
  - `✅ [Backend] Supabase connection ok` — DB connected

  If build fails on `PyJWT`:
  - Check `backend/requirements.txt` has exactly `PyJWT[cryptography]==2.9.0`
  - Railway may need `cryptography` version pinned — add `cryptography==42.0.8` on a new line

  If startup logs show `ENABLE_BANKING_PRIVATE_KEY: False`:
  - Go to Railway → Variables → add `ENABLE_BANKING_PRIVATE_KEY` with full PEM value
  - Redeploy

- [ ] **Step 3: Verify Railway health endpoint**

  ```bash
  curl https://accounting-production-d529.up.railway.app/health
  ```
  Expected: `{"status":"ok"}` with HTTP 200.
  If 502/503: Railway hasn't finished deploying yet — wait 60s and retry.

- [ ] **Step 4: Watch Vercel build log**

  Go to Vercel Dashboard → your project → Deployments → latest → View Function Logs.

  Watch for:
  - Build completing without TypeScript errors
  - All 6 routes listed: `/`, `/login`, `/transactions`, `/banking/connect`, `/banking/callback`, `/_not-found`

  If Vercel build fails with `Module not found: Can't resolve '@/components/SyncButton'`:
  - Check `frontend/components/SyncButton.tsx` exists and is committed

---

### Task 8: Register callback URL in Enable Banking portal

This must be done before the connect flow will work.

- [ ] **Step 1: Register redirect URL**

  Go to **Enable Banking Developer Portal → Your Application → Settings → Redirect URLs**.
  Add: `https://accounting-flax-pi.vercel.app/banking/callback`
  Save.

  Without this, Enable Banking returns an error after the user authorises at their bank.

---

### Task 9: End-to-end test

Do each step, verify the expected outcome before moving to the next.

- [ ] **Step 1: Open transactions page**

  Go to `https://accounting-flax-pi.vercel.app/transactions`

  Expected: **Connect Bank** button visible in the top-right (no bank connected yet).
  If **Sync** button shows instead: a stale `bank_connections` row exists — go to Supabase → Table Editor → bank_connections → delete the row, refresh.

- [ ] **Step 2: Start connection flow**

  Click **Connect Bank** → you land on `/banking/connect`.
  Expected: a bank dropdown + Connect button.

- [ ] **Step 3: Select bank and connect**

  Select a bank (e.g. BNP Paribas) → click **Connect**.
  Expected: page redirects to Enable Banking's authorization page (`ob.enablebanking.com`).
  If you see "Could not connect to your bank":
  - Open browser devtools → Network tab → find the `/api/banking/connect` call → check its response body
  - Common cause: Railway hasn't deployed yet, or `ENABLE_BANKING_PRIVATE_KEY` is missing

- [ ] **Step 4: Authorize at bank**

  Complete the bank authorization steps on Enable Banking's page.
  Expected: redirected back to `https://accounting-flax-pi.vercel.app/transactions?bank_connected=1`
  Expected: green banner "Bank connected. Press Sync to import your transactions."
  If you see `?bank_error=1`:
  - Check Railway logs for the `/api/banking/sessions` call
  - Common cause: `code` parameter was missing from the callback URL (Enable Banking config issue)

- [ ] **Step 5: Sync transactions**

  Click **Sync**.
  Expected: loading spinner → "N new transactions synced" message → transaction list populates.
  If "Sync failed":
  - Open browser devtools → Network → `/api/banking/sync` → check response body
  - Check Railway logs for the error

- [ ] **Step 6: Verify transaction data**

  Transactions should show: description, date, bank name, amount with sign (negative for debits), Unmatched badge.

---

## Session close checklist

- [ ] Update `docs/project/config/build-log.md` — mark Plan 3 complete
- [ ] Update `docs/project/config/codebase.md` — add new modules
- [ ] Append any new bugs hit to `workflow/ERRORS.md`
- [ ] Append any architectural decisions to `workflow/ADR.md`
