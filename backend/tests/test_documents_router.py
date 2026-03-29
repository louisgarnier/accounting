import hashlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app


def auth_headers():
    return {"Authorization": "Bearer test-token"}


def mock_user():
    user = MagicMock()
    user.id = "681fe954-ab83-4767-bcdc-d6e04b329171"
    return user


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: mock_user()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


FAKE_OCR = {
    "ocr_status": "success",
    "ocr_confidence": 0.95,
    "ocr_raw": {"responses": [{}]},
    "date": "2026-03-15",
    "amount": 42.50,
    "vendor": "Amazon EU",
    "field_confidence": {"date": 0.95, "amount": 0.95, "vendor": 0.57},
}

FAKE_FILE = b"fake-image-content"
FAKE_MD5 = hashlib.md5(FAKE_FILE).hexdigest()


def test_upload_stores_file_and_returns_ocr_fields(client):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "doc-uuid-1"}]
    )
    mock_storage = MagicMock()
    mock_storage.from_.return_value.upload.return_value = MagicMock()

    with patch("app.routers.documents.get_db", return_value=mock_db):
        with patch("app.routers.documents.extract_fields", return_value=FAKE_OCR):
            with patch("app.routers.documents.get_storage", return_value=mock_storage):
                resp = client.post(
                    "/api/documents/upload",
                    files={"file": ("receipt.jpg", FAKE_FILE, "image/jpeg")},
                    headers=auth_headers(),
                )

    assert resp.status_code == 200
    data = resp.json()
    assert data["date"] == "2026-03-15"
    assert data["amount"] == 42.50
    assert data["vendor"] == "Amazon EU"
    assert data["ocr_status"] == "success"
    assert "document_id" in data
    assert "field_confidence" in data


def test_upload_rejects_unsupported_file_type(client):
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("doc.txt", b"text content", "text/plain")},
        headers=auth_headers(),
    )
    assert resp.status_code == 422


def test_upload_rejects_file_over_10mb(client):
    big_file = b"x" * (10 * 1024 * 1024 + 1)
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("big.jpg", big_file, "image/jpeg")},
        headers=auth_headers(),
    )
    assert resp.status_code == 413


def test_upload_detects_duplicate_by_md5(client):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "existing-doc-id"}]
    )

    with patch("app.routers.documents.get_db", return_value=mock_db):
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("receipt.jpg", FAKE_FILE, "image/jpeg")},
            headers=auth_headers(),
        )

    assert resp.status_code == 409
    assert "duplicate" in resp.json()["detail"].lower()


def test_upload_saves_failed_ocr_record(client):
    """Even if OCR fails, the document record is saved with ocr_status=failed."""
    failed_ocr = {
        "ocr_status": "failed",
        "ocr_confidence": 0.0,
        "ocr_raw": None,
        "date": None,
        "amount": None,
        "vendor": None,
        "field_confidence": {"date": 0.0, "amount": 0.0, "vendor": 0.0},
    }
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "doc-uuid-2"}]
    )
    mock_storage = MagicMock()
    mock_storage.from_.return_value.upload.return_value = MagicMock()

    with patch("app.routers.documents.get_db", return_value=mock_db):
        with patch("app.routers.documents.extract_fields", return_value=failed_ocr):
            with patch("app.routers.documents.get_storage", return_value=mock_storage):
                resp = client.post(
                    "/api/documents/upload",
                    files={"file": ("receipt.jpg", FAKE_FILE, "image/jpeg")},
                    headers=auth_headers(),
                )

    assert resp.status_code == 200
    assert resp.json()["ocr_status"] == "failed"
