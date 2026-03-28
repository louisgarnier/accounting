import time
from typing import Callable

from app.database import get_db
from app.logger import db_logger, log_to_supabase


def _log(operation: str, table: str, duration_ms: int, extra: dict) -> None:
    db_logger.info(f"🗄️ [DB] {operation} {table} ({duration_ms}ms)")
    log_to_supabase({
        "layer": "database",
        "level": "info",
        "message": f"{operation} {table}",
        "duration_ms": duration_ms,
        "context": {"table": table, "operation": operation, **extra},
    })


def _log_error(operation: str, table: str, error: Exception) -> None:
    db_logger.error(f"❌ [DB] {operation} {table} error: {error}")
    log_to_supabase({
        "layer": "database",
        "level": "error",
        "message": f"{operation} {table} failed",
        "context": {"table": table, "operation": operation, "error": str(error)},
    })


def db_select(table: str, build_query: Callable) -> list:
    """Execute a select. build_query receives the table builder, returns the query chain."""
    start = time.monotonic()
    try:
        result = build_query(get_db().table(table)).execute()
        rows = len(result.data) if result.data else 0
        _log("select", table, int((time.monotonic() - start) * 1000), {"rows_returned": rows})
        return result.data or []
    except Exception as e:
        _log_error("select", table, e)
        raise


def db_insert(table: str, row: dict) -> dict:
    """Insert one row. Returns the inserted row."""
    start = time.monotonic()
    try:
        result = get_db().table(table).insert(row).execute()
        _log("insert", table, int((time.monotonic() - start) * 1000), {"rows_inserted": 1})
        return result.data[0] if result.data else {}
    except Exception as e:
        _log_error("insert", table, e)
        raise


def db_delete(table: str, build_query: Callable) -> int:
    """Execute a delete. build_query receives the table builder. Returns deleted row count."""
    start = time.monotonic()
    try:
        result = build_query(get_db().table(table)).execute()
        rows = len(result.data) if result.data else 0
        _log("delete", table, int((time.monotonic() - start) * 1000), {"rows_deleted": rows})
        return rows
    except Exception as e:
        _log_error("delete", table, e)
        raise
