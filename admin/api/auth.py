"""Admin auth — login endpoint."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from common.database import get_db
from common.core.security import verify_password, create_access_token
from common.models.user import User
from sqlalchemy import select

router = APIRouter(prefix="/admin/auth", tags=["Admin Auth"])


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminTokenResponse(BaseModel):
    access_token: str
    user_id: int
    username: str


@router.post("/login", response_model=AdminTokenResponse)
async def admin_login(req: AdminLoginRequest, db: AsyncSession = Depends(get_db)):
    """Admin login — only users with role='admin' can authenticate."""
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    token = create_access_token({"sub": str(user.user_id)})
    return AdminTokenResponse(
        access_token=token,
        user_id=user.user_id,
        username=user.username,
    )
