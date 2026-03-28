# Plan 2: Bank Transactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **IMPORTANT — Next.js 16:** Before writing any frontend code, read `frontend/node_modules/next/dist/docs/` — Next.js 16 has breaking changes from prior versions. The frontend AGENTS.md explicitly warns about this. Key known change: middleware is now `proxy.ts` with `export function proxy()`.

**Goal:** Receive bank transactions from Enable Banking via webhook, store them in Supabase, and display them in a transactions list page.

**Architecture:** FastAPI receives Enable Banking webhook POST requests, verifies the HMAC-SHA256 signature, deduplicates by `external_id`, and saves transactions to Supabase using the service-role key. The Next.js transactions page queries Supabase directly (server component) to list transactions ordered by date.

**Tech Stack:** FastAPI + supabase-py (backend), Next.js 16 server component + @supabase/ssr (frontend), HMAC-SHA256 signature verification (hmac + hashlib stdlib)

---

## Prerequisites (Manual Steps Before Starting)

1. **Get your Supabase user ID:**
   - Supabase Dashboard → Authentication → Users → click your user → copy the `User UID`
   - You'll need this for `APP_USER_ID` env var

2. **Generate a webhook secret:**
   - Run in terminal: `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - Save this value — you'll add it to Railway and to Enable Banking

3. **Add env vars to Railway:**
   - `APP_USER_ID` = your Supabase user UID
   - `ENABLE_BANKING_WEBHOOK_SECRET` = the secret you generated above

4. **Configure Enable Banking webhook** (after Railway deploy):
   - Log into Enable Banking dashboard
   - Set webhook URL to: `https://accounting-production-d529.up.railway.app/api/webhooks/enable-banking`
   - Set the webhook secret to the same value as `ENABLE_BANKING_WEBHOOK_SECRET`

---

## File Structure

```
backend/
  app/
    database.py          NEW — Supabase admin client singleton (reusable across routers)
    routers/
      webhooks.py        NEW — Enable Banking webhook endpoint
    config.py            MODIFY — add APP_USER_ID, ENABLE_BANKING_WEBHOOK_SECRET
  tests/
    test_webhooks.py     NEW — webhook tests

frontend/
  app/(dashboard)/
    transactions/
      page.tsx           NEW — transaction list server component
    layout.tsx           MODIFY — add Transactions nav link
```

---

## Task 1: Backend — Enable Banking Webhook

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/database.py`
- Create: `backend/app/routers/webhooks.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_webhooks.py`

- [ ] **Step 1: Write failing tests first**

Create `backend/tests/test_webhooks.py`:
```python
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

WEBHOOK_SECRET = "test-webhook-secret"


def make_signature(payload: dict, secret: str) -> str:
    body = json.dumps(payload, separators=(",", ":")).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_without_signature_returns_401():
    response = client.post("/api/webhooks/enable-banking", json={})
    assert response.status_code == 401


def test_webhook_with_wrong_signature_returns_401():
    payload = {"transactions": []}
    response = client.post(
        "/api/webhooks/enable-banking",
        json=payload,
        headers={"X-Enable-Banking-Signature": "wrong-signature"},
    )
    assert response.status_code == 401


def test_webhook_with_valid_signature_and_no_transactions_returns_200():
    payload = {"account": {"institution_name": "BNP"}, "transactions": []}
    sig = make_signature(payload, WEBHOOK_SECRET)
    with (
        patch("app.routers.webhooks.ENABLE_BANKING_WEBHOOK_SECRET", WEBHOOK_SECRET),
        patch("app.routers.webhooks.save_transactions", return_value=0),
    ):
        response = client.post(
            "/api/webhooks/enable-banking",
            json=payload,
            headers={"X-Enable-Banking-Signature": sig},
        )
    assert response.status_code == 200
    assert response.json() == {"saved": 0}


def test_webhook_saves_new_transactions():
    payload = {
        "account": {"institution_name": "BNP Paribas"},
        "transactions": [
            {
                "uid": "txn-001",
                "booking_date": "2026-03-28",
                "transaction_amount": {"amount": "-42.50", "currency": "EUR"},
                "remittance_information_unstructured": "Supermarché Casino",
            }
        ],
    }
    sig = make_signature(payload, WEBHOOK_SECRET)
    with (
        patch("app.routers.webhooks.ENABLE_BANKING_WEBHOOK_SECRET", WEBHOOK_SECRET),
        patch("app.routers.webhooks.save_transactions", return_value=1) as mock_save,
    ):
        response = client.post(
            "/api/webhooks/enable-banking",
            json=payload,
            headers={"X-Enable-Banking-Signature": sig},
        )
    assert response.status_code == 200
    assert response.json() == {"saved": 1}
    mock_save.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/louisgarnier/Claude/accounting/backend
source .venv/bin/activate
pytest tests/test_webhooks.py -v
```

Expected: `ModuleNotFoundError` or route not found errors.

- [ ] **Step 3: Update backend/app/config.py**

```python
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
APP_USER_ID: str = os.getenv("APP_USER_ID", "")
ENABLE_BANKING_WEBHOOK_SECRET: str = os.getenv("ENABLE_BANKING_WEBHOOK_SECRET", "")
```

- [ ] **Step 4: Update backend/tests/conftest.py**

```python
import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("APP_USER_ID", "test-user-id")
os.environ.setdefault("ENABLE_BANKING_WEBHOOK_SECRET", "test-webhook-secret")
```

- [ ] **Step 5: Create backend/app/database.py**

```python
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

_client: Client | None = None


def get_db() -> Client:
    """Return a Supabase admin client (lazy singleton)."""
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client
```

- [ ] **Step 6: Create backend/app/routers/webhooks.py**

```python
import hashlib
import hmac
import json
from datetime import date

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import APP_USER_ID, ENABLE_BANKING_WEBHOOK_SECRET
from app.database import get_db

router = APIRouter(prefix="/api/webhooks")


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from Enable Banking."""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def save_transactions(transactions: list[dict], source_bank: str) -> int:
    """Save new transactions to Supabase, skipping duplicates. Returns count saved."""
    if not transactions:
        return 0

    db = get_db()
    saved = 0

    for txn in transactions:
        external_id = txn.get("uid") or txn.get("entry_reference") or txn.get("transaction_id")
        if not external_id:
            continue

        # Check for duplicate
        existing = (
            db.table("transactions")
            .select("id")
            .eq("external_id", external_id)
            .execute()
        )
        if existing.data:
            continue

        # Parse amount and currency
        amount_data = txn.get("transaction_amount", {})
        amount_str = amount_data.get("amount", "0")
        currency = amount_data.get("currency", "EUR")

        # Parse date
        booking_date = txn.get("booking_date") or txn.get("value_date")

        # Parse description
        description = (
            txn.get("remittance_information_unstructured")
            or txn.get("remittance_information_structured")
            or txn.get("creditor_name")
            or txn.get("debtor_name")
            or "No description"
        )

        db.table("transactions").insert({
            "user_id": APP_USER_ID,
            "external_id": external_id,
            "date": booking_date,
            "amount": float(amount_str),
            "description": description,
            "currency": currency,
            "source_bank": source_bank,
        }).execute()

        saved += 1

    return saved


@router.post("/enable-banking")
async def enable_banking_webhook(
    request: Request,
    x_enable_banking_signature: str | None = Header(default=None),
):
    if not x_enable_banking_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing signature header",
        )

    body = await request.body()

    if not verify_signature(body, x_enable_banking_signature, ENABLE_BANKING_WEBHOOK_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    payload = json.loads(body)
    account = payload.get("account", {})
    source_bank = account.get("institution_name", "Unknown")
    transactions = payload.get("transactions", [])

    saved = save_transactions(transactions, source_bank)

    return {"saved": saved}
```

- [ ] **Step 7: Register webhook router in backend/app/main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health
from app.routers.protected_test import router as protected_test_router
from app.routers.webhooks import router as webhooks_router
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
app.include_router(webhooks_router)
```

- [ ] **Step 8: Run all tests — verify they pass**

```bash
cd /Users/louisgarnier/Claude/accounting/backend
source .venv/bin/activate
pytest tests/ -v
```

Expected:
```
PASSED tests/test_health.py::test_health_returns_ok
PASSED tests/test_auth.py::test_protected_route_without_token_returns_403
PASSED tests/test_auth.py::test_protected_route_with_invalid_token_returns_401
PASSED tests/test_auth.py::test_protected_route_with_valid_token_returns_200
PASSED tests/test_webhooks.py::test_webhook_without_signature_returns_401
PASSED tests/test_webhooks.py::test_webhook_with_wrong_signature_returns_401
PASSED tests/test_webhooks.py::test_webhook_with_valid_signature_and_no_transactions_returns_200
PASSED tests/test_webhooks.py::test_webhook_saves_new_transactions
8 passed
```

- [ ] **Step 9: Update .env.example**

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
FRONTEND_URL=http://localhost:3000
APP_USER_ID=your-supabase-user-uid
ENABLE_BANKING_WEBHOOK_SECRET=your-webhook-secret
```

- [ ] **Step 10: Commit**

```bash
cd /Users/louisgarnier/Claude/accounting
python3 scripts/git_ops.py add backend/app/config.py backend/app/database.py backend/app/routers/webhooks.py backend/app/main.py backend/tests/conftest.py backend/tests/test_webhooks.py backend/.env.example
python3 scripts/git_ops.py commit -m "[EPIC-1] feat: add Enable Banking webhook endpoint with signature verification"
python3 scripts/git_ops.py push
```

---

## Task 2: Frontend — Transaction List Page

**Files:**
- Create: `frontend/app/(dashboard)/transactions/page.tsx`
- Modify: `frontend/app/(dashboard)/layout.tsx`

- [ ] **Step 1: Read Next.js 16 server component docs**

Before writing any code, read:
```
frontend/node_modules/next/dist/docs/01-app/02-guides/data-fetching.md
```
Note any breaking changes from Next.js 14/15 patterns.

- [ ] **Step 2: Modify frontend/app/(dashboard)/layout.tsx — add nav**

```typescript
import Link from 'next/link'
import LogoutButton from '@/components/LogoutButton'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <h1 className="text-lg font-semibold text-slate-900">Accounting</h1>
          <nav className="flex gap-4">
            <Link
              href="/transactions"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Transactions
            </Link>
          </nav>
        </div>
        <LogoutButton />
      </header>
      <main className="px-4 py-6 max-w-2xl mx-auto">{children}</main>
    </div>
  )
}
```

- [ ] **Step 3: Create frontend/app/(dashboard)/transactions/page.tsx**

```typescript
import { createClient } from '@/lib/supabase/server'

type Transaction = {
  id: string
  date: string
  amount: number
  description: string
  currency: string
  source_bank: string | null
  matches: { id: string }[]
}

export default async function TransactionsPage() {
  const supabase = await createClient()

  const { data: transactions, error } = await supabase
    .from('transactions')
    .select('id, date, amount, description, currency, source_bank, matches(id)')
    .order('date', { ascending: false })

  if (error) {
    return (
      <div className="text-red-600 text-sm">
        Failed to load transactions. Please try again.
      </div>
    )
  }

  if (!transactions || transactions.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-500 text-sm">No transactions yet.</p>
        <p className="text-slate-400 text-xs mt-2">
          Transactions will appear here once Enable Banking syncs your account.
        </p>
      </div>
    )
  }

  return (
    <div>
      <h2 className="text-base font-semibold text-slate-900 mb-4">
        Transactions
        <span className="ml-2 text-sm font-normal text-slate-500">
          {transactions.length} total
        </span>
      </h2>

      <ul className="space-y-2">
        {transactions.map((txn) => {
          const matched = txn.matches && txn.matches.length > 0
          return (
            <li
              key={txn.id}
              className="bg-white rounded-lg border border-slate-200 px-4 py-3 flex items-center justify-between"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900 truncate">
                  {txn.description}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {txn.date}
                  {txn.source_bank && ` · ${txn.source_bank}`}
                </p>
              </div>
              <div className="flex items-center gap-3 ml-4 shrink-0">
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    matched
                      ? 'bg-green-50 text-green-700'
                      : 'bg-amber-50 text-amber-700'
                  }`}
                >
                  {matched ? 'Matched' : 'Unmatched'}
                </span>
                <span className="text-sm font-medium text-slate-900 tabular-nums">
                  {txn.amount < 0 ? '-' : '+'}
                  {Math.abs(txn.amount).toFixed(2)} {txn.currency}
                </span>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
```

- [ ] **Step 4: Verify build passes**

```bash
cd /Users/louisgarnier/Claude/accounting/frontend
npm run build
```

Expected: clean build, no TypeScript errors.

If there are TypeScript errors with the `matches` nested select type, adjust the `Transaction` type to:
```typescript
matches: { id: string }[] | null
```
and update the matched check to:
```typescript
const matched = txn.matches !== null && txn.matches.length > 0
```

- [ ] **Step 5: Commit**

```bash
cd /Users/louisgarnier/Claude/accounting
python3 scripts/git_ops.py add "frontend/app/(dashboard)/transactions/" "frontend/app/(dashboard)/layout.tsx"
python3 scripts/git_ops.py commit -m "[EPIC-1] feat: add transaction list page"
python3 scripts/git_ops.py push
```

---

## Self-Review

**Spec coverage:**
- US-05 (bank transactions via Enable Banking webhook) → Task 1 ✓
- US-07 (view transactions) → Task 2 ✓ (list view, no filter yet — filter comes in a later plan when there's real data to filter)
- Security: webhook signature verification ✓
- Deduplication by external_id ✓
- Matched/unmatched status visible ✓

**Placeholder scan:** No TBDs, all code is complete.

**Type consistency:**
- `save_transactions(transactions: list[dict], source_bank: str) -> int` used consistently
- `get_db()` returns `Client` used in webhooks.py ✓
- Transaction type in page.tsx matches Supabase schema ✓

**Note on Enable Banking payload format:** Enable Banking's exact field names may differ slightly from what's implemented. The `save_transactions` function handles multiple common field names (`uid`, `entry_reference`, `transaction_id` for external ID; `remittance_information_unstructured`, `creditor_name`, etc. for description). If Enable Banking sends different fields, update `webhooks.py:save_transactions` accordingly.
