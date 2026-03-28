from fastapi import APIRouter, Depends
from app.auth import get_current_user

router = APIRouter(prefix="/api")


@router.get("/protected-test")
def protected_test(user=Depends(get_current_user)):
    return {"user_id": user.id}
