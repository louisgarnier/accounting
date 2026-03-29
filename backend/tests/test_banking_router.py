import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_current_user


def auth_headers():
    return {"Authorization": "Bearer test-token"}


def mock_user():
    user = MagicMock()
    user.id = "681fe954-ab83-4767-bcdc-d6e04b329171"
    return user


@pytest.fixture(autouse=True)
def override_auth():
    """Override get_current_user for all banking tests."""
    app.dependency_overrides[get_current_user] = lambda: mock_user()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_connect_returns_url(client):
    with patch("app.routers.banking.start_auth", return_value="https://ob.enablebanking.com/auth?s=x"):
        resp = client.post(
            "/api/banking/connect",
            json={"bank_name": "BNP Paribas", "bank_country": "FR"},
            headers=auth_headers(),
        )
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://ob.enablebanking.com/auth?s=x"


def test_connect_returns_502_on_enable_banking_error(client):
    with patch("app.routers.banking.start_auth", side_effect=Exception("API down")):
        resp = client.post(
            "/api/banking/connect",
            json={"bank_name": "BNP Paribas", "bank_country": "FR"},
            headers=auth_headers(),
        )
    assert resp.status_code == 502


def test_sessions_stores_accounts_and_returns_count(client):
    mock_db = MagicMock()
    mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
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


def test_sessions_returns_502_on_enable_banking_error(client):
    with patch("app.routers.banking.create_session", side_effect=Exception("invalid code")):
        resp = client.post(
            "/api/banking/sessions",
            json={"code": "bad-code"},
            headers=auth_headers(),
        )
    assert resp.status_code == 502


def test_sync_saves_transactions_and_returns_count(client):
    mock_db = MagicMock()
    # First call: connections query returns one account.
    # Second call: dedup check returns empty (transaction not seen before).
    mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        MagicMock(data=[{"account_uid": "acc-uid-1", "institution_name": "BNP Paribas"}]),
        MagicMock(data=[]),
    ]
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()
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
            resp = client.post("/api/banking/sync", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["synced"] == 1


def test_sync_returns_404_if_no_connections(client):
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    with patch("app.routers.banking.get_db", return_value=mock_db):
        resp = client.post("/api/banking/sync", headers=auth_headers())
    assert resp.status_code == 404


def test_sync_debit_amount_is_negative(client):
    """DBIT transactions must be stored as negative amounts."""
    saved_rows = []

    def fake_insert(row):
        saved_rows.append(row)
        m = MagicMock()
        m.execute.return_value = MagicMock()
        return m

    mock_db = MagicMock()
    # connections query
    connections_result = MagicMock(data=[{"account_uid": "acc-uid-1", "institution_name": "BNP"}])
    # dedup check: no existing transaction
    dedup_result = MagicMock(data=[])
    mock_db.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        connections_result,
        dedup_result,
    ]
    mock_db.table.return_value.insert.side_effect = fake_insert
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
            client.post("/api/banking/sync", headers=auth_headers())
    assert len(saved_rows) == 1, "Expected exactly one transaction to be inserted"
    assert saved_rows[0]["amount"] < 0, f"DBIT amount should be negative, got {saved_rows[0]['amount']}"
