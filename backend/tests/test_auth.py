from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)


def test_protected_route_without_token_returns_403():
    response = client.get("/api/protected-test")
    assert response.status_code == 403


def test_protected_route_with_invalid_token_returns_401():
    with patch("app.auth.supabase_admin") as mock_supabase:
        mock_supabase.auth.get_user.side_effect = Exception("Invalid token")
        response = client.get(
            "/api/protected-test",
            headers={"Authorization": "Bearer invalid_token"},
        )
    assert response.status_code == 401


def test_protected_route_with_valid_token_returns_200():
    mock_user = MagicMock()
    mock_user.id = "user-123"
    mock_response = MagicMock()
    mock_response.user = mock_user

    with patch("app.auth.supabase_admin") as mock_supabase:
        mock_supabase.auth.get_user.return_value = mock_response
        response = client.get(
            "/api/protected-test",
            headers={"Authorization": "Bearer valid_token"},
        )
    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123"}
