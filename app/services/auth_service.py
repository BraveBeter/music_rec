"""Authentication service."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone

from app.models.user import User
from app.models.interaction import UserInteraction
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token


USER_SEQ_KEY = "user:seq:{user_id}"
MAX_SEQ_LENGTH = 50


async def warm_user_sequence(db: AsyncSession, user_id: int):
    """Load user's historical play/like interactions from MySQL into Redis on login."""
    from app.utils import get_redis

    try:
        redis = await get_redis()
        key = USER_SEQ_KEY.format(user_id=user_id)

        # Skip if sequence already warm
        existing_len = await redis.llen(key)
        if existing_len >= 3:
            return

        # Load recent play/like interactions
        result = await db.execute(
            select(UserInteraction.track_id)
            .where(
                UserInteraction.user_id == user_id,
                UserInteraction.interaction_type.in_([1, 2])
            )
            .order_by(UserInteraction.created_at.desc())
            .limit(MAX_SEQ_LENGTH)
        )
        track_ids = [row[0] for row in result.fetchall()]

        if not track_ids:
            return

        # Push to Redis (most recent first via LPUSH)
        await redis.delete(key)
        for track_id in track_ids:
            await redis.lpush(key, track_id)
        await redis.ltrim(key, 0, MAX_SEQ_LENGTH - 1)
        await redis.expire(key, 86400 * 7)
    except Exception:
        pass  # Non-critical; recommendation fallback handles this


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

    # Warm user sequence in Redis for SASRec
    await warm_user_sequence(db, user.user_id)

    return user


def generate_tokens(user: User) -> dict:
    """Generate access + refresh token pair for a user."""
    token_data = {"sub": str(user.user_id)}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
    }
