"""Admin data generation — trigger LastFM or synthetic data generation."""
import asyncio
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_db
from common.models.user import User
from admin.dependencies import get_admin_user
from ml_pipeline.data_process.enrich_lastfm_media import enrich_lastfm_media

logger = logging.getLogger("admin")
router = APIRouter(prefix="/admin/data", tags=["Admin Data Generation"])

# Track running tasks
_running_tasks: dict[str, asyncio.subprocess.Process] = {}
_running_async_tasks: dict[str, asyncio.Task] = {}


@router.post("/generate-lastfm")
async def generate_lastfm(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Trigger LastFM 1K data generation."""
    if "generate_lastfm" in _running_tasks:
        return {"status": "already_running"}

    process = await asyncio.create_subprocess_exec(
        "python", "-m", "ml_pipeline.data_process.generate_lastfm_data", "--enrich-media",
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


@router.post("/enrich-lastfm-media")
async def enrich_lastfm(
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Backfill media URLs for existing LastFM-imported tracks."""
    del db, admin
    task_name = "enrich_lastfm_media"
    running_task = _running_async_tasks.get(task_name)
    if running_task and not running_task.done():
        return {"status": "already_running"}

    async def _run_enrichment():
        try:
            stats = await enrich_lastfm_media(
                track_prefix="LFM",
                only_missing=True,
                limit=limit,
                skip_attempted=True,
            )
            logger.info("[lastfm-media] completed: %s", stats)
        except Exception as exc:
            logger.exception("[lastfm-media] failed: %s", exc)
        finally:
            _running_async_tasks.pop(task_name, None)

    _running_async_tasks[task_name] = asyncio.create_task(_run_enrichment())
    return {"status": "started", "limit": limit}


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
