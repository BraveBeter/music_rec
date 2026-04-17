"""Interaction service - behavior logging with Redis sliding window."""
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from common.models.interaction import UserInteraction
from common.models.track import Track
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


async def get_play_history(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """
    Get deduplicated play history with pagination.

    For each track, only the most recent play is kept.
    Returns (items_with_track_info, total_count).
    """
    from sqlalchemy import func, text

    # Use a subquery to get the latest interaction per track
    # Then join with tracks to get track details
    offset = (page - 1) * page_size

    # Count total unique tracks played
    count_result = await db.execute(
        select(func.count()).select_from(
            select(func.distinct(UserInteraction.track_id))
            .where(
                UserInteraction.user_id == user_id,
                UserInteraction.interaction_type == 1,
            )
            .subquery()
        )
    )
    total = count_result.scalar() or 0

    # Get latest interaction per track, paginated
    # Use ROW_NUMBER to pick latest per track
    query = text("""
        SELECT i.interaction_id, i.user_id, i.track_id, i.interaction_type,
               i.rating, i.play_duration, i.completion_rate, i.created_at,
               t.title, t.artist_name, t.album_name,
               t.duration_ms, t.preview_url, t.cover_url, t.play_count
        FROM (
            SELECT ui.*,
                   ROW_NUMBER() OVER (PARTITION BY ui.track_id ORDER BY ui.created_at DESC) AS rn
            FROM user_interactions ui
            WHERE ui.user_id = :uid AND ui.interaction_type = 1
        ) i
        JOIN tracks t ON t.track_id = i.track_id
        WHERE i.rn = 1 AND t.status = 1
        ORDER BY i.created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(
        query,
        {"uid": user_id, "limit": page_size, "offset": offset},
    )
    rows = result.fetchall()

    # Get column names from result for safe access
    col_names = result.keys()

    items = []
    for row in rows:
        row_map = dict(zip(col_names, row))
        items.append({
            "interaction_id": row_map["interaction_id"],
            "track_id": row_map["track_id"],
            "interaction_type": row_map["interaction_type"],
            "play_duration": row_map["play_duration"],
            "completion_rate": row_map["completion_rate"],
            "created_at": str(row_map["created_at"]),
            "track": {
                "track_id": row_map["track_id"],
                "title": row_map["title"],
                "artist_name": row_map["artist_name"],
                "album_name": row_map["album_name"],
                "duration_ms": row_map["duration_ms"],
                "preview_url": row_map["preview_url"],
                "cover_url": row_map["cover_url"],
                "play_count": row_map["play_count"] or 0,
            },
        })

    return items, total


async def get_user_sequence_from_redis(user_id: int) -> list[str]:
    """Get user's recent play sequence from Redis for SASRec."""
    try:
        redis = await get_redis()
        key = USER_SEQ_KEY.format(user_id=user_id)
        return await redis.lrange(key, 0, MAX_SEQ_LENGTH - 1)
    except Exception:
        return []
