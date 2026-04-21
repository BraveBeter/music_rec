"""
Train DeepFM ranking model.
Run: uv run python -m ml_pipeline.training.train_deepfm
"""
import os
import sys
import json
import logging
from datetime import datetime

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

    # Recommendation evaluation for NDCG@10 (needed for version comparison)
    deepfm_eval_result = None
    try:
        logger.info("Running recommendation evaluation for DeepFM...")
        test_recs = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "test.parquet"))
        all_interactions = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "all_interactions.parquet"))
        user2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet")).values)
        track2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet")).values)
        user_features = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user_features.parquet"))
        item_features = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "item_features.parquet"))

        # Use model's own features
        model_sparse = deepfm.sparse_features
        model_dense = deepfm.dense_features
        model_sparse_dims = deepfm.sparse_dims

        candidates = item_features.nlargest(500, "log_popularity")
        item_feat_idx = {row["track_id"]: row for _, row in candidates.iterrows()}
        user_feat_idx = {row["user_id"]: row for _, row in user_features.iterrows()}

        def deepfm_recommend(user_id):
            user_row = user_feat_idx.get(user_id)
            if user_row is None:
                return []
            sparse_rows, dense_rows, valid_candidates = [], [], []
            for track_id, item_row in item_feat_idx.items():
                sparse_vals = []
                for feat in model_sparse:
                    if feat == "user_idx":
                        val = int(user2idx.get(user_id, 0))
                    elif feat == "track_idx":
                        val = int(track2idx.get(track_id, 0))
                    elif feat in user_row.index:
                        val = int(user_row[feat])
                    elif feat in item_row.index:
                        val = int(item_row[feat])
                    else:
                        val = 0
                    if feat in model_sparse_dims:
                        val = min(val, model_sparse_dims[feat] - 1)
                    sparse_vals.append(val)
                dense_vals = []
                for feat in model_dense:
                    if feat in user_row.index:
                        dense_vals.append(float(user_row[feat]))
                    elif feat in item_row.index:
                        dense_vals.append(float(item_row[feat]))
                    else:
                        dense_vals.append(0.0)
                sparse_rows.append(sparse_vals)
                dense_rows.append(dense_vals)
                valid_candidates.append(track_id)
            if not valid_candidates:
                return []
            import numpy as np
            sparse_array = np.array(sparse_rows, dtype=np.int64)
            dense_array = np.array(dense_rows, dtype=np.float32)
            scores = deepfm.predict(sparse_array, dense_array)
            ranked = sorted(zip(valid_candidates, scores), key=lambda x: x[1], reverse=True)
            return [(tid, float(s)) for tid, s in ranked[:20]]

        deepfm_eval_result = evaluate_model(
            model_name="DeepFM",
            recommend_fn=deepfm_recommend,
            test_data=test_recs,
            all_interactions=all_interactions,
            num_items=len(track2idx),
        )
        logger.info(f"DeepFM recommendation metrics: {deepfm_eval_result}")
        if tracker:
            tracker.append_log(f"DeepFM rec eval: NDCG@10={deepfm_eval_result.get('ndcg@10', 0):.4f}")
    except Exception as e:
        logger.warning(f"DeepFM recommendation evaluation failed: {e}")

    # Version management: save version + compare + promote
    version_id = task_id or f"train_deepfm_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    from ml_pipeline.models.versioning import ModelRegistry
    registry = ModelRegistry()
    # Use recommendation metrics for comparison, fall back to classification metrics
    comparison_metrics = deepfm_eval_result if deepfm_eval_result else results
    registry.save_version_artifacts("deepfm", version_id)
    registry.register_version("deepfm", version_id, comparison_metrics)
    promoted = registry.compare_and_promote("deepfm", version_id, comparison_metrics)
    if promoted:
        logger.info("DeepFM: new version promoted to production")
        if tracker:
            tracker.append_log("DeepFM: promoted (NDCG@10 improved)")
    else:
        logger.info("DeepFM: new version rejected (NDCG@10 did not improve)")
        if tracker:
            tracker.append_log("DeepFM: rejected (NDCG@10 did not improve)")

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
