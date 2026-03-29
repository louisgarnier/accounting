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


def test_aspsps_returns_bank_list(client):
    with patch("app.routers.banking.get_aspsps", return_value=[
        {"name": "BNP Paribas", "country": "FR"},
        {"name": "Société Générale", "country": "FR"},
    ]):
        resp = client.get("/api/banking/aspsps?country=FR", headers=auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["aspsps"]) == 2
    assert data["aspsps"][0]["name"] == "BNP Paribas"


def test_aspsps_returns_502_on_error(client):
    with patch("app.routers.banking.get_aspsps", side_effect=Exception("API error")):
        resp = client.get("/api/banking/aspsps?country=FR", headers=auth_headers())
    assert resp.status_code == 502


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
    # Connections query: .table().select().eq(user_id).execute()  — single .eq()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"account_uid": "acc-uid-1", "institution_name": "BNP Paribas", "account_name": "Main"}]
    )
    # Dedup query: .table().select().eq(account_uid).eq(external_id).execute() — double .eq()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]  # not seen before
    )
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
    assert data["connections"][0]["account_uid"] == "acc-uid-1"


def test_sync_debit_amount_is_negative(client):
    """DBIT transactions must be stored as negative amounts."""
    saved_rows = []

    def fake_insert(row):
        saved_rows.append(row)
        m = MagicMock()
        m.execute.return_value = MagicMock()
        return m

    mock_db = MagicMock()
    # Connections query: single .eq()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"account_uid": "acc-uid-1", "institution_name": "BNP", "account_name": "Main"}]
    )
    # Dedup query: double .eq()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]  # not seen before
    )
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
