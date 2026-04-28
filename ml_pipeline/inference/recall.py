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

SOURCE_ORDER = {
    "itemcf": 0,
    "sasrec": 1,
    "tag": 2,
    "popularity": 3,
}

RRF_K = 30
ITEMCF_ANCHOR_BIAS = 0.20
ITEMCF_RRF_WEIGHT = 0.50
SASREC_OVERLAP_WEIGHT = 0.05
SASREC_EXPLORE_WEIGHT = 0.01
TAG_EXPLORE_WEIGHT = 0.01
POPULARITY_EXPLORE_WEIGHT = 0.005
SASREC_CONFIDENCE_THRESHOLD = 0.20
PRIMARY_CANDIDATE_FLOOR = 80


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


def _rrf_score(rank: int, k: int = RRF_K) -> float:
    """Reciprocal rank fusion score."""
    return 1.0 / (k + rank + 1)


def _merge_ranked_candidates(
    candidates: dict[str, float],
    sources: dict[str, set[str]],
    results: list[tuple[str, float]],
    source_name: str,
    weight: float,
    *,
    anchor_bias: float = 0.0,
    allow_new: bool = True,
    max_new: int | None = None,
    seen_items: set[str] | None = None,
):
    """Merge a ranked list into fused candidates using conservative rank-based scoring."""
    added_new = 0
    for rank, (track_id, _) in enumerate(results):
        if seen_items and track_id in seen_items:
            continue

        delta = weight * _rrf_score(rank)
        if track_id in candidates:
            candidates[track_id] += delta
            sources[track_id].add(source_name)
            continue

        if not allow_new:
            continue
        if max_new is not None and added_new >= max_new:
            break

        candidates[track_id] = anchor_bias + delta
        sources[track_id] = {source_name}
        added_new += 1


def _format_source_label(source_names: set[str]) -> str:
    """Render merged source labels in stable priority order."""
    if not source_names:
        return "unknown"
    ordered = sorted(source_names, key=lambda name: SOURCE_ORDER.get(name, 99))
    return "+".join(ordered)


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
    candidates: dict[str, float] = {}
    candidate_sources: dict[str, set[str]] = {}
    seen_items = set(user_sequence or [])

    itemcf_results = itemcf_recall(user_id, top_k=itemcf_k) if user_id is not None else []

    sasrec_results: list[tuple[str, float]] = []
    sasrec_confidence = 0.0
    if user_sequence and len(user_sequence) >= 3:
        sasrec_results = sasrec_recall(user_sequence, top_k=sasrec_k)
        sasrec_confidence = _sasrec_confidence(sasrec_results)
        if sasrec_confidence < SASREC_CONFIDENCE_THRESHOLD:
            logger.debug(
                f"SASRec confidence too low ({sasrec_confidence:.2f}), keeping SASRec as fallback only"
            )
            sasrec_results = []

    if itemcf_results:
        # Warm users: keep ItemCF as the anchor, and only use SASRec as a light consensus signal.
        _merge_ranked_candidates(
            candidates,
            candidate_sources,
            itemcf_results,
            "itemcf",
            ITEMCF_RRF_WEIGHT,
            anchor_bias=ITEMCF_ANCHOR_BIAS,
            seen_items=seen_items,
        )

        if sasrec_results:
            _merge_ranked_candidates(
                candidates,
                candidate_sources,
                sasrec_results,
                "sasrec",
                SASREC_OVERLAP_WEIGHT,
                allow_new=len(itemcf_results) < PRIMARY_CANDIDATE_FLOOR,
                max_new=max(0, PRIMARY_CANDIDATE_FLOOR - len(itemcf_results)),
                seen_items=seen_items,
            )

        if user_sequence and len(user_sequence) >= 3 and len(candidates) < PRIMARY_CANDIDATE_FLOOR:
            tag_results = tag_based_recall(user_sequence, top_k=50)
            _merge_ranked_candidates(
                candidates,
                candidate_sources,
                tag_results,
                "tag",
                TAG_EXPLORE_WEIGHT,
                max_new=max(0, PRIMARY_CANDIDATE_FLOOR - len(candidates)),
                seen_items=seen_items,
            )
    else:
        # Sparse / sequence-only users: fall back to sequential + content/popularity recall.
        if sasrec_results:
            _merge_ranked_candidates(
                candidates,
                candidate_sources,
                sasrec_results,
                "sasrec",
                0.60,
                anchor_bias=0.10,
                seen_items=seen_items,
            )

        if user_sequence and len(user_sequence) >= 3:
            tag_results = tag_based_recall(user_sequence, top_k=50)
            _merge_ranked_candidates(
                candidates,
                candidate_sources,
                tag_results,
                "tag",
                0.15,
                seen_items=seen_items,
            )

    if popular_tracks and len(candidates) < max(popularity_k, PRIMARY_CANDIDATE_FLOOR):
        user_liked_ids = set(user_sequence or [])
        pop_results = genre_weighted_popularity_recall(
            popular_tracks,
            user_liked_track_ids=user_liked_ids if user_liked_ids else None,
            top_k=popularity_k,
            max_per_genre=5,
        )
        _merge_ranked_candidates(
            candidates,
            candidate_sources,
            pop_results,
            "popularity",
            POPULARITY_EXPLORE_WEIGHT if itemcf_results else 0.08,
            max_new=max(0, max(popularity_k, PRIMARY_CANDIDATE_FLOOR) - len(candidates)),
            seen_items=seen_items,
        )

    result = [
        (track_id, score, _format_source_label(candidate_sources.get(track_id, set())))
        for track_id, score in candidates.items()
    ]
    result.sort(key=lambda x: x[1], reverse=True)

    logger.debug(f"Multi-recall: {len(result)} candidates "
                 f"(user_id={user_id}, seq_len={len(user_sequence) if user_sequence else 0}, "
                 f"sasrec_conf={sasrec_confidence:.2f}, itemcf={len(itemcf_results)})")

    return result
