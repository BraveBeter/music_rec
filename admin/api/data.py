"""Admin data generation — trigger LastFM or synthetic data generation."""
import asyncio
import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_db
from common.models.user import User
from admin.dependencies import get_admin_user

logger = logging.getLogger("admin")
router = APIRouter(prefix="/admin/data", tags=["Admin Data Generation"])

# Track running tasks
_running_tasks: dict[str, asyncio.subprocess.Process] = {}


@router.post("/generate-lastfm")
async def generate_lastfm(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Trigger LastFM 1K data generation."""
    if "generate_lastfm" in _running_tasks:
        return {"status": "already_running"}

    process = await asyncio.create_subprocess_exec(
        "python", "-m", "ml_pipeline.data_process.generate_lastfm_data",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    _running_tasks["generate_lastfm"] = process

    async def _log_output():
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            logger.info(f"[lastfm] {line.decode().rstrip()}")
        await process.wait()
        _running_tasks.pop("generate_lastfm", None)

    asyncio.create_task(_log_output())
    return {"status": "started", "pid": process.pid}


@router.post("/generate-synthetic")
async def generate_synthetic(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Trigger synthetic data generation."""
    if "generate_synthetic" in _running_tasks:
        return {"status": "already_running"}

    process = await asyncio.create_subprocess_exec(
        "python", "-m", "ml_pipeline.data_process.generate_synthetic_data",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    _running_tasks["generate_synthetic"] = process

    async def _log_output():
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            logger.info(f"[synthetic] {line.decode().rstrip()}")
        await process.wait()
        _running_tasks.pop("generate_synthetic", None)

    asyncio.create_task(_log_output())
    return {"status": "started", "pid": process.pid}
