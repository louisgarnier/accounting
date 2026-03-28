# Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **IMPORTANT — Next.js 16:** Before writing any frontend code, read `frontend/node_modules/next/dist/docs/` — Next.js 16 has breaking changes. The frontend AGENTS.md warns about this.

**Goal:** Capture every request, error, and state change across all layers into a Supabase `logs` table so errors can be diagnosed by querying Supabase directly — no manual log sharing needed.

**Architecture:** Frontend writes logs directly to Supabase via the user session client. Backend writes to Supabase via service role in a background thread (never blocks requests), plus stdout (Railway) and optional local files (LOG_DIR). A `request_id` UUID is generated per fetch and passed in headers so frontend + backend log entries for the same call can be correlated with one query.

**Tech Stack:** Python logging + threading (backend), Supabase `logs` table (all layers), Next.js 16 client component + `createBrowserClient` (frontend), FastAPI middleware (API layer)

---

## File Structure

```
supabase/migrations/20260328_logs.sql   NEW  — logs table DDL + RLS
backend/app/logger.py                   MOD  — add db_logger, log_to_supabase()
backend/app/db_logger.py                NEW  — db_select / db_insert / db_delete wrappers
backend/app/main.py                     MOD  — startup checks, updated middleware with timing + request_id
backend/app/routers/banking.py          MOD  — use db_logger, add session step logs
backend/app/routers/webhooks.py         MOD  — use db_logger
backend/tests/test_db_logger.py         NEW  — tests for db_logger wrappers
backend/tests/test_logging.py           MOD  — add middleware timing + request_id tests
backend/.env.example                    MOD  — add LOG_DIR=../logs
frontend/lib/logger.ts                  NEW  — client logger: info/warn/error/fetch
frontend/app/(dashboard)/banking/connect/page.tsx   MOD  — log config on mount, use logger.fetch
frontend/app/(dashboard)/banking/callback/page.tsx  MOD  — log each OAuth step inline
frontend/components/SyncButton.tsx      MOD  — use logger.fetch
```

---

## Task 1: Supabase Migration — `logs` Table

**Files:**
- Create: `supabase/migrations/20260328_logs.sql`

- [ ] **Step 1: Create the migration file**

Create `supabase/migrations/20260328_logs.sql`:

```sql
-- logs table: receives entries from all layers (frontend, api, backend, database)
create table if not exists public.logs (
  id           uuid        default gen_random_uuid() primary key,
  created_at   timestamptz default now(),
  layer        text        not null check (layer in ('frontend', 'api', 'backend', 'database')),
  level        text        not null check (level in ('info', 'warn', 'error')),
  message      text        not null,
  request_id   text,
  url          text,
  method       text,
  status_code  integer,
  duration_ms  integer,
  context      jsonb,
  user_id      uuid references auth.users(id)
);

-- Backend (service role) has full access — bypasses RLS
-- Frontend (user session) can insert own rows only
alter table public.logs enable row level security;

create policy "users can insert own logs"
  on public.logs for insert
  to authenticated
  with check (auth.uid() = user_id);

-- Index for common queries
create index logs_created_at_idx on public.logs (created_at desc);
create index logs_level_idx      on public.logs (level);
create index logs_request_id_idx on public.logs (request_id) where request_id is not null;
create index logs_layer_idx      on public.logs (layer);
```

- [ ] **Step 2: Run in Supabase dashboard**

Open Supabase → SQL Editor → paste the file above → Run.
Expected: "Success. No rows returned."

- [ ] **Step 3: Commit**

```bash
cd /Users/louisgarnier/Claude/accounting
python3 scripts/git_ops.py add supabase/migrations/20260328_logs.sql
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: add logs table with RLS"
python3 scripts/git_ops.py push
```

---

## Task 2: Backend — `logger.py` + `log_to_supabase`

**Files:**
- Modify: `backend/app/logger.py`
- Modify: `backend/tests/test_logging.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_logging.py` (after existing tests):

```python
# --- log_to_supabase ---

def test_log_to_supabase_inserts_entry_in_background(monkeypatch):
    """log_to_supabase writes to Supabase logs table in a background thread."""
    import time
    from unittest.mock import MagicMock, patch

    mock_db = MagicMock()
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()

    with patch("app.logger._get_db_for_logging", return_value=mock_db):
        from app.logger import log_to_supabase
        log_to_supabase({"layer": "backend", "level": "info", "message": "test"})
        time.sleep(0.05)  # let the background thread finish

    mock_db.table.assert_called_with("logs")
    inserted = mock_db.table.return_value.insert.call_args[0][0]
    assert inserted["message"] == "test"
    assert inserted["layer"] == "backend"


def test_log_to_supabase_does_not_raise_on_error(monkeypatch):
    """log_to_supabase never raises even if Supabase is unavailable."""
    import time
    from unittest.mock import patch

    with patch("app.logger._get_db_for_logging", side_effect=Exception("db down")):
        from app.logger import log_to_supabase
        log_to_supabase({"layer": "backend", "level": "error", "message": "oops"})
        time.sleep(0.05)
    # No exception raised — test passes by completing
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/louisgarnier/Claude/accounting/backend
python3 -m pytest tests/test_logging.py::test_log_to_supabase_inserts_entry_in_background tests/test_logging.py::test_log_to_supabase_does_not_raise_on_error -v
```

Expected: `ImportError` or `AttributeError` — `log_to_supabase` not defined yet.

- [ ] **Step 3: Replace `backend/app/logger.py` entirely**

```python
import logging
import os
import sys
import threading
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Internal: Supabase write (fire-and-forget, never blocks, never raises)
# ---------------------------------------------------------------------------

def _get_db_for_logging():
    """Lazy import to avoid circular dependency at module load time."""
    from app.database import get_db
    return get_db()


def log_to_supabase(entry: dict) -> None:
    """Write a log entry to Supabase in a background thread. Never raises."""
    def _write():
        try:
            _get_db_for_logging().table("logs").insert(entry).execute()
        except Exception:
            pass  # logging must never break the app

    threading.Thread(target=_write, daemon=True).start()


# ---------------------------------------------------------------------------
# Python loggers: stdout + optional local file
# ---------------------------------------------------------------------------

def _build_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    logger.addHandler(stdout_handler)

    log_dir = os.getenv("LOG_DIR")
    if log_dir:
        path = Path(log_dir) / f"{filename}_{date.today().isoformat()}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


backend_logger  = _build_logger("backend",  "backend")
api_logger      = _build_logger("api",       "api")
db_logger       = _build_logger("database",  "database")
frontend_logger = _build_logger("frontend",  "frontend")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_logging.py -v
```

Expected: all pass (including the 5 existing logging tests).

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py add backend/app/logger.py backend/tests/test_logging.py
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: add log_to_supabase fire-and-forget writer"
python3 scripts/git_ops.py push
```

---

## Task 3: Backend — `db_logger.py`

**Files:**
- Create: `backend/app/db_logger.py`
- Create: `backend/tests/test_db_logger.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_db_logger.py`:

```python
import time
import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def mock_db():
    db = MagicMock()
    with patch("app.db_logger.get_db", return_value=db):
        yield db


@pytest.fixture(autouse=True)
def silence_supabase_log(monkeypatch):
    monkeypatch.setattr("app.db_logger.log_to_supabase", lambda entry: None)


def test_db_select_returns_rows(mock_db):
    """db_select executes the query and returns the data list."""
    from app.db_logger import db_select

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "1"}, {"id": "2"}])

    result = db_select("transactions", lambda t: t.select("id").eq("user_id", "u1"))

    assert result == [{"id": "1"}, {"id": "2"}]


def test_db_select_returns_empty_list_on_no_rows(mock_db):
    """db_select returns [] when Supabase returns no rows."""
    from app.db_logger import db_select

    mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(data=[])

    result = db_select("bank_connections", lambda t: t.select("id"))

    assert result == []


def test_db_select_raises_on_exception(mock_db):
    """db_select re-raises exceptions from Supabase."""
    from app.db_logger import db_select

    mock_db.table.return_value.select.return_value.execute.side_effect = RuntimeError("db error")

    with pytest.raises(RuntimeError, match="db error"):
        db_select("transactions", lambda t: t.select("id"))


def test_db_insert_returns_inserted_row(mock_db):
    """db_insert executes the insert and returns the first inserted row."""
    from app.db_logger import db_insert

    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "abc", "amount": -42.5}]
    )

    result = db_insert("transactions", {"amount": -42.5, "user_id": "u1"})

    assert result == {"id": "abc", "amount": -42.5}
    mock_db.table.assert_called_with("transactions")


def test_db_insert_raises_on_exception(mock_db):
    """db_insert re-raises exceptions from Supabase."""
    from app.db_logger import db_insert

    mock_db.table.return_value.insert.return_value.execute.side_effect = RuntimeError("constraint")

    with pytest.raises(RuntimeError, match="constraint"):
        db_insert("transactions", {"amount": 0})


def test_db_delete_returns_deleted_count(mock_db):
    """db_delete executes the delete and returns the count of deleted rows."""
    from app.db_logger import db_delete

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "1"}, {"id": "2"}]
    )

    count = db_delete("bank_connections", lambda t: t.delete().eq("user_id", "u1"))

    assert count == 2


def test_db_delete_returns_zero_on_no_match(mock_db):
    """db_delete returns 0 when no rows matched the filter."""
    from app.db_logger import db_delete

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    count = db_delete("bank_connections", lambda t: t.delete().eq("user_id", "nobody"))

    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_db_logger.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.db_logger'`

- [ ] **Step 3: Create `backend/app/db_logger.py`**

```python
import time
from typing import Callable

from app.database import get_db
from app.logger import db_logger, log_to_supabase


def _log(operation: str, table: str, duration_ms: int, extra: dict) -> None:
    db_logger.info(f"🗄️ [DB] {operation} {table} ({duration_ms}ms)")
    log_to_supabase({
        "layer": "database",
        "level": "info",
        "message": f"{operation} {table}",
        "duration_ms": duration_ms,
        "context": {"table": table, "operation": operation, **extra},
    })


def _log_error(operation: str, table: str, error: Exception) -> None:
    db_logger.error(f"❌ [DB] {operation} {table} error: {error}")
    log_to_supabase({
        "layer": "database",
        "level": "error",
        "message": f"{operation} {table} failed",
        "context": {"table": table, "operation": operation, "error": str(error)},
    })


def db_select(table: str, build_query: Callable) -> list:
    """Execute a select. build_query receives the table builder, returns the query chain."""
    start = time.monotonic()
    try:
        result = build_query(get_db().table(table)).execute()
        rows = len(result.data) if result.data else 0
        _log("select", table, int((time.monotonic() - start) * 1000), {"rows_returned": rows})
        return result.data or []
    except Exception as e:
        _log_error("select", table, e)
        raise


def db_insert(table: str, row: dict) -> dict:
    """Insert one row. Returns the inserted row."""
    start = time.monotonic()
    try:
        result = get_db().table(table).insert(row).execute()
        _log("insert", table, int((time.monotonic() - start) * 1000), {"rows_inserted": 1})
        return result.data[0] if result.data else {}
    except Exception as e:
        _log_error("insert", table, e)
        raise


def db_delete(table: str, build_query: Callable) -> int:
    """Execute a delete. build_query receives the table builder. Returns deleted row count."""
    start = time.monotonic()
    try:
        result = build_query(get_db().table(table)).execute()
        rows = len(result.data) if result.data else 0
        _log("delete", table, int((time.monotonic() - start) * 1000), {"rows_deleted": rows})
        return rows
    except Exception as e:
        _log_error("delete", table, e)
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_db_logger.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run full test suite — verify no regressions**

```bash
python3 -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py add backend/app/db_logger.py backend/tests/test_db_logger.py
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: add db_logger wrappers with timing and Supabase logging"
python3 scripts/git_ops.py push
```

---

## Task 4: Backend — `main.py` Startup Checks + Improved Middleware

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_logging.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_logging.py`:

```python
# --- Middleware: timing and request_id ---

def test_api_middleware_includes_timing_ms(caplog):
    """Response log includes duration in milliseconds."""
    with caplog.at_level(logging.INFO, logger="api"):
        client.get("/health")

    messages = [r.message for r in caplog.records]
    assert any("ms" in m for m in messages)


def test_api_middleware_echoes_x_request_id_header(caplog):
    """When X-Request-ID is provided, it appears in the log and response header."""
    with caplog.at_level(logging.INFO, logger="api"):
        response = client.get("/health", headers={"X-Request-ID": "test-req-123"})

    assert response.headers.get("X-Request-ID") == "test-req-123"
    messages = [r.message for r in caplog.records]
    assert any("test-req-123" in m for m in messages)


def test_api_middleware_generates_request_id_when_missing(caplog):
    """When X-Request-ID is absent, the middleware generates one and includes it in the response."""
    with caplog.at_level(logging.INFO, logger="api"):
        response = client.get("/health")

    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) == 36  # UUID format
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_logging.py::test_api_middleware_includes_timing_ms tests/test_logging.py::test_api_middleware_echoes_x_request_id_header tests/test_logging.py::test_api_middleware_generates_request_id_when_missing -v
```

Expected: all fail — middleware doesn't set X-Request-ID header yet.

- [ ] **Step 3: Replace `backend/app/main.py` entirely**

```python
import os
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import FRONTEND_URL
from app.logger import api_logger, backend_logger, log_to_supabase
from app.routers import health
from app.routers.banking import router as banking_router
from app.routers.protected_test import router as protected_test_router
from app.routers.webhooks import router as webhooks_router

app = FastAPI(title="Accounting API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start = time.monotonic()

    api_logger.info(f"📥 {request.method} {request.url.path} req={request_id}")
    log_to_supabase({
        "layer": "api",
        "level": "info",
        "message": f"{request.method} {request.url.path}",
        "method": request.method,
        "url": str(request.url.path),
        "request_id": request_id,
    })

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        tb = traceback.format_exc()
        api_logger.error(f"❌ {request.method} {request.url.path} unhandled: {exc}\n{tb}")
        log_to_supabase({
            "layer": "api",
            "level": "error",
            "message": f"unhandled exception: {exc}",
            "method": request.method,
            "url": str(request.url.path),
            "request_id": request_id,
            "duration_ms": duration_ms,
            "context": {"traceback": tb},
        })
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    duration_ms = int((time.monotonic() - start) * 1000)
    api_logger.info(f"📤 {request.method} {request.url.path} → {response.status_code} ({duration_ms}ms) req={request_id}")
    log_to_supabase({
        "layer": "api",
        "level": "info",
        "message": f"{request.method} {request.url.path} → {response.status_code}",
        "method": request.method,
        "url": str(request.url.path),
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "request_id": request_id,
    })

    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(health.router)
app.include_router(protected_test_router)
app.include_router(webhooks_router)
app.include_router(banking_router)


@app.on_event("startup")
async def startup_event():
    """Log env var presence (never values) and verify Supabase connectivity."""
    env_vars = [
        "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "FRONTEND_URL",
        "APP_USER_ID", "ENABLE_BANKING_WEBHOOK_SECRET",
        "ENABLE_BANKING_APP_ID", "ENABLE_BANKING_PRIVATE_KEY",
    ]
    presence = {var: bool(os.getenv(var)) for var in env_vars}
    backend_logger.info(f"🚀 [Backend] starting — env vars: {presence}")
    log_to_supabase({
        "layer": "backend",
        "level": "info",
        "message": "startup",
        "context": {"env_vars_present": presence},
    })

    try:
        from app.database import get_db
        get_db().table("logs").select("id").limit(1).execute()
        backend_logger.info("✅ [Backend] Supabase connection ok")
        log_to_supabase({"layer": "backend", "level": "info", "message": "supabase connection ok"})
    except Exception as e:
        backend_logger.error(f"❌ [Backend] Supabase connection failed: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_logging.py -v
```

Expected: all pass (including the 3 new tests + 7 existing ones).

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py add backend/app/main.py backend/tests/test_logging.py
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: add startup checks, request timing, and X-Request-ID to middleware"
python3 scripts/git_ops.py push
```

---

## Task 5: Backend — Update Routers to Use `db_logger`

**Files:**
- Modify: `backend/app/routers/banking.py`
- Modify: `backend/app/routers/webhooks.py`

- [ ] **Step 1: Replace `backend/app/routers/banking.py` entirely**

```python
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import get_current_user
from app.config import FRONTEND_URL
from app.db_logger import db_delete, db_insert, db_select
from app.logger import backend_logger, log_to_supabase
from app.services.enable_banking import create_session, fetch_transactions, start_auth

router = APIRouter(prefix="/api/banking")

REDIRECT_URL = f"{FRONTEND_URL}/banking/callback"


class ConnectRequest(BaseModel):
    bank_name: str
    bank_country: str


class SessionRequest(BaseModel):
    code: str


@router.post("/connect")
async def connect_bank(req: ConnectRequest, user=Depends(get_current_user)):
    """Start bank connection — returns Enable Banking authorization URL."""
    state = str(uuid.uuid4())
    try:
        url = start_auth(req.bank_name, req.bank_country, REDIRECT_URL, state)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Enable Banking error: {exc}")
    return {"url": url}


@router.post("/sessions")
async def create_banking_session(req: SessionRequest, user=Depends(get_current_user)):
    """Exchange authorization code for session; store all accounts."""
    backend_logger.info(f"📥 [Banking] sessions: code received for user {user.id}")

    try:
        accounts = create_session(req.code)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Enable Banking error: {exc}")

    backend_logger.info(f"✅ [Banking] sessions: Enable Banking session created, {len(accounts)} accounts")

    # Replace any previous connections (re-auth scenario)
    db_delete("bank_connections", lambda t: t.delete().eq("user_id", str(user.id)))

    for acc in accounts:
        db_insert("bank_connections", {
            "user_id": str(user.id),
            "session_id": acc["session_id"],
            "account_uid": acc["account_uid"],
            "account_iban": acc.get("account_iban", ""),
            "account_name": acc.get("account_name", ""),
            "institution_name": acc.get("institution_name", ""),
        })

    backend_logger.info(f"✅ [Banking] sessions: {len(accounts)} accounts stored for user {user.id}")
    log_to_supabase({
        "layer": "backend",
        "level": "info",
        "message": f"bank session created: {len(accounts)} accounts stored",
        "context": {"accounts_count": len(accounts)},
        "user_id": str(user.id),
    })

    return {"connected": len(accounts)}


@router.post("/sync")
async def sync_transactions(user=Depends(get_current_user)):
    """Pull latest 90 days of transactions from all connected accounts."""
    connections = db_select(
        "bank_connections",
        lambda t: t.select("account_uid, institution_name").eq("user_id", str(user.id)),
    )

    if not connections:
        raise HTTPException(status_code=404, detail="No bank connections found. Connect a bank first.")

    date_from = (date.today() - timedelta(days=90)).isoformat()
    total_saved = 0

    for conn in connections:
        try:
            raw_txns = fetch_transactions(conn["account_uid"], date_from)
        except Exception:
            continue

        for txn in raw_txns:
            external_id = txn.get("transaction_id") or txn.get("entry_reference")
            if not external_id:
                continue

            existing = db_select(
                "transactions",
                lambda t: t.select("id").eq("external_id", external_id),
            )
            if existing:
                continue

            raw_amount = txn.get("transaction_amount", {}).get("amount", "0")
            try:
                amount = float(raw_amount)
            except (ValueError, TypeError):
                amount = 0.0

            if txn.get("credit_debit_indicator", "DBIT") == "DBIT":
                amount = -abs(amount)
            else:
                amount = abs(amount)

            remittance = txn.get("remittance_information", [])
            description = (
                " ".join(remittance)
                if remittance
                else (
                    txn.get("creditor", {}).get("name")
                    or txn.get("debtor", {}).get("name")
                    or "No description"
                )
            )

            db_insert("transactions", {
                "user_id": str(user.id),
                "external_id": external_id,
                "date": txn.get("booking_date") or txn.get("value_date"),
                "amount": amount,
                "description": description,
                "currency": txn.get("transaction_amount", {}).get("currency", "EUR"),
                "source_bank": conn["institution_name"],
            })
            total_saved += 1

    return {"synced": total_saved}
```

- [ ] **Step 2: Replace `backend/app/routers/webhooks.py` entirely**

```python
import hashlib
import hmac
import json

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import APP_USER_ID, ENABLE_BANKING_WEBHOOK_SECRET
from app.db_logger import db_insert, db_select
from app.logger import backend_logger

router = APIRouter(prefix="/api/webhooks")


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def save_transactions(transactions: list[dict], source_bank: str) -> int:
    if not transactions:
        return 0

    saved = 0
    for txn in transactions:
        external_id = (
            txn.get("uid")
            or txn.get("entry_reference")
            or txn.get("transaction_id")
        )
        if not external_id:
            backend_logger.warning(f"⚠️ [Webhooks] skipping transaction with no external_id")
            continue

        existing = db_select(
            "transactions",
            lambda t: t.select("id").eq("external_id", external_id),
        )
        if existing:
            continue

        amount_data = txn.get("transaction_amount", {})
        raw_amount = amount_data.get("amount") or "0"
        currency = amount_data.get("currency", "EUR")
        try:
            amount_val = float(raw_amount)
        except (ValueError, TypeError):
            amount_val = 0.0

        booking_date = txn.get("booking_date") or txn.get("value_date")
        description = (
            txn.get("remittance_information_unstructured")
            or txn.get("remittance_information_structured")
            or txn.get("creditor_name")
            or txn.get("debtor_name")
            or "No description"
        )

        db_insert("transactions", {
            "user_id": APP_USER_ID,
            "external_id": external_id,
            "date": booking_date,
            "amount": amount_val,
            "description": description,
            "currency": currency,
            "source_bank": source_bank,
        })
        saved += 1

    return saved


@router.post("/enable-banking")
async def enable_banking_webhook(
    request: Request,
    x_enable_banking_signature: str | None = Header(default=None),
):
    if not x_enable_banking_signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature header")

    body = await request.body()

    if not verify_signature(body, x_enable_banking_signature, ENABLE_BANKING_WEBHOOK_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    payload = json.loads(body)
    account = payload.get("account", {})
    source_bank = account.get("institution_name", "Unknown")
    transactions = payload.get("transactions", [])

    backend_logger.info(f"📥 [Webhooks] received {len(transactions)} transactions from {source_bank}")
    saved = save_transactions(transactions, source_bank)
    backend_logger.info(f"✅ [Webhooks] saved {saved} new transactions from {source_bank}")

    return {"saved": saved}
```

- [ ] **Step 3: Run full test suite — all existing tests must still pass**

```bash
python3 -m pytest tests/ -v
```

Expected: all pass. The router tests mock `get_db` and `save_transactions` directly — the refactor to `db_logger` is transparent to them.

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py add backend/app/routers/banking.py backend/app/routers/webhooks.py
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: use db_logger in all routers, add session step logging"
python3 scripts/git_ops.py push
```

---

## Task 6: Frontend — `lib/logger.ts`

**Files:**
- Create: `frontend/lib/logger.ts`

No unit tests needed — the logger wraps Supabase which is an external dependency. Tested end-to-end in Task 7 by verifying rows appear in the `logs` table.

- [ ] **Step 1: Create `frontend/lib/logger.ts`**

```typescript
'use client'

import { createClient } from '@/lib/supabase/client'

type LogRow = {
  layer: 'frontend'
  level: 'info' | 'warn' | 'error'
  message: string
  request_id?: string
  url?: string
  method?: string
  status_code?: number
  duration_ms?: number
  context?: Record<string, unknown>
  user_id?: string | null
}

async function write(row: Omit<LogRow, 'layer'>): Promise<void> {
  try {
    const supabase = createClient()
    const { data: { user } } = await supabase.auth.getUser()
    await supabase.from('logs').insert({
      ...row,
      layer: 'frontend',
      user_id: user?.id ?? null,
    })
  } catch {
    // never let logging crash the app
  }
}

export const logger = {
  info: (message: string, context?: Record<string, unknown>) =>
    write({ level: 'info', message, context }),

  warn: (message: string, context?: Record<string, unknown>) =>
    write({ level: 'warn', message, context }),

  error: (message: string, context?: Record<string, unknown>) =>
    write({ level: 'error', message, context }),

  /**
   * Wrap a fetch call with logging.
   * Usage:
   *   const req = logger.fetch('POST', url)
   *   const resp = await fetch(url, { headers: { 'X-Request-ID': req.request_id, ... } })
   *   req.done(resp.status)              // on success
   *   req.done(resp.status, errorBody)   // on HTTP error
   *   req.networkError(e)               // on TypeError (network failure)
   */
  fetch: (method: string, url: string) => {
    const request_id = crypto.randomUUID()
    const start = Date.now()
    write({ level: 'info', message: 'fetch started', method, url, request_id })

    return {
      request_id,
      done: (status_code: number, context?: Record<string, unknown>) => {
        const duration_ms = Date.now() - start
        write({
          level: status_code >= 400 ? 'error' : 'info',
          message: status_code >= 400 ? 'fetch error' : 'fetch success',
          method, url, status_code, duration_ms, request_id, context,
        })
      },
      networkError: (error: unknown) => {
        const duration_ms = Date.now() - start
        write({
          level: 'error',
          message: 'network error',
          method, url, request_id, duration_ms,
          context: { error: error instanceof Error ? error.message : String(error) },
        })
      },
    }
  },
}
```

- [ ] **Step 2: Verify build passes**

```bash
cd /Users/louisgarnier/Claude/accounting/frontend
./node_modules/.bin/next build 2>&1
```

Expected: clean build, no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/louisgarnier/Claude/accounting
python3 scripts/git_ops.py add frontend/lib/logger.ts
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: add frontend logger writing to Supabase logs table"
python3 scripts/git_ops.py push
```

---

## Task 7: Frontend — Wire Logger into Components

**Files:**
- Modify: `frontend/app/(dashboard)/banking/connect/page.tsx`
- Modify: `frontend/components/SyncButton.tsx`
- Modify: `frontend/app/(dashboard)/banking/callback/page.tsx`

- [ ] **Step 1: Replace `frontend/app/(dashboard)/banking/connect/page.tsx` entirely**

```tsx
'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { logger } from '@/lib/logger'

const BANKS = [
  { name: 'BNP Paribas', country: 'FR' },
  { name: 'Société Générale', country: 'FR' },
  { name: 'Crédit Agricole', country: 'FR' },
  { name: 'LCL', country: 'FR' },
  { name: "Caisse d'Épargne", country: 'FR' },
  { name: 'Banque Populaire', country: 'FR' },
  { name: 'La Banque Postale', country: 'FR' },
  { name: 'HSBC France', country: 'FR' },
  { name: 'Revolut', country: 'GB' },
]

export default function ConnectBankPage() {
  const [selectedBank, setSelectedBank] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    // Log config on mount — immediately visible if NEXT_PUBLIC_BACKEND_URL is missing
    logger.info('app config', {
      backend_url: process.env.NEXT_PUBLIC_BACKEND_URL ?? 'undefined',
      supabase_url: process.env.NEXT_PUBLIC_SUPABASE_URL ?? 'undefined',
    })
  }, [])

  async function handleConnect() {
    if (!selectedBank) return
    setLoading(true)
    setError('')

    const bank = BANKS.find((b) => b.name === selectedBank)!
    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()

    const url = `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/connect`
    const req = logger.fetch('POST', url)

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session?.access_token}`,
          'X-Request-ID': req.request_id,
        },
        body: JSON.stringify({ bank_name: bank.name, bank_country: bank.country }),
      })

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        req.done(resp.status, body)
        throw new Error(body.detail || `HTTP ${resp.status}`)
      }

      req.done(resp.status)
      const { url: redirectUrl } = await resp.json()
      window.location.href = redirectUrl
    } catch (e) {
      if (e instanceof TypeError) {
        req.networkError(e)
      }
      setError(`Could not connect: ${e instanceof Error ? e.message : 'unknown error'}`)
      setLoading(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto py-8">
      <h2 className="text-base font-semibold text-slate-900 mb-1">Connect your bank</h2>
      <p className="text-sm text-slate-500 mb-6">
        You will be redirected to authorise access. This is a one-time setup.
      </p>

      <label className="block text-sm font-medium text-slate-700 mb-1">Select your bank</label>
      <select
        value={selectedBank}
        onChange={(e) => setSelectedBank(e.target.value)}
        className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mb-4 bg-white"
      >
        <option value="">— choose a bank —</option>
        {BANKS.map((b) => (
          <option key={b.name} value={b.name}>{b.name}</option>
        ))}
      </select>

      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

      <button
        onClick={handleConnect}
        disabled={!selectedBank || loading}
        className="w-full bg-slate-900 text-white text-sm font-medium rounded-md px-4 py-2 disabled:opacity-50"
      >
        {loading ? 'Redirecting…' : 'Connect'}
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Replace `frontend/components/SyncButton.tsx` entirely**

```tsx
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { logger } from '@/lib/logger'

export default function SyncButton() {
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const router = useRouter()

  async function handleSync() {
    setLoading(true)
    setMessage('')

    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()

    const url = `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/sync`
    const req = logger.fetch('POST', url)

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session?.access_token}`,
          'X-Request-ID': req.request_id,
        },
      })

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        req.done(resp.status, body)
        throw new Error('Sync failed')
      }

      const data = await resp.json()
      req.done(resp.status)
      setMessage(
        data.synced === 0
          ? 'Already up to date'
          : `${data.synced} new transaction${data.synced !== 1 ? 's' : ''} synced`
      )
      router.refresh()
    } catch (e) {
      if (e instanceof TypeError) {
        req.networkError(e)
      }
      setMessage('Sync failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleSync}
        disabled={loading}
        className="text-sm bg-slate-900 text-white rounded-md px-3 py-1.5 disabled:opacity-50"
      >
        {loading ? 'Syncing…' : 'Sync'}
      </button>
      {message && <span className="text-xs text-slate-500">{message}</span>}
    </div>
  )
}
```

- [ ] **Step 3: Replace `frontend/app/(dashboard)/banking/callback/page.tsx` entirely**

```tsx
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export default async function BankingCallbackPage({
  searchParams,
}: {
  searchParams: Promise<{ code?: string; error?: string; state?: string }>
}) {
  const params = await searchParams
  const supabase = await createClient()
  const { data: { session } } = await supabase.auth.getSession()

  // Log callback receipt — fire and forget
  void supabase.from('logs').insert({
    layer: 'frontend',
    level: params.error || !params.code ? 'error' : 'info',
    message: 'oauth callback received',
    context: { has_code: !!params.code, has_error: !!params.error, error: params.error ?? null },
    user_id: session?.user.id ?? null,
  }).catch(() => {})

  if (params.error || !params.code) {
    redirect('/transactions?bank_error=1')
  }

  if (!session) {
    redirect('/login')
  }

  // Log the session exchange attempt
  void supabase.from('logs').insert({
    layer: 'frontend',
    level: 'info',
    message: 'oauth callback: calling sessions endpoint',
    user_id: session.user.id,
  }).catch(() => {})

  const resp = await fetch(
    `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/sessions`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ code: params.code }),
      cache: 'no-store',
    }
  )

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    void supabase.from('logs').insert({
      layer: 'frontend',
      level: 'error',
      message: 'oauth callback: sessions endpoint failed',
      status_code: resp.status,
      context: body,
      user_id: session.user.id,
    }).catch(() => {})
    redirect('/transactions?bank_error=1')
  }

  const data = await resp.json()
  void supabase.from('logs').insert({
    layer: 'frontend',
    level: 'info',
    message: 'oauth callback: bank connected',
    context: { accounts_connected: data.connected },
    user_id: session.user.id,
  }).catch(() => {})

  redirect('/transactions?bank_connected=1')
}
```

- [ ] **Step 4: Verify build passes**

```bash
cd /Users/louisgarnier/Claude/accounting/frontend
./node_modules/.bin/next build 2>&1
```

Expected: clean build, no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/louisgarnier/Claude/accounting
python3 scripts/git_ops.py add "frontend/app/(dashboard)/banking/connect/page.tsx" frontend/components/SyncButton.tsx "frontend/app/(dashboard)/banking/callback/page.tsx"
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: wire frontend logger into connect, sync, and callback flows"
python3 scripts/git_ops.py push
```

---

## Task 8: Update `.env.example` + Deploy + Verify

**Files:**
- Modify: `backend/.env.example`

- [ ] **Step 1: Update `backend/.env.example`**

Add `LOG_DIR=../logs` to the file. Full file contents:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
FRONTEND_URL=http://localhost:3000
APP_USER_ID=your-supabase-user-uid
ENABLE_BANKING_WEBHOOK_SECRET=your-webhook-secret
ENABLE_BANKING_APP_ID=your-enable-banking-app-id
ENABLE_BANKING_PRIVATE_KEY=your-rsa-private-key-single-line-with-slash-n
LOG_DIR=../logs
```

- [ ] **Step 2: Commit and push**

```bash
cd /Users/louisgarnier/Claude/accounting
python3 scripts/git_ops.py add backend/.env.example
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: add LOG_DIR to env example"
python3 scripts/git_ops.py push
```

- [ ] **Step 3: Confirm NEXT_PUBLIC_BACKEND_URL in Vercel**

In Vercel dashboard → your project → Settings → Environment Variables:
- Confirm `NEXT_PUBLIC_BACKEND_URL` = `https://accounting-production-d529.up.railway.app` (no trailing slash)
- If it was just added, trigger a new deployment: Deployments → … → Redeploy

- [ ] **Step 4: Verify Railway deploy succeeds**

Railway dashboard → Deployments → confirm latest commit is ACTIVE and green.

- [ ] **Step 5: Verify logs appear in Supabase**

Open the app → connect page → the `useEffect` fires immediately on load.

Query in Supabase SQL editor:
```sql
select created_at, layer, level, message, context
from logs
order by created_at desc
limit 10;
```

Expected: rows with `layer='frontend'`, `message='app config'`, `context` showing `backend_url` value.

If `backend_url` is `"undefined"`, NEXT_PUBLIC_BACKEND_URL is not set in Vercel → fix and redeploy.
If `backend_url` is the Railway URL, environment is correct.

- [ ] **Step 6: Update build log**

Update `docs/project/config/build-log.md` — add Plan 4 logging section, mark tasks complete.

---

## Self-Review

**Spec coverage:**
- ✅ `logs` table with all fields including `request_id` → Task 1
- ✅ `log_to_supabase` fire-and-forget → Task 2
- ✅ `db_logger` wrappers for all DB operations → Task 3
- ✅ Startup env var presence log → Task 4
- ✅ Supabase connection check on startup → Task 4
- ✅ API middleware with timing + X-Request-ID → Task 4
- ✅ Unhandled exception handler → Task 4
- ✅ Banking router session step logging → Task 5
- ✅ Webhook receipt logging → Task 5
- ✅ Frontend `logger.fetch` with `request_id`, `done`, `networkError` → Task 6
- ✅ Config snapshot on connect page mount → Task 7
- ✅ OAuth callback step logging → Task 7
- ✅ RLS: frontend insert own rows only → Task 1

**Type consistency:**
- `db_select` returns `list`, used as `list` in all routers ✅
- `db_insert` returns `dict`, not used in routers (fire-and-forget) ✅
- `db_delete` returns `int`, not used in routers ✅
- `logger.fetch` returns `{ request_id, done, networkError }` used consistently ✅
- `log_to_supabase` takes `dict`, called consistently with `layer`, `level`, `message` keys ✅
