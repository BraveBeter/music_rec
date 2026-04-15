"""User endpoints."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.dependencies import get_current_user
from common.models.user import User
from common.models.user_favorite import UserFavorite
from common.models.interaction import UserInteraction
from app.schemas.user import UserProfile, UpdateProfileRequest

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserProfile)
async def get_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return current_user


@router.put("/me/profile", response_model=UserProfile)
async def update_profile(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user profile fields (age, gender, country)."""
    if req.age is not None:
        current_user.age = req.age
    if req.gender is not None:
        current_user.gender = req.gender
    if req.country is not None:
        current_user.country = req.country

    db.add(current_user)
    await db.flush()
    await db.refresh(current_user)
    return current_user


@router.get("/me/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user statistics: play count, favorites count, days since registration."""
    play_count_result = await db.execute(
        select(func.count()).where(
            UserInteraction.user_id == current_user.user_id,
            UserInteraction.interaction_type == 1,  # play
        )
    )
    play_count = play_count_result.scalar() or 0

    fav_count_result = await db.execute(
        select(func.count()).where(UserFavorite.user_id == current_user.user_id)
    )
    fav_count = fav_count_result.scalar() or 0

    created_at = current_user.created_at
    if created_at:
        # Ensure timezone-aware comparison
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - created_at).days
    else:
        days = 0

    return {
        "play_count": play_count,
        "favorites_count": fav_count,
        "days_registered": days,
    }


@router.get("/me/favorites/ids")
async def get_favorite_ids(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a list of track IDs that the current user has favorited."""
    result = await db.execute(
        select(UserFavorite.track_id).where(UserFavorite.user_id == current_user.user_id)
    )
    ids = [row[0] for row in result.all()]
    return {"track_ids": ids}
