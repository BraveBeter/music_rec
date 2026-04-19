"""Training orchestration service — manages ML training subprocess lifecycle."""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from ml_pipeline.training.progress import ProgressTracker, PROGRESS_DIR

logger = logging.getLogger("admin")

# In-memory mapping: task_id -> subprocess
_running: dict[str, asyncio.subprocess.Process] = {}


def _task_id(name: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{name}_{ts}"


async def start_training(name: str, module: str) -> dict:
    """Start a training subprocess with progress tracking.
    Returns {"task_id": ..., "status": "started", "pid": ...}
    """
    # Check if already running (same task type)
    active = ProgressTracker.list_active()
    for a in active:
        if a.get("task_type") == name and a.get("status") == "running":
            return {"status": "already_running", "task_id": a["task_id"], "name": name}

    tid = _task_id(name)
    cmd = ["python", "-m", module, "--task-id", tid]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    _running[tid] = process

    # Log output in background
    async def _log_output():
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            logger.info(f"[{name}:{tid}] {line.decode().rstrip()}")
        await process.wait()
        _running.pop(tid, None)
        logger.info(f"Training '{tid}' subprocess exited with code {process.returncode}")

    asyncio.create_task(_log_output())
    return {"status": "started", "task_id": tid, "pid": process.pid}


def get_progress(task_id: str) -> dict | None:
    return ProgressTracker.read_progress(task_id)


def list_progress() -> list[dict]:
    """Return all progress records, excluding evaluation tasks."""
    return [r for r in ProgressTracker.list_all_progress() if r.get("task_type") != "evaluate"]


def list_active() -> list[dict]:
    """Return active training tasks, excluding evaluation tasks."""
    return [t for t in ProgressTracker.list_active() if t.get("task_type") != "evaluate"]


def list_history(limit: int = 50) -> list[dict]:
    """Return completed/interrupted/error training runs (most recent first). Excludes evaluation tasks."""
    all_runs = ProgressTracker.list_all_progress()
    history = [
        r for r in all_runs
        if r.get("status") in ("completed", "error", "interrupted")
        and r.get("task_type") != "evaluate"
    ]
    return history[:limit]


async def cancel_training(task_id: str) -> dict:
    """Cancel a running training task."""
    from ml_pipeline.training.progress import _atomic_write, _progress_path, PROGRESS_DIR, EVAL_PROGRESS_DIR

    def _write_back(progress: dict):
        """Write progress back to whichever directory it lives in."""
        for d in [PROGRESS_DIR, EVAL_PROGRESS_DIR]:
            path = _progress_path(task_id, d)
            if os.path.exists(path):
                _atomic_write(path, progress, d)
                return
        # Fallback: write to training dir
        _atomic_write(_progress_path(task_id), progress)

    proc = _running.get(task_id)
    if not proc:
        # Check if it's still marked as running in the progress file
        progress = ProgressTracker.read_progress(task_id)
        if progress and progress.get("status") == "running":
            progress["status"] = "cancelled"
            progress["error"] = "Cancelled by admin"
            progress["completed_at"] = datetime.now(timezone.utc).isoformat()
            _write_back(progress)
            return {"status": "cancelled", "task_id": task_id}
        return {"status": "not_found", "task_id": task_id}

    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        proc.kill()

    _running.pop(task_id, None)

    progress = ProgressTracker.read_progress(task_id)
    if progress:
        progress["status"] = "cancelled"
        progress["error"] = "Cancelled by admin"
        progress["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_back(progress)

    return {"status": "cancelled", "task_id": task_id}
