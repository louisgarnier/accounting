import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth import get_current_user
from app.database import get_db
from app.logger import backend_logger
from app.services.ocr import extract_fields

router = APIRouter(prefix="/api/documents")

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class ConfirmRequest(BaseModel):
    date: str | None = None
    amount: float | None = None
    vendor: str | None = None
    category_id: str | None = None


def get_storage():
    """Return the Supabase storage client."""
    return get_db().storage


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Upload a receipt/invoice, run OCR, save record. Returns extracted fields + document_id."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {', '.join(ALLOWED_TYPES)}"
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")

    # MD5 duplicate detection (scoped to user)
    file_hash = hashlib.md5(file_bytes).hexdigest()
    db = get_db()
    existing = (
        db.table("documents")
        .select("id")
        .eq("user_id", str(user.id))
        .eq("file_hash", file_hash)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="Duplicate document detected. This file has already been uploaded."
        )

    # Run OCR
    backend_logger.info(f"📥 [Documents] running OCR on {file.filename} ({file.content_type})")
    ocr = extract_fields(file_bytes, file.content_type)

    # Upload to Supabase Storage
    document_id = str(uuid.uuid4())
    ext = (file.filename or "file").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    storage_path = f"{user.id}/{document_id}.{ext}"

    storage = get_storage()
    storage.from_("documents").upload(
        storage_path,
        file_bytes,
        {"content-type": file.content_type},
    )

    # Generate stored_filename from OCR results (best-effort)
    date_part = ocr["date"] or "0000-00-00"
    vendor_part = _slugify(ocr["vendor"] or "unknown")
    amount_part = f"{ocr['amount']:.2f}" if ocr["amount"] is not None else "0.00"
    stored_filename = f"{date_part}_{vendor_part}_{amount_part}.{ext}"

    # Save document record
    db.table("documents").insert({
        "id": document_id,
        "user_id": str(user.id),
        "original_filename": file.filename,
        "stored_filename": stored_filename,
        "storage_path": storage_path,
        "file_hash": file_hash,
        "date": ocr["date"],
        "amount": ocr["amount"],
        "vendor": ocr["vendor"],
        "ocr_status": ocr["ocr_status"],
        "ocr_confidence": ocr["ocr_confidence"],
        "ocr_raw": ocr["ocr_raw"],
        "source": "upload",
    }).execute()

    backend_logger.info(f"✅ [Documents] saved doc {document_id} ocr_status={ocr['ocr_status']}")

    return {
        "document_id": document_id,
        "date": ocr["date"],
        "amount": ocr["amount"],
        "vendor": ocr["vendor"],
        "ocr_status": ocr["ocr_status"],
        "ocr_confidence": ocr["ocr_confidence"],
        "field_confidence": ocr["field_confidence"],
        "stored_filename": stored_filename,
    }


@router.patch("/{document_id}/confirm")
async def confirm_document(
    document_id: str,
    req: ConfirmRequest,
    user=Depends(get_current_user),
):
    """Finalise a document record with user-reviewed fields."""
    date_part = req.date or "0000-00-00"
    vendor_part = _slugify(req.vendor or "unknown")
    amount_part = f"{req.amount:.2f}" if req.amount is not None else "0.00"
    stored_filename = f"{date_part}_{vendor_part}_{amount_part}"

    db = get_db()
    result = db.table("documents").update({
        "date": req.date,
        "amount": req.amount,
        "vendor": req.vendor,
        "category_id": req.category_id,
        "stored_filename": stored_filename,
    }).eq("id", document_id).eq("user_id", str(user.id)).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    backend_logger.info(f"✅ [Documents] confirmed doc {document_id}")
    return {"confirmed": True}


def _slugify(text: str) -> str:
    """Convert vendor name to a safe filename fragment."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text[:40].strip("_")
