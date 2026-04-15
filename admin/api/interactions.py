"""Admin interactions — batch import."""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from common.database import get_db
from common.models.user import User
from admin.dependencies import get_admin_user

logger = logging.getLogger("admin")
router = APIRouter(prefix="/admin/interactions", tags=["Admin Interactions"])


class InteractionItem(BaseModel):
    user_id: int
    track_id: str
    interaction_type: int
    rating: Optional[float] = None
    play_duration: Optional[int] = None
    completion_rate: Optional[float] = None
    created_at: Optional[str] = None


class BatchInteractionRequest(BaseModel):
    interactions: list[InteractionItem]


@router.post("/batch")
async def batch_insert_interactions(
    req: BatchInteractionRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Batch insert interactions."""
    inserted = 0
    failed = 0

    for ia in req.interactions:
        try:
            await db.execute(text("""
                INSERT INTO user_interactions
                (user_id, track_id, interaction_type, rating, play_duration, completion_rate, created_at)
                VALUES (:user_id, :track_id, :interaction_type, :rating, :play_duration, :completion_rate, :created_at)
            """), {
                "user_id": ia.user_id,
                "track_id": ia.track_id,
                "interaction_type": ia.interaction_type,
                "rating": ia.rating,
                "play_duration": ia.play_duration,
                "completion_rate": ia.completion_rate,
                "created_at": ia.created_at or datetime.now(),
            })
            inserted += 1
        except Exception as e:
            logger.warning(f"Failed to insert interaction: {e}")
            failed += 1

    await db.commit()
    return {"inserted": inserted, "failed": failed, "total": len(req.interactions)}
