"""Favorites endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.user_favorite import UserFavorite
from app.models.track import Track
from app.schemas.track import TrackResponse

router = APIRouter(prefix="/favorites", tags=["Favorites"])


@router.get("", response_model=list[TrackResponse])
async def list_favorites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's favorite tracks."""
    result = await db.execute(
        select(Track)
        .join(UserFavorite, Track.track_id == UserFavorite.track_id)
        .where(UserFavorite.user_id == current_user.user_id)
        .order_by(UserFavorite.created_at.desc())
    )
    tracks = result.scalars().all()
    return [TrackResponse.model_validate(t) for t in tracks]


@router.post("/{track_id}", status_code=201)
async def add_favorite(
    track_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a track to favorites."""
    # Check if track exists
    track = await db.execute(select(Track).where(Track.track_id == track_id))
    if not track.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Track not found")

    # Check if already favorited
    existing = await db.execute(
        select(UserFavorite).where(
            UserFavorite.user_id == current_user.user_id,
            UserFavorite.track_id == track_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"code": 200, "msg": "Already in favorites"}

    fav = UserFavorite(user_id=current_user.user_id, track_id=track_id)
    db.add(fav)
    return {"code": 201, "msg": "Added to favorites"}


@router.delete("/{track_id}")
async def remove_favorite(
    track_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a track from favorites."""
    await db.execute(
        delete(UserFavorite).where(
            UserFavorite.user_id == current_user.user_id,
            UserFavorite.track_id == track_id,
        )
    )
    return {"code": 200, "msg": "Removed from favorites"}
