"""
Recall Module: Multi-channel recall for recommendation candidates.
Combines ItemCF, SASRec, and popularity-based recall.
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
    Multi-channel recall with adaptive weights: merge candidates
    from multiple sources, weighting each source by user context.

    Returns:
        list of (track_id, score, source) tuples, deduplicated
    """
    candidates: dict[str, tuple[float, str]] = {}

    seq_len = len(user_sequence) if user_sequence else 0
    sasrec_ok = seq_len >= 3
    itemcf_w, sasrec_w, pop_w = _get_adaptive_weights(seq_len, sasrec_ok)

    # 1. SASRec recall
    if sasrec_w > 0 and user_sequence and seq_len >= 3:
        sasrec_results = sasrec_recall(user_sequence, top_k=sasrec_k)
        for track_id, score in sasrec_results:
            candidates[track_id] = (score * sasrec_w, "sasrec")

    # 2. ItemCF recall
    if itemcf_w > 0 and user_id is not None:
        itemcf_results = itemcf_recall(user_id, top_k=itemcf_k)
        for track_id, score in itemcf_results:
            weighted_score = score * itemcf_w
            if track_id not in candidates:
                candidates[track_id] = (weighted_score, "itemcf")
            else:
                existing_score = candidates[track_id][0]
                candidates[track_id] = (existing_score + weighted_score, "sasrec+itemcf")

    # 3. Popularity fallback
    if pop_w > 0 and popular_tracks:
        pop_results = popularity_recall(popular_tracks, top_k=popularity_k)
        for track_id, score in pop_results:
            if track_id not in candidates:
                candidates[track_id] = (score * pop_w, "popularity")

    # Sort by score descending
    result = [(tid, info[0], info[1]) for tid, info in candidates.items()]
    result.sort(key=lambda x: x[1], reverse=True)

    logger.debug(f"Multi-recall: {len(result)} candidates "
                 f"(user_id={user_id}, seq_len={seq_len}, "
                 f"w=[itemcf={itemcf_w}, sasrec={sasrec_w}, pop={pop_w}])")

    return result
