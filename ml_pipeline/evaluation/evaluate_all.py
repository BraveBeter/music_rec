"""
Unified evaluation script: compare ItemCF, DeepFM, SASRec, and Multi-recall Funnel
on the same dataset using identical metrics.

Prerequisites:
    uv run python -m ml_pipeline.data_process.preprocess
    uv run python -m ml_pipeline.data_process.feature_engineering

Usage:
    uv run python -m ml_pipeline.evaluation.evaluate_all
"""
import os
import sys
import json
import logging

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, MODEL_DIR
from ml_pipeline.evaluation.metrics import evaluate_model, format_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_FILES = [
    "train.parquet", "val.parquet", "test.parquet",
    "all_interactions.parquet",
    "user2idx.parquet", "track2idx.parquet",
    "user_sequences.json",
    "train_deepfm.parquet", "val_deepfm.parquet",
    "feature_meta.json",
    "user_features.parquet", "item_features.parquet",
]


def _check_data():
    """Check that all preprocessed data files exist."""
    missing = [f for f in REQUIRED_FILES if not os.path.exists(os.path.join(PROCESSED_DATA_DIR, f))]
    if missing:
        logger.error("Missing preprocessed data files:")
        for f in missing:
            logger.error(f"  - {f}")
        logger.error("Run preprocess and feature_engineering first:")
        logger.error("  uv run python -m ml_pipeline.data_process.preprocess")
        logger.error("  uv run python -m ml_pipeline.data_process.feature_engineering")
        sys.exit(1)


def _load_data():
    """Load all preprocessed data into memory."""
    logger.info("Loading preprocessed data...")

    data = {}
    for name in ["train", "val", "test", "all_interactions"]:
        data[name] = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, f"{name}.parquet"))

    data["user2idx"] = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet")).values)
    data["track2idx"] = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet")).values)
    data["idx2track"] = {v: k for k, v in data["track2idx"].items()}

    with open(os.path.join(PROCESSED_DATA_DIR, "user_sequences.json")) as f:
        seq_raw = json.load(f)
        data["sequences"] = {int(k): v for k, v in seq_raw.items()}

    with open(os.path.join(PROCESSED_DATA_DIR, "feature_meta.json")) as f:
        data["feature_meta"] = json.load(f)

    data["train_deepfm"] = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "train_deepfm.parquet"))
    data["val_deepfm"] = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "val_deepfm.parquet"))

    data["user_features"] = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user_features.parquet"))
    data["item_features"] = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "item_features.parquet"))

    logger.info(f"  Users: {len(data['user2idx'])}, Tracks: {len(data['track2idx'])}")
    logger.info(f"  Train: {len(data['train'])}, Test: {len(data['test'])}")

    return data


def _train_itemcf(train, user2idx, track2idx):
    """Train ItemCF model."""
    from ml_pipeline.models.item_cf import ItemCF
    logger.info("Training ItemCF...")
    model = ItemCF(top_k_similar=50)
    model.fit(train, user2idx, track2idx)
    model.save()
    logger.info("ItemCF trained and saved.")
    return model


def _train_deepfm(train_deepfm, val_deepfm, feature_meta):
    """Train DeepFM model."""
    from ml_pipeline.models.deepfm import DeepFMRecommender
    logger.info("Training DeepFM...")
    model = DeepFMRecommender()
    model.fit(
        train_data=train_deepfm,
        val_data=val_deepfm,
        feature_meta=feature_meta,
        epochs=30,
        batch_size=256,
        lr=1e-3,
        patience=5,
    )
    model.save()
    logger.info("DeepFM trained and saved.")
    return model


def _train_sasrec(sequences, track2idx):
    """Train SASRec model."""
    from ml_pipeline.models.sasrec import SASRecRecommender
    logger.info("Training SASRec...")
    model = SASRecRecommender(hidden_dim=64, num_heads=2, num_blocks=2)
    model.fit(
        sequences=sequences,
        track2idx=track2idx,
        epochs=30,
        batch_size=128,
        lr=1e-3,
        patience=8,
    )
    model.save()
    logger.info("SASRec trained and saved.")
    return model


def _reset_inference_singletons():
    """Reset lazy-loaded singletons in inference modules so they pick up newly saved models."""
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
    logger.info("Reset inference module singletons.")


def _build_itemcf_fn(itemcf_model, top_k=20):
    """Wrap ItemCF as recommend_fn(user_id) -> list[tuple]."""
    def recommend(user_id):
        return itemcf_model.recommend(user_id, top_k=top_k)
    return recommend


def _build_sasrec_fn(sasrec_model, train_df, top_k=20):
    """Wrap SASRec as recommend_fn(user_id) -> list[tuple]."""
    train_plays = train_df[train_df["interaction_type"].isin([1, 2])].sort_values("created_at")
    user_train_seqs = train_plays.groupby("user_id")["track_id"].apply(list).to_dict()

    def recommend(user_id):
        seq = user_train_seqs.get(user_id, [])
        if len(seq) < 3:
            return []
        return sasrec_model.recommend(seq, top_k=top_k)
    return recommend


def _build_deepfm_fn(deepfm_model, feature_meta, user_features, item_features,
                     user2idx, track2idx, top_k=20, candidate_pool_size=500):
    """
    Wrap DeepFM as recommend_fn(user_id) -> list[tuple].

    Uses top-N popular items as candidate pool since DeepFM is a ranking model,
    not a recall model. In the real pipeline it ranks candidates from multi-recall.
    """
    sparse_features = feature_meta["sparse_features"]
    dense_features = feature_meta["dense_features"]

    # Build candidate pool: most popular items
    candidates = item_features.nlargest(candidate_pool_size, "log_popularity")

    # Pre-index item features for fast lookup
    item_feat_idx = {row["track_id"]: row for _, row in candidates.iterrows()}
    user_feat_idx = {row["user_id"]: row for _, row in user_features.iterrows()}

    def recommend(user_id):
        user_row = user_feat_idx.get(user_id)
        if user_row is None:
            return []

        sparse_rows = []
        dense_rows = []
        valid_candidates = []

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
        scores = deepfm_model.predict(sparse_array, dense_array)

        ranked = sorted(zip(valid_candidates, scores), key=lambda x: x[1], reverse=True)
        return [(tid, float(s)) for tid, s in ranked[:top_k]]

    return recommend


def _build_funnel_fn(train_df, top_k=20):
    """Wrap the full multi-recall funnel as recommend_fn(user_id) -> list[tuple]."""
    from ml_pipeline.inference.pipeline import recommend

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


def main():
    try:
        import torch
        torch.manual_seed(42)
    except ImportError:
        pass
    np.random.seed(42)

    logger.info("=" * 60)
    logger.info("Unified Model Evaluation: ItemCF vs DeepFM vs SASRec vs Funnel")
    logger.info("=" * 60)

    # Check and load data
    _check_data()
    data = _load_data()

    train = data["train"]
    test = data["test"]
    all_interactions = data["all_interactions"]
    user2idx = data["user2idx"]
    track2idx = data["track2idx"]
    num_items = len(track2idx)

    # Train all models
    itemcf = _train_itemcf(train, user2idx, track2idx)
    deepfm = _train_deepfm(data["train_deepfm"], data["val_deepfm"], data["feature_meta"])
    sasrec = _train_sasrec(data["sequences"], track2idx)

    # Reset inference singletons so funnel picks up new models
    _reset_inference_singletons()

    # Build recommend functions
    logger.info("Building recommend functions...")
    k_values = [5, 10, 20]

    itemcf_fn = _build_itemcf_fn(itemcf, top_k=20)
    sasrec_fn = _build_sasrec_fn(sasrec, train, top_k=20)
    deepfm_fn = _build_deepfm_fn(
        deepfm, data["feature_meta"], data["user_features"], data["item_features"],
        user2idx, track2idx, top_k=20, candidate_pool_size=500,
    )
    funnel_fn = _build_funnel_fn(train, top_k=20)

    # Evaluate all models
    results = []

    logger.info("Evaluating ItemCF...")
    results.append(evaluate_model(
        "ItemCF", itemcf_fn, test, all_interactions,
        k_values=k_values, num_items=num_items,
    ))

    logger.info("Evaluating DeepFM...")
    results.append(evaluate_model(
        "DeepFM", deepfm_fn, test, all_interactions,
        k_values=k_values, num_items=num_items,
    ))

    logger.info("Evaluating SASRec...")
    results.append(evaluate_model(
        "SASRec", sasrec_fn, test, all_interactions,
        k_values=k_values, num_items=num_items,
    ))

    logger.info("Evaluating Multi-recall Funnel...")
    results.append(evaluate_model(
        "Multi-recall Funnel", funnel_fn, test, all_interactions,
        k_values=k_values, num_items=num_items,
    ))

    # Generate report
    report = format_report(results, k_values=k_values)
    logger.info("\n" + report)

    # Save report
    os.makedirs(MODEL_DIR, exist_ok=True)
    report_path = os.path.join(MODEL_DIR, "comparison_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    json_path = os.path.join(MODEL_DIR, "comparison_report.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"\nReport saved to {report_path}")
    logger.info(f"JSON saved to {json_path}")
    logger.info("Done!")


if __name__ == "__main__":
    main()
