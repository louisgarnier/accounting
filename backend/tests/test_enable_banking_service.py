import time
import pytest
from unittest.mock import patch, MagicMock
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt

# Generate a throw-away RSA key for tests (done once at module load)
_test_rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PRIVATE_KEY = _test_rsa_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
TEST_APP_ID = "test-app-id-1234"


@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    monkeypatch.setattr("app.services.enable_banking.ENABLE_BANKING_PRIVATE_KEY", TEST_PRIVATE_KEY)
    monkeypatch.setattr("app.services.enable_banking.ENABLE_BANKING_APP_ID", TEST_APP_ID)


def test_make_jwt_is_valid_rs256():
    from app.services.enable_banking import _make_jwt
    token = _make_jwt()
    public_key = _test_rsa_key.public_key()
    payload = pyjwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience="api.enablebanking.com",
    )
    assert payload["iss"] == "enablebanking.com"
    assert payload["aud"] == "api.enablebanking.com"
    assert payload["exp"] > time.time()


def test_make_jwt_has_correct_kid():
    from app.services.enable_banking import _make_jwt
    token = _make_jwt()
    header = pyjwt.get_unverified_header(token)
    assert header["kid"] == TEST_APP_ID
    assert header["alg"] == "RS256"


def test_start_auth_returns_url():
    from app.services.enable_banking import start_auth
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "url": "https://ob.enablebanking.com/auth?session=abc",
        "authorization_id": "uuid-123",
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("app.services.enable_banking.httpx.post", return_value=mock_resp) as mock_post:
        url = start_auth("BNP Paribas", "FR", "https://myapp.com/callback", "state-xyz")
    assert url == "https://ob.enablebanking.com/auth?session=abc"
    body = mock_post.call_args[1]["json"]
    assert body["aspsp"]["name"] == "BNP Paribas"
    assert body["aspsp"]["country"] == "FR"
    assert body["redirect_url"] == "https://myapp.com/callback"
    assert body["state"] == "state-xyz"
    assert "valid_until" in body["access"]


def test_create_session_returns_accounts():
    from app.services.enable_banking import create_session
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "session_id": "sess-001",
        "aspsp": {"name": "BNP Paribas", "country": "FR"},
        "accounts": [
            {
                "uid": "acc-uid-1",
                "name": "Main Account",
                "account_id": {"iban": "FR7630004000031234567890143"},
            }
        ],
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("app.services.enable_banking.httpx.post", return_value=mock_resp):
        accounts = create_session("auth-code-123")
    assert len(accounts) == 1
    assert accounts[0]["account_uid"] == "acc-uid-1"
    assert accounts[0]["session_id"] == "sess-001"
    assert accounts[0]["institution_name"] == "BNP Paribas"
    assert accounts[0]["account_iban"] == "FR7630004000031234567890143"


def test_fetch_transactions_handles_pagination():
    from app.services.enable_banking import fetch_transactions
    page1 = MagicMock()
    page1.json.return_value = {
        "transactions": [{"transaction_id": "t1"}, {"transaction_id": "t2"}],
        "continuation_key": "key-page2",
    }
    page1.raise_for_status = MagicMock()
    page2 = MagicMock()
    page2.json.return_value = {
        "transactions": [{"transaction_id": "t3"}],
        "continuation_key": None,
    }
    page2.raise_for_status = MagicMock()
    with patch("app.services.enable_banking.httpx.get", side_effect=[page1, page2]) as mock_get:
        txns = fetch_transactions("acc-uid-1", "2024-01-01")
    assert len(txns) == 3
    assert txns[0]["transaction_id"] == "t1"
    assert txns[2]["transaction_id"] == "t3"
    # Second call must include continuation_key
    second_call_params = mock_get.call_args_list[1][1]["params"]
    assert second_call_params["continuation_key"] == "key-page2"


def test_fetch_transactions_no_pagination():
    from app.services.enable_banking import fetch_transactions
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "transactions": [{"transaction_id": "t1"}],
        "continuation_key": None,
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("app.services.enable_banking.httpx.get", return_value=mock_resp) as mock_get:
        txns = fetch_transactions("acc-uid-1", "2024-01-01")
    assert len(txns) == 1
    assert mock_get.call_count == 1
