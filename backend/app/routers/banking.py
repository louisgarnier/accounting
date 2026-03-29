import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import get_current_user
from app.config import FRONTEND_URL
from app.database import get_db
from app.services.enable_banking import create_session, fetch_transactions, get_aspsps, start_auth

router = APIRouter(prefix="/api/banking")

# The URL Enable Banking redirects to after the user authorises
REDIRECT_URL = f"{FRONTEND_URL}/banking/callback"


class ConnectRequest(BaseModel):
    bank_name: str
    bank_country: str


class SessionRequest(BaseModel):
    code: str


class SyncRequest(BaseModel):
    account_uid: str
    full_sync: bool = False


@router.get("/aspsps")
async def list_aspsps(country: str = "FR", user=Depends(get_current_user)):
    """Return supported banks for a given country code."""
    try:
        aspsps = get_aspsps(country)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Enable Banking error: {exc}")
    return {"aspsps": [{"name": a["name"], "country": a["country"]} for a in aspsps]}


@router.delete("/connections/{account_uid}")
async def remove_connection(account_uid: str, user=Depends(get_current_user)):
    """Remove a specific bank connection for the current user."""
    db = get_db()
    try:
        db.table("bank_connections").delete().eq("user_id", str(user.id)).eq("account_uid", account_uid).execute()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Database error: {exc}")
    return {"removed": True}


@router.get("/connections")
async def list_connections(user=Depends(get_current_user)):
    """Return all bank connections for the current user."""
    db = get_db()
    try:
        result = (
            db.table("bank_connections")
            .select("account_uid, account_name, account_iban, institution_name, last_synced")
            .eq("user_id", str(user.id))
            .order("created_at")
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Database error: {exc}")
    return {"connections": result.data}


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
