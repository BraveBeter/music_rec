"""Recommendation endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.dependencies import get_current_user_optional, get_current_user
from common.models.user import User
from app.schemas.recommendation import RecommendationResponse, GroupedSimilarResponse
from app.services.recommendation_service import get_recommendations, get_similar_recommendations

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/feed", response_model=RecommendationResponse)
async def get_feed(
    size: int = Query(20, ge=1, le=100),
    scene: str = Query("home_feed"),
    current_track_id: str | None = Query(None),
    current_user: User | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get personalized recommendation feed.
    Supports authenticated and anonymous users.
    Cold-start falls back to popularity ranking.
    """
    user_id = current_user.user_id if current_user else None
    result = await get_recommendations(
        db=db,
        user_id=user_id,
        size=size,
        scene=scene,
        current_track_id=current_track_id,
    )
    return RecommendationResponse(**result)


@router.get("/similar", response_model=GroupedSimilarResponse)
async def get_similar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get recommendations based on user's top-played tracks using ItemCF.
    Returns groups of similar tracks per source track.
    """
    result = await get_similar_recommendations(db=db, user_id=current_user.user_id)
    return GroupedSimilarResponse(**result)
