import threading

from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

_client: Client | None = None
_lock = threading.Lock()


def get_db() -> Client:
    """Return a Supabase admin client (thread-safe lazy singleton)."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client
