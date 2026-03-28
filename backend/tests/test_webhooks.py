import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

WEBHOOK_SECRET = "test-webhook-secret"


def make_signature(payload: dict, secret: str) -> str:
    body = json.dumps(payload).encode()
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
