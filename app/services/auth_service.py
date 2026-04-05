"""Authentication service."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone

from app.models.user import User
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token


async def register_user(
    db: AsyncSession, username: str, password: str,
    age: int | None = None, gender: int | None = None, country: str | None = None
) -> User:
    """Register a new user."""
    # Check if username exists
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        raise ValueError("Username already exists")

    user = User(
        username=username,
        password_hash=hash_password(password),
        age=age,
        gender=gender,
        country=country,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    """Authenticate user by username/password. Returns user or None."""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return None

    # Update last_login
    await db.execute(
        update(User).where(User.user_id == user.user_id).values(
            last_login=datetime.now(timezone.utc)
        )
    )
    return user


def generate_tokens(user: User) -> dict:
    """Generate access + refresh token pair for a user."""
    token_data = {"sub": str(user.user_id)}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
    }
