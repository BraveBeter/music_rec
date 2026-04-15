"""
Recall Module: Multi-channel recall for recommendation candidates.
Combines ItemCF, SASRec, tag-based, and popularity-based recall with score normalization.
"""
import os
import sys
import json
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
_track_genre_map = None
_genre_tracks_map = None


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


def _load_track_genre_map() -> dict[str, list[str]]:
    """Lazy-load track -> genre names mapping."""
    global _track_genre_map
    if _track_genre_map is not None:
        return _track_genre_map
    try:
        path = os.path.join(PROCESSED_DATA_DIR, "track_genres.json")
        if os.path.exists(path):
            with open(path) as f:
                _track_genre_map = json.load(f)
        else:
            _track_genre_map = {}
    except Exception:
        _track_genre_map = {}
    return _track_genre_map


def _load_genre_tracks_map() -> dict[str, list[str]]:
    """Lazy-load genre -> track_ids mapping."""
    global _genre_tracks_map
    if _genre_tracks_map is not None:
        return _genre_tracks_map
    try:
        path = os.path.join(PROCESSED_DATA_DIR, "genre_tracks.json")
        if os.path.exists(path):
            with open(path) as f:
                _genre_tracks_map = json.load(f)
        else:
            _genre_tracks_map = {}
    except Exception:
        _genre_tracks_map = {}
    return _genre_tracks_map


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


def tag_based_recall(
    user_sequence: list[str],
    top_k: int = 50,
) -> list[tuple[str, float]]:
    """
    Recall candidates based on user's preferred tags (genres).
    Uses the user's play sequence to identify preferred genres,
    then returns tracks from those genres weighted by affinity.
    """
    track_genres = _load_track_genre_map()
    genre_tracks = _load_genre_tracks_map()
    if not track_genres or not genre_tracks or not user_sequence:
        return []

    # Count genre frequency in user's sequence
    genre_freq: dict[str, int] = {}
    for tid in user_sequence:
        for genre in track_genres.get(tid, []):
            genre_freq[genre] = genre_freq.get(genre, 0) + 1

    if not genre_freq:
        return []

    total = sum(genre_freq.values())
    seen = set(user_sequence)
    candidates: dict[str, float] = {}

    for genre, freq in genre_freq.items():
        genre_weight = freq / total
        for track_id in genre_tracks.get(genre, []):
            if track_id in seen or track_id in candidates:
                continue
            candidates[track_id] = genre_weight

    sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
    return sorted_candidates[:top_k]


def genre_weighted_popularity_recall(
    popular_tracks: list[dict],
    user_liked_track_ids: set[str] | None = None,
    top_k: int = 50,
    max_per_genre: int = 5,
) -> list[tuple[str, float]]:
    """
    Popularity recall with genre diversity and user preference weighting.
    Limits per-genre representation and boosts genres the user likes.
    """
    track_genres = _load_track_genre_map()
    if not track_genres:
        return popularity_recall(popular_tracks, top_k=top_k)

    # Count user's genre preferences from their history
    user_genre_weight: dict[str, float] = {}
    if user_liked_track_ids:
        genre_count: dict[str, float] = {}
        for tid in user_liked_track_ids:
            for genre in track_genres.get(tid, []):
                genre_count[genre] = genre_count.get(genre, 0) + 1
        total = sum(genre_count.values()) or 1
        user_genre_weight = {g: c / total for g, c in genre_count.items()}

    genre_counts: dict[str, int] = {}
    results = []
    for i, track in enumerate(popular_tracks[:top_k * 3]):
        track_id = track.get("track_id") or track.get("id", "")
        genres = track_genres.get(track_id, [])

        dominant_genre = genres[0] if genres else "unknown"
        if genre_counts.get(dominant_genre, 0) >= max_per_genre:
            continue
        genre_counts[dominant_genre] = genre_counts.get(dominant_genre, 0) + 1

        base_score = 1.0 / (i + 1)
        genre_boost = max((user_genre_weight.get(g, 0) for g in genres), default=0) if user_genre_weight else 0
        score = base_score * (1.0 + genre_boost * 2.0)

        results.append((track_id, score))
        if len(results) >= top_k:
            break

    return results


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

    # 2.5 Tag-based recall (genre preference from user sequence)
    if user_sequence and len(user_sequence) >= 3:
        tag_results = _normalize_scores(tag_based_recall(user_sequence, top_k=50))
        tag_w = 0.5
        for track_id, score in tag_results:
            weighted = score * tag_w
            if track_id not in candidates:
                candidates[track_id] = (weighted, "tag")
            else:
                existing_score = candidates[track_id][0]
                candidates[track_id] = (existing_score + weighted, candidates[track_id][1])

    # 3. Popularity fallback (genre-aware)
    if popular_tracks:
        user_liked_ids = {tid for tid in candidates} if candidates else None
        pop_results = _normalize_scores(
            genre_weighted_popularity_recall(
                popular_tracks,
                user_liked_track_ids=user_liked_ids,
                top_k=popularity_k,
                max_per_genre=5,
            )
        )
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
