"""
Recommendation Pipeline: orchestrates recall → ranking → output.
This is the main entry point for online recommendation inference.
"""
import os
import sys
import json
import logging
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ml_pipeline.inference.recall import multi_recall
from ml_pipeline.inference.ranking import rank_candidates
from ml_pipeline.config import MODEL_DIR, PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Check if models exist
def _models_available() -> dict[str, bool]:
    """Check which models are available on disk."""
    return {
        "item_cf": os.path.exists(os.path.join(MODEL_DIR, "item_cf", "meta.json")),
        "svd": os.path.exists(os.path.join(MODEL_DIR, "svd", "meta.json")),
        "deepfm": os.path.exists(os.path.join(MODEL_DIR, "deepfm", "meta.json")),
        "sasrec": os.path.exists(os.path.join(MODEL_DIR, "sasrec", "meta.json")),
        "deepfm_onnx": os.path.exists(os.path.join(MODEL_DIR, "deepfm", "deepfm_model.onnx")),
    }


_track_genre_map_cache = None


def _load_track_genre_map() -> dict[str, list[str]]:
    """Lazy-load track genre mapping for MMR."""
    global _track_genre_map_cache
    if _track_genre_map_cache is not None:
        return _track_genre_map_cache
    try:
        path = os.path.join(PROCESSED_DATA_DIR, "track_genres.json")
        if os.path.exists(path):
            with open(path) as f:
                _track_genre_map_cache = json.load(f)
        else:
            _track_genre_map_cache = {}
    except Exception:
        _track_genre_map_cache = {}
    return _track_genre_map_cache


def apply_mmr_rerank(
    ranked_items: list[tuple[str, float]],
    lambda_param: float = 0.7,
    max_per_genre: int = 3,
    top_k: int = 20,
) -> list[tuple[str, float]]:
    """
    Apply MMR-style re-ranking for genre diversity.
    Balances relevance score with genre novelty.
    """
    track_genres = _load_track_genre_map()
    if not track_genres:
        return ranked_items[:top_k]

    selected: list[tuple[str, float]] = []
    selected_genres: dict[str, int] = {}
    remaining = list(ranked_items)

    while remaining and len(selected) < top_k:
        best_idx = -1
        best_mmr = -float('inf')

        for i, (track_id, score) in enumerate(remaining):
            genres = track_genres.get(track_id, [])
            primary_genre = genres[0] if genres else "unknown"

            if selected_genres.get(primary_genre, 0) >= max_per_genre:
                continue

            diversity_penalty = 0.0
            if selected:
                for sel_tid, _ in selected:
                    sel_genres = set(track_genres.get(sel_tid, []))
                    overlap = len(set(genres) & sel_genres)
                    union = len(set(genres) | sel_genres)
                    if union > 0:
                        diversity_penalty += overlap / union
                diversity_penalty /= len(selected)

            mmr_score = lambda_param * score - (1 - lambda_param) * diversity_penalty

            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = i

        if best_idx == -1:
            # All remaining hit genre caps; relax and continue
            max_per_genre += 1
            continue

        track_id, score = remaining.pop(best_idx)
        selected.append((track_id, score))
        genres = track_genres.get(track_id, [])
        primary_genre = genres[0] if genres else "unknown"
        selected_genres[primary_genre] = selected_genres.get(primary_genre, 0) + 1

    return selected


def recommend(
    user_id: Optional[int],
    user_sequence: Optional[list[str]] = None,
    popular_tracks: Optional[list[dict]] = None,
    top_k: int = 20,
    use_onnx: bool = False,
) -> dict:
    """
    Full recommendation pipeline: recall → rank → output.
    
    Args:
        user_id: user ID (None for anonymous)
        user_sequence: recent play sequence from Redis
        popular_tracks: fallback popular tracks list
        top_k: number of items to return
        use_onnx: use ONNX runtime for DeepFM ranking
    
    Returns:
        dict with strategy, items list, and metadata
    """
    models = _models_available()
    has_any_model = any(models.values())

    if not has_any_model:
        # No trained models — pure cold-start
        return {
            "strategy": "popularity_cold_start",
            "is_fallback": True,
            "items": [],  # caller should fill with popular tracks
            "debug": {"models_available": models},
        }

    # Determine strategy based on user context
    has_sequence = user_sequence and len(user_sequence) >= 3
    is_cold_user = not has_sequence and (user_id is None)

    if is_cold_user:
        strategy = "cold_start_popular"
    elif has_sequence and models.get("sasrec"):
        strategy = "sasrec_deepfm" if models.get("deepfm") else "sasrec_only"
    elif models.get("item_cf"):
        strategy = "itemcf_deepfm" if models.get("deepfm") else "itemcf_only"
    else:
        strategy = "popularity_fallback"

    # --- Step 1: Recall ---
    recall_results = multi_recall(
        user_id=user_id,
        user_sequence=user_sequence,
        popular_tracks=popular_tracks or [],
        itemcf_k=150,
        sasrec_k=150,
        popularity_k=50,
    )

    if not recall_results:
        return {
            "strategy": "popularity_cold_start",
            "is_fallback": True,
            "items": [],
            "debug": {"reason": "empty_recall", "models_available": models},
        }

    # --- Step 2: Rank ---
    candidate_ids = [r[0] for r in recall_results]
    recall_scores = {r[0]: r[1] for r in recall_results}

    if models.get("deepfm") and user_id is not None:
        try:
            ranked = rank_candidates(
                user_id=user_id,
                candidate_track_ids=candidate_ids,
                recall_scores=recall_scores,
                top_k=top_k,
                use_onnx=use_onnx and models.get("deepfm_onnx", False),
            )
        except Exception as e:
            logger.warning(f"Ranking failed, using recall order: {e}")
            ranked = [(tid, score) for tid, score, _ in recall_results[:top_k]]
    else:
        # No ranking model, use recall scores
        ranked = [(tid, score) for tid, score, _ in recall_results[:top_k]]

    # --- Step 2.5: Diversity re-ranking ---
    if ranked:
        ranked = apply_mmr_rerank(
            ranked,
            lambda_param=0.7,
            max_per_genre=3,
            top_k=top_k,
        )

    # --- Step 3: Format output ---
    items = [{"track_id": tid, "score": score} for tid, score in ranked]

    return {
        "strategy": strategy,
        "is_fallback": strategy.startswith("cold_start") or strategy.startswith("popularity"),
        "items": items,
        "debug": {
            "models_available": models,
            "recall_count": len(recall_results),
            "ranked_count": len(ranked),
            "user_seq_len": len(user_sequence) if user_sequence else 0,
        },
    }
