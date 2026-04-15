"""
Ranking Module: DeepFM-based candidate ranking.
Takes recall candidates and re-ranks them using learned feature interactions.
"""
import os
import sys
import logging
import json

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import MODEL_DIR, PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Lazy-loaded components
_deepfm = None
_feature_meta = None
_user_features = None
_item_features = None
_user2idx = None
_track2idx = None
_onnx_session = None


def _load_deepfm():
    """Lazy-load DeepFM model."""
    global _deepfm, _feature_meta
    if _deepfm is not None:
        return

    try:
        from ml_pipeline.models.deepfm import DeepFMRecommender
        _deepfm = DeepFMRecommender()
        _deepfm.load()

        with open(os.path.join(PROCESSED_DATA_DIR, "feature_meta.json")) as f:
            _feature_meta = json.load(f)

        logger.info("DeepFM model loaded for ranking")
    except Exception as e:
        logger.warning(f"Failed to load DeepFM: {e}")
        _deepfm = None


def _load_onnx():
    """Lazy-load ONNX model as alternative to PyTorch."""
    global _onnx_session, _feature_meta
    if _onnx_session is not None:
        return

    onnx_path = os.path.join(MODEL_DIR, "deepfm", "deepfm_model.onnx")
    if not os.path.exists(onnx_path):
        return

    try:
        import onnxruntime as ort
        _onnx_session = ort.InferenceSession(onnx_path)

        with open(os.path.join(PROCESSED_DATA_DIR, "feature_meta.json")) as f:
            _feature_meta = json.load(f)

        logger.info("ONNX DeepFM model loaded for ranking")
    except Exception as e:
        logger.warning(f"Failed to load ONNX model: {e}")


def _load_features():
    """Lazy-load user and item features."""
    global _user_features, _item_features, _user2idx, _track2idx
    if _user_features is not None and _user2idx is not None:
        return

    try:
        _user_features = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user_features.parquet"))
        _item_features = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "item_features.parquet"))
        _user2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet")).values)
        _track2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet")).values)
        logger.info(f"Loaded features: {len(_user_features)} users, {len(_item_features)} items")
    except Exception as e:
        logger.warning(f"Failed to load features: {e}")


def rank_candidates(
    user_id: int,
    candidate_track_ids: list[str],
    recall_scores: dict[str, float] | None = None,
    top_k: int = 20,
    use_onnx: bool = False,
) -> list[tuple[str, float]]:
    """
    Rank candidate items using DeepFM.
    
    Args:
        user_id: user ID
        candidate_track_ids: list of candidate track IDs from recall
        recall_scores: optional dict of recall scores for score blending
        top_k: number of items to return
        use_onnx: whether to use ONNX runtime instead of PyTorch
    
    Returns:
        list of (track_id, score) tuples, sorted by score descending
    """
    _load_features()

    if _user_features is None or _item_features is None:
        # Fallback: use recall scores directly
        logger.warning("Features not available, using recall scores for ranking")
        if recall_scores:
            items = sorted(recall_scores.items(), key=lambda x: x[1], reverse=True)
            return items[:top_k]
        return [(tid, 1.0 / (i + 1)) for i, tid in enumerate(candidate_track_ids[:top_k])]

    if use_onnx:
        _load_onnx()
    else:
        _load_deepfm()

    if _deepfm is None and _onnx_session is None:
        # Fallback
        logger.warning("No ranking model available, using recall order")
        if recall_scores:
            items = sorted(recall_scores.items(), key=lambda x: x[1], reverse=True)
            return items[:top_k]
        return [(tid, 1.0 / (i + 1)) for i, tid in enumerate(candidate_track_ids[:top_k])]

    # Build feature matrix for candidates
    user_row = _user_features[_user_features["user_id"] == user_id]
    if user_row.empty:
        if recall_scores:
            items = sorted(recall_scores.items(), key=lambda x: x[1], reverse=True)
            return items[:top_k]
        return [(tid, 1.0) for tid in candidate_track_ids[:top_k]]

    user_row = user_row.iloc[0]
    sparse_features = _feature_meta["sparse_features"]
    dense_features = _feature_meta["dense_features"]

    sparse_rows = []
    dense_rows = []
    valid_track_ids = []

    for track_id in candidate_track_ids:
        item_row = _item_features[_item_features["track_id"] == track_id]
        if item_row.empty:
            continue

        item_row = item_row.iloc[0]

        # Build sparse features
        sparse_vals = []
        for feat in sparse_features:
            if feat == "user_idx":
                sparse_vals.append(int(_user2idx.get(user_id, 0)))
            elif feat == "track_idx":
                sparse_vals.append(int(_track2idx.get(track_id, 0)))
            elif feat in user_row.index:
                sparse_vals.append(int(user_row[feat]))
            elif feat in item_row.index:
                sparse_vals.append(int(item_row[feat]))
            else:
                sparse_vals.append(0)

        # Build dense features
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
        valid_track_ids.append(track_id)

    if not valid_track_ids:
        return [(tid, 1.0) for tid in candidate_track_ids[:top_k]]

    sparse_array = np.array(sparse_rows, dtype=np.int64)
    dense_array = np.array(dense_rows, dtype=np.float32)

    # Predict
    if use_onnx and _onnx_session is not None:
        outputs = _onnx_session.run(None, {
            "sparse_inputs": sparse_array,
            "dense_inputs": dense_array,
        })
        scores = outputs[0].flatten()
    else:
        scores = _deepfm.predict(sparse_array, dense_array)

    # Normalize DeepFM scores to [0, 1] via sigmoid for stable blending
    scores = 1.0 / (1.0 + np.exp(-scores))

    # Normalize recall scores to [0, 1] for fair comparison
    if recall_scores:
        recall_vals = list(recall_scores.values())
        r_min, r_max = min(recall_vals), max(recall_vals)
        r_range = r_max - r_min if r_max > r_min else 1.0
        normalized_recall = {
            tid: (s - r_min) / r_range for tid, s in recall_scores.items()
        }
        for i, track_id in enumerate(valid_track_ids):
            recall_score = normalized_recall.get(track_id, 0.0)
            # 70% DeepFM + 30% recall
            scores[i] = scores[i] * 0.7 + recall_score * 0.3

    # Sort and return top-K
    ranked = sorted(zip(valid_track_ids, scores), key=lambda x: x[1], reverse=True)
    return [(tid, float(score)) for tid, score in ranked[:top_k]]
