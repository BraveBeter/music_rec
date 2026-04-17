"""
Evaluate already-trained models on test data (no retraining).

Loads saved models from data/models/, evaluates on the preprocessed test set,
and writes comparison_report.json / comparison_report.md.

Prerequisites:
  - Preprocessed data exists in data/processed/
  - At least one model has been trained (data/models/<model>/meta.json exists)

Usage:
  uv run python -m ml_pipeline.evaluation.evaluate_trained [--task-id <id>]
"""
import argparse
import os
import sys
import json
import logging

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, MODEL_DIR
from ml_pipeline.evaluation.metrics import evaluate_model, format_report
from ml_pipeline.training.progress import ProgressTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_DATA_FILES = [
    "train.parquet", "val.parquet", "test.parquet",
    "all_interactions.parquet",
    "user2idx.parquet", "track2idx.parquet",
    "user_sequences.json",
    "train_deepfm.parquet", "val_deepfm.parquet",
    "feature_meta.json",
    "user_features.parquet", "item_features.parquet",
]


def _check_data():
    missing = [f for f in REQUIRED_DATA_FILES if not os.path.exists(os.path.join(PROCESSED_DATA_DIR, f))]
    if missing:
        logger.error("Missing preprocessed data files:")
        for f in missing:
            logger.error(f"  - {f}")
        logger.error("Run preprocess first: uv run python -m ml_pipeline.data_process.preprocess")
        return False
    return True


def _load_data():
    import pandas as pd
    logger.info("Loading preprocessed data...")
    data = {}
    for name in ["train", "val", "test", "all_interactions"]:
        data[name] = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, f"{name}.parquet"))
    data["user2idx"] = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet")).values)
    data["track2idx"] = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet")).values)
    with open(os.path.join(PROCESSED_DATA_DIR, "user_sequences.json")) as f:
        data["sequences"] = {int(k): v for k, v in json.load(f).items()}
    with open(os.path.join(PROCESSED_DATA_DIR, "feature_meta.json")) as f:
        data["feature_meta"] = json.load(f)
    data["user_features"] = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user_features.parquet"))
    data["item_features"] = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "item_features.parquet"))
    logger.info(f"  Users: {len(data['user2idx'])}, Tracks: {len(data['track2idx'])}")
    return data


def _model_available(name: str) -> bool:
    return os.path.exists(os.path.join(MODEL_DIR, name, "meta.json"))


def _build_itemcf_fn(top_k=20):
    from ml_pipeline.models.item_cf import ItemCF
    logger.info("Loading ItemCF model...")
    model = ItemCF()
    model.load()

    def recommend(user_id):
        return model.recommend(user_id, top_k=top_k)
    return recommend


def _build_sasrec_fn(train_df, top_k=20):
    from ml_pipeline.models.sasrec import SASRecRecommender
    logger.info("Loading SASRec model...")
    model = SASRecRecommender()
    model.load()

    train_plays = train_df[train_df["interaction_type"].isin([1, 2])].sort_values("created_at")
    user_train_seqs = train_plays.groupby("user_id")["track_id"].apply(list).to_dict()

    def recommend(user_id):
        seq = user_train_seqs.get(user_id, [])
        if len(seq) < 3:
            return []
        return model.recommend(seq, top_k=top_k)
    return recommend


def _build_deepfm_fn(feature_meta, user_features, item_features,
                     user2idx, track2idx, top_k=20, candidate_pool_size=500):
    from ml_pipeline.models.deepfm import DeepFMRecommender
    logger.info("Loading DeepFM model...")
    model = DeepFMRecommender()
    model.load()

    sparse_features = feature_meta["sparse_features"]
    dense_features = feature_meta["dense_features"]
    candidates = item_features.nlargest(candidate_pool_size, "log_popularity")
    item_feat_idx = {row["track_id"]: row for _, row in candidates.iterrows()}
    user_feat_idx = {row["user_id"]: row for _, row in user_features.iterrows()}

    def recommend(user_id):
        user_row = user_feat_idx.get(user_id)
        if user_row is None:
            return []
        sparse_rows, dense_rows, valid_candidates = [], [], []
        for track_id, item_row in item_feat_idx.items():
            sparse_vals = []
            for feat in sparse_features:
                if feat == "user_idx":
                    sparse_vals.append(int(user2idx.get(user_id, 0)))
                elif feat == "track_idx":
                    sparse_vals.append(int(track2idx.get(track_id, 0)))
                elif feat in user_row.index:
                    sparse_vals.append(int(user_row[feat]))
                elif feat in item_row.index:
                    sparse_vals.append(int(item_row[feat]))
                else:
                    sparse_vals.append(0)
            dense_vals = []
            for feat in dense_features:
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
        sparse_array = np.array(sparse_rows, dtype=np.int64)
        dense_array = np.array(dense_rows, dtype=np.float32)
        scores = model.predict(sparse_array, dense_array)
        ranked = sorted(zip(valid_candidates, scores), key=lambda x: x[1], reverse=True)
        return [(tid, float(s)) for tid, s in ranked[:top_k]]
    return recommend


def _build_funnel_fn(train_df, top_k=20):
    from ml_pipeline.inference.pipeline import recommend

    # Reset singletons so funnel picks up latest saved models
    import ml_pipeline.inference.recall as recall_mod
    import ml_pipeline.inference.ranking as ranking_mod
    recall_mod._item_cf = None
    recall_mod._sasrec = None
    ranking_mod._deepfm = None
    ranking_mod._feature_meta = None
    ranking_mod._user_features = None
    ranking_mod._item_features = None
    ranking_mod._user2idx = None
    ranking_mod._track2idx = None
    ranking_mod._onnx_session = None

    train_plays = train_df[train_df["interaction_type"].isin([1, 2])].sort_values("created_at")
    user_train_seqs = train_plays.groupby("user_id")["track_id"].apply(list).to_dict()

    def recommend_fn(user_id):
        seq = user_train_seqs.get(user_id, [])
        result = recommend(
            user_id=user_id,
            user_sequence=seq if len(seq) >= 3 else None,
            top_k=top_k,
        )
        return [(item["track_id"], item["score"]) for item in result.get("items", [])]
    return recommend_fn


def main(task_id: str | None = None):
    try:
        import torch
        torch.manual_seed(42)
    except ImportError:
        pass
    np.random.seed(42)

    # Determine models to evaluate for progress tracking
    available_models = [n for n in ["item_cf", "deepfm", "sasrec"] if _model_available(n)]
    total_phases = len(available_models) + (1 if available_models else 0)  # models + funnel

    tracker = None
    if task_id:
        tracker = ProgressTracker(task_id, "evaluate", total_phases=total_phases)
        tracker.__enter__()

    def _log(msg: str):
        logger.info(msg)
        if tracker:
            tracker.append_log(msg)

    def _phase(name: str, idx: int):
        if tracker:
            tracker.update_phase(name, idx)

    _log("=" * 60)
    _log("Evaluating trained models (no retraining)")
    _log("=" * 60)

    if not _check_data():
        if tracker:
            _log("Error: missing preprocessed data files")
            tracker.__exit__(RuntimeError, RuntimeError("Missing preprocessed data files"), None)
        sys.exit(1)

    _log("Loading preprocessed data...")
    data = _load_data()
    train = data["train"]
    test = data["test"]
    all_interactions = data["all_interactions"]
    user2idx = data["user2idx"]
    track2idx = data["track2idx"]
    num_items = len(track2idx)
    k_values = [5, 10, 20]
    results = []
    phase_idx = 0

    # Evaluate each available model
    if _model_available("item_cf"):
        phase_idx += 1
        _phase("Evaluating ItemCF", phase_idx)
        _log("Evaluating ItemCF...")
        itemcf_fn = _build_itemcf_fn(top_k=20)
        results.append(evaluate_model(
            "ItemCF", itemcf_fn, test, all_interactions,
            k_values=k_values, num_items=num_items,
        ))
        _log("ItemCF done")
    else:
        _log("ItemCF model not found, skipping")

    if _model_available("deepfm"):
        phase_idx += 1
        _phase("Evaluating DeepFM", phase_idx)
        _log("Evaluating DeepFM...")
        deepfm_fn = _build_deepfm_fn(
            data["feature_meta"], data["user_features"], data["item_features"],
            user2idx, track2idx, top_k=20, candidate_pool_size=500,
        )
        results.append(evaluate_model(
            "DeepFM", deepfm_fn, test, all_interactions,
            k_values=k_values, num_items=num_items,
        ))
        _log("DeepFM done")
    else:
        _log("DeepFM model not found, skipping")

    if _model_available("sasrec"):
        phase_idx += 1
        _phase("Evaluating SASRec", phase_idx)
        _log("Evaluating SASRec...")
        sasrec_fn = _build_sasrec_fn(train, top_k=20)
        results.append(evaluate_model(
            "SASRec", sasrec_fn, test, all_interactions,
            k_values=k_values, num_items=num_items,
        ))
        _log("SASRec done")
    else:
        _log("SASRec model not found, skipping")

    # Funnel evaluation (requires at least one model)
    available_any = _model_available("item_cf") or _model_available("deepfm") or _model_available("sasrec")
    if available_any:
        phase_idx += 1
        _phase("Evaluating Multi-recall Funnel", phase_idx)
        _log("Evaluating Multi-recall Funnel...")
        funnel_fn = _build_funnel_fn(train, top_k=20)
        results.append(evaluate_model(
            "Multi-recall Funnel", funnel_fn, test, all_interactions,
            k_values=k_values, num_items=num_items,
        ))
        _log("Funnel done")

    if not results:
        _log("No trained models found. Train at least one model first.")
        if tracker:
            tracker.__exit__(RuntimeError, RuntimeError("No trained models"), None)
        sys.exit(1)

    # Generate report
    report = format_report(results, k_values=k_values)
    logger.info("\n" + report)

    os.makedirs(MODEL_DIR, exist_ok=True)
    report_path = os.path.join(MODEL_DIR, "comparison_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    json_path = os.path.join(MODEL_DIR, "comparison_report.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    _log(f"Report saved to {report_path}")
    _log(f"JSON saved to {json_path}")
    _log("Done!")

    if tracker:
        tracker.__exit__(None, None, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default=None)
    args = parser.parse_args()
    main(task_id=args.task_id)
