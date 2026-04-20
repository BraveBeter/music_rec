"""
Item-based Collaborative Filtering (ItemCF).
Computes item-item similarity using cosine similarity on the user-item interaction matrix.
Uses sparse top-K storage to keep memory manageable for large catalogs.
"""
import os
import sys
import logging
import json

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, lil_matrix

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, MODEL_DIR, TOP_K

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class ItemCF:
    """Item-based Collaborative Filtering model with sparse top-K similarity."""

    def __init__(self, top_k_similar: int = 50):
        self.top_k_similar = top_k_similar
        # Sparse storage: item_idx -> [(similar_item_idx, score), ...]
        self.item_sim_topk: dict[int, list[tuple[int, float]]] = {}
        self.user_item_matrix: csr_matrix | None = None
        self.num_users = 0
        self.num_items = 0
        self.user2idx: dict = {}
        self.track2idx: dict = {}
        self.idx2track: dict = {}

    def fit(self, interactions: pd.DataFrame, user2idx: dict, track2idx: dict):
        """
        Build item-item similarity matrix (top-K sparse).

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

        # Compute top-K similarity per item in batches to limit memory
        logger.info(f"Computing top-{self.top_k_similar} item similarity (batched)...")
        self.item_sim_topk = {}

        # Normalize item vectors (rows of item_matrix) for cosine similarity
        item_matrix = self.user_item_matrix.T  # items × users, sparse
        # Pre-compute norms
        norms = np.sqrt(np.asarray(item_matrix.power(2).sum(axis=1)).flatten())
        norms[norms == 0] = 1.0  # avoid division by zero

        batch_size = 500
        k = min(self.top_k_similar, self.num_items - 1)

        for start in range(0, self.num_items, batch_size):
            end = min(start + batch_size, self.num_items)
            # Compute similarity of batch items to ALL items
            batch = item_matrix[start:end]  # sparse slice
            # cosine_sim = batch @ item_matrix.T / (norms_batch * norms_all)
            sim = batch.dot(item_matrix.T).toarray()  # (batch_size, num_items) dense
            # Normalize
            batch_norms = norms[start:end, np.newaxis]
            sim = sim / (batch_norms * norms[np.newaxis, :] + 1e-10)

            # Zero self-similarity
            for i in range(end - start):
                global_idx = start + i
                sim[i, global_idx] = 0.0

            # Keep top-K
            for i in range(end - start):
                global_idx = start + i
                row = sim[i]
                top_indices = np.argpartition(row, -k)[-k:]
                top_indices = top_indices[np.argsort(row[top_indices])[::-1]]
                self.item_sim_topk[global_idx] = [
                    (int(idx), float(row[idx])) for idx in top_indices if row[idx] > 0
                ]

            if (start // batch_size) % 10 == 0:
                logger.info(f"  Similarity batch {start}-{end}/{self.num_items}")

        total_entries = sum(len(v) for v in self.item_sim_topk.values())
        logger.info(f"Item similarity: {len(self.item_sim_topk)} items, {total_entries} top-K pairs")

    def recommend(self, user_id: int, top_k: int = TOP_K, exclude_seen: bool = True) -> list[tuple[str, float]]:
        """
        Recommend top-K items for a user.

        Returns:
            list of (track_id, score) tuples
        """
        if not self.item_sim_topk:
            raise RuntimeError("Model not fitted. Call fit() first.")

        user_idx = self.user2idx.get(int(user_id))
        if user_idx is None:
            return []

        # Get user's interacted items
        user_items = self.user_item_matrix[user_idx].toarray().flatten()
        interacted_indices = np.nonzero(user_items)[0]

        if len(interacted_indices) == 0:
            return []

        # Score items using sparse top-K similarity
        scores: dict[int, float] = {}
        for item_idx in interacted_indices:
            weight = user_items[item_idx]
            for sim_idx, sim_score in self.item_sim_topk.get(item_idx, []):
                scores[sim_idx] = scores.get(sim_idx, 0.0) + sim_score * weight

        # Exclude already seen items
        if exclude_seen:
            for idx in interacted_indices:
                scores.pop(idx, None)

        # Top-K
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = []
        for idx, score in sorted_items:
            if score <= 0:
                break
            track_id = self.idx2track.get(idx, str(idx))
            results.append((track_id, float(score)))

        return results

    def get_similar_items(self, track_id: str, top_k: int = 20) -> list[tuple[str, float]]:
        """Get most similar items to a given track."""
        track_idx = self.track2idx.get(track_id)
        if track_idx is None or track_idx not in self.item_sim_topk:
            return []

        sims = self.item_sim_topk[track_idx][:top_k]
        return [(self.idx2track.get(idx, str(idx)), score) for idx, score in sims if score > 0]

    def save(self, path: str | None = None):
        """Save model to disk."""
        save_dir = path or os.path.join(MODEL_DIR, "item_cf")
        os.makedirs(save_dir, exist_ok=True)

        from scipy.sparse import save_npz
        save_npz(os.path.join(save_dir, "user_item_matrix.npz"), self.user_item_matrix)

        # Save top-K similarity as JSON (keys as strings for JSON compatibility)
        sim_serializable = {
            str(k): [(int(i), round(s, 6)) for i, s in v]
            for k, v in self.item_sim_topk.items()
        }
        with open(os.path.join(save_dir, "item_sim_topk.json"), "w") as f:
            json.dump(sim_serializable, f)

        meta = {
            "num_users": self.num_users,
            "num_items": self.num_items,
            "top_k_similar": self.top_k_similar,
        }
        with open(os.path.join(save_dir, "meta.json"), "w") as f:
            json.dump(meta, f)

        # Save ID mappings so inference uses training-time indices
        pd.DataFrame(list(self.user2idx.items()), columns=["user_id", "idx"]).to_parquet(
            os.path.join(save_dir, "user2idx.parquet"), index=False
        )
        pd.DataFrame(list(self.track2idx.items()), columns=["track_id", "idx"]).to_parquet(
            os.path.join(save_dir, "track2idx.parquet"), index=False
        )

        logger.info(f"ItemCF model saved to {save_dir}")

    def load(self, path: str | None = None):
        """Load model from disk."""
        load_dir = path or os.path.join(MODEL_DIR, "item_cf")

        from scipy.sparse import load_npz
        self.user_item_matrix = load_npz(os.path.join(load_dir, "user_item_matrix.npz"))

        with open(os.path.join(load_dir, "meta.json")) as f:
            meta = json.load(f)
        self.num_users = meta["num_users"]
        self.num_items = meta["num_items"]

        with open(os.path.join(load_dir, "item_sim_topk.json")) as f:
            sim_data = json.load(f)
        self.item_sim_topk = {int(k): [(int(i), s) for i, s in v] for k, v in sim_data.items()}

        # Load ID mappings from model directory (training-time mapping)
        saved_user = os.path.join(load_dir, "user2idx.parquet")
        saved_track = os.path.join(load_dir, "track2idx.parquet")
        if os.path.exists(saved_user) and os.path.exists(saved_track):
            self.user2idx = dict(pd.read_parquet(saved_user).values)
            self.track2idx = dict(pd.read_parquet(saved_track).values)
        else:
            # Fallback for models saved before this fix
            user2idx_df = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet"))
            track2idx_df = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet"))
            self.user2idx = {int(k): int(v) for k, v in user2idx_df.values}
            self.track2idx = {str(k): int(v) for k, v in track2idx_df.values}
        self.idx2track = {v: k for k, v in self.track2idx.items()}

        logger.info(f"ItemCF model loaded from {load_dir} "
                     f"({self.num_items} items, {len(self.item_sim_topk)} with similarity data)")
