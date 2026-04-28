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

RANKER_RECALL_WEIGHT = 0.85
RANKER_DEEPFM_WEIGHT = 0.15
TOP_ARTIST_BONUS = 0.20
LAST_ARTIST_BONUS = 0.10
TOP_GENRE_BONUS = 0.05
LAST_GENRE_BONUS = 0.05


def _load_deepfm():
    """Lazy-load DeepFM model."""
    global _deepfm, _feature_meta
    if _deepfm is not None:
        return

    try:
        from ml_pipeline.models.deepfm import DeepFMRecommender
        _deepfm = DeepFMRecommender()
        _deepfm.load()

        # Use model's own feature metadata for correct input alignment
        # (feature_meta.json may have different feature counts after re-running feature_engineering)
        _feature_meta = {
            "sparse_features": _deepfm.sparse_features,
            "dense_features": _deepfm.dense_features,
            "sparse_dims": _deepfm.sparse_dims,
        }

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

        # Load feature metadata from saved model (not from processed data)
        meta_path = os.path.join(MODEL_DIR, "deepfm", "meta.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                _feature_meta = json.load(f)
        else:
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
        # Use training-time index mappings if saved alongside model
        saved_user = os.path.join(MODEL_DIR, "deepfm", "user2idx.parquet")
        saved_track = os.path.join(MODEL_DIR, "deepfm", "track2idx.parquet")
        if os.path.exists(saved_user) and os.path.exists(saved_track):
            _user2idx = dict(pd.read_parquet(saved_user).values)
            _track2idx = dict(pd.read_parquet(saved_track).values)
        else:
            _user2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet")).values)
            _track2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet")).values)
        logger.info(f"Loaded features: {len(_user_features)} users, {len(_item_features)} items")
    except Exception as e:
        logger.warning(f"Failed to load features: {e}")


def _minmax_normalize(values: np.ndarray) -> np.ndarray:
    """Normalize a score array to [0, 1]."""
    if values.size == 0:
        return values
    min_val = float(values.min())
    max_val = float(values.max())
    if max_val - min_val < 1e-8:
        return np.ones_like(values, dtype=np.float32)
    return ((values - min_val) / (max_val - min_val)).astype(np.float32)


def build_dense_feature_value(feat: str, user_row: pd.Series, item_row: pd.Series) -> float:
    """Build dense feature values, including user-item cross features."""
    if feat in user_row.index:
        return float(user_row[feat])
    if feat in item_row.index:
        return float(item_row[feat])
    if feat == "top_artist_match":
        return float(int(user_row.get("top_artist_idx", -1)) == int(item_row.get("artist_idx", -2)))
    if feat == "top_genre_match":
        return float(int(user_row.get("top_genre_idx", -1)) == int(item_row.get("primary_genre_idx", -2)))
    if feat == "last_artist_match":
        return float(int(user_row.get("last_artist_idx", -1)) == int(item_row.get("artist_idx", -2)))
    if feat == "last_genre_match":
        return float(int(user_row.get("last_genre_idx", -1)) == int(item_row.get("primary_genre_idx", -2)))
    return 0.0


def build_deepfm_candidate_pool(
    item_features: pd.DataFrame,
    user_row: pd.Series,
    candidate_pool_size: int = 2000,
) -> pd.DataFrame:
    """Build a metadata-driven candidate pool for standalone DeepFM evaluation."""
    preferred_artist_ids = {
        int(user_row.get("top_artist_idx", -1)),
        int(user_row.get("last_artist_idx", -1)),
    }
    preferred_artist_ids.discard(-1)

    preferred_genre_ids = {
        int(user_row.get("top_genre_idx", -1)),
        int(user_row.get("last_genre_idx", -1)),
    }
    preferred_genre_ids.discard(-1)

    candidate_frames = []
    if preferred_artist_ids or preferred_genre_ids:
        mask = pd.Series(False, index=item_features.index)
        if preferred_artist_ids and "artist_idx" in item_features.columns:
            mask |= item_features["artist_idx"].isin(preferred_artist_ids)
        if preferred_genre_ids and "primary_genre_idx" in item_features.columns:
            mask |= item_features["primary_genre_idx"].isin(preferred_genre_ids)
        candidate_frames.append(item_features.loc[mask].nlargest(candidate_pool_size, "log_popularity"))

    candidate_frames.append(item_features.nlargest(candidate_pool_size, "log_popularity"))
    candidates = pd.concat(candidate_frames, ignore_index=True).drop_duplicates("track_id")
    return candidates.head(candidate_pool_size)


def build_deepfm_prior_bonus(user_row: pd.Series, item_row: pd.Series) -> float:
    """Metadata prior bonus for standalone/online DeepFM scoring."""
    return (
        TOP_ARTIST_BONUS * build_dense_feature_value("top_artist_match", user_row, item_row)
        + LAST_ARTIST_BONUS * build_dense_feature_value("last_artist_match", user_row, item_row)
        + TOP_GENRE_BONUS * build_dense_feature_value("top_genre_match", user_row, item_row)
        + LAST_GENRE_BONUS * build_dense_feature_value("last_genre_match", user_row, item_row)
    )


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
    sparse_dims = _feature_meta.get("sparse_dims", {})

    sparse_rows = []
    dense_rows = []
    valid_track_ids = []
    prior_bonus = []

    for track_id in candidate_track_ids:
        item_row = _item_features[_item_features["track_id"] == track_id]
        if item_row.empty:
            continue

        item_row = item_row.iloc[0]

        # Build sparse features
        sparse_vals = []
        for feat in sparse_features:
            if feat == "user_idx":
                val = int(_user2idx.get(user_id, 0))
            elif feat == "track_idx":
                val = int(_track2idx.get(track_id, 0))
            elif feat in user_row.index:
                val = int(user_row[feat])
            elif feat in item_row.index:
                val = int(item_row[feat])
            else:
                val = 0
            # Clip to valid embedding range
            if feat in sparse_dims:
                val = min(val, sparse_dims[feat] - 1)
            sparse_vals.append(val)

        # Build dense features
        dense_vals = []
        for feat in dense_features:
            dense_vals.append(build_dense_feature_value(feat, user_row, item_row))

        sparse_rows.append(sparse_vals)
        dense_rows.append(dense_vals)
        valid_track_ids.append(track_id)
        prior_bonus.append(build_deepfm_prior_bonus(user_row, item_row))

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
    scores = np.asarray(scores, dtype=np.float32) + np.asarray(prior_bonus, dtype=np.float32)

    # DeepFM forward already returns probabilities in [0, 1].
    # Normalize within the candidate set before blending with recall.
    scores = _minmax_normalize(np.asarray(scores, dtype=np.float32))

    if recall_scores:
        recall_vals = list(recall_scores.values())
        r_min, r_max = min(recall_vals), max(recall_vals)
        r_range = r_max - r_min if r_max > r_min else 1.0
        normalized_recall = {
            tid: (s - r_min) / r_range for tid, s in recall_scores.items()
        }
        for i, track_id in enumerate(valid_track_ids):
            recall_score = normalized_recall.get(track_id, 0.0)
            # Online ranking should be conservative: strong recall, light model correction.
            scores[i] = recall_score * RANKER_RECALL_WEIGHT + scores[i] * RANKER_DEEPFM_WEIGHT

    # Sort and return top-K
    ranked = sorted(zip(valid_track_ids, scores), key=lambda x: x[1], reverse=True)
    return [(tid, float(score)) for tid, score in ranked[:top_k]]
