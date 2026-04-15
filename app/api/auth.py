"""Authentication endpoints: register, login, refresh, logout."""
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshResponse
from app.services.auth_service import register_user, authenticate_user, generate_tokens
from common.core.security import decode_token
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    try:
        user = await register_user(
            db, req.username, req.password,
            age=req.age, gender=req.gender, country=req.country,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    tokens = generate_tokens(user)

    # Set refresh token in HTTP-Only cookie
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=False,  # Set True in production with HTTPS
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )

    return TokenResponse(
        access_token=tokens["access_token"],
        user_id=user.user_id,
        username=user.username,
        role=user.role,
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Login with username and password."""
    user = await authenticate_user(db, req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    tokens = generate_tokens(user)

    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )

    return TokenResponse(
        access_token=tokens["access_token"],
        user_id=user.user_id,
        username=user.username,
        role=user.role,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(request: Request, response: Response):
    """Refresh access token using the HTTP-Only refresh cookie."""
    refresh = request.cookies.get("refresh_token")
    if not refresh:
        raise HTTPException(status_code=401, detail="No refresh token")

    payload = decode_token(refresh)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    from common.core.security import create_access_token
    new_access = create_access_token({"sub": payload["sub"]})

    return RefreshResponse(access_token=new_access)


@router.post("/logout")
async def logout(response: Response):
    """Logout by clearing the refresh token cookie."""
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")
    return {"code": 200, "msg": "Logged out"}
