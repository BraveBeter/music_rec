"""Admin training — trigger preprocessing and model training."""
import asyncio
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_db
from common.models.user import User
from admin.dependencies import get_admin_user

logger = logging.getLogger("admin")
router = APIRouter(prefix="/admin/training", tags=["Admin Training"])

_running: dict[str, asyncio.subprocess.Process] = {}


async def _run_pipeline(name: str, module: str) -> dict:
    if name in _running:
        return {"status": "already_running", "name": name}

    process = await asyncio.create_subprocess_exec(
        "python", "-m", module,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    _running[name] = process

    async def _log_output():
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            logger.info(f"[{name}] {line.decode().rstrip()}")
        await process.wait()
        _running.pop(name, None)
        logger.info(f"Training task '{name}' completed")

    asyncio.create_task(_log_output())
    return {"status": "started", "name": name, "pid": process.pid}


@router.post("/preprocess")
async def run_preprocess(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Trigger data preprocessing pipeline."""
    return await _run_pipeline("preprocess", "ml_pipeline.data_process.preprocess")


@router.post("/train-baseline")
async def train_baseline(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Train ItemCF baseline model."""
    return await _run_pipeline("train_baseline", "ml_pipeline.training.train_baseline")


@router.post("/train-sasrec")
async def train_sasrec(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Train SASRec sequential model."""
    return await _run_pipeline("train_sasrec", "ml_pipeline.training.train_sasrec")


@router.post("/train-deepfm")
async def train_deepfm(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Train DeepFM ranking model."""
    return await _run_pipeline("train_deepfm", "ml_pipeline.training.train_deepfm")
