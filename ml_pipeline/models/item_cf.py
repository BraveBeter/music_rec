"""
Item-based Collaborative Filtering (ItemCF).
Computes item-item similarity using cosine similarity on the user-item interaction matrix.
"""
import os
import sys
import logging
import json

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, MODEL_DIR, TOP_K

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class ItemCF:
    """Item-based Collaborative Filtering model."""

    def __init__(self, top_k_similar: int = 50):
        self.top_k_similar = top_k_similar
        self.item_sim_matrix: np.ndarray | None = None
        self.user_item_matrix: csr_matrix | None = None
        self.num_users = 0
        self.num_items = 0
        self.user2idx: dict = {}
        self.track2idx: dict = {}
        self.idx2track: dict = {}

    def fit(self, interactions: pd.DataFrame, user2idx: dict, track2idx: dict):
        """
        Build item-item similarity matrix.
        
        Args:
            interactions: DataFrame with user_idx, track_idx, label columns
            user2idx: user_id -> user_idx mapping
            track2idx: track_id -> track_idx mapping
        """
        self.user2idx = {int(k): int(v) for k, v in user2idx.items()}
        self.track2idx = {str(k): int(v) for k, v in track2idx.items()}
        self.idx2track = {v: k for k, v in self.track2idx.items()}
        self.num_users = len(user2idx)
        self.num_items = len(track2idx)

        # Build user-item matrix (only positive interactions)
        positive = interactions[interactions["label"] == 1]

        # Implicit feedback: use completion_rate as weight if available
        if "completion_rate" in positive.columns:
            values = positive["completion_rate"].fillna(1.0).values
        else:
            values = np.ones(len(positive))

        user_indices = positive["user_idx"].values.astype(int)
        item_indices = positive["track_idx"].values.astype(int)

        self.user_item_matrix = csr_matrix(
            (values, (user_indices, item_indices)),
            shape=(self.num_users, self.num_items),
        )

        logger.info(f"User-item matrix: {self.user_item_matrix.shape}, "
                     f"nnz={self.user_item_matrix.nnz}")

        # Compute item-item cosine similarity
        logger.info("Computing item-item cosine similarity...")
        item_matrix = self.user_item_matrix.T  # items × users
        self.item_sim_matrix = cosine_similarity(item_matrix)

        # Zero out self-similarity
        np.fill_diagonal(self.item_sim_matrix, 0)

        logger.info(f"Item similarity matrix: {self.item_sim_matrix.shape}")

    def recommend(self, user_id: int, top_k: int = TOP_K, exclude_seen: bool = True) -> list[tuple[str, float]]:
        """
        Recommend top-K items for a user.
        
        Returns:
            list of (track_id, score) tuples
        """
        if self.item_sim_matrix is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        user_idx = self.user2idx.get(int(user_id))
        if user_idx is None:
            return []

        # Get user's interacted items
        user_items = self.user_item_matrix[user_idx].toarray().flatten()
        interacted_indices = np.nonzero(user_items)[0]

        if len(interacted_indices) == 0:
            return []

        # Score all items: sum of similarity to user's items, weighted by user's rating
        scores = np.zeros(self.num_items)
        for item_idx in interacted_indices:
            weight = user_items[item_idx]
            scores += self.item_sim_matrix[item_idx] * weight

        # Exclude already seen items
        if exclude_seen:
            scores[interacted_indices] = -np.inf

        # Top-K
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                break
            track_id = self.idx2track.get(idx, str(idx))
            results.append((track_id, float(scores[idx])))

        return results

    def get_similar_items(self, track_id: str, top_k: int = 20) -> list[tuple[str, float]]:
        """Get most similar items to a given track."""
        track_idx = self.track2idx.get(track_id)
        if track_idx is None or self.item_sim_matrix is None:
            return []

        sim_scores = self.item_sim_matrix[track_idx]
        top_indices = np.argsort(sim_scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if sim_scores[idx] <= 0:
                break
            tid = self.idx2track.get(idx, str(idx))
            results.append((tid, float(sim_scores[idx])))

        return results

    def save(self, path: str | None = None):
        """Save model to disk."""
        save_dir = path or os.path.join(MODEL_DIR, "item_cf")
        os.makedirs(save_dir, exist_ok=True)

        np.save(os.path.join(save_dir, "item_sim_matrix.npy"), self.item_sim_matrix)
        from scipy.sparse import save_npz
        save_npz(os.path.join(save_dir, "user_item_matrix.npz"), self.user_item_matrix)

        meta = {
            "num_users": self.num_users,
            "num_items": self.num_items,
            "top_k_similar": self.top_k_similar,
        }
        with open(os.path.join(save_dir, "meta.json"), "w") as f:
            json.dump(meta, f)

        logger.info(f"ItemCF model saved to {save_dir}")

    def load(self, path: str | None = None):
        """Load model from disk."""
        load_dir = path or os.path.join(MODEL_DIR, "item_cf")

        self.item_sim_matrix = np.load(os.path.join(load_dir, "item_sim_matrix.npy"))
        from scipy.sparse import load_npz
        self.user_item_matrix = load_npz(os.path.join(load_dir, "user_item_matrix.npz"))

        with open(os.path.join(load_dir, "meta.json")) as f:
            meta = json.load(f)
        self.num_users = meta["num_users"]
        self.num_items = meta["num_items"]

        user2idx_df = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet"))
        track2idx_df = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet"))
        self.user2idx = {int(k): int(v) for k, v in user2idx_df.values}
        self.track2idx = {str(k): int(v) for k, v in track2idx_df.values}
        self.idx2track = {v: k for k, v in self.track2idx.items()}

        logger.info(f"ItemCF model loaded from {load_dir}")
