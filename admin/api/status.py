"""Admin status — system overview."""
import os
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from common.database import get_db
from common.models.user import User
from admin.dependencies import get_admin_user

logger = logging.getLogger("admin")
router = APIRouter(prefix="/admin/status", tags=["Admin Status"])


@router.get("")
async def system_status(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Get system status: data counts and model availability."""
    # Data counts
    counts = {}
    for table in ["users", "tracks", "user_interactions", "track_features", "tags"]:
        result = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
        counts[table] = result.scalar()

    # Model availability
    from ml_pipeline.config import MODEL_DIR
    models = {}
    for model_name in ["item_cf", "svd", "deepfm", "sasrec"]:
        meta_path = os.path.join(MODEL_DIR, model_name, "meta.json")
        models[model_name] = os.path.exists(meta_path)

    return {
        "data": counts,
        "models": models,
    }
