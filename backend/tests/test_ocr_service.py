import pytest
from unittest.mock import patch, MagicMock
from app.services.ocr import extract_fields, parse_amount, parse_date, parse_vendor


def test_parse_amount_finds_euro_amount():
    assert parse_amount("Total: €42.50") == (42.50, 1.0)


def test_parse_amount_finds_comma_decimal():
    assert parse_amount("Montant: 12,90 EUR") == (12.90, 1.0)


def test_parse_amount_returns_none_when_missing():
    assert parse_amount("No money here") == (None, 0.0)


def test_parse_date_iso_format():
    date, conf = parse_date("Invoice date: 2026-03-15")
    assert date == "2026-03-15"
    assert conf == 1.0


def test_parse_date_european_format():
    date, conf = parse_date("Date: 15/03/2026")
    assert date == "2026-03-15"
    assert conf == 0.8


def test_parse_date_returns_none_when_missing():
    assert parse_date("no date here") == (None, 0.0)


def test_parse_vendor_returns_first_meaningful_line():
    text = "\n\nAmazon EU\nOrder #123\nTotal: €42.50"
    vendor, conf = parse_vendor(text)
    assert vendor == "Amazon EU"
    assert conf == 0.6


def test_parse_vendor_returns_none_for_empty_text():
    assert parse_vendor("") == (None, 0.0)


def test_extract_fields_calls_vision_api_and_returns_parsed_fields():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "responses": [{
            "fullTextAnnotation": {
                "text": "Amazon EU\n2026-03-15\nTotal: €42.50",
                "pages": [{"confidence": 0.95}]
            }
        }]
    }
    mock_response.status_code = 200

    with patch("app.services.ocr.httpx.post", return_value=mock_response):
        result = extract_fields(b"fake-image-bytes", "image/jpeg")

    assert result["vendor"] == "Amazon EU"
    assert result["date"] == "2026-03-15"
    assert result["amount"] == 42.50
    assert result["ocr_status"] == "success"
    assert result["ocr_confidence"] >= 0.9


def test_extract_fields_returns_failed_when_no_text():
    mock_response = MagicMock()
    mock_response.json.return_value = {"responses": [{}]}
    mock_response.status_code = 200

    with patch("app.services.ocr.httpx.post", return_value=mock_response):
        result = extract_fields(b"blank-image", "image/jpeg")

    assert result["ocr_status"] == "failed"
    assert result["vendor"] is None
    assert result["amount"] is None
    assert result["date"] is None


def test_extract_fields_returns_failed_on_api_error():
    with patch("app.services.ocr.httpx.post", side_effect=Exception("network error")):
        result = extract_fields(b"bytes", "image/jpeg")

    assert result["ocr_status"] == "failed"
