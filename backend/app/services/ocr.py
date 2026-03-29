import base64
import re
from datetime import datetime

import httpx

from app.config import GOOGLE_VISION_API_KEY

VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"

# Confidence threshold below which a field is flagged as low-confidence
LOW_CONFIDENCE_THRESHOLD = 0.7


def parse_amount(text: str) -> tuple[float | None, float]:
    """Extract the largest monetary amount from text. Returns (amount, confidence)."""
    patterns = [
        r"(?:€|EUR\s*)(\d+[.,]\d{2})",
        r"(\d+[.,]\d{2})\s*(?:€|EUR)",
        r"(?:USD|\$)\s*(\d+[.,]\d{2})",
        r"(\d+[.,]\d{2})\s*(?:USD|\$)",
        r"(\d+[.,]\d{2})",
    ]
    candidates = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw = match.group(1).replace(",", ".")
            try:
                candidates.append(float(raw))
            except ValueError:
                pass
    if not candidates:
        return None, 0.0
    return max(candidates), 1.0


def parse_date(text: str) -> tuple[str | None, float]:
    """Extract a date from text. Returns (ISO date string, confidence)."""
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1), 1.0

    m = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", text)
    if m:
        try:
            d = datetime.strptime(f"{m.group(1)}/{m.group(2)}/{m.group(3)}", "%d/%m/%Y")
            return d.strftime("%Y-%m-%d"), 0.8
        except ValueError:
            pass

    m = re.search(
        r"\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})\b",
        text, re.IGNORECASE
    )
    if m:
        try:
            d = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
            return d.strftime("%Y-%m-%d"), 0.8
        except ValueError:
            pass

    return None, 0.0


def parse_vendor(text: str) -> tuple[str | None, float]:
    """Extract vendor name — first non-empty, non-numeric line of text."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^[\d€$.,/:%-]+$", line):
            continue
        if len(line) < 2:
            continue
        return line[:80], 0.6
    return None, 0.0


def extract_fields(file_bytes: bytes, mime_type: str) -> dict:
    """
    Call Google Vision API and parse date, amount, vendor from the response.
    Returns a dict with: date, amount, vendor, ocr_status, ocr_confidence,
    ocr_raw, field_confidence (per-field dict).
    """
    try:
        payload = {
            "requests": [{
                "image": {"content": base64.b64encode(file_bytes).decode()},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            }]
        }
        resp = httpx.post(
            f"{VISION_API_URL}?key={GOOGLE_VISION_API_KEY}",
            json=payload,
            timeout=30,
        )
        data = resp.json()
    except Exception:
        return _failed_result()

    responses = data.get("responses", [{}])
    annotation = responses[0].get("fullTextAnnotation") if responses else None

    if not annotation:
        return _failed_result()

    raw_text = annotation.get("text", "")
    pages = annotation.get("pages", [{}])
    page_confidence = pages[0].get("confidence", 0.5) if pages else 0.5

    date, date_conf = parse_date(raw_text)
    amount, amount_conf = parse_amount(raw_text)
    vendor, vendor_conf = parse_vendor(raw_text)

    overall_confidence = page_confidence

    return {
        "ocr_status": "success",
        "ocr_confidence": overall_confidence,
        "ocr_raw": data,
        "date": date,
        "amount": amount,
        "vendor": vendor,
        "field_confidence": {
            "date": date_conf * overall_confidence,
            "amount": amount_conf * overall_confidence,
            "vendor": vendor_conf * overall_confidence,
        },
    }


def _failed_result() -> dict:
    return {
        "ocr_status": "failed",
        "ocr_confidence": 0.0,
        "ocr_raw": None,
        "date": None,
        "amount": None,
        "vendor": None,
        "field_confidence": {"date": 0.0, "amount": 0.0, "vendor": 0.0},
    }
