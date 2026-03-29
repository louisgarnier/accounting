# Multi-Bank Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the user to connect multiple business bank accounts, manage them from a dedicated Banks page, and sync each bank independently with incremental or full (90-day) sync options.

**Architecture:** A new `/banking` management page lists all connected banks with per-bank Sync and Remove controls. The backend gains a `GET /connections` endpoint, a `DELETE /connections/{account_uid}` endpoint, and an updated `POST /sync` that accepts a specific `account_uid` and a `full_sync` flag. `POST /sessions` switches from delete-all to upsert so new connections append to the list. A `last_synced` column is added to `bank_connections`.

**Tech Stack:** FastAPI, Supabase PostgreSQL, Next.js 16.2.1, httpx, supabase-py 2.7.4

---

## Integration Assumptions (read before coding)

- `psu_type` in Enable Banking must be `"business"` — we are business accounts only.
- `account_uid` is Enable Banking's stable per-account identifier. It is the correct dedup key.
- `POST /sessions` may return multiple accounts per bank (e.g. Revolut EUR + CAD). All are stored as separate rows with the same `session_id`.
- Supabase upsert syntax: `.upsert({...}, on_conflict="account_uid")` — updates the row if `account_uid` already exists.
- `last_synced` is stored as ISO 8601 UTC string. Use `datetime.now(timezone.utc).isoformat()`.

---

## File Structure

**Created:**
- `supabase/migrations/004_bank_connections_last_synced.sql` — adds `last_synced` column
- `frontend/app/(dashboard)/banking/page.tsx` — bank config page (list + per-bank controls)
- `frontend/components/BankSyncButton.tsx` — per-bank sync button (incremental + full sync)

**Modified:**
- `backend/app/routers/banking.py` — sessions upsert, new GET /connections, DELETE /connections/{uid}, updated POST /sync
- `backend/tests/test_banking_router.py` — tests for all new/changed endpoints
- `backend/app/services/enable_banking.py` — change `psu_type` to `"business"`
- `frontend/app/(dashboard)/layout.tsx` — add Banks nav item
- `frontend/app/(dashboard)/banking/callback/page.tsx` — redirect to `/banking` after connect
- `frontend/app/(dashboard)/transactions/page.tsx` — remove SyncButton and Connect Bank link
- `frontend/components/SyncButton.tsx` — delete (replaced by BankSyncButton)

---

## Critical Testing Pattern — Table-Scoped Mocks

When a route queries multiple tables (e.g. `bank_connections` then `transactions`), use `side_effect` on `mock_db.table` to return separate mocks per table. This prevents chain collisions between queries that both use double `.eq()`.

```python
bank_conn_mock = MagicMock()
txn_mock = MagicMock()

def table_router(name):
    return bank_conn_mock if name == "bank_connections" else txn_mock

mock_db.table.side_effect = table_router
```

Never use `mock_db.table.return_value` for routes that touch more than one table.

---

### Task 1: Supabase migration — add last_synced to bank_connections

**Files:**
- Create: `supabase/migrations/004_bank_connections_last_synced.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- supabase/migrations/004_bank_connections_last_synced.sql
alter table bank_connections add column if not exists last_synced timestamptz;
```

- [ ] **Step 2: Run in Supabase Dashboard → SQL Editor → New Query**

Paste the SQL above and click Run.
Expected: "Success. No rows returned."

- [ ] **Step 3: Verify**

Go to Table Editor → bank_connections → check that `last_synced` column appears.

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py add supabase/migrations/004_bank_connections_last_synced.sql
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: add last_synced column to bank_connections"
```

---

### Task 2: Backend — fix psu_type + sessions upsert

**Files:**
- Modify: `backend/app/services/enable_banking.py`
- Modify: `backend/app/routers/banking.py`
- Modify: `backend/tests/test_banking_router.py`

#### Step 2a — fix psu_type

- [ ] **Step 1: Update psu_type in enable_banking.py**

In `backend/app/services/enable_banking.py`, change line:
```python
"psu_type": "personal",
```
to:
```python
"psu_type": "business",
```

- [ ] **Step 2: Run existing service tests**

```bash
cd backend && pytest tests/test_enable_banking_service.py -v
```
Expected: all pass (psu_type is not tested there, no breakage).

#### Step 2b — sessions upsert

Current `POST /sessions` deletes all connections then inserts. Replace with upsert so new banks append.

- [ ] **Step 3: Write the failing test**

Add to `backend/tests/test_banking_router.py`:

```python
def test_sessions_appends_without_deleting_existing(client):
    """Connecting a second bank must not remove the first."""
    mock_db = MagicMock()
    mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    with patch("app.routers.banking.create_session", return_value=[
        {
            "session_id": "sess-2",
            "account_uid": "acc-uid-2",
            "account_iban": "FR76...",
            "account_name": "Second",
            "institution_name": "Société Générale",
        }
    ]):
        with patch("app.routers.banking.get_db", return_value=mock_db):
            resp = client.post(
                "/api/banking/sessions",
                json={"code": "auth-code-2"},
                headers=auth_headers(),
            )
    assert resp.status_code == 200
    assert resp.json()["connected"] == 1
    # Must NOT have called delete
    mock_db.table.return_value.delete.assert_not_called()
    # Must have called upsert
    mock_db.table.return_value.upsert.assert_called_once()
```

- [ ] **Step 4: Run to confirm it fails**

```bash
cd backend && pytest tests/test_banking_router.py::test_sessions_appends_without_deleting_existing -v
```
Expected: FAIL — `delete` is still called, `upsert` is not.

- [ ] **Step 5: Update POST /sessions in banking.py**

Replace the sessions endpoint:

```python
@router.post("/sessions")
async def create_banking_session(req: SessionRequest, user=Depends(get_current_user)):
    """Exchange authorization code for session; upsert accounts (never deletes existing connections)."""
    try:
        accounts = create_session(req.code)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Enable Banking error: {exc}")

    db = get_db()
    for acc in accounts:
        db.table("bank_connections").upsert(
            {
                "user_id": str(user.id),
                "session_id": acc["session_id"],
                "account_uid": acc["account_uid"],
                "account_iban": acc.get("account_iban", ""),
                "account_name": acc.get("account_name", ""),
                "institution_name": acc.get("institution_name", ""),
            },
            on_conflict="account_uid",
        ).execute()

    return {"connected": len(accounts)}
```

Also update the existing `test_sessions_stores_accounts_and_returns_count` test — it now expects `upsert` not `insert`:

```python
def test_sessions_stores_accounts_and_returns_count(client):
    mock_db = MagicMock()
    mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    with patch("app.routers.banking.create_session", return_value=[
        {
            "session_id": "sess-1",
            "account_uid": "acc-uid-1",
            "account_iban": "FR76...",
            "account_name": "Main",
            "institution_name": "BNP Paribas",
        }
    ]):
        with patch("app.routers.banking.get_db", return_value=mock_db):
            resp = client.post(
                "/api/banking/sessions",
                json={"code": "auth-code-from-callback"},
                headers=auth_headers(),
            )
    assert resp.status_code == 200
    assert resp.json()["connected"] == 1
```

- [ ] **Step 6: Run all banking router tests**

```bash
cd backend && pytest tests/test_banking_router.py -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py add backend/app/services/enable_banking.py backend/app/routers/banking.py backend/tests/test_banking_router.py
python3 scripts/git_ops.py commit -m "[EPIC-4] fix: sessions upsert (append banks, never delete); psu_type=business"
```

---

### Task 3: Backend — GET /api/banking/connections

**Files:**
- Modify: `backend/app/routers/banking.py`
- Modify: `backend/tests/test_banking_router.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_banking_router.py`:

```python
def test_list_connections_returns_all_banks(client):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[
            {
                "account_uid": "acc-uid-1",
                "account_name": "Main",
                "account_iban": "FR76...",
                "institution_name": "BNP Paribas",
                "last_synced": None,
            },
            {
                "account_uid": "acc-uid-2",
                "account_name": "Business",
                "account_iban": "GB29...",
                "institution_name": "Revolut",
                "last_synced": "2026-03-29T10:00:00+00:00",
            },
        ]
    )
    with patch("app.routers.banking.get_db", return_value=mock_db):
        resp = client.get("/api/banking/connections", headers=auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["connections"]) == 2
    assert data["connections"][0]["institution_name"] == "BNP Paribas"
    assert data["connections"][1]["last_synced"] == "2026-03-29T10:00:00+00:00"
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd backend && pytest tests/test_banking_router.py::test_list_connections_returns_all_banks -v
```
Expected: FAIL — 404 (route doesn't exist yet).

- [ ] **Step 3: Add GET /connections to banking.py**

Add after the `list_aspsps` endpoint:

```python
@router.get("/connections")
async def list_connections(user=Depends(get_current_user)):
    """Return all bank connections for the current user."""
    db = get_db()
    result = (
        db.table("bank_connections")
        .select("account_uid, account_name, account_iban, institution_name, last_synced")
        .eq("user_id", str(user.id))
        .order("created_at")
        .execute()
    )
    return {"connections": result.data}
```

- [ ] **Step 4: Run the test**

```bash
cd backend && pytest tests/test_banking_router.py::test_list_connections_returns_all_banks -v
```
Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
cd backend && pytest tests/test_banking_router.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py add backend/app/routers/banking.py backend/tests/test_banking_router.py
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: add GET /api/banking/connections"
```

---

### Task 4: Backend — DELETE /api/banking/connections/{account_uid}

**Files:**
- Modify: `backend/app/routers/banking.py`
- Modify: `backend/tests/test_banking_router.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_banking_router.py`:

```python
def test_remove_connection_deletes_and_returns_ok(client):
    mock_db = MagicMock()
    mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
    with patch("app.routers.banking.get_db", return_value=mock_db):
        resp = client.delete("/api/banking/connections/acc-uid-1", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json() == {"removed": True}


def test_remove_connection_scoped_to_user(client):
    """Delete must filter by both user_id and account_uid."""
    mock_db = MagicMock()
    mock_db.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
    with patch("app.routers.banking.get_db", return_value=mock_db):
        client.delete("/api/banking/connections/acc-uid-1", headers=auth_headers())
    # Verify the chain was called with correct args
    mock_db.table.assert_called_with("bank_connections")
    first_eq = mock_db.table.return_value.delete.return_value.eq
    first_eq.assert_called_with("user_id", "681fe954-ab83-4767-bcdc-d6e04b329171")
    second_eq = first_eq.return_value.eq
    second_eq.assert_called_with("account_uid", "acc-uid-1")
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd backend && pytest tests/test_banking_router.py::test_remove_connection_deletes_and_returns_ok tests/test_banking_router.py::test_remove_connection_scoped_to_user -v
```
Expected: FAIL — 405/404 (route doesn't exist).

- [ ] **Step 3: Add DELETE /connections/{account_uid} to banking.py**

```python
@router.delete("/connections/{account_uid}")
async def remove_connection(account_uid: str, user=Depends(get_current_user)):
    """Remove a specific bank connection for the current user."""
    db = get_db()
    db.table("bank_connections").delete().eq("user_id", str(user.id)).eq("account_uid", account_uid).execute()
    return {"removed": True}
```

- [ ] **Step 4: Run the new tests**

```bash
cd backend && pytest tests/test_banking_router.py::test_remove_connection_deletes_and_returns_ok tests/test_banking_router.py::test_remove_connection_scoped_to_user -v
```
Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
cd backend && pytest -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py add backend/app/routers/banking.py backend/tests/test_banking_router.py
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: add DELETE /api/banking/connections/{account_uid}"
```

---

### Task 5: Backend — update POST /api/banking/sync (per-bank, incremental/full)

**Files:**
- Modify: `backend/app/routers/banking.py`
- Modify: `backend/tests/test_banking_router.py`

The new sync endpoint accepts `{ account_uid, full_sync }`. It fetches only the specified account, uses `last_synced` as `date_from` unless `full_sync=true` (then 90 days), then updates `last_synced` after a successful fetch.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_banking_router.py`:

```python
def test_sync_incremental_uses_last_synced_date(client):
    """Incremental sync uses last_synced as date_from."""
    bank_conn_mock = MagicMock()
    txn_mock = MagicMock()

    def table_router(name):
        return bank_conn_mock if name == "bank_connections" else txn_mock

    mock_db = MagicMock()
    mock_db.table.side_effect = table_router

    bank_conn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"account_uid": "acc-uid-1", "institution_name": "Revolut", "account_name": "Main", "last_synced": "2026-03-01"}]
    )
    bank_conn_mock.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
    txn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    txn_mock.insert.return_value.execute.return_value = MagicMock()

    captured = {}
    def fake_fetch(account_uid, date_from):
        captured["date_from"] = date_from
        return []

    with patch("app.routers.banking.fetch_transactions", side_effect=fake_fetch):
        with patch("app.routers.banking.get_db", return_value=mock_db):
            resp = client.post(
                "/api/banking/sync",
                json={"account_uid": "acc-uid-1", "full_sync": False},
                headers=auth_headers(),
            )
    assert resp.status_code == 200
    assert captured["date_from"] == "2026-03-01"


def test_sync_full_uses_90_day_window(client):
    """Full sync ignores last_synced and uses 90 days ago."""
    from datetime import date, timedelta
    bank_conn_mock = MagicMock()
    txn_mock = MagicMock()

    def table_router(name):
        return bank_conn_mock if name == "bank_connections" else txn_mock

    mock_db = MagicMock()
    mock_db.table.side_effect = table_router

    bank_conn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"account_uid": "acc-uid-1", "institution_name": "Revolut", "account_name": "Main", "last_synced": "2026-03-01"}]
    )
    bank_conn_mock.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
    txn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    txn_mock.insert.return_value.execute.return_value = MagicMock()

    captured = {}
    def fake_fetch(account_uid, date_from):
        captured["date_from"] = date_from
        return []

    with patch("app.routers.banking.fetch_transactions", side_effect=fake_fetch):
        with patch("app.routers.banking.get_db", return_value=mock_db):
            resp = client.post(
                "/api/banking/sync",
                json={"account_uid": "acc-uid-1", "full_sync": True},
                headers=auth_headers(),
            )
    assert resp.status_code == 200
    expected_date = (date.today() - timedelta(days=90)).isoformat()
    assert captured["date_from"] == expected_date


def test_sync_updates_last_synced_after_fetch(client):
    """last_synced must be written to bank_connections after sync."""
    bank_conn_mock = MagicMock()
    txn_mock = MagicMock()

    def table_router(name):
        return bank_conn_mock if name == "bank_connections" else txn_mock

    mock_db = MagicMock()
    mock_db.table.side_effect = table_router

    bank_conn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"account_uid": "acc-uid-1", "institution_name": "Revolut", "account_name": "Main", "last_synced": None}]
    )
    bank_conn_mock.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
    txn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    txn_mock.insert.return_value.execute.return_value = MagicMock()

    with patch("app.routers.banking.fetch_transactions", return_value=[]):
        with patch("app.routers.banking.get_db", return_value=mock_db):
            resp = client.post(
                "/api/banking/sync",
                json={"account_uid": "acc-uid-1", "full_sync": False},
                headers=auth_headers(),
            )
    assert resp.status_code == 200
    bank_conn_mock.update.assert_called_once()
    update_payload = bank_conn_mock.update.call_args[0][0]
    assert "last_synced" in update_payload


def test_sync_returns_404_if_connection_not_found(client):
    bank_conn_mock = MagicMock()

    def table_router(name):
        return bank_conn_mock

    mock_db = MagicMock()
    mock_db.table.side_effect = table_router
    bank_conn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    with patch("app.routers.banking.get_db", return_value=mock_db):
        resp = client.post(
            "/api/banking/sync",
            json={"account_uid": "nonexistent", "full_sync": False},
            headers=auth_headers(),
        )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd backend && pytest tests/test_banking_router.py::test_sync_incremental_uses_last_synced_date tests/test_banking_router.py::test_sync_full_uses_90_day_window tests/test_banking_router.py::test_sync_updates_last_synced_after_fetch tests/test_banking_router.py::test_sync_returns_404_if_connection_not_found -v
```
Expected: FAIL — old sync endpoint doesn't accept a body with `account_uid`.

- [ ] **Step 3: Replace POST /sync in banking.py**

First add a new request model at the top of the file (near the other models):

```python
class SyncRequest(BaseModel):
    account_uid: str
    full_sync: bool = False
```

Then replace the sync endpoint:

```python
@router.post("/sync")
async def sync_transactions(req: SyncRequest, user=Depends(get_current_user)):
    """Pull transactions for one account. full_sync=True uses 90-day window; default uses last_synced."""
    from datetime import datetime, timezone

    db = get_db()
    conn_result = (
        db.table("bank_connections")
        .select("account_uid, institution_name, account_name, last_synced")
        .eq("user_id", str(user.id))
        .eq("account_uid", req.account_uid)
        .execute()
    )
    if not conn_result.data:
        raise HTTPException(status_code=404, detail="Bank connection not found.")

    conn = conn_result.data[0]

    if req.full_sync or not conn.get("last_synced"):
        date_from = (date.today() - timedelta(days=90)).isoformat()
    else:
        date_from = conn["last_synced"][:10]  # take YYYY-MM-DD portion

    try:
        raw_txns = fetch_transactions(conn["account_uid"], date_from)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Enable Banking error: {exc}")

    total_saved = 0
    for txn in raw_txns:
        external_id = (
            txn.get("transaction_id")
            or txn.get("entry_reference")
            or txn.get("internal_transaction_id")
        )
        if not external_id:
            from app.logger import backend_logger
            backend_logger.warning(f"⚠️ [Banking] skipped txn — no external_id. Keys: {list(txn.keys())} | remittance: {txn.get('remittance_information')} | amount: {txn.get('transaction_amount')}")
            continue

        existing = (
            db.table("transactions")
            .select("id")
            .eq("account_uid", conn["account_uid"])
            .eq("external_id", external_id)
            .execute()
        )
        if existing.data:
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

        db.table("transactions").insert(
            {
                "user_id": str(user.id),
                "external_id": external_id,
                "account_uid": conn["account_uid"],
                "date": txn.get("booking_date") or txn.get("value_date"),
                "amount": amount,
                "description": description,
                "currency": txn.get("transaction_amount", {}).get("currency", "EUR"),
                "source_bank": conn["institution_name"],
            }
        ).execute()
        total_saved += 1

    db.table("bank_connections").update(
        {"last_synced": datetime.now(timezone.utc).isoformat()}
    ).eq("user_id", str(user.id)).eq("account_uid", req.account_uid).execute()

    return {"synced": total_saved}
```

- [ ] **Step 4: Update the old sync tests that used the old signature**

The old `test_sync_saves_transactions_and_returns_count`, `test_sync_returns_404_if_no_connections`, and `test_sync_debit_amount_is_negative` tests used the old endpoint (no body, synced all connections). Replace them with these updated versions:

```python
def test_sync_saves_transactions_and_returns_count(client):
    bank_conn_mock = MagicMock()
    txn_mock = MagicMock()

    def table_router(name):
        return bank_conn_mock if name == "bank_connections" else txn_mock

    mock_db = MagicMock()
    mock_db.table.side_effect = table_router

    bank_conn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"account_uid": "acc-uid-1", "institution_name": "BNP Paribas", "account_name": "Main", "last_synced": None}]
    )
    bank_conn_mock.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
    # Dedup check: not seen before
    txn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    txn_mock.insert.return_value.execute.return_value = MagicMock()

    with patch("app.routers.banking.fetch_transactions", return_value=[
        {
            "transaction_id": "txn-001",
            "booking_date": "2024-03-01",
            "transaction_amount": {"amount": "42.50", "currency": "EUR"},
            "credit_debit_indicator": "DBIT",
            "remittance_information": ["Coffee shop"],
        }
    ]):
        with patch("app.routers.banking.get_db", return_value=mock_db):
            resp = client.post(
                "/api/banking/sync",
                json={"account_uid": "acc-uid-1", "full_sync": False},
                headers=auth_headers(),
            )
    assert resp.status_code == 200
    assert resp.json()["synced"] == 1


def test_sync_debit_amount_is_negative(client):
    """DBIT transactions must be stored as negative amounts."""
    saved_rows = []

    def fake_insert(row):
        saved_rows.append(row)
        m = MagicMock()
        m.execute.return_value = MagicMock()
        return m

    bank_conn_mock = MagicMock()
    txn_mock = MagicMock()

    def table_router(name):
        return bank_conn_mock if name == "bank_connections" else txn_mock

    mock_db = MagicMock()
    mock_db.table.side_effect = table_router

    bank_conn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"account_uid": "acc-uid-1", "institution_name": "BNP", "account_name": "Main", "last_synced": None}]
    )
    bank_conn_mock.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
    txn_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    txn_mock.insert.side_effect = fake_insert

    with patch("app.routers.banking.fetch_transactions", return_value=[
        {
            "transaction_id": "txn-debit",
            "booking_date": "2024-03-01",
            "transaction_amount": {"amount": "100.00", "currency": "EUR"},
            "credit_debit_indicator": "DBIT",
            "remittance_information": ["Groceries"],
        }
    ]):
        with patch("app.routers.banking.get_db", return_value=mock_db):
            client.post(
                "/api/banking/sync",
                json={"account_uid": "acc-uid-1", "full_sync": False},
                headers=auth_headers(),
            )
    assert len(saved_rows) == 1, "Expected exactly one transaction to be inserted"
    assert saved_rows[0]["amount"] < 0, f"DBIT amount should be negative, got {saved_rows[0]['amount']}"
```

Remove `test_sync_returns_404_if_no_connections` — it's replaced by `test_sync_returns_404_if_connection_not_found` added in Step 1.

- [ ] **Step 5: Run all banking router tests**

```bash
cd backend && pytest tests/test_banking_router.py -v
```
Expected: all pass.

- [ ] **Step 6: Run full suite**

```bash
cd backend && pytest -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py add backend/app/routers/banking.py backend/tests/test_banking_router.py
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: per-bank sync with incremental/full option and last_synced tracking"
```

---

### Task 6: Frontend — Banks page + nav + cleanup

**Files:**
- Create: `frontend/app/(dashboard)/banking/page.tsx`
- Create: `frontend/components/BankSyncButton.tsx`
- Modify: `frontend/app/(dashboard)/layout.tsx`
- Modify: `frontend/app/(dashboard)/banking/callback/page.tsx`
- Modify: `frontend/app/(dashboard)/transactions/page.tsx`
- Delete: `frontend/components/SyncButton.tsx`

- [ ] **Step 1: Create BankSyncButton component**

Create `frontend/components/BankSyncButton.tsx`:

```tsx
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

interface Props {
  accountUid: string
}

export default function BankSyncButton({ accountUid }: Props) {
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const router = useRouter()

  async function handleSync(fullSync: boolean) {
    setLoading(true)
    setMessage('')
    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()
    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/sync`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${session?.access_token}`,
          },
          body: JSON.stringify({ account_uid: accountUid, full_sync: fullSync }),
        }
      )
      if (!resp.ok) throw new Error('Sync failed')
      const data = await resp.json()
      setMessage(
        data.synced === 0
          ? 'Already up to date'
          : `${data.synced} new transaction${data.synced !== 1 ? 's' : ''} synced`
      )
      router.refresh()
    } catch {
      setMessage('Sync failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <button
          onClick={() => handleSync(false)}
          disabled={loading}
          className="text-xs bg-slate-900 text-white rounded px-2.5 py-1 disabled:opacity-50"
        >
          {loading ? 'Syncing…' : 'Sync'}
        </button>
        <button
          onClick={() => handleSync(true)}
          disabled={loading}
          className="text-xs text-slate-500 hover:text-slate-700 disabled:opacity-50"
        >
          Full sync
        </button>
      </div>
      {message && <span className="text-xs text-slate-400">{message}</span>}
    </div>
  )
}
```

- [ ] **Step 2: Create the Banks page**

Create `frontend/app/(dashboard)/banking/page.tsx`:

```tsx
import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'
import BankSyncButton from '@/components/BankSyncButton'

type Connection = {
  account_uid: string
  account_name: string | null
  account_iban: string | null
  institution_name: string | null
  last_synced: string | null
}

async function removeConnection(accountUid: string, accessToken: string) {
  'use server'
  // This is a Server Action — called from the Remove form below
  await fetch(
    `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/connections/${accountUid}`,
    {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: 'no-store',
    }
  )
}

export default async function BanksPage() {
  const supabase = await createClient()
  const { data: { session } } = await supabase.auth.getSession()

  const resp = await fetch(
    `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/connections`,
    {
      headers: { Authorization: `Bearer ${session?.access_token}` },
      cache: 'no-store',
    }
  )
  const data = resp.ok ? await resp.json() : { connections: [] }
  const connections: Connection[] = data.connections

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-base font-semibold text-slate-900">
          Connected Banks
          {connections.length > 0 && (
            <span className="ml-2 text-sm font-normal text-slate-500">
              {connections.length} account{connections.length !== 1 ? 's' : ''}
            </span>
          )}
        </h2>
        <Link
          href="/banking/connect"
          className="text-sm bg-slate-900 text-white rounded-md px-3 py-1.5"
        >
          + Add Bank
        </Link>
      </div>

      {connections.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-slate-500 text-sm">No banks connected yet.</p>
          <Link
            href="/banking/connect"
            className="mt-4 inline-block text-sm text-slate-900 underline"
          >
            Connect your first bank
          </Link>
        </div>
      ) : (
        <ul className="space-y-3">
          {connections.map((conn) => (
            <li
              key={conn.account_uid}
              className="bg-white rounded-lg border border-slate-200 px-4 py-3 flex items-center justify-between"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900">
                  {conn.institution_name}
                  {conn.account_name && (
                    <span className="ml-1.5 text-slate-500 font-normal">
                      — {conn.account_name}
                    </span>
                  )}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {conn.account_iban || conn.account_uid}
                  {conn.last_synced && (
                    <> · Last synced {new Date(conn.last_synced).toLocaleDateString()}</>
                  )}
                  {!conn.last_synced && ' · Never synced'}
                </p>
              </div>
              <div className="flex items-center gap-4 ml-4 shrink-0">
                <BankSyncButton accountUid={conn.account_uid} />
                <form
                  action={async () => {
                    'use server'
                    await removeConnection(conn.account_uid, session?.access_token ?? '')
                  }}
                >
                  <button
                    type="submit"
                    className="text-xs text-red-500 hover:text-red-700"
                  >
                    Remove
                  </button>
                </form>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Add Banks nav item to layout**

In `frontend/app/(dashboard)/layout.tsx`, update the nav:

```tsx
<nav className="flex gap-4">
  <Link
    href="/transactions"
    className="text-sm text-slate-600 hover:text-slate-900"
  >
    Transactions
  </Link>
  <Link
    href="/banking"
    className="text-sm text-slate-600 hover:text-slate-900"
  >
    Banks
  </Link>
</nav>
```

- [ ] **Step 4: Update callback to redirect to /banking**

In `frontend/app/(dashboard)/banking/callback/page.tsx`, change the last two lines:

```tsx
  if (!resp.ok) {
    redirect('/banking?bank_error=1')
  }

  redirect('/banking?bank_connected=1')
```

- [ ] **Step 5: Update transactions page — remove Sync and Connect Bank**

Replace `frontend/app/(dashboard)/transactions/page.tsx` with this cleaned-up version (no SyncButton, no Connect Bank link, no bank flash messages):

```tsx
import { createClient } from '@/lib/supabase/server'

type Transaction = {
  id: string
  date: string
  amount: number
  description: string
  currency: string
  source_bank: string | null
  matches: { id: string }[] | null
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

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-slate-900">
          Transactions
          {transactions && transactions.length > 0 && (
            <span className="ml-2 text-sm font-normal text-slate-500">
              {transactions.length} total
            </span>
          )}
        </h2>
      </div>

      {!transactions || transactions.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-slate-500 text-sm">No transactions yet.</p>
          <p className="text-slate-400 text-xs mt-2">
            Go to Banks to connect an account and sync.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {(transactions as Transaction[]).map((txn) => {
            const matched = txn.matches !== null && txn.matches.length > 0
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
      )}
    </div>
  )
}
```

- [ ] **Step 6: Delete SyncButton.tsx**

```bash
rm frontend/components/SyncButton.tsx
```

- [ ] **Step 7: Run frontend build**

```bash
cd frontend && npm run build 2>&1
```
Expected: `✓ Compiled successfully`. Routes listed: `/`, `/login`, `/transactions`, `/banking`, `/banking/connect`, `/banking/callback`, `/_not-found`.

If build fails with `Cannot find module '@/components/SyncButton'`: check that `SyncButton` import was removed from `transactions/page.tsx`.

- [ ] **Step 8: Commit**

```bash
python3 scripts/git_ops.py add "frontend/app/(dashboard)/banking/page.tsx" "frontend/components/BankSyncButton.tsx" "frontend/app/(dashboard)/layout.tsx" "frontend/app/(dashboard)/banking/callback/page.tsx" "frontend/app/(dashboard)/transactions/page.tsx"
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: banks config page, per-bank sync, remove connection, nav update"
```

---

### Task 7: Pre-deploy checklist

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend && pytest -v
```
Expected: all pass, 0 failed.

- [ ] **Step 2: Run frontend build**

```bash
cd frontend && npm run build 2>&1
```
Expected: `✓ Compiled successfully`.

- [ ] **Step 3: Push**

```bash
python3 scripts/git_ops.py push
```

- [ ] **Step 4: Verify Railway health**

```bash
curl https://accounting-production-d529.up.railway.app/health
```
Expected: `{"status":"ok"}`.

---

### Task 8: End-to-end test

- [ ] Go to `https://accounting-flax-pi.vercel.app/banking`
  Expected: "Banks" nav item visible. Page shows "No banks connected yet" + Add Bank button.

- [ ] Click **+ Add Bank** → connect a bank → callback redirects to `/banking` with the new connection listed.

- [ ] Click **Sync** on the connected bank.
  Expected: spinner → "N new transactions synced" → last synced date updates on the page.

- [ ] Click **+ Add Bank** again → connect a second bank.
  Expected: both banks now listed (first bank not removed).

- [ ] Click **Full sync** on one bank.
  Expected: pulls 90 days, dedup prevents duplicates from the earlier sync.

- [ ] Click **Remove** on one bank.
  Expected: bank disappears from the list. Its transactions remain in Transactions page.

- [ ] Go to `/transactions` — all transactions from all connected banks visible, no Sync button.

---

## Session close checklist

- [ ] Update `docs/project/config/build-log.md` — mark Plan 4 complete
- [ ] Update `docs/project/config/codebase.md` — add new modules
- [ ] Append any new bugs to `workflow/ERRORS.md`
- [ ] Append any architectural decisions to `workflow/ADR.md`
