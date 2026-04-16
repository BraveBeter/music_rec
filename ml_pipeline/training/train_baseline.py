"""
Train baseline models: ItemCF + SVD Matrix Factorization.
Run: uv run python -m ml_pipeline.training.train_baseline
"""
import os
import sys
import json
import logging

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, MODEL_DIR
from ml_pipeline.models.item_cf import ItemCF
from ml_pipeline.models.matrix_factorization import SVDRecommender
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
    logger.info("Training Baseline Models: ItemCF + SVD")
    logger.info("=" * 60)

    # Load data
    logger.info("Loading data...")
    train = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "train.parquet"))
    val = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "val.parquet"))
    test = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "test.parquet"))
    all_interactions = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "all_interactions.parquet"))

    user2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet")).values)
    track2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet")).values)

    num_users = len(user2idx)
    num_items = len(track2idx)
    logger.info(f"Data: {num_users} users, {num_items} items, {len(train)} train, {len(test)} test")

    # Baseline has 2 phases: ItemCF (1 pass) + SVD (30 epochs)
    svd_epochs = 30
    total_phases = 2
    if task_id:
        from ml_pipeline.training.progress import ProgressTracker
        tracker = ProgressTracker(task_id, "train_baseline", total_epochs=svd_epochs, total_phases=total_phases)
        tracker.__enter__()
        tracker.append_log(f"Data: {num_users} users, {num_items} items, {len(train)} train")

    results = []

    # ---- Phase 1: ItemCF ----
    logger.info("\n" + "=" * 40)
    logger.info("Training ItemCF...")
    logger.info("=" * 40)

    if tracker:
        tracker.update_phase("ItemCF Training", 1)
        tracker.append_log("Phase 1/2: Training ItemCF...")

    item_cf = ItemCF(top_k_similar=50)
    item_cf.fit(train, user2idx, track2idx)
    item_cf.save()

    logger.info("Evaluating ItemCF...")
    item_cf_result = evaluate_model(
        model_name="ItemCF",
        recommend_fn=lambda uid: item_cf.recommend(uid, top_k=20),
        test_data=test,
        all_interactions=all_interactions,
        num_items=num_items,
    )
    results.append(item_cf_result)
    logger.info(f"ItemCF results: {item_cf_result}")

    if tracker:
        tracker.append_log(f"ItemCF done. Metrics: {item_cf_result}")

    # ---- Phase 2: SVD (BPR-MF) ----
    logger.info("\n" + "=" * 40)
    logger.info("Training SVD (BPR-MF)...")
    logger.info("=" * 40)

    if tracker:
        tracker.update_phase("SVD Training", 2)
        tracker.append_log("Phase 2/2: Training SVD (BPR-MF)...")

    svd = SVDRecommender(embedding_dim=64)
    svd.fit(
        train_interactions=train,
        val_interactions=val,
        user2idx=user2idx,
        track2idx=track2idx,
        epochs=svd_epochs,
        batch_size=256,
        lr=1e-3,
    )
    svd.save()

    if tracker:
        tracker.update_epoch(svd_epochs, train_loss=0)
        tracker.append_log(f"SVD training done ({svd_epochs} epochs)")

    logger.info("Evaluating SVD...")
    user_seen = all_interactions.groupby("user_id")["track_id"].apply(set).to_dict()

    svd_result = evaluate_model(
        model_name="SVD (BPR-MF)",
        recommend_fn=lambda uid: svd.recommend(uid, top_k=20, seen_items=user_seen.get(uid, set())),
        test_data=test,
        all_interactions=all_interactions,
        num_items=num_items,
    )
    results.append(svd_result)
    logger.info(f"SVD results: {svd_result}")

    # ---- Report ----
    report = format_report(results)
    report_path = os.path.join(MODEL_DIR, "baseline_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info("\n" + report)
    logger.info(f"\nReport saved to {report_path}")

    if tracker:
        combined_metrics = {}
        for r in results:
            combined_metrics.update(r)
        tracker.mark_completed(combined_metrics)
        tracker.__exit__(None, None, None)


if __name__ == "__main__":
    main()
