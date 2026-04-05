"""
SVD Matrix Factorization (BPR-MF).
PyTorch implementation with Bayesian Personalized Ranking loss.
Learns user and item embeddings for recommendation.
"""
import os
import sys
import logging
import json

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, MODEL_DIR, EMBEDDING_DIM, LEARNING_RATE, BATCH_SIZE, EPOCHS, TOP_K

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class BPRDataset(Dataset):
    """BPR triplet dataset: (user, positive_item, negative_item)"""

    def __init__(self, interactions: pd.DataFrame, num_items: int):
        self.users = interactions["user_idx"].values.astype(np.int64)
        self.pos_items = interactions["track_idx"].values.astype(np.int64)
        self.num_items = num_items

        # Build user positive sets for negative sampling
        self.user_pos = {}
        for u, i in zip(self.users, self.pos_items):
            if u not in self.user_pos:
                self.user_pos[u] = set()
            self.user_pos[u].add(i)

    def __len__(self):
        return len(self.users)

    def __getitem__(self, idx):
        user = self.users[idx]
        pos_item = self.pos_items[idx]

        # Random negative sampling
        neg_item = np.random.randint(0, self.num_items)
        while neg_item in self.user_pos.get(user, set()):
            neg_item = np.random.randint(0, self.num_items)

        return (
            torch.tensor(user, dtype=torch.long),
            torch.tensor(pos_item, dtype=torch.long),
            torch.tensor(neg_item, dtype=torch.long),
        )


class MatrixFactorization(nn.Module):
    """BPR Matrix Factorization model."""

    def __init__(self, num_users: int, num_items: int, embedding_dim: int = EMBEDDING_DIM):
        super().__init__()
        self.num_users = num_users
        self.num_items = num_items
        self.embedding_dim = embedding_dim

        self.user_embedding = nn.Embedding(num_users, embedding_dim)
        self.item_embedding = nn.Embedding(num_items, embedding_dim)
        self.user_bias = nn.Embedding(num_users, 1)
        self.item_bias = nn.Embedding(num_items, 1)

        # Xavier initialization
        nn.init.xavier_normal_(self.user_embedding.weight)
        nn.init.xavier_normal_(self.item_embedding.weight)
        nn.init.zeros_(self.user_bias.weight)
        nn.init.zeros_(self.item_bias.weight)

    def forward(self, user_ids, item_ids):
        """Compute user-item scores."""
        user_emb = self.user_embedding(user_ids)
        item_emb = self.item_embedding(item_ids)
        u_bias = self.user_bias(user_ids).squeeze()
        i_bias = self.item_bias(item_ids).squeeze()

        score = (user_emb * item_emb).sum(dim=-1) + u_bias + i_bias
        return score

    def bpr_loss(self, user_ids, pos_ids, neg_ids, reg_lambda=1e-5):
        """BPR loss: maximize difference between positive and negative item scores."""
        pos_score = self.forward(user_ids, pos_ids)
        neg_score = self.forward(user_ids, neg_ids)

        loss = -torch.log(torch.sigmoid(pos_score - neg_score) + 1e-8).mean()

        # L2 regularization
        reg = reg_lambda * (
            self.user_embedding(user_ids).norm(2).pow(2) +
            self.item_embedding(pos_ids).norm(2).pow(2) +
            self.item_embedding(neg_ids).norm(2).pow(2)
        ) / user_ids.shape[0]

        return loss + reg

    def predict_all(self, user_idx: int) -> np.ndarray:
        """Predict scores for all items for a given user."""
        self.eval()
        with torch.no_grad():
            user_tensor = torch.tensor([user_idx], dtype=torch.long)
            user_emb = self.user_embedding(user_tensor)  # (1, emb)
            all_items = torch.arange(self.num_items)
            item_emb = self.item_embedding(all_items)  # (num_items, emb)
            u_bias = self.user_bias(user_tensor)  # (1, 1)
            i_bias = self.item_bias(all_items).squeeze()  # (num_items,)

            scores = (user_emb * item_emb).sum(dim=-1) + u_bias.squeeze() + i_bias
        return scores.numpy()

    def get_item_embeddings(self) -> np.ndarray:
        """Get all item embeddings for FAISS indexing."""
        return self.item_embedding.weight.detach().numpy()

    def get_user_embeddings(self) -> np.ndarray:
        """Get all user embeddings."""
        return self.user_embedding.weight.detach().numpy()


class SVDRecommender:
    """Wrapper for training and inference with the MF model."""

    def __init__(self, embedding_dim: int = EMBEDDING_DIM):
        self.embedding_dim = embedding_dim
        self.model: MatrixFactorization | None = None
        self.user2idx: dict = {}
        self.track2idx: dict = {}
        self.idx2track: dict = {}

    def fit(
        self,
        train_interactions: pd.DataFrame,
        val_interactions: pd.DataFrame | None = None,
        user2idx: dict = None,
        track2idx: dict = None,
        epochs: int = EPOCHS,
        batch_size: int = BATCH_SIZE,
        lr: float = LEARNING_RATE,
    ):
        """Train the model."""
        self.user2idx = {int(k): int(v) for k, v in (user2idx or {}).items()}
        self.track2idx = {str(k): int(v) for k, v in (track2idx or {}).items()}
        self.idx2track = {v: k for k, v in self.track2idx.items()}

        num_users = len(self.user2idx)
        num_items = len(self.track2idx)

        # Only positive interactions for BPR
        pos_train = train_interactions[train_interactions["label"] == 1].copy()

        self.model = MatrixFactorization(num_users, num_items, self.embedding_dim)
        optimizer = optim.Adam(self.model.parameters(), lr=lr, weight_decay=1e-6)

        dataset = BPRDataset(pos_train, num_items)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)

        self.model.train()
        best_loss = float("inf")

        for epoch in range(epochs):
            total_loss = 0.0
            for user, pos, neg in loader:
                optimizer.zero_grad()
                loss = self.model.bpr_loss(user, pos, neg)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

            avg_loss = total_loss / len(loader)
            if (epoch + 1) % 5 == 0 or epoch == 0:
                logger.info(f"Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.4f}")

            if avg_loss < best_loss:
                best_loss = avg_loss

        logger.info(f"Training complete. Best loss: {best_loss:.4f}")

    def recommend(self, user_id: int, top_k: int = TOP_K, exclude_seen: bool = True,
                  seen_items: set | None = None) -> list[tuple[str, float]]:
        """Recommend top-K items for a user."""
        if self.model is None:
            raise RuntimeError("Model not trained.")

        user_idx = self.user2idx.get(int(user_id))
        if user_idx is None:
            return []

        scores = self.model.predict_all(user_idx)

        if exclude_seen and seen_items:
            for tid in seen_items:
                tidx = self.track2idx.get(tid)
                if tidx is not None:
                    scores[tidx] = -np.inf

        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] <= -1e8:
                break
            track_id = self.idx2track.get(idx, str(idx))
            results.append((track_id, float(scores[idx])))

        return results

    def save(self, path: str | None = None):
        save_dir = path or os.path.join(MODEL_DIR, "svd")
        os.makedirs(save_dir, exist_ok=True)

        torch.save(self.model.state_dict(), os.path.join(save_dir, "svd_model.pt"))

        meta = {
            "num_users": self.model.num_users,
            "num_items": self.model.num_items,
            "embedding_dim": self.embedding_dim,
        }
        with open(os.path.join(save_dir, "meta.json"), "w") as f:
            json.dump(meta, f)

        # Save embeddings for FAISS
        np.save(os.path.join(save_dir, "item_embeddings.npy"), self.model.get_item_embeddings())
        np.save(os.path.join(save_dir, "user_embeddings.npy"), self.model.get_user_embeddings())

        logger.info(f"SVD model saved to {save_dir}")

    def load(self, path: str | None = None):
        load_dir = path or os.path.join(MODEL_DIR, "svd")

        with open(os.path.join(load_dir, "meta.json")) as f:
            meta = json.load(f)

        self.model = MatrixFactorization(
            meta["num_users"], meta["num_items"], meta["embedding_dim"]
        )
        self.model.load_state_dict(torch.load(
            os.path.join(load_dir, "svd_model.pt"), weights_only=True
        ))
        self.model.eval()
        self.embedding_dim = meta["embedding_dim"]

        # Reload ID mappings — cast keys to native Python int
        user2idx_df = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet"))
        track2idx_df = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet"))
        self.user2idx = {int(k): int(v) for k, v in user2idx_df.values}
        self.track2idx = {str(k): int(v) for k, v in track2idx_df.values}
        self.idx2track = {v: k for k, v in self.track2idx.items()}

        logger.info(f"SVD model loaded from {load_dir}")
