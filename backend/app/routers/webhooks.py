import hashlib
import hmac
import json

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
        external_id = (
            txn.get("uid")
            or txn.get("entry_reference")
            or txn.get("transaction_id")
        )
        if not external_id:
            continue

        existing = (
            db.table("transactions")
            .select("id")
            .eq("external_id", external_id)
            .execute()
        )
        if existing.data:
            continue

        amount_data = txn.get("transaction_amount", {})
        amount_str = amount_data.get("amount", "0")
        currency = amount_data.get("currency", "EUR")
        booking_date = txn.get("booking_date") or txn.get("value_date")
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
