"""Admin training — trigger preprocessing, model training, and progress tracking."""
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_db
from common.models.user import User
from admin.dependencies import get_admin_user
from admin.services import training_service

logger = logging.getLogger("admin")
router = APIRouter(prefix="/admin/training", tags=["Admin Training"])

# Module mapping: task name -> Python module path
MODULE_MAP = {
    "preprocess": "ml_pipeline.data_process.preprocess",
    "feature_engineering": "ml_pipeline.data_process.feature_engineering",
    "train_baseline": "ml_pipeline.training.train_baseline",
    "train_sasrec": "ml_pipeline.training.train_sasrec",
    "train_deepfm": "ml_pipeline.training.train_deepfm",
    "evaluate": "ml_pipeline.evaluation.evaluate_trained",
}


@router.post("/preprocess")
async def run_preprocess(admin: User = Depends(get_admin_user)):
    """Trigger data preprocessing pipeline."""
    return await training_service.start_training("preprocess", MODULE_MAP["preprocess"])


@router.post("/feature-engineering")
async def run_feature_engineering(admin: User = Depends(get_admin_user)):
    """Trigger feature engineering pipeline."""
    return await training_service.start_training("feature_engineering", MODULE_MAP["feature_engineering"])


@router.post("/train-baseline")
async def train_baseline(admin: User = Depends(get_admin_user)):
    """Train ItemCF baseline model."""
    return await training_service.start_training("train_baseline", MODULE_MAP["train_baseline"])


@router.post("/train-sasrec")
async def train_sasrec(admin: User = Depends(get_admin_user)):
    """Train SASRec sequential model."""
    return await training_service.start_training("train_sasrec", MODULE_MAP["train_sasrec"])


@router.post("/train-deepfm")
async def train_deepfm(admin: User = Depends(get_admin_user)):
    """Train DeepFM ranking model."""
    return await training_service.start_training("train_deepfm", MODULE_MAP["train_deepfm"])


@router.post("/train-all")
async def train_all(admin: User = Depends(get_admin_user)):
    """Run full training pipeline: preprocess + all models."""
    results = []
    # Sequential: preprocess first, then models
    for name in ["preprocess", "train_baseline", "train_sasrec", "train_deepfm"]:
        result = await training_service.start_training(name, MODULE_MAP[name])
        results.append(result)
    return {"status": "started", "tasks": results}


@router.post("/evaluate")
async def run_evaluation(admin: User = Depends(get_admin_user)):
    """Evaluate all trained models on test data."""
    return await training_service.start_training("evaluate", MODULE_MAP["evaluate"])


@router.get("/progress")
async def list_training_progress(admin: User = Depends(get_admin_user)):
    """List all training progress records."""
    return {"progress": training_service.list_progress()}


@router.get("/progress/{task_id}")
async def get_training_progress(task_id: str, admin: User = Depends(get_admin_user)):
    """Get progress for a specific training task."""
    progress = training_service.get_progress(task_id)
    if not progress:
        return {"error": "not_found", "task_id": task_id}
    return progress


@router.get("/progress/{task_id}/stream")
async def training_progress_stream(task_id: str, admin: User = Depends(get_admin_user)):
    """SSE endpoint for real-time training progress updates."""
    async def event_generator():
        # Wait for progress file to appear (subprocess may still be starting)
        for _ in range(30):
            progress = training_service.get_progress(task_id)
            if progress:
                break
            await asyncio.sleep(1)
        else:
            yield f"data: {json.dumps({'status': 'not_found', 'task_id': task_id})}\n\n"
            return

        while True:
            progress = training_service.get_progress(task_id)
            if not progress:
                break
            yield f"data: {json.dumps(progress, default=str)}\n\n"
            if progress.get("status") in ("completed", "error", "interrupted", "cancelled"):
                break
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/history")
async def training_history(limit: int = Query(50, ge=1, le=200), admin: User = Depends(get_admin_user)):
    """Get completed training history."""
    return {"history": training_service.list_history(limit)}


@router.post("/cancel/{task_id}")
async def cancel_training(task_id: str, admin: User = Depends(get_admin_user)):
    """Cancel a running training task."""
    return await training_service.cancel_training(task_id)
