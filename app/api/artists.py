"""Artist endpoints - search, favorites, and track listing."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.dependencies import get_current_user
from common.models.user import User
from app.schemas.track import TrackResponse, TrackListResponse
from app.services.artist_service import (
    search_artists,
    get_artist_tracks,
    get_favorite_artists,
    get_favorite_artist_ids,
    add_artist_favorite,
    remove_artist_favorite,
)

router = APIRouter(prefix="/artists", tags=["Artists"])


@router.get("/search")
async def artist_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search artists by name."""
    results = await search_artists(db, query=q, limit=limit)
    return {"items": results, "total": len(results)}


@router.get("/{artist_name}/tracks", response_model=TrackListResponse)
async def artist_tracks(
    artist_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get all tracks by an artist."""
    tracks, total = await get_artist_tracks(db, artist_name, page=page, page_size=page_size)
    return TrackListResponse(
        items=[TrackResponse.model_validate(t) for t in tracks],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/favorites")
async def list_artist_favorites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's favorited artists."""
    artists = await get_favorite_artists(db, current_user.user_id)
    return {"items": artists, "total": len(artists)}


@router.get("/me/favorites/ids")
async def list_artist_favorite_ids(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of favorited artist names (lightweight)."""
    names = await get_favorite_artist_ids(db, current_user.user_id)
    return {"artist_names": names}


@router.post("/favorites/{artist_name}", status_code=201)
async def add_artist_to_favorites(
    artist_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add an artist to favorites."""
    try:
        await add_artist_favorite(db, current_user.user_id, artist_name)
        return {"code": 201, "msg": "Artist favorited"}
    except Exception:
        # Likely duplicate - ignore
        return {"code": 200, "msg": "Already favorited"}


@router.delete("/favorites/{artist_name}")
async def remove_artist_from_favorites(
    artist_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an artist from favorites."""
    removed = await remove_artist_favorite(db, current_user.user_id, artist_name)
    if not removed:
        raise HTTPException(status_code=404, detail="Artist not in favorites")
    return {"code": 200, "msg": "Artist unfavorited"}
