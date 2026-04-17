"""
Shared progress tracking for ML training pipelines.

Training scripts write progress to JSON files that the admin backend reads.
This is the simplest cross-process communication channel since training
runs as an asyncio subprocess without access to the FastAPI app's Redis.

Usage in training scripts:
    tracker = ProgressTracker("train_sasrec_20260416_143000", "train_sasrec", total_epochs=50)
    tracker.update_epoch(epoch, train_loss=0.34, val_loss=0.38)
    tracker.append_log("Epoch 15/50 - loss: 0.34")
    # On exit (context manager) auto-marks completed or error
"""
import json
import os
import time
import tempfile
from datetime import datetime, timezone
from typing import Optional

PROGRESS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "training_progress")

MAX_LOG_LINES = 200


def _ensure_dir():
    os.makedirs(PROGRESS_DIR, exist_ok=True)


def _progress_path(task_id: str) -> str:
    return os.path.join(PROGRESS_DIR, f"{task_id}.json")


def _atomic_write(path: str, data: dict):
    """Write JSON atomically via write-then-rename."""
    _ensure_dir()
    tmp_fd, tmp_path = tempfile.mkstemp(dir=PROGRESS_DIR, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


class ProgressTracker:
    """Context-manager progress tracker for a training task."""

    def __init__(self, task_id: str, task_type: str, total_epochs: int = 0, total_phases: int = 0):
        self.task_id = task_id
        self.task_type = task_type
        self.total_epochs = total_epochs
        self.total_phases = total_phases
        self._path = _progress_path(task_id)
        self._data: Optional[dict] = None

    def __enter__(self):
        self._data = {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "current_epoch": 0,
            "total_epochs": self.total_epochs,
            "current_phase": "",
            "phase_index": 0,
            "total_phases": self.total_phases,
            "train_loss": None,
            "val_loss": None,
            "best_val_loss": None,
            "metrics": {},
            "log_lines": [],
            "completed_at": None,
            "error": None,
        }
        _atomic_write(self._path, self._data)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._data is None:
            return
        if exc_type is not None:
            self._data["status"] = "error"
            self._data["error"] = f"{exc_type.__name__}: {exc_val}"
        elif self._data["status"] == "running":
            self._data["status"] = "completed"
        self._data["completed_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write(self._path, self._data)

    def _flush(self):
        if self._data:
            _atomic_write(self._path, self._data)

    def update_epoch(self, epoch: int, train_loss: float = None, val_loss: float = None, metrics: dict = None):
        """Update progress after an epoch completes."""
        if not self._data:
            return
        self._data["current_epoch"] = epoch
        if train_loss is not None:
            self._data["train_loss"] = round(float(train_loss), 6)
        if val_loss is not None:
            self._data["val_loss"] = round(float(val_loss), 6)
            if self._data["best_val_loss"] is None or val_loss < self._data["best_val_loss"]:
                self._data["best_val_loss"] = round(float(val_loss), 6)
        if metrics:
            self._data["metrics"].update(metrics)
        self._flush()

    def update_phase(self, phase_name: str, phase_index: int):
        """Update progress for phase-based tasks (e.g., preprocessing)."""
        if not self._data:
            return
        self._data["current_phase"] = phase_name
        self._data["phase_index"] = phase_index
        self._flush()

    def append_log(self, line: str):
        """Append a log line (keeps last MAX_LOG_LINES)."""
        if not self._data:
            return
        self._data["log_lines"].append(line)
        if len(self._data["log_lines"]) > MAX_LOG_LINES:
            self._data["log_lines"] = self._data["log_lines"][-MAX_LOG_LINES:]
        self._flush()

    def mark_completed(self, metrics: dict = None):
        """Explicitly mark task as completed with optional metrics."""
        if not self._data:
            return
        self._data["status"] = "completed"
        self._data["completed_at"] = datetime.now(timezone.utc).isoformat()
        if metrics:
            self._data["metrics"].update(metrics)
        self._flush()

    # ---- Static helpers for reading progress ----

    @staticmethod
    def read_progress(task_id: str) -> Optional[dict]:
        path = _progress_path(task_id)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    @staticmethod
    def list_all_progress() -> list[dict]:
        _ensure_dir()
        results = []
        for fname in sorted(os.listdir(PROGRESS_DIR), reverse=True):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(PROGRESS_DIR, fname)
            try:
                with open(path) as f:
                    results.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
        return results

    @staticmethod
    def list_active() -> list[dict]:
        return [p for p in ProgressTracker.list_all_progress() if p.get("status") == "running"]

    @staticmethod
    def cleanup_old(max_age_days: int = 30):
        """Remove progress files older than max_age_days."""
        _ensure_dir()
        cutoff = time.time() - max_age_days * 86400
        for fname in os.listdir(PROGRESS_DIR):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(PROGRESS_DIR, fname)
            if os.path.getmtime(path) < cutoff:
                os.unlink(path)

    @staticmethod
    def mark_interrupted_on_startup():
        """Call on admin startup: mark any 'running' tasks as 'interrupted'."""
        for progress in ProgressTracker.list_active():
            progress["status"] = "interrupted"
            progress["error"] = "Admin server restarted during training"
            progress["completed_at"] = datetime.now(timezone.utc).isoformat()
            _atomic_write(_progress_path(progress["task_id"]), progress)
