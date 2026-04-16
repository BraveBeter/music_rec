"""Admin scheduler API — manage training schedules and thresholds."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from common.models.user import User
from admin.dependencies import get_admin_user

logger = logging.getLogger("admin")
router = APIRouter(prefix="/admin/scheduler", tags=["Admin Scheduler"])


# ---- Schemas ----

class ScheduleCreate(BaseModel):
    name: str
    task_type: str  # preprocess|train_baseline|train_sasrec|train_deepfm|train_all
    schedule_type: str = "cron"  # cron|interval|threshold
    cron_expr: Optional[str] = None
    interval_minutes: Optional[int] = None
    threshold_interactions: Optional[int] = None
    is_enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    task_type: Optional[str] = None
    schedule_type: Optional[str] = None
    cron_expr: Optional[str] = None
    interval_minutes: Optional[int] = None
    threshold_interactions: Optional[int] = None
    is_enabled: Optional[bool] = None


class ThresholdUpdate(BaseModel):
    last_training_count: int


# ---- Endpoints ----

def _get_service():
    """Get the scheduler service from app state."""
    from admin.main import app
    return app.state.scheduler


@router.get("/schedules")
async def list_schedules(admin: User = Depends(get_admin_user)):
    service = _get_service()
    return {"schedules": await service.get_schedules()}


@router.post("/schedules")
async def create_schedule(data: ScheduleCreate, admin: User = Depends(get_admin_user)):
    valid_task_types = ["preprocess", "train_baseline", "train_sasrec", "train_deepfm", "train_all"]
    if data.task_type not in valid_task_types:
        raise HTTPException(400, f"Invalid task_type. Must be one of: {valid_task_types}")
    valid_schedule_types = ["cron", "interval", "threshold"]
    if data.schedule_type not in valid_schedule_types:
        raise HTTPException(400, f"Invalid schedule_type. Must be one of: {valid_schedule_types}")

    service = _get_service()
    schedule = await service.create_schedule(data.model_dump())
    return schedule


@router.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: int, data: ScheduleUpdate, admin: User = Depends(get_admin_user)):
    service = _get_service()
    result = await service.update_schedule(schedule_id, data.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(404, "Schedule not found")
    return result


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int, admin: User = Depends(get_admin_user)):
    service = _get_service()
    deleted = await service.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(404, "Schedule not found")
    return {"status": "deleted"}


@router.post("/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: int, admin: User = Depends(get_admin_user)):
    service = _get_service()
    result = await service.toggle_schedule(schedule_id)
    if not result:
        raise HTTPException(404, "Schedule not found")
    return result


@router.get("/threshold")
async def get_threshold(admin: User = Depends(get_admin_user)):
    service = _get_service()
    return await service.get_threshold()


@router.put("/threshold")
async def update_threshold(data: ThresholdUpdate, admin: User = Depends(get_admin_user)):
    service = _get_service()
    return await service.update_threshold(data.last_training_count)


@router.post("/check-threshold")
async def check_threshold(admin: User = Depends(get_admin_user)):
    service = _get_service()
    return await service.check_threshold_now()
