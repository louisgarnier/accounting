import time
import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def mock_db():
    db = MagicMock()
    with patch("app.db_logger.get_db", return_value=db):
        yield db


@pytest.fixture(autouse=True)
def silence_supabase_log(monkeypatch):
    monkeypatch.setattr("app.db_logger.log_to_supabase", lambda entry: None)


def test_db_select_returns_rows(mock_db):
    """db_select executes the query and returns the data list."""
    from app.db_logger import db_select

    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "1"}, {"id": "2"}])

    result = db_select("transactions", lambda t: t.select("id").eq("user_id", "u1"))

    assert result == [{"id": "1"}, {"id": "2"}]


def test_db_select_returns_empty_list_on_no_rows(mock_db):
    """db_select returns [] when Supabase returns no rows."""
    from app.db_logger import db_select

    mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(data=[])

    result = db_select("bank_connections", lambda t: t.select("id"))

    assert result == []


def test_db_select_raises_on_exception(mock_db):
    """db_select re-raises exceptions from Supabase."""
    from app.db_logger import db_select

    mock_db.table.return_value.select.return_value.execute.side_effect = RuntimeError("db error")

    with pytest.raises(RuntimeError, match="db error"):
        db_select("transactions", lambda t: t.select("id"))


def test_db_insert_returns_inserted_row(mock_db):
    """db_insert executes the insert and returns the first inserted row."""
    from app.db_logger import db_insert

    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "abc", "amount": -42.5}]
    )

    result = db_insert("transactions", {"amount": -42.5, "user_id": "u1"})

    assert result == {"id": "abc", "amount": -42.5}
    mock_db.table.assert_called_with("transactions")


def test_db_insert_raises_on_exception(mock_db):
    """db_insert re-raises exceptions from Supabase."""
    from app.db_logger import db_insert

    mock_db.table.return_value.insert.return_value.execute.side_effect = RuntimeError("constraint")

    with pytest.raises(RuntimeError, match="constraint"):
        db_insert("transactions", {"amount": 0})


def test_db_delete_returns_deleted_count(mock_db):
    """db_delete executes the delete and returns the count of deleted rows."""
    from app.db_logger import db_delete

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "1"}, {"id": "2"}]
    )

    count = db_delete("bank_connections", lambda t: t.delete().eq("user_id", "u1"))

    assert count == 2


def test_db_delete_returns_zero_on_no_match(mock_db):
    """db_delete returns 0 when no rows matched the filter."""
    from app.db_logger import db_delete

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    count = db_delete("bank_connections", lambda t: t.delete().eq("user_id", "nobody"))

    assert count == 0
