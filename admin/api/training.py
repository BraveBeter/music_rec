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
    """Run full training pipeline sequentially: each step waits for the previous to complete."""
    import asyncio

    pipeline = ["preprocess", "feature_engineering", "train_baseline", "train_sasrec", "train_deepfm"]

    # Start first task immediately so frontend gets a task_id to subscribe to
    first_result = await training_service.start_training(pipeline[0], MODULE_MAP[pipeline[0]])
    first_tid = first_result.get("task_id", "")

    # Run the rest of the pipeline sequentially in background
    async def _run_pipeline():
        # Wait for first task
        prev_tid = first_tid
        for name in pipeline[1:]:
            # Wait for previous task to finish
            while True:
                progress = training_service.get_progress(prev_tid)
                if progress and progress.get("status") in ("completed", "error", "interrupted", "cancelled"):
                    break
                await asyncio.sleep(2)

            # Check if previous step succeeded
            prev_progress = training_service.get_progress(prev_tid)
            if prev_progress and prev_progress.get("status") != "completed":
                logger.warning(f"Pipeline stopped: step before '{name}' ended with status {prev_progress.get('status')}")
                break

            # Start next step
            result = await training_service.start_training(name, MODULE_MAP[name])
            prev_tid = result.get("task_id", "")

    asyncio.create_task(_run_pipeline())
    return {"status": "started", "tasks": [first_result]}


@router.post("/evaluate")
async def run_evaluation(
    model: str = Query(None, description="Model to evaluate: item_cf, deepfm, sasrec, or None for all"),
    version_id: str = Query(None, description="Specific version ID to evaluate"),
    admin: User = Depends(get_admin_user),
):
    """Evaluate trained models on test data. Optionally filter by model and version."""
    from ml_pipeline.models.versioning import ModelRegistry

    cmd_extra = []
    if model:
        cmd_extra.extend(["--model", model])
    if version_id and model:
        registry = ModelRegistry()
        version_dir = registry.get_version_dir(model, version_id)
        if version_dir:
            cmd_extra.extend(["--version-dir", version_dir])

    if not cmd_extra:
        return await training_service.start_training("evaluate", MODULE_MAP["evaluate"])

    # Build custom command with extra args
    from datetime import datetime as _dt
    from ml_pipeline.training.progress import ProgressTracker

    active = ProgressTracker.list_active()
    for a in active:
        if a.get("task_type") == "evaluate" and a.get("status") == "running":
            return {"status": "already_running", "task_id": a["task_id"], "name": "evaluate"}

    tid = f"evaluate_{_dt.now().strftime('%Y%m%d_%H%M%S')}"
    cmd = ["python", "-m", MODULE_MAP["evaluate"], "--task-id", tid] + cmd_extra

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def _log_output():
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            logger.info(f"[evaluate:{tid}] {line.decode().rstrip()}")
        await process.wait()

    asyncio.create_task(_log_output())
    return {"status": "started", "task_id": tid, "pid": process.pid}


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


# ---- Evaluation-specific endpoints ----

@router.get("/eval-progress")
async def list_eval_progress(admin: User = Depends(get_admin_user)):
    """List all evaluation progress records."""
    return {"progress": training_service.list_eval_progress()}


@router.get("/eval-history")
async def eval_history(limit: int = Query(50, ge=1, le=200), admin: User = Depends(get_admin_user)):
    """Get completed evaluation history."""
    return {"history": training_service.list_eval_history(limit)}


@router.get("/eval-report/{task_id}")
async def get_eval_report(task_id: str, admin: User = Depends(get_admin_user)):
    """Get evaluation results for a specific task."""
    return training_service.get_eval_report(task_id)


# ---- Model versioning endpoints ----

@router.get("/model-versions")
async def get_model_versions(admin: User = Depends(get_admin_user)):
    """Get all model version info from registry."""
    return training_service.get_model_versions()


@router.post("/model-versions/{model_name}/{version_id}/promote")
async def promote_model_version(model_name: str, version_id: str,
                                admin: User = Depends(get_admin_user)):
    """Manually promote a specific model version to production."""
    return training_service.promote_model_version(model_name, version_id)
