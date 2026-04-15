"""
Recall Module: Multi-channel recall for recommendation candidates.
Combines ItemCF, SASRec, and popularity-based recall with score normalization.
"""
import os
import sys
import logging
from typing import Optional

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import MODEL_DIR, PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Lazy-loaded models
_item_cf = None
_sasrec = None


def _get_item_cf():
    """Lazy-load ItemCF model."""
    global _item_cf
    if _item_cf is None:
        try:
            from ml_pipeline.models.item_cf import ItemCF
            _item_cf = ItemCF()
            _item_cf.load()
            logger.info("ItemCF model loaded for recall")
        except Exception as e:
            logger.warning(f"Failed to load ItemCF: {e}")
    return _item_cf


def _get_sasrec():
    """Lazy-load SASRec model."""
    global _sasrec
    if _sasrec is None:
        try:
            from ml_pipeline.models.sasrec import SASRecRecommender
            _sasrec = SASRecRecommender()
            _sasrec.load()
            logger.info("SASRec model loaded for recall")
        except Exception as e:
            logger.warning(f"Failed to load SASRec: {e}")
    return _sasrec


def _normalize_scores(results: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Min-max normalize scores to [0, 1]."""
    if not results:
        return results
    scores = [s for _, s in results]
    mn, mx = min(scores), max(scores)
    rng = mx - mn
    if rng < 1e-8:
        return [(tid, 1.0) for tid, _ in results]
    return [(tid, (s - mn) / rng) for tid, s in results]


def _sasrec_confidence(results: list[tuple[str, float]]) -> float:
    """
    Measure SASRec confidence: how much the top scores stand out.
    Returns a value in [0, 1] — higher means more confident.
    """
    if len(results) < 3:
        return 0.0
    scores = sorted([s for _, s in results], reverse=True)
    top_mean = np.mean(scores[:3])
    rest_mean = np.mean(scores[3:]) if len(scores) > 3 else 0.0
    score_range = max(scores) - min(scores)
    if score_range < 1e-8:
        return 0.0
    # Confidence = how much top-3 exceeds the rest, normalized
    return min(1.0, (top_mean - rest_mean) / score_range)


def itemcf_recall(user_id: int, top_k: int = 100) -> list[tuple[str, float]]:
    """Recall candidates using ItemCF collaborative filtering."""
    model = _get_item_cf()
    if model is None:
        return []
    try:
        return model.recommend(user_id, top_k=top_k)
    except Exception as e:
        logger.warning(f"ItemCF recall failed: {e}")
        return []


def sasrec_recall(user_sequence: list[str], top_k: int = 100) -> list[tuple[str, float]]:
    """Recall candidates using SASRec sequential model."""
    model = _get_sasrec()
    if model is None or len(user_sequence) < 3:
        return []
    try:
        return model.recommend(user_sequence, top_k=top_k)
    except Exception as e:
        logger.warning(f"SASRec recall failed: {e}")
        return []


def popularity_recall(popular_tracks: list[dict], top_k: int = 50) -> list[tuple[str, float]]:
    """Fallback recall using popular tracks."""
    results = []
    for i, track in enumerate(popular_tracks[:top_k]):
        track_id = track.get("track_id") or track.get("id", "")
        score = 1.0 / (i + 1)  # Inverse rank score
        results.append((track_id, score))
    return results


def _get_adaptive_weights(
    seq_len: int,
    sasrec_available: bool = False,
) -> tuple[float, float, float]:
    """
    Adaptive weights based on user context.

    Returns (itemcf_w, sasrec_w, pop_w).

    Strategy:
    - Rich interaction + long sequence → trust both CF and sequential
    - Rich interaction + no sequence → heavy ItemCF
    - Long sequence only → trust SASRec, moderate ItemCF
    - Cold / sparse → rely on popularity
    """
    if seq_len >= 10 and sasrec_available:
        # Strong user: both models reliable, ItemCF still dominant
        return 1.5, 1.0, 0.1
    elif seq_len >= 10:
        # Strong user, no SASRec → heavy ItemCF
        return 1.5, 0.0, 0.2
    elif seq_len >= 3 and sasrec_available:
        # Moderate user: balanced blend
        return 1.2, 0.8, 0.2
    elif seq_len >= 3:
        # Moderate user, no SASRec
        return 1.2, 0.0, 0.3
    else:
        # Cold / sparse: mostly popularity, light ItemCF
        return 0.6, 0.0, 0.5


def multi_recall(
    user_id: Optional[int],
    user_sequence: Optional[list[str]] = None,
    popular_tracks: Optional[list[dict]] = None,
    itemcf_k: int = 100,
    sasrec_k: int = 100,
    popularity_k: int = 50,
) -> list[tuple[str, float, str]]:
    """
    Multi-channel recall with normalized score merging and quality gating.

    Returns:
        list of (track_id, score, source) tuples, deduplicated and sorted
    """
    candidates: dict[str, tuple[float, str]] = {}

    # 1. SASRec recall (with quality gating)
    sasrec_w = 0.0
    if user_sequence and len(user_sequence) >= 3:
        sasrec_results = _normalize_scores(sasrec_recall(user_sequence, top_k=sasrec_k))
        confidence = _sasrec_confidence(sasrec_results)
        # Only trust SASRec if it shows meaningful score differentiation
        sasrec_w = min(confidence * 2, 1.0)  # scale up, cap at 1.0
        if sasrec_w < 0.2:
            logger.debug(f"SASRec confidence too low ({confidence:.2f}), skipping SASRec candidates")
            sasrec_results = []
        else:
            logger.debug(f"SASRec confidence={confidence:.2f}, weight={sasrec_w:.2f}")
        for track_id, score in sasrec_results:
            candidates[track_id] = (score * sasrec_w, "sasrec")

    # 2. ItemCF recall (normalized)
    itemcf_w = 1.0  # ItemCF is the most reliable source
    if user_id is not None:
        itemcf_results = _normalize_scores(itemcf_recall(user_id, top_k=itemcf_k))
        for track_id, score in itemcf_results:
            weighted = score * itemcf_w
            if track_id not in candidates:
                candidates[track_id] = (weighted, "itemcf")
            else:
                existing_score = candidates[track_id][0]
                candidates[track_id] = (existing_score + weighted, "sasrec+itemcf")

    # 3. Popularity fallback (normalized)
    if popular_tracks:
        pop_results = _normalize_scores(popularity_recall(popular_tracks, top_k=popularity_k))
        for track_id, score in pop_results:
            if track_id not in candidates:
                candidates[track_id] = (score * pop_w, "popularity")

    # Sort by score descending
    result = [(tid, info[0], info[1]) for tid, info in candidates.items()]
    result.sort(key=lambda x: x[1], reverse=True)

    logger.debug(f"Multi-recall: {len(result)} candidates "
                 f"(user_id={user_id}, seq_len={len(user_sequence) if user_sequence else 0}, "
                 f"sasrec_w={sasrec_w:.2f})")

    return result
