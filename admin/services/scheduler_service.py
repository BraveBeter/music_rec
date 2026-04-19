"""Scheduler service — APScheduler wrapper for automated model retraining."""
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_db, async_session_factory, Base, engine
from common.models.training_schedule import TrainingSchedule, TrainingThresholdState
from admin.services import training_service
from ml_pipeline.training.progress import ProgressTracker

logger = logging.getLogger("admin")

# Global lock: only one training pipeline can run at a time
_training_lock = asyncio.Lock()

# Task type -> module mapping
MODULE_MAP = {
    "preprocess": "ml_pipeline.data_process.preprocess",
    "train_baseline": "ml_pipeline.training.train_baseline",
    "train_sasrec": "ml_pipeline.training.train_sasrec",
    "train_deepfm": "ml_pipeline.training.train_deepfm",
}

VALID_TASK_TYPES = list(MODULE_MAP.keys()) + ["train_all"]
VALID_SCHEDULE_TYPES = ["cron", "interval", "threshold"]


class SchedulerService:
    def __init__(self):
        from common.config import get_settings
        settings = get_settings()
        tz = getattr(settings, 'SCHEDULER_TIMEZONE', 'Asia/Shanghai')
        self._scheduler = AsyncIOScheduler(timezone=tz)
        self._started = False

    async def start(self):
        """Start the scheduler and load existing jobs from DB."""
        if self._started:
            return

        # Ensure DB tables exist (handles existing databases where init.sql hasn't run)
        await self._ensure_tables()

        self._scheduler.start()
        self._started = True
        logger.info("Scheduler service started")

        # Load enabled schedules from DB
        await self._load_schedules_from_db()

        # Add periodic threshold checker (every 10 minutes)
        self._scheduler.add_job(
            self._check_thresholds,
            IntervalTrigger(minutes=10),
            id="threshold_checker",
            replace_existing=True,
        )
        logger.info("Threshold checker scheduled (every 10 min)")

    async def shutdown(self):
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("Scheduler service stopped")

    async def _ensure_tables(self):
        """Create scheduler tables if they don't exist yet."""
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Scheduler tables ensured")
        except Exception as e:
            logger.warning(f"Could not create scheduler tables: {e}")

    async def _load_schedules_from_db(self):
        """Load all enabled schedules from DB and register APScheduler jobs."""
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(TrainingSchedule).where(TrainingSchedule.is_enabled == 1)
                )
                schedules = result.scalars().all()
                for schedule in schedules:
                    try:
                        self._add_job(schedule)
                    except Exception as e:
                        logger.error(f"Failed to load schedule {schedule.schedule_id}: {e}")
        except Exception as e:
            logger.warning(f"Could not load schedules from DB: {e}")

    def _add_job(self, schedule: TrainingSchedule):
        """Register an APScheduler job from a TrainingSchedule record."""
        job_id = f"schedule_{schedule.schedule_id}"

        if schedule.schedule_type == "cron" and schedule.cron_expr:
            parts = schedule.cron_expr.split()
            trigger = CronTrigger(
                minute=parts[0] if len(parts) > 0 else "*",
                hour=parts[1] if len(parts) > 1 else "*",
                day=parts[2] if len(parts) > 2 else "*",
                month=parts[3] if len(parts) > 3 else "*",
                day_of_week=parts[4] if len(parts) > 4 else "*",
            )
        elif schedule.schedule_type == "interval" and schedule.interval_minutes:
            trigger = IntervalTrigger(minutes=schedule.interval_minutes)
        else:
            logger.warning(f"Schedule {schedule.schedule_id} has no valid trigger config, skipping")
            return

        self._scheduler.add_job(
            self._execute_scheduled_task,
            trigger=trigger,
            id=job_id,
            args=[schedule.schedule_id],
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=300,
            coalesce=True,
        )
        logger.info(f"Registered scheduled job: {job_id} ({schedule.schedule_type}: {schedule.cron_expr or schedule.interval_minutes}m)")

    def _remove_job(self, schedule_id: int):
        job_id = f"schedule_{schedule_id}"
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

    async def _execute_scheduled_task(self, schedule_id: int):
        """Callback when a scheduled job fires. Acquires global lock to prevent parallel training."""
        if _training_lock.locked():
            logger.info(f"Skipping schedule {schedule_id}: another training is already running")
            return

        async with _training_lock:
            logger.info(f"Scheduled task firing for schedule_id={schedule_id}")
            try:
                # Double-check: is any training already active?
                active = ProgressTracker.list_active()
                if active:
                    logger.info(f"Skipping schedule {schedule_id}: {len(active)} training task(s) already active")
                    return

                async with async_session_factory() as session:
                    result = await session.execute(
                        select(TrainingSchedule).where(TrainingSchedule.schedule_id == schedule_id)
                    )
                    schedule = result.scalar_one_or_none()
                    if not schedule or not schedule.is_enabled:
                        return

                    task_type = schedule.task_type
                    schedule.last_run_at = datetime.now()
                    await session.commit()

                if task_type == "train_all":
                    for name, module in MODULE_MAP.items():
                        await training_service.start_training(name, module)
                elif task_type in MODULE_MAP:
                    await training_service.start_training(task_type, MODULE_MAP[task_type])
                else:
                    logger.warning(f"Unknown task_type: {task_type}")
            except Exception as e:
                logger.error(f"Error executing scheduled task {schedule_id}: {e}")

    async def _check_thresholds(self):
        """Check if any threshold-based schedules should fire."""
        try:
            async with async_session_factory() as session:
                # Get current interaction count
                result = await session.execute(text("SELECT COUNT(*) FROM user_interactions"))
                current_count = result.scalar() or 0

                # Get threshold state
                result = await session.execute(select(TrainingThresholdState))
                state = result.scalar_one_or_none()

                # Get enabled threshold schedules
                result = await session.execute(
                    select(TrainingSchedule).where(
                        TrainingSchedule.is_enabled == 1,
                        TrainingSchedule.schedule_type == "threshold",
                    )
                )
                threshold_schedules = result.scalars().all()

                if not threshold_schedules:
                    return

                last_count = state.last_training_count if state else 0
                delta = current_count - last_count
                logger.info(f"Threshold check: current={current_count}, last={last_count}, delta={delta}")

                for schedule in threshold_schedules:
                    threshold = schedule.threshold_interactions or 0
                    if delta >= threshold > 0:
                        logger.info(f"Threshold triggered for schedule {schedule.schedule_id}: delta={delta} >= {threshold}")
                        await self._execute_scheduled_task(schedule.schedule_id)

                # Update threshold state
                if state:
                    state.last_training_count = current_count
                else:
                    state = TrainingThresholdState(last_training_count=current_count)
                    session.add(state)
                await session.commit()
        except Exception as e:
            logger.error(f"Error checking thresholds: {e}")

    # ---- CRUD operations ----

    async def get_schedules(self) -> list[dict]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TrainingSchedule).order_by(TrainingSchedule.schedule_id.desc())
            )
            schedules = result.scalars().all()
            return [_to_dict(s) for s in schedules]

    async def create_schedule(self, data: dict) -> dict:
        async with async_session_factory() as session:
            schedule = TrainingSchedule(
                name=data["name"],
                task_type=data["task_type"],
                schedule_type=data.get("schedule_type", "cron"),
                cron_expr=data.get("cron_expr"),
                interval_minutes=data.get("interval_minutes"),
                threshold_interactions=data.get("threshold_interactions"),
                is_enabled=data.get("is_enabled", 1),
            )
            session.add(schedule)
            await session.commit()
            await session.refresh(schedule)

            if schedule.is_enabled:
                self._add_job(schedule)

            return _to_dict(schedule)

    async def update_schedule(self, schedule_id: int, data: dict) -> dict | None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TrainingSchedule).where(TrainingSchedule.schedule_id == schedule_id)
            )
            schedule = result.scalar_one_or_none()
            if not schedule:
                return None

            for key in ["name", "task_type", "schedule_type", "cron_expr",
                         "interval_minutes", "threshold_interactions", "is_enabled"]:
                if key in data:
                    setattr(schedule, key, data[key])

            await session.commit()
            await session.refresh(schedule)

            # Re-register job
            self._remove_job(schedule_id)
            if schedule.is_enabled:
                self._add_job(schedule)

            return _to_dict(schedule)

    async def delete_schedule(self, schedule_id: int) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TrainingSchedule).where(TrainingSchedule.schedule_id == schedule_id)
            )
            schedule = result.scalar_one_or_none()
            if not schedule:
                return False

            await session.delete(schedule)
            await session.commit()
            self._remove_job(schedule_id)
            return True

    async def toggle_schedule(self, schedule_id: int) -> dict | None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TrainingSchedule).where(TrainingSchedule.schedule_id == schedule_id)
            )
            schedule = result.scalar_one_or_none()
            if not schedule:
                return None

            schedule.is_enabled = 0 if schedule.is_enabled else 1
            await session.commit()
            await session.refresh(schedule)

            self._remove_job(schedule_id)
            if schedule.is_enabled:
                self._add_job(schedule)

            return _to_dict(schedule)

    async def get_threshold(self) -> dict:
        async with async_session_factory() as session:
            result = await session.execute(select(TrainingThresholdState))
            state = result.scalar_one_or_none()

            count_result = await session.execute(text("SELECT COUNT(*) FROM user_interactions"))
            current_count = count_result.scalar() or 0

            return {
                "last_training_count": state.last_training_count if state else 0,
                "current_interaction_count": current_count,
            }

    async def update_threshold(self, last_training_count: int) -> dict:
        async with async_session_factory() as session:
            result = await session.execute(select(TrainingThresholdState))
            state = result.scalar_one_or_none()
            if state:
                state.last_training_count = last_training_count
            else:
                state = TrainingThresholdState(last_training_count=last_training_count)
                session.add(state)
            await session.commit()
            return {"status": "updated", "last_training_count": last_training_count}

    async def check_threshold_now(self) -> dict:
        """Manually trigger a threshold check."""
        await self._check_thresholds()
        return {"status": "checked"}


def _to_dict(schedule: TrainingSchedule) -> dict:
    return {
        "schedule_id": schedule.schedule_id,
        "name": schedule.name,
        "task_type": schedule.task_type,
        "schedule_type": schedule.schedule_type,
        "cron_expr": schedule.cron_expr,
        "interval_minutes": schedule.interval_minutes,
        "threshold_interactions": schedule.threshold_interactions,
        "is_enabled": bool(schedule.is_enabled),
        "last_run_at": str(schedule.last_run_at) if schedule.last_run_at else None,
        "next_run_at": str(schedule.next_run_at) if schedule.next_run_at else None,
        "created_at": str(schedule.created_at) if schedule.created_at else None,
    }
