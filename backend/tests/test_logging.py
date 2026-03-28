"""
Tests for logging infrastructure:
- Enable Banking API errors include response body in exception message
- API errors are logged to the 'backend' logger
- HTTP requests are logged to the 'api' logger
"""
import logging
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def patch_enable_banking_config(monkeypatch):
    monkeypatch.setattr("app.services.enable_banking.ENABLE_BANKING_PRIVATE_KEY", "")
    monkeypatch.setattr("app.services.enable_banking.ENABLE_BANKING_APP_ID", "test-app-id")
    monkeypatch.setattr("app.services.enable_banking._make_jwt", lambda: "dummy-test-jwt")


def _make_http_error(status_code: int, body: str) -> httpx.HTTPStatusError:
    mock_request = MagicMock(spec=httpx.Request)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = body
    return httpx.HTTPStatusError(
        f"{status_code}", request=mock_request, response=mock_response
    )


# --- Enable Banking error transparency ---

def test_start_auth_error_includes_response_body():
    """When Enable Banking returns an error, the raised exception includes the response body."""
    from app.services.enable_banking import start_auth

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = _make_http_error(
        401, '{"error": "invalid_jwt", "message": "JWT verification failed"}'
    )

    with patch("app.services.enable_banking.httpx.post", return_value=mock_resp):
        with pytest.raises(Exception) as exc_info:
            start_auth("Revolut", "FR", "http://localhost/callback", "state")

    error_str = str(exc_info.value)
    assert "401" in error_str
    assert "invalid_jwt" in error_str


def test_create_session_error_includes_response_body():
    """When Enable Banking session creation fails, the raised exception includes the response body."""
    from app.services.enable_banking import create_session

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = _make_http_error(
        400, '{"error": "invalid_code", "message": "Authorization code expired"}'
    )

    with patch("app.services.enable_banking.httpx.post", return_value=mock_resp):
        with pytest.raises(Exception) as exc_info:
            create_session("expired-code")

    error_str = str(exc_info.value)
    assert "400" in error_str
    assert "invalid_code" in error_str


def test_enable_banking_api_error_is_logged_to_backend_logger(caplog):
    """Enable Banking API errors are logged at ERROR level to the 'backend' logger."""
    from app.services.enable_banking import start_auth

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = _make_http_error(
        422, '{"error": "validation_error", "detail": "field aspsp.name is required"}'
    )

    with patch("app.services.enable_banking.httpx.post", return_value=mock_resp):
        with caplog.at_level(logging.ERROR, logger="backend"):
            with pytest.raises(Exception):
                start_auth("UnknownBank", "FR", "http://localhost/callback", "state")

    assert any("422" in r.message and "validation_error" in r.message for r in caplog.records)


# --- API request logging middleware ---

def test_api_middleware_logs_requests(caplog):
    """HTTP requests and responses are logged to the 'api' logger."""
    with caplog.at_level(logging.INFO, logger="api"):
        response = client.get("/health")

    assert response.status_code == 200
    messages = [r.message for r in caplog.records]
    assert any("GET" in m and "/health" in m for m in messages)
    assert any("200" in m for m in messages)


def test_api_middleware_logs_failed_requests(caplog):
    """Failed requests (4xx/5xx) are also logged with their status code."""
    with caplog.at_level(logging.INFO, logger="api"):
        response = client.get("/nonexistent-route")

    assert response.status_code == 404
    messages = [r.message for r in caplog.records]
    assert any("404" in m for m in messages)


# --- log_to_supabase ---

def test_log_to_supabase_inserts_entry_in_background():
    """log_to_supabase writes to Supabase logs table in a background thread."""
    import time
    from unittest.mock import MagicMock, patch

    mock_db = MagicMock()
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock()

    with patch("app.logger._get_db_for_logging", return_value=mock_db):
        from app.logger import log_to_supabase
        log_to_supabase({"layer": "backend", "level": "info", "message": "test"})
        time.sleep(0.05)  # let the background thread finish

    mock_db.table.assert_called_with("logs")
    inserted = mock_db.table.return_value.insert.call_args[0][0]
    assert inserted["message"] == "test"
    assert inserted["layer"] == "backend"


def test_log_to_supabase_does_not_raise_on_error():
    """log_to_supabase never raises even if Supabase is unavailable."""
    import time
    from unittest.mock import patch

    with patch("app.logger._get_db_for_logging", side_effect=Exception("db down")):
        from app.logger import log_to_supabase
        log_to_supabase({"layer": "backend", "level": "error", "message": "oops"})
        time.sleep(0.05)
    # No exception raised — test passes by completing
