from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

security = HTTPBearer()

supabase_admin: Client = None  # type: ignore[assignment]


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    global supabase_admin
    token = credentials.credentials
    try:
        if supabase_admin is None:
            supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        response = supabase_admin.auth.get_user(token)
        return response.user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
