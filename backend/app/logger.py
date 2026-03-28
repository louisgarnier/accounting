import logging
import os
import sys
import threading
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Internal: Supabase write (fire-and-forget, never blocks, never raises)
# ---------------------------------------------------------------------------

def _get_db_for_logging():
    """Lazy import to avoid circular dependency at module load time."""
    from app.database import get_db
    return get_db()


def log_to_supabase(entry: dict) -> None:
    """Write a log entry to Supabase in a background thread. Never raises."""
    def _write():
        try:
            _get_db_for_logging().table("logs").insert(entry).execute()
        except Exception:
            pass  # logging must never break the app

    threading.Thread(target=_write, daemon=True).start()


# ---------------------------------------------------------------------------
# Python loggers: stdout + optional local file
# ---------------------------------------------------------------------------

def _build_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    logger.addHandler(stdout_handler)

    log_dir = os.getenv("LOG_DIR")
    if log_dir:
        path = Path(log_dir) / f"{filename}_{date.today().isoformat()}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


backend_logger  = _build_logger("backend",  "backend")
api_logger      = _build_logger("api",       "api")
db_logger       = _build_logger("database",  "database")
frontend_logger = _build_logger("frontend",  "frontend")
