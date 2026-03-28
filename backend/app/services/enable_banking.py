import time
import httpx
import jwt as pyjwt
from datetime import datetime, timezone, timedelta
from app.config import ENABLE_BANKING_APP_ID, ENABLE_BANKING_PRIVATE_KEY
from app.logger import backend_logger

ENABLE_BANKING_BASE_URL = "https://api.enablebanking.com"


def _make_jwt() -> str:
    now = int(time.time())
    # Railway stores the key with literal \n — normalise to real newlines
    private_key = ENABLE_BANKING_PRIVATE_KEY.replace("\\n", "\n")
    return pyjwt.encode(
        {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": ENABLE_BANKING_APP_ID},
    )


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_make_jwt()}"}


def start_auth(bank_name: str, bank_country: str, redirect_url: str, state: str) -> str:
    """Start bank authorization. Returns URL to redirect the user to."""
    valid_until = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    resp = httpx.post(
        f"{ENABLE_BANKING_BASE_URL}/auth",
        json={
            "access": {
                "valid_until": valid_until,
            },
            "aspsp": {"name": bank_name, "country": bank_country},
            "state": state,
            "redirect_url": redirect_url,
            "psu_type": "personal",
        },
        headers=_auth_headers(),
        timeout=10.0,
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        backend_logger.error(f"❌ [EnableBanking] start_auth {e.response.status_code}: {e.response.text}")
        raise RuntimeError(f"Enable Banking {e.response.status_code}: {e.response.text}") from e
    return resp.json()["url"]


def create_session(code: str) -> list[dict]:
    """Exchange authorization code for session. Returns list of account dicts."""
    resp = httpx.post(
        f"{ENABLE_BANKING_BASE_URL}/sessions",
        json={"code": code},
        headers=_auth_headers(),
        timeout=10.0,
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        backend_logger.error(f"❌ [EnableBanking] create_session {e.response.status_code}: {e.response.text}")
        raise RuntimeError(f"Enable Banking {e.response.status_code}: {e.response.text}") from e
    data = resp.json()
    institution_name = data.get("aspsp", {}).get("name", "Unknown")
    session_id = data["session_id"]
    accounts = []
    for acc in data.get("accounts", []):
        iban = acc.get("account_id", {}).get("iban") or ""
        accounts.append({
            "session_id": session_id,
            "account_uid": acc["uid"],
            "account_iban": iban,
            "account_name": acc.get("name", ""),
            "institution_name": institution_name,
        })
    return accounts


def fetch_transactions(account_uid: str, date_from: str) -> list[dict]:
    """Fetch all transactions for an account, handling pagination."""
    transactions = []
    params: dict = {"date_from": date_from}
    while True:
        resp = httpx.get(
            f"{ENABLE_BANKING_BASE_URL}/accounts/{account_uid}/transactions",
            params=params,
            headers=_auth_headers(),
            timeout=15.0,
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            backend_logger.error(f"❌ [EnableBanking] fetch_transactions {e.response.status_code}: {e.response.text}")
            raise RuntimeError(f"Enable Banking {e.response.status_code}: {e.response.text}") from e
        data = resp.json()
        transactions.extend(data.get("transactions", []))
        continuation_key = data.get("continuation_key")
        if not continuation_key:
            break
        params["continuation_key"] = continuation_key
    return transactions
