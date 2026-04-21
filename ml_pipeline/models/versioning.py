"""
Model versioning and auto-promotion system.

Manages model version storage, metric comparison, and automatic promotion
of better models to the production directory.

Usage in training scripts:
    from ml_pipeline.models.versioning import ModelRegistry

    registry = ModelRegistry()
    promoted = registry.compare_and_promote("item_cf", task_id, itemcf_metrics)
    if promoted:
        logger.info("New model promoted to production (NDCG@10 improved)")
    else:
        logger.info("New model rejected (NDCG@10 did not improve)")
"""
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

VERSION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "model_versions",
)
MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "models",
)
REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "model_registry.json",
)

DEFAULT_PRIMARY_METRIC = "ndcg@10"
DEFAULT_KEEP_VERSIONS = 3


class ModelRegistry:
    """Manages model versions, metrics, and promotion decisions."""

    def __init__(self, registry_path: str = REGISTRY_PATH,
                 version_dir: str = VERSION_DIR,
                 model_dir: str = MODEL_DIR):
        self._registry_path = registry_path
        self._version_dir = version_dir
        self._model_dir = model_dir

    def load(self) -> dict:
        if os.path.exists(self._registry_path):
            with open(self._registry_path) as f:
                return json.load(f)
        return {
            "primary_metric": DEFAULT_PRIMARY_METRIC,
            "keep_versions": DEFAULT_KEEP_VERSIONS,
            "models": {},
        }

    def save(self, data: dict):
        os.makedirs(os.path.dirname(self._registry_path), exist_ok=True)
        tmp_path = self._registry_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp_path, self._registry_path)

    def save_version_artifacts(self, model_name: str, version_id: str):
        """Copy current production model files to version directory.

        Call this AFTER model.save() so the version dir gets the latest files.
        """
        src_dir = os.path.join(self._model_dir, model_name)
        dst_dir = os.path.join(self._version_dir, model_name, version_id)

        if not os.path.exists(src_dir):
            logger.warning(f"Production model dir not found: {src_dir}")
            return

        os.makedirs(dst_dir, exist_ok=True)
        for fname in os.listdir(src_dir):
            src_file = os.path.join(src_dir, fname)
            if os.path.isfile(src_file):
                shutil.copy2(src_file, os.path.join(dst_dir, fname))

        logger.info(f"Saved version artifacts: {model_name}/{version_id}")

    def register_version(self, model_name: str, version_id: str,
                         metrics: dict) -> dict:
        """Register a new version with its metrics. Returns the updated registry."""
        registry = self.load()
        models = registry.setdefault("models", {})
        model_entry = models.setdefault(model_name, {"active_version": None, "versions": {}})

        model_entry["versions"][version_id] = {
            "status": "pending",
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "promoted_at": None,
            "metrics": metrics,
        }

        self.save(registry)
        return registry

    def compare_and_promote(self, model_name: str, version_id: str,
                            new_metrics: dict,
                            primary_metric: str = None) -> bool:
        """Compare new version metrics with active version and promote if better.

        Returns True if promoted to production, False if rejected.
        """
        registry = self.load()
        primary_metric = primary_metric or registry.get("primary_metric", DEFAULT_PRIMARY_METRIC)
        keep = registry.get("keep_versions", DEFAULT_KEEP_VERSIONS)

        models = registry.setdefault("models", {})
        model_entry = models.setdefault(model_name, {"active_version": None, "versions": {}})

        new_score = new_metrics.get(primary_metric)
        if new_score is None:
            logger.warning(f"Primary metric '{primary_metric}' not found in new version metrics, promoting by default")
            new_score = float("-inf")

        active_version = model_entry.get("active_version")
        old_score = None
        if active_version and active_version in model_entry.get("versions", {}):
            old_metrics = model_entry["versions"][active_version].get("metrics", {})
            old_score = old_metrics.get(primary_metric)

        should_promote = False
        if active_version is None:
            # No previous version — always promote
            should_promote = True
            logger.info(f"[{model_name}] First version, promoting automatically")
        elif new_score > old_score:
            should_promote = True
            logger.info(
                f"[{model_name}] New version better: {primary_metric}={new_score:.4f} > {old_score:.4f}, promoting"
            )
        else:
            logger.info(
                f"[{model_name}] New version worse: {primary_metric}={new_score:.4f} <= {old_score:.4f}, rejecting"
            )

        # Update version status
        version_entry = model_entry["versions"].get(version_id, {})
        now = datetime.now(timezone.utc).isoformat()

        if should_promote:
            # Mark previous active as superseded
            if active_version and active_version in model_entry.get("versions", {}):
                model_entry["versions"][active_version]["status"] = "superseded"

            # Promote to production
            self._promote_files(model_name, version_id)
            version_entry["status"] = "active"
            version_entry["promoted_at"] = now
            model_entry["active_version"] = version_id
        else:
            version_entry["status"] = "rejected"

        # Ensure the version entry is updated
        if version_id in model_entry["versions"]:
            model_entry["versions"][version_id].update(version_entry)

        self.save(registry)

        # Cleanup old versions
        self.cleanup_old_versions(model_name, keep)

        return should_promote

    def _promote_files(self, model_name: str, version_id: str):
        """Copy version directory contents to production directory."""
        src_dir = os.path.join(self._version_dir, model_name, version_id)
        dst_dir = os.path.join(self._model_dir, model_name)

        if not os.path.exists(src_dir):
            logger.error(f"Version directory not found: {src_dir}")
            return

        os.makedirs(dst_dir, exist_ok=True)

        # Clear existing production files
        for fname in os.listdir(dst_dir):
            fpath = os.path.join(dst_dir, fname)
            if os.path.isfile(fpath):
                os.unlink(fpath)

        # Copy version files to production
        for fname in os.listdir(src_dir):
            src_file = os.path.join(src_dir, fname)
            if os.path.isfile(src_file):
                shutil.copy2(src_file, os.path.join(dst_dir, fname))

        logger.info(f"Promoted {model_name}/{version_id} to production")

    def promote_version(self, model_name: str, version_id: str) -> bool:
        """Manually promote a specific version to production (admin action)."""
        registry = self.load()
        models = registry.get("models", {})
        model_entry = models.get(model_name)

        if not model_entry or version_id not in model_entry.get("versions", {}):
            logger.error(f"Version not found: {model_name}/{version_id}")
            return False

        active_version = model_entry.get("active_version")
        if active_version and active_version in model_entry["versions"]:
            model_entry["versions"][active_version]["status"] = "superseded"

        self._promote_files(model_name, version_id)

        now = datetime.now(timezone.utc).isoformat()
        model_entry["versions"][version_id]["status"] = "active"
        model_entry["versions"][version_id]["promoted_at"] = now
        model_entry["active_version"] = version_id

        self.save(registry)
        logger.info(f"Manually promoted {model_name}/{version_id} to production")
        return True

    def cleanup_old_versions(self, model_name: str, keep: int = DEFAULT_KEEP_VERSIONS):
        """Remove oldest version directories beyond keep limit.

        Never deletes the active version.
        """
        registry = self.load()
        model_entry = registry.get("models", {}).get(model_name)
        if not model_entry:
            return

        versions = model_entry.get("versions", {})
        active_version = model_entry.get("active_version")

        # Sort versions by saved_at timestamp (oldest first)
        sorted_versions = sorted(
            [(vid, v.get("saved_at", "")) for vid, v in versions.items()],
            key=lambda x: x[1],
        )

        # Collect versions to remove (non-active, oldest first)
        to_remove = []
        non_active = [(vid, ts) for vid, ts in sorted_versions if vid != active_version]

        if len(non_active) > keep:
            to_remove = non_active[:len(non_active) - keep]

        for vid, _ in to_remove:
            # Remove from disk
            vdir = os.path.join(self._version_dir, model_name, vid)
            if os.path.exists(vdir):
                shutil.rmtree(vdir)
                logger.info(f"Cleaned up old version: {model_name}/{vid}")

            # Remove from registry
            versions.pop(vid, None)

        if to_remove:
            self.save(registry)

    def get_active_version(self, model_name: str) -> Optional[dict]:
        """Get the active version info for a model."""
        registry = self.load()
        model_entry = registry.get("models", {}).get(model_name)
        if not model_entry:
            return None

        active_id = model_entry.get("active_version")
        if not active_id:
            return None

        return {
            "version_id": active_id,
            **model_entry["versions"].get(active_id, {}),
        }

    def list_versions(self, model_name: str = None) -> dict:
        """List all versions, optionally filtered by model name.

        Returns the full models dict or a single model's versions.
        """
        registry = self.load()
        models = registry.get("models", {})

        if model_name:
            return models.get(model_name, {})
        return models

    def get_all_model_info(self) -> dict:
        """Get complete model info including all versions for admin API."""
        registry = self.load()
        primary_metric = registry.get("primary_metric", DEFAULT_PRIMARY_METRIC)
        return {
            "primary_metric": primary_metric,
            "keep_versions": registry.get("keep_versions", DEFAULT_KEEP_VERSIONS),
            "models": registry.get("models", {}),
        }

    def get_version_dir(self, model_name: str, version_id: str) -> Optional[str]:
        """Get the filesystem path for a specific model version."""
        vdir = os.path.join(self._version_dir, model_name, version_id)
        return vdir if os.path.exists(vdir) else None
