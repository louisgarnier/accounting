# Plan 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap the full project infrastructure — Supabase schema, FastAPI backend, Next.js PWA frontend, and auth (login/logout) — so that the app runs locally and deploys to Vercel + Railway.

**Architecture:** Next.js PWA (Vercel) calls Supabase directly for auth and data reads. FastAPI (Railway) handles all heavy processing. Supabase provides PostgreSQL, file storage, and OAuth. All tables have RLS locked to the authenticated user.

**Tech Stack:** Next.js 14 (App Router, TypeScript, Tailwind), FastAPI (Python 3.11), Supabase (PostgreSQL + Storage + Auth), next-pwa, @supabase/ssr, Railway (Docker), Vercel

---

## Prerequisites (Manual Steps — Do These Before Starting)

These require a browser and cannot be automated:

1. **Create Supabase project** at https://supabase.com → New project → note your `Project URL` and `anon key` and `service_role key`
2. **Enable email auth** in Supabase → Authentication → Providers → Email → Enable
3. **Create your user account** in Supabase → Authentication → Users → Add user → use your email
4. **Create storage bucket** → Storage → New bucket → name: `documents` → Private → Save
5. **Create Vercel account** at https://vercel.com if not already done
6. **Create Railway account** at https://railway.app if not already done

---

## Task 1: Project Infrastructure

**Files:**
- Create: `scripts/git_ops.py`
- Create: `workflow/ADR.md`
- Create: `workflow/ERRORS.md`
- Create: `docs/project/config/build-log.md`
- Create: `docs/project/config/codebase.md`
- Create: `logs/.gitkeep`
- Create: `.gitignore`

- [ ] **Step 1: Create scripts/git_ops.py**

```python
#!/usr/bin/env python3
"""Git operations wrapper — use this for all git commands per CLAUDE.md."""
import subprocess
import sys
import argparse


def run(cmd: list[str]) -> int:
    result = subprocess.run(cmd, check=False)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Git operations wrapper")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status")

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("files", nargs="+")

    commit_parser = subparsers.add_parser("commit")
    commit_parser.add_argument("-m", "--message", required=True)

    subparsers.add_parser("push")

    log_parser = subparsers.add_parser("log")
    log_parser.add_argument("--oneline", action="store_true")

    diff_parser = subparsers.add_parser("diff")
    diff_parser.add_argument("args", nargs="*")

    args = parser.parse_args()

    if args.command == "status":
        return run(["git", "status"])
    elif args.command == "add":
        return run(["git", "add"] + args.files)
    elif args.command == "commit":
        return run(["git", "commit", "-m", args.message])
    elif args.command == "push":
        return run(["git", "push"])
    elif args.command == "log":
        cmd = ["git", "log"]
        if args.oneline:
            cmd.append("--oneline")
        return run(cmd)
    elif args.command == "diff":
        return run(["git", "diff"] + args.args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create workflow/ADR.md**

```markdown
# Architecture Decision Records

## ADR-001 — Tech Stack
**Date:** 2026-03-28
**Decision:** Next.js PWA (Vercel) + FastAPI (Railway) + Supabase
**Reason:** Supabase handles OAuth, RLS, and file storage out of the box. FastAPI handles OCR and integrations where Python has the best library support. Next.js is the strongest frontend choice for this use case.
**Status:** Accepted
```

- [ ] **Step 3: Create workflow/ERRORS.md**

```markdown
# Known Errors & Fixes

_Append here after fixing any bug. Format: date | area | error | fix | prevention rule_

| Date | Area | Error | Fix | Prevention |
|------|------|-------|-----|------------|
```

- [ ] **Step 4: Create docs/project/config/build-log.md**

```markdown
# Build Log

## Stage: Plan 1 — Foundation
**Status:** In progress
**Started:** 2026-03-28

### Completed
- Design spec written and approved

### In Progress
- Task 1: Project infrastructure

### Blockers
_None_
```

- [ ] **Step 5: Create docs/project/config/codebase.md**

```markdown
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
_Updated as modules are added_
```

- [ ] **Step 6: Create logs/.gitkeep and .gitignore**

Create `logs/.gitkeep` (empty file).

Create `.gitignore`:
```
# Dependencies
node_modules/
__pycache__/
*.pyc
.venv/
venv/

# Environment
.env
.env.local
.env.*.local

# Logs
logs/*.log

# Build
.next/
dist/
build/

# OS
.DS_Store

# IDE
.vscode/
.idea/
```

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py add scripts/git_ops.py workflow/ADR.md workflow/ERRORS.md docs/project/config/build-log.md docs/project/config/codebase.md logs/.gitkeep .gitignore
python3 scripts/git_ops.py commit -m "[EPIC-1] chore: add project infrastructure and workflow files"
python3 scripts/git_ops.py push
```

---

## Task 2: Supabase Schema & Storage

**Files:**
- Create: `supabase/migrations/001_initial_schema.sql`

- [ ] **Step 1: Create supabase/migrations/001_initial_schema.sql**

```sql
-- ============================================================
-- Accounting App — Initial Schema
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- Categories
create table categories (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  name        text not null,
  created_at  timestamptz default now()
);

-- Documents (receipts & invoices)
create table documents (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references auth.users(id) on delete cascade,
  original_filename text,
  stored_filename   text,
  storage_path      text,
  file_hash         text,
  date              date,
  amount            numeric(10,2),
  vendor            text,
  category_id       uuid references categories(id) on delete set null,
  ocr_raw           jsonb,
  ocr_status        text default 'pending'
                    check (ocr_status in ('pending', 'success', 'failed')),
  ocr_confidence    float,
  source            text check (source in ('upload', 'outlook', 'gmail', 'drive')),
  created_at        timestamptz default now()
);

-- Bank transactions
create table transactions (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  date          date not null,
  amount        numeric(10,2) not null,
  description   text,
  currency      text default 'EUR',
  source_bank   text,
  external_id   text unique,
  created_at    timestamptz default now()
);

-- Document ↔ Transaction matches
create table matches (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  transaction_id uuid not null unique references transactions(id) on delete cascade,
  document_id    uuid not null unique references documents(id) on delete cascade,
  matched_at     timestamptz default now()
);

-- OAuth integrations (Outlook, Gmail, Drive)
create table integrations (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  provider      text not null check (provider in ('outlook', 'gmail', 'drive')),
  folder_id     text,
  folder_name   text,
  refresh_token text,
  created_at    timestamptz default now(),
  unique(user_id, provider)
);

-- ============================================================
-- Row Level Security
-- ============================================================

alter table categories    enable row level security;
alter table documents     enable row level security;
alter table transactions  enable row level security;
alter table matches       enable row level security;
alter table integrations  enable row level security;

create policy "own_categories"
  on categories for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "own_documents"
  on documents for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "own_transactions"
  on transactions for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "own_matches"
  on matches for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "own_integrations"
  on integrations for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ============================================================
-- Storage RLS (documents bucket)
-- Run after creating the 'documents' bucket in Supabase UI
-- ============================================================

create policy "own_documents_storage"
  on storage.objects for all
  using (
    bucket_id = 'documents'
    and auth.uid()::text = (storage.foldername(name))[1]
  )
  with check (
    bucket_id = 'documents'
    and auth.uid()::text = (storage.foldername(name))[1]
  );
```

- [ ] **Step 2: Run migration in Supabase**

Open Supabase Dashboard → SQL Editor → New query → paste the entire contents of `001_initial_schema.sql` → Run.

Expected: all 5 tables visible in Table Editor, RLS enabled on each.

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py add supabase/migrations/001_initial_schema.sql
python3 scripts/git_ops.py commit -m "[EPIC-1] feat: add initial database schema with RLS"
python3 scripts/git_ops.py push
```

---

## Task 3: FastAPI Backend Scaffold

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/health.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/Dockerfile`
- Create: `backend/.env.example`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/__init__.py` (empty).

Create `backend/tests/test_health.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
supabase==2.7.4
python-dotenv==1.0.1
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 3: Create virtual environment and install**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 4: Run test to verify it fails**

```bash
cd backend
source .venv/bin/activate
pytest tests/test_health.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 5: Create app/config.py**

```python
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
```

- [ ] **Step 6: Create app/routers/health.py**

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Create app/main.py**

```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health
from app.config import FRONTEND_URL

app = FastAPI(title="Accounting API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
```

- [ ] **Step 8: Create .env.example**

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
FRONTEND_URL=http://localhost:3000
```

Copy to `.env` and fill in your Supabase values (from Supabase Dashboard → Settings → API).

- [ ] **Step 9: Run test to verify it passes**

```bash
cd backend
source .venv/bin/activate
pytest tests/test_health.py -v
```

Expected:
```
PASSED tests/test_health.py::test_health_returns_ok
1 passed in 0.XXs
```

- [ ] **Step 10: Verify server starts**

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Open http://localhost:8000/health — expected: `{"status":"ok"}`
Open http://localhost:8000/docs — expected: FastAPI swagger UI

- [ ] **Step 11: Create Dockerfile**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 12: Commit**

```bash
python3 scripts/git_ops.py add backend/
python3 scripts/git_ops.py commit -m "[EPIC-1] feat: add FastAPI backend scaffold with health endpoint"
python3 scripts/git_ops.py push
```

---

## Task 4: FastAPI Auth Middleware

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/app/routers/protected_test.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing auth tests**

Create `backend/tests/test_auth.py`:
```python
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)


def test_protected_route_without_token_returns_403():
    response = client.get("/api/protected-test")
    assert response.status_code == 403


def test_protected_route_with_invalid_token_returns_401():
    with patch("app.auth.supabase_admin") as mock_supabase:
        mock_supabase.auth.get_user.side_effect = Exception("Invalid token")
        response = client.get(
            "/api/protected-test",
            headers={"Authorization": "Bearer invalid_token"},
        )
    assert response.status_code == 401


def test_protected_route_with_valid_token_returns_200():
    mock_user = MagicMock()
    mock_user.id = "user-123"
    mock_response = MagicMock()
    mock_response.user = mock_user

    with patch("app.auth.supabase_admin") as mock_supabase:
        mock_supabase.auth.get_user.return_value = mock_response
        response = client.get(
            "/api/protected-test",
            headers={"Authorization": "Bearer valid_token"},
        )
    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
source .venv/bin/activate
pytest tests/test_auth.py -v
```

Expected: `ModuleNotFoundError` or route not found

- [ ] **Step 3: Create app/auth.py**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

security = HTTPBearer()

supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials
    try:
        response = supabase_admin.auth.get_user(token)
        return response.user
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
```

- [ ] **Step 4: Create app/routers/protected_test.py**

```python
from fastapi import APIRouter, Depends
from app.auth import get_current_user

router = APIRouter(prefix="/api")


@router.get("/protected-test")
def protected_test(user=Depends(get_current_user)):
    return {"user_id": user.id}
```

- [ ] **Step 5: Register router in app/main.py**

```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health
from app.routers.protected_test import router as protected_test_router
from app.config import FRONTEND_URL

app = FastAPI(title="Accounting API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(protected_test_router)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

Expected:
```
PASSED tests/test_health.py::test_health_returns_ok
PASSED tests/test_auth.py::test_protected_route_without_token_returns_403
PASSED tests/test_auth.py::test_protected_route_with_invalid_token_returns_401
PASSED tests/test_auth.py::test_protected_route_with_valid_token_returns_200
4 passed
```

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py add backend/app/auth.py backend/app/routers/protected_test.py backend/app/main.py backend/tests/test_auth.py
python3 scripts/git_ops.py commit -m "[EPIC-1] feat: add JWT auth middleware for FastAPI"
python3 scripts/git_ops.py push
```

---

## Task 5: Next.js PWA Scaffold

**Files:**
- Create: `frontend/` (via create-next-app)
- Modify: `frontend/next.config.ts`
- Create: `frontend/public/manifest.json`
- Create: `frontend/lib/supabase/client.ts`
- Create: `frontend/lib/supabase/server.ts`
- Create: `frontend/lib/supabase/middleware.ts`
- Create: `frontend/middleware.ts`
- Create: `frontend/.env.local.example`

- [ ] **Step 1: Scaffold Next.js app**

```bash
cd /path/to/accounting
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --app \
  --no-src-dir \
  --import-alias "@/*"
cd frontend
```

- [ ] **Step 2: Install Supabase and PWA dependencies**

```bash
cd frontend
npm install @supabase/ssr @supabase/supabase-js
npm install next-pwa
npm install --save-dev @types/node
```

- [ ] **Step 3: Create .env.local.example**

```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Copy to `.env.local` and fill in your values (Supabase Dashboard → Settings → API → `anon` key).

- [ ] **Step 4: Create lib/supabase/client.ts** (browser-side Supabase client)

```typescript
import { createBrowserClient } from '@supabase/ssr'

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}
```

- [ ] **Step 5: Create lib/supabase/server.ts** (server-side Supabase client)

```typescript
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export async function createClient() {
  const cookieStore = await cookies()

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          } catch {
            // Server component — cookie setting handled by middleware
          }
        },
      },
    }
  )
}
```

- [ ] **Step 6: Create lib/supabase/middleware.ts**

```typescript
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          )
          supabaseResponse = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  const { data: { user } } = await supabase.auth.getUser()

  if (!user && !request.nextUrl.pathname.startsWith('/login')) {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    return NextResponse.redirect(url)
  }

  return supabaseResponse
}
```

- [ ] **Step 7: Create middleware.ts at frontend root**

```typescript
import { type NextRequest } from 'next/server'
import { updateSession } from '@/lib/supabase/middleware'

export async function middleware(request: NextRequest) {
  return await updateSession(request)
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
```

- [ ] **Step 8: Create public/manifest.json**

```json
{
  "name": "Accounting App",
  "short_name": "Accounting",
  "description": "Personal expense and receipt tracker",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#0f172a",
  "icons": [
    {
      "src": "/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

Create placeholder icons directory:
```bash
mkdir -p frontend/public/icons
# Add icon-192.png and icon-512.png manually (any placeholder PNG for now)
```

- [ ] **Step 9: Configure next.config.ts for PWA**

```typescript
import type { NextConfig } from 'next'
const withPWA = require('next-pwa')({
  dest: 'public',
  disable: process.env.NODE_ENV === 'development',
})

const nextConfig: NextConfig = {
  // No additional config needed for now
}

module.exports = withPWA(nextConfig)
```

- [ ] **Step 10: Add manifest link to app/layout.tsx**

Replace the existing `<head>` metadata in `app/layout.tsx` with:
```typescript
import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Accounting App',
  description: 'Personal expense and receipt tracker',
  manifest: '/manifest.json',
  themeColor: '#0f172a',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  )
}
```

- [ ] **Step 11: Verify Next.js starts**

```bash
cd frontend
npm run dev
```

Open http://localhost:3000 — expected: redirects to /login (page not found yet, that's ok — middleware is working)

- [ ] **Step 12: Commit**

```bash
python3 scripts/git_ops.py add frontend/
python3 scripts/git_ops.py commit -m "[EPIC-1] feat: add Next.js PWA scaffold with Supabase client and auth middleware"
python3 scripts/git_ops.py push
```

---

## Task 6: Auth UI — Login & Logout

**Files:**
- Create: `frontend/app/login/page.tsx`
- Create: `frontend/app/login/actions.ts`
- Create: `frontend/app/(dashboard)/layout.tsx`
- Create: `frontend/app/(dashboard)/page.tsx`
- Create: `frontend/components/LogoutButton.tsx`

- [ ] **Step 1: Create app/login/actions.ts** (server actions for auth)

```typescript
'use server'

import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export async function login(formData: FormData) {
  const supabase = await createClient()

  const { error } = await supabase.auth.signInWithPassword({
    email: formData.get('email') as string,
    password: formData.get('password') as string,
  })

  if (error) {
    redirect('/login?error=Invalid+email+or+password')
  }

  revalidatePath('/', 'layout')
  redirect('/')
}

export async function logout() {
  const supabase = await createClient()
  await supabase.auth.signOut()
  redirect('/login')
}
```

- [ ] **Step 2: Create app/login/page.tsx**

```typescript
import { login } from './actions'

export default function LoginPage({
  searchParams,
}: {
  searchParams: { error?: string }
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-bold text-slate-900 mb-8 text-center">
          Accounting App
        </h1>

        <form className="space-y-4">
          {searchParams.error && (
            <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded">
              {searchParams.error}
            </p>
          )}

          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-slate-700 mb-1"
            >
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              className="w-full px-3 py-3 border border-slate-300 rounded-lg text-base focus:outline-none focus:ring-2 focus:ring-slate-900"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-slate-700 mb-1"
            >
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              required
              autoComplete="current-password"
              className="w-full px-3 py-3 border border-slate-300 rounded-lg text-base focus:outline-none focus:ring-2 focus:ring-slate-900"
            />
          </div>

          <button
            formAction={login}
            className="w-full py-3 px-4 bg-slate-900 text-white rounded-lg text-base font-medium active:bg-slate-700"
          >
            Sign in
          </button>
        </form>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create components/LogoutButton.tsx**

```typescript
'use client'

import { logout } from '@/app/login/actions'

export default function LogoutButton() {
  return (
    <form action={logout}>
      <button
        type="submit"
        className="text-sm text-slate-500 hover:text-slate-900"
      >
        Sign out
      </button>
    </form>
  )
}
```

- [ ] **Step 4: Create app/(dashboard)/layout.tsx**

```typescript
import LogoutButton from '@/components/LogoutButton'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">Accounting</h1>
        <LogoutButton />
      </header>
      <main className="px-4 py-6 max-w-2xl mx-auto">{children}</main>
    </div>
  )
}
```

- [ ] **Step 5: Create app/(dashboard)/page.tsx** (placeholder dashboard)

```typescript
export default function DashboardPage() {
  return (
    <div className="text-center py-16">
      <p className="text-slate-500">Dashboard — coming soon</p>
    </div>
  )
}
```

- [ ] **Step 6: Remove default app/page.tsx**

Delete `frontend/app/page.tsx` (the default Next.js home page — it will be replaced by `(dashboard)/page.tsx`).

- [ ] **Step 7: Verify auth flow end-to-end**

```bash
cd frontend
npm run dev
```

1. Open http://localhost:3000 → should redirect to /login
2. Enter the email/password you created in Supabase Prerequisites
3. Should redirect to / and show "Dashboard — coming soon" with a "Sign out" link
4. Click Sign out → should redirect back to /login

- [ ] **Step 8: Commit**

```bash
python3 scripts/git_ops.py add frontend/app/login/ frontend/app/\(dashboard\)/ frontend/components/
python3 scripts/git_ops.py commit -m "[EPIC-1] feat: add login/logout UI with Supabase auth"
python3 scripts/git_ops.py push
```

---

## Task 7: Deploy Configuration

**Files:**
- Create: `frontend/vercel.json`
- Create: `backend/railway.json`
- Create: `docs/project/config/env-vars.md`

- [ ] **Step 1: Create frontend/vercel.json**

```json
{
  "framework": "nextjs",
  "buildCommand": "npm run build",
  "outputDirectory": ".next",
  "installCommand": "npm install"
}
```

- [ ] **Step 2: Create backend/railway.json**

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

- [ ] **Step 3: Create docs/project/config/env-vars.md**

```markdown
# Environment Variables

## Frontend (Vercel)

| Variable | Where to find |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase Dashboard → Settings → API → Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase Dashboard → Settings → API → anon/public key |
| `NEXT_PUBLIC_API_URL` | Your Railway backend URL (e.g. https://accounting-api.up.railway.app) |

## Backend (Railway)

| Variable | Where to find |
|---|---|
| `SUPABASE_URL` | Supabase Dashboard → Settings → API → Project URL |
| `SUPABASE_SERVICE_KEY` | Supabase Dashboard → Settings → API → service_role key |
| `FRONTEND_URL` | Your Vercel frontend URL (e.g. https://accounting.vercel.app) |
| `PORT` | Set automatically by Railway |
```

- [ ] **Step 4: Deploy backend to Railway**

1. Go to https://railway.app → New Project → Deploy from GitHub repo
2. Select `louisgarnier/accounting` → select `backend/` as root directory
3. Add environment variables from the table above
4. Deploy — wait for health check at `/health` to pass
5. Copy the Railway URL (e.g. `https://accounting-api.up.railway.app`)

- [ ] **Step 5: Deploy frontend to Vercel**

1. Go to https://vercel.com → New Project → Import `louisgarnier/accounting`
2. Set root directory to `frontend/`
3. Add environment variables from the table above (use the Railway URL for `NEXT_PUBLIC_API_URL`)
4. Deploy
5. Copy the Vercel URL

- [ ] **Step 6: Update FRONTEND_URL in Railway**

In Railway → your project → Variables → update `FRONTEND_URL` to your actual Vercel URL → redeploy.

- [ ] **Step 7: Verify production login flow**

1. Open your Vercel URL on your phone
2. Login with your Supabase credentials
3. Should see dashboard placeholder
4. Add to home screen (Safari → Share → Add to Home Screen / Chrome → Install app)

- [ ] **Step 8: Update build-log.md**

```markdown
## Stage: Plan 1 — Foundation
**Status:** Complete
**Completed:** 2026-03-28

### Completed
- Project infrastructure (workflow files, git_ops.py)
- Supabase schema with RLS on all tables
- FastAPI scaffold with health endpoint and JWT auth middleware
- Next.js PWA scaffold with Supabase client and auth middleware
- Login/logout UI
- Deployed to Vercel (frontend) + Railway (backend)
```

- [ ] **Step 9: Final commit**

```bash
python3 scripts/git_ops.py add frontend/vercel.json backend/railway.json docs/project/config/env-vars.md docs/project/config/build-log.md
python3 scripts/git_ops.py commit -m "[EPIC-1] chore: add deploy config and update build log"
python3 scripts/git_ops.py push
```

---

## Self-Review Checklist

- [x] Spec coverage: schema covers all 5 tables (categories, documents, transactions, matches, integrations) ✓
- [x] Auth middleware tested with 3 cases (no token, invalid token, valid token) ✓
- [x] Login redirects unauthenticated users via Next.js middleware ✓
- [x] RLS enabled on all tables with user_id policies ✓
- [x] Storage RLS included in migration ✓
- [x] PWA manifest configured ✓
- [x] Deploy instructions complete for both Vercel and Railway ✓
- [x] Environment variables documented ✓
- [x] git_ops.py created per CLAUDE.md convention ✓
- [x] workflow/ADR.md and ERRORS.md created per CLAUDE.md convention ✓
