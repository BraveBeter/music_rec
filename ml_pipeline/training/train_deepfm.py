"""
Train DeepFM ranking model.
Run: uv run python -m ml_pipeline.training.train_deepfm
"""
import os
import sys
import json
import logging

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, MODEL_DIR
from ml_pipeline.models.deepfm import DeepFMRecommender
from ml_pipeline.evaluation.metrics import evaluate_model, format_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _get_task_id() -> str | None:
    """Parse --task-id from sys.argv if present."""
    for i, arg in enumerate(sys.argv):
        if arg == "--task-id" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def main():
    task_id = _get_task_id()
    tracker = None

    logger.info("=" * 60)
    logger.info("Training DeepFM Ranking Model")
    logger.info("=" * 60)

    # Load data
    train = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "train_deepfm.parquet"))
    val = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "val_deepfm.parquet"))
    test = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "test_deepfm.parquet"))

    with open(os.path.join(PROCESSED_DATA_DIR, "feature_meta.json")) as f:
        feature_meta = json.load(f)

    logger.info(f"Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

    epochs = 30
    if task_id:
        from ml_pipeline.training.progress import ProgressTracker
        tracker = ProgressTracker(task_id, "train_deepfm", total_epochs=epochs)
        tracker.__enter__()
        tracker.update_phase("training", 0)
        tracker.append_log(f"Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

    # Train
    deepfm = DeepFMRecommender()
    history = deepfm.fit(
        train_data=train,
        val_data=val,
        feature_meta=feature_meta,
        epochs=epochs,
        batch_size=256,
        lr=1e-3,
        patience=5,
    )

    # Track per-epoch progress from history
    if tracker and history.get("train_loss"):
        for epoch_idx, (tl, vl) in enumerate(zip(history["train_loss"], history["val_loss"])):
            tracker.update_epoch(epoch_idx + 1, train_loss=tl, val_loss=vl)
        tracker.append_log(f"Training done. {len(history['train_loss'])} epochs completed.")

    # Save model
    deepfm.save()

    # Save ID mappings alongside model so evaluation uses training-time indices
    import shutil
    model_dir = os.path.join(MODEL_DIR, "deepfm")
    for mapping_file in ["user2idx.parquet", "track2idx.parquet"]:
        src = os.path.join(PROCESSED_DATA_DIR, mapping_file)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(model_dir, mapping_file))

    # Export ONNX
    try:
        deepfm.export_onnx()
        logger.info("ONNX export successful")
    except Exception as e:
        logger.warning(f"ONNX export failed: {e}")

    # Evaluate on test set — compute AUC and LogLoss directly
    from sklearn.metrics import roc_auc_score, log_loss

    sparse_features = feature_meta["sparse_features"]
    dense_features = feature_meta["dense_features"]

    test_sparse = test[sparse_features].values.astype(np.int64)
    test_dense = test[dense_features].values.astype(np.float32)
    test_labels = test["label"].values

    preds = deepfm.predict(test_sparse, test_dense)
    preds_clipped = np.clip(preds, 1e-7, 1 - 1e-7)

    try:
        auc = roc_auc_score(test_labels, preds)
        logloss = log_loss(test_labels, preds_clipped)
        logger.info(f"DeepFM Test AUC: {auc:.4f}, LogLoss: {logloss:.4f}")
    except Exception as e:
        logger.warning(f"Could not compute AUC/LogLoss: {e}")
        auc, logloss = 0.0, 0.0

    results = {
        "model": "DeepFM",
        "test_auc": float(auc),
        "test_logloss": float(logloss),
        "train_loss_final": history["train_loss"][-1] if history.get("train_loss") else None,
        "val_loss_final": history["val_loss"][-1] if history.get("val_loss") else None,
    }

    report_path = os.path.join(MODEL_DIR, "deepfm_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)

    if tracker:
        tracker.mark_completed(results)
        tracker.__exit__(None, None, None)

    logger.info(f"Report saved to {report_path}")
    logger.info("DeepFM training complete!")


if __name__ == "__main__":
    main()
