"""Interaction service - behavior logging with Redis sliding window."""
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.interaction import UserInteraction
from app.models.track import Track
from app.utils import get_redis

logger = logging.getLogger("music_rec")

# Redis key patterns
USER_SEQ_KEY = "user:seq:{user_id}"  # Sliding window of recent plays for SASRec
MAX_SEQ_LENGTH = 50


async def log_interaction(
    db: AsyncSession,
    user_id: int,
    track_id: str,
    interaction_type: int,
    rating: float | None = None,
    play_duration: int | None = None,
) -> UserInteraction:
    """Log a user interaction event and update Redis session."""
    # Compute completion_rate
    completion_rate = None
    if play_duration is not None and interaction_type == 1:  # play
        result = await db.execute(
            select(Track.duration_ms).where(Track.track_id == track_id)
        )
        duration_ms = result.scalar_one_or_none()
        if duration_ms and duration_ms > 0:
            completion_rate = min(play_duration / duration_ms, 1.0)

    # Persist to MySQL
    interaction = UserInteraction(
        user_id=user_id,
        track_id=track_id,
        interaction_type=interaction_type,
        rating=rating,
        play_duration=play_duration,
        completion_rate=completion_rate,
    )
    db.add(interaction)
    await db.flush()

    # Update play_count on track if it's a play event
    if interaction_type == 1:
        from sqlalchemy import update
        await db.execute(
            update(Track).where(Track.track_id == track_id).values(
                play_count=Track.play_count + 1
            )
        )

    # Update Redis sliding window for SASRec
    try:
        redis = await get_redis()
        key = USER_SEQ_KEY.format(user_id=user_id)
        if interaction_type in (1, 2):  # play or like
            await redis.lpush(key, track_id)
            await redis.ltrim(key, 0, MAX_SEQ_LENGTH - 1)
            await redis.expire(key, 86400 * 7)  # 7 days TTL
    except Exception as e:
        logger.warning(f"Redis update failed for user {user_id}: {e}")

    await db.refresh(interaction)
    return interaction


async def get_user_history(
    db: AsyncSession, user_id: int, limit: int = 50
) -> list[UserInteraction]:
    """Get recent interactions for a user."""
    result = await db.execute(
        select(UserInteraction)
        .where(UserInteraction.user_id == user_id)
        .order_by(UserInteraction.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_user_sequence_from_redis(user_id: int) -> list[str]:
    """Get user's recent play sequence from Redis for SASRec."""
    try:
        redis = await get_redis()
        key = USER_SEQ_KEY.format(user_id=user_id)
        return await redis.lrange(key, 0, MAX_SEQ_LENGTH - 1)
    except Exception:
        return []
