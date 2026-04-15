"""Recommendation service - orchestrates recall + ranking pipeline."""
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from common.models.track import Track
from common.models.offline_recommendation import OfflineRecommendation
from app.services.track_service import get_popular_tracks
from app.utils import get_redis

logger = logging.getLogger("music_rec")

CACHE_KEY = "rec:user:{user_id}"
CACHE_TTL = 1800  # 30 minutes

# User sequence key in Redis (from interaction_service)
USER_SEQ_KEY = "user:seq:{user_id}"


async def get_recommendations(
    db: AsyncSession,
    user_id: int | None,
    size: int = 20,
    scene: str = "home_feed",
    current_track_id: str | None = None,
) -> dict:
    """
    Get personalized recommendations.
    Strategy:
      1. Redis cache → return cached
      2. ML pipeline (recall + ranking) → return personalized
      3. Offline precomputed → fallback
      4. Popularity cold-start → final fallback
    """
    # 1. Try Redis cache
    if user_id:
        try:
            redis = await get_redis()
            cached = await redis.get(CACHE_KEY.format(user_id=user_id))
            if cached:
                data = json.loads(cached)
                return {
                    "strategy_matched": data.get("strategy", "cached"),
                    "is_fallback": False,
                    "items": data["items"][:size],
                }
        except Exception as e:
            logger.warning(f"Redis cache read failed: {e}")

    # 2. Try ML pipeline (recall + ranking)
    if user_id:
        ml_result = await _ml_pipeline_recommend(db, user_id, size)
        if ml_result and ml_result.get("items"):
            # Cache the result
            await cache_recommendations(user_id, ml_result["strategy"], ml_result["items"])
            return {
                "strategy_matched": ml_result["strategy"],
                "is_fallback": ml_result.get("is_fallback", False),
                "items": ml_result["items"][:size],
            }

    # 3. Try offline recommendations from MySQL (fallback)
    if user_id:
        result = await db.execute(
            select(OfflineRecommendation).where(
                OfflineRecommendation.user_id == user_id
            )
        )
        offline_rec = result.scalar_one_or_none()
        if offline_rec and offline_rec.recommended_track_ids:
            track_ids = offline_rec.recommended_track_ids[:size]
            tracks = await _fetch_tracks_by_ids(db, track_ids)
            if tracks:
                return {
                    "strategy_matched": "offline_precomputed",
                    "is_fallback": True,
                    "items": [_track_to_dict(t) for t in tracks],
                }

    # 4. Fallback: popular tracks (cold-start)
    popular = await get_popular_tracks(db, limit=size)
    return {
        "strategy_matched": "popularity_cold_start",
        "is_fallback": True,
        "items": [_track_to_dict(t) for t in popular],
    }


async def _ml_pipeline_recommend(db: AsyncSession, user_id: int, size: int) -> dict | None:
    """
    Run the ML recommendation pipeline (recall → ranking).
    Returns None if models are not available.
    """
    try:
        from ml_pipeline.inference.pipeline import recommend as ml_recommend

        # Get user sequence from Redis
        user_sequence = await _get_user_sequence(user_id)

        # Get popular tracks for fallback recall
        popular = await get_popular_tracks(db, limit=50)
        popular_dicts = [_track_to_dict(t) for t in popular]

        # Run ML pipeline
        result = ml_recommend(
            user_id=user_id,
            user_sequence=user_sequence,
            popular_tracks=popular_dicts,
            top_k=size,
        )

        if not result or not result.get("items"):
            return None

        # Enrich items with full track data from DB
        track_ids = [item["track_id"] for item in result["items"]]
        scores = {item["track_id"]: item.get("score") for item in result["items"]}

        tracks = await _fetch_tracks_by_ids(db, track_ids)
        items = []
        for track in tracks:
            d = _track_to_dict(track)
            d["score"] = scores.get(track.track_id)
            items.append(d)

        return {
            "strategy": result["strategy"],
            "is_fallback": result.get("is_fallback", False),
            "items": items,
        }

    except ImportError:
        logger.debug("ML pipeline not available (missing dependencies)")
        return None
    except Exception as e:
        logger.warning(f"ML pipeline recommendation failed: {e}")
        return None


async def _get_user_sequence(user_id: int) -> list[str]:
    """Get user's recent play sequence from Redis."""
    try:
        redis = await get_redis()
        key = USER_SEQ_KEY.format(user_id=user_id)
        seq = await redis.lrange(key, 0, 49)
        # Redis returns bytes, decode to str
        return [s.decode("utf-8") if isinstance(s, bytes) else s for s in seq]
    except Exception:
        return []


async def cache_recommendations(user_id: int, strategy: str, items: list[dict]):
    """Cache recommendation results in Redis."""
    try:
        redis = await get_redis()
        data = json.dumps({"strategy": strategy, "items": items}, ensure_ascii=False)
        await redis.setex(CACHE_KEY.format(user_id=user_id), CACHE_TTL, data)
    except Exception as e:
        logger.warning(f"Redis cache write failed: {e}")


async def _fetch_tracks_by_ids(db: AsyncSession, track_ids: list[str]) -> list[Track]:
    """Fetch tracks by a list of IDs, preserving order."""
    if not track_ids:
        return []
    result = await db.execute(
        select(Track).where(Track.track_id.in_(track_ids), Track.status == 1)
    )
    tracks = result.scalars().all()
    # Preserve original order
    track_map = {t.track_id: t for t in tracks}
    return [track_map[tid] for tid in track_ids if tid in track_map]


def _track_to_dict(track: Track) -> dict:
    """Convert Track ORM to response dict."""
    return {
        "track_id": track.track_id,
        "title": track.title,
        "artist_name": track.artist_name,
        "album_name": track.album_name,
        "duration_ms": track.duration_ms,
        "preview_url": track.preview_url,
        "cover_url": track.cover_url,
        "score": None,
    }
