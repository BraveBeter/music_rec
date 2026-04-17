"""Interaction endpoints - behavior event logging."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.dependencies import get_current_user
from common.models.user import User
from app.schemas.interaction import InteractionCreate, InteractionResponse, PlayHistoryResponse
from app.services.interaction_service import log_interaction, get_user_history, get_play_history

router = APIRouter(prefix="/interactions", tags=["Interactions"])


@router.post("", status_code=201)
async def create_interaction(
    req: InteractionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Log a user interaction event (play/like/skip/rate)."""
    interaction = await log_interaction(
        db=db,
        user_id=current_user.user_id,
        track_id=req.track_id,
        interaction_type=req.interaction_type,
        rating=req.rating,
        play_duration=req.play_duration,
    )
    return {
        "code": 201,
        "msg": "Interaction logged",
        "data": {"interaction_id": interaction.interaction_id},
    }


@router.get("/history", response_model=list[InteractionResponse])
async def interaction_history(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's recent interaction history."""
    interactions = await get_user_history(db, current_user.user_id, limit)
    results = []
    for i in interactions:
        results.append(InteractionResponse(
            interaction_id=i.interaction_id,
            track_id=i.track_id,
            interaction_type=i.interaction_type,
            rating=i.rating,
            play_duration=i.play_duration,
            completion_rate=i.completion_rate,
            created_at=str(i.created_at),
        ))
    return results


@router.get("/play-history", response_model=PlayHistoryResponse)
async def play_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get deduplicated play history with pagination (latest play per track)."""
    from app.schemas.interaction import PlayHistoryItem, PlayHistoryTrack
    items, total = await get_play_history(
        db, current_user.user_id, page=page, page_size=page_size,
    )
    return PlayHistoryResponse(
        items=[PlayHistoryItem(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
