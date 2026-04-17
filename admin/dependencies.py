"""Admin auth dependency."""
from fastapi import Depends, HTTPException, Query, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from common.database import get_db
from common.core.security import decode_token
from common.models.user import User

security_scheme = HTTPBearer(auto_error=False)


async def get_admin_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    token: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract user from token and verify admin role."""
    jwt = None
    if credentials:
        jwt = credentials.credentials
    if not jwt:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            jwt = auth_header[7:]
    if not jwt and token:
        jwt = token
    if not jwt:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(jwt)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.user_id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    return user
