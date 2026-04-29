"""
SASRec: Self-Attentive Sequential Recommendation.
A left-to-right unidirectional Transformer model for next-item prediction.
Reference: Kang & McAuley, "Self-Attentive Sequential Recommendation", ICDM 2018.
"""
import os
import sys
import logging
import json
import math

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import (
    PROCESSED_DATA_DIR, MODEL_DIR, EMBEDDING_DIM,
    LEARNING_RATE, BATCH_SIZE, EPOCHS, MAX_SEQ_LEN,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class SASRecDataset(Dataset):
    """Dataset for SASRec: each sample = (input_seq, positive_target, negative_target).

    Item indices are offset by +1 so that 0 is reserved for padding.
    """

    def __init__(
        self,
        sequences: dict[str, list[str]],
        track2idx: dict,
        max_len: int = MAX_SEQ_LEN,
        num_negatives: int = 3,
    ):
        self.max_len = max_len
        self.num_items = len(track2idx)
        self.track2idx = track2idx
        self.num_negatives = max(1, num_negatives)
        self.samples = []
        # Collect all positive items for hard-negative sampling
        self.all_items = np.arange(1, self.num_items + 1)

        for user_id, seq in sequences.items():
            # Convert to indices (+1 offset to avoid padding collision)
            idx_seq = [track2idx[tid] + 1 for tid in seq if tid in track2idx]
            if len(idx_seq) < 3:
                continue

            # Remove consecutive duplicates to reduce noise
            deduped = [idx_seq[0]]
            for i in range(1, len(idx_seq)):
                if idx_seq[i] != idx_seq[i - 1]:
                    deduped.append(idx_seq[i])
            if len(deduped) < 3:
                continue

            # Create training pairs: predict next item from prefix
            for end_pos in range(2, len(deduped)):
                input_seq = deduped[:end_pos]
                target = deduped[end_pos]
                self.samples.append((input_seq, target, set(deduped)))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        input_seq, target, positive_items = self.samples[idx]

        # Pad / truncate to max_len. Right padding avoids fully-masked rows
        # when causal attention is combined with a key padding mask.
        seq = input_seq[-self.max_len:]
        pad_len = self.max_len - len(seq)
        padded = seq + ([0] * pad_len)

        # Negative sampling: avoid every item already seen in the user's history.
        negatives = []
        used_negatives = set()
        while len(negatives) < self.num_negatives:
            neg = np.random.randint(1, self.num_items + 1)
            if neg in positive_items or neg in used_negatives:
                continue
            used_negatives.add(neg)
            negatives.append(neg)

        return (
            torch.tensor(padded, dtype=torch.long),
            torch.tensor(target, dtype=torch.long),
            torch.tensor(negatives, dtype=torch.long),
        )


class SASRecContinuationDataset(Dataset):
    """
    Temporal validation/test dataset.

    Each sample predicts a future item using only the sequence prefix that
    would have been available before that interaction happened.
    """

    def __init__(
        self,
        history_sequences: dict[int, list[str]],
        future_sequences: dict[int, list[str]],
        track2idx: dict,
        max_len: int = MAX_SEQ_LEN,
        num_negatives: int = 3,
    ):
        self.max_len = max_len
        self.num_items = len(track2idx)
        self.track2idx = track2idx
        self.num_negatives = max(1, num_negatives)
        self.samples = []

        for user_id, history_seq in history_sequences.items():
            future_seq = future_sequences.get(user_id)
            if not future_seq:
                continue

            tagged = []
            for tid in history_seq:
                if tid in track2idx:
                    tagged.append((track2idx[tid] + 1, False))
            for tid in future_seq:
                if tid in track2idx:
                    tagged.append((track2idx[tid] + 1, True))

            if len(tagged) < 3:
                continue

            deduped = [tagged[0]]
            for item_idx, is_future in tagged[1:]:
                if item_idx != deduped[-1][0]:
                    deduped.append((item_idx, is_future))

            prefix = []
            seen_items = set()
            for item_idx, is_future in deduped:
                if len(prefix) >= 2 and is_future:
                    self.samples.append((list(prefix), item_idx, set(seen_items)))
                prefix.append(item_idx)
                seen_items.add(item_idx)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        input_seq, target, positive_items = self.samples[idx]

        seq = input_seq[-self.max_len:]
        pad_len = self.max_len - len(seq)
        padded = seq + ([0] * pad_len)

        negatives = []
        used_negatives = set()
        while len(negatives) < self.num_negatives:
            neg = np.random.randint(1, self.num_items + 1)
            if neg in positive_items or neg in used_negatives:
                continue
            used_negatives.add(neg)
            negatives.append(neg)

        return (
            torch.tensor(padded, dtype=torch.long),
            torch.tensor(target, dtype=torch.long),
            torch.tensor(negatives, dtype=torch.long),
        )


class PointWiseFeedForward(nn.Module):
    def __init__(self, hidden_dim: int, ff_dim: int, dropout: float = 0.2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(hidden_dim, ff_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(ff_dim, hidden_dim),
            nn.Dropout(dropout),
        )

    def forward(self, x):
        return self.net(x)


class SASRecBlock(nn.Module):
    """Single Transformer block for SASRec."""

    def __init__(self, hidden_dim: int, num_heads: int, ff_dim: int, dropout: float = 0.2):
        super().__init__()
        self.attention = nn.MultiheadAttention(
            hidden_dim, num_heads, dropout=dropout, batch_first=True
        )
        self.norm1 = nn.LayerNorm(hidden_dim)
        self.norm2 = nn.LayerNorm(hidden_dim)
        self.ffn = PointWiseFeedForward(hidden_dim, ff_dim, dropout)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        mask: torch.Tensor | None = None,
        padding_mask: torch.Tensor | None = None,
    ):
        # Self-attention with causal mask
        attn_out, _ = self.attention(
            x,
            x,
            x,
            attn_mask=mask,
            key_padding_mask=padding_mask,
            need_weights=False,
        )
        x = self.norm1(x + self.dropout(attn_out))
        ff_out = self.ffn(x)
        x = self.norm2(x + ff_out)
        return x


class SASRec(nn.Module):
    """
    Self-Attentive Sequential Recommendation model.
    
    Uses a stack of Transformer blocks with causal masking
    to model sequential user behavior.
    """

    def __init__(
        self,
        num_items: int,
        max_len: int = MAX_SEQ_LEN,
        hidden_dim: int = EMBEDDING_DIM,
        num_heads: int = 2,
        num_blocks: int = 2,
        ff_dim: int = None,
        dropout: float = 0.5,
    ):
        super().__init__()
        self.num_items = num_items
        self.max_len = max_len
        self.hidden_dim = hidden_dim
        ff_dim = ff_dim or hidden_dim * 4

        # Item embedding (0 = padding, 1..num_items = items)
        self.item_embedding = nn.Embedding(num_items + 1, hidden_dim, padding_idx=0)
        self.positional_embedding = nn.Embedding(max_len, hidden_dim)

        self.dropout = nn.Dropout(dropout)
        self.norm = nn.LayerNorm(hidden_dim)

        # Transformer blocks
        self.blocks = nn.ModuleList([
            SASRecBlock(hidden_dim, num_heads, ff_dim, dropout)
            for _ in range(num_blocks)
        ])

        self._init_weights()

    def _init_weights(self):
        nn.init.xavier_normal_(self.item_embedding.weight[1:])  # Skip padding
        nn.init.xavier_normal_(self.positional_embedding.weight)

    def _get_causal_mask(self, seq_len: int, device: torch.device) -> torch.Tensor:
        """Generate causal attention mask."""
        mask = torch.triu(torch.ones(seq_len, seq_len, device=device), diagonal=1).bool()
        return mask

    def _get_last_hidden(
        self,
        input_seq: torch.Tensor,
        seq_output: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Return the representation of the last non-padding token for each sequence."""
        if seq_output is None:
            seq_output = self.forward(input_seq)
        lengths = input_seq.ne(0).sum(dim=1).clamp(min=1)
        last_indices = lengths - 1
        batch_indices = torch.arange(input_seq.size(0), device=input_seq.device)
        return seq_output[batch_indices, last_indices, :]

    def forward(self, input_seq: torch.Tensor) -> torch.Tensor:
        """
        Args:
            input_seq: (batch, max_len) - padded item indices
        Returns:
            (batch, max_len, hidden_dim) - sequence representations
        """
        batch_size, seq_len = input_seq.shape

        padding_mask = input_seq.eq(0)

        # Embeddings
        positions = torch.arange(seq_len, device=input_seq.device).unsqueeze(0)
        x = self.item_embedding(input_seq) + self.positional_embedding(positions)
        x = x.masked_fill(padding_mask.unsqueeze(-1), 0.0)
        x = self.dropout(self.norm(x))

        # Causal mask
        mask = self._get_causal_mask(seq_len, input_seq.device)

        # Transformer blocks
        for block in self.blocks:
            x = block(x, mask, padding_mask)

        return x

    def predict(self, input_seq: torch.Tensor, candidate_items: torch.Tensor | None = None) -> torch.Tensor:
        """
        Predict scores for candidate items.
        
        Args:
            input_seq: (batch, max_len) - padded sequences
            candidate_items: (batch, num_candidates) or None (predict all)
        Returns:
            scores: (batch, num_candidates) or (batch, num_items)
        """
        seq_output = self.forward(input_seq)  # (batch, max_len, hidden)
        last_output = self._get_last_hidden(input_seq, seq_output)  # (batch, hidden)

        if candidate_items is not None:
            item_emb = self.item_embedding(candidate_items)  # (batch, num_cand, hidden)
            scores = (last_output.unsqueeze(1) * item_emb).sum(dim=-1)  # (batch, num_cand)
        else:
            # Score all items: embeddings[1..num_items] map to items 0..num_items-1
            all_emb = self.item_embedding.weight[1:]  # (num_items, hidden), skip padding
            scores = torch.matmul(last_output, all_emb.T)  # (batch, num_items)

        return scores


class SASRecRecommender:
    """High-level wrapper for SASRec training and inference."""

    def __init__(self, hidden_dim: int = EMBEDDING_DIM, num_heads: int = 2, num_blocks: int = 2):
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads
        self.num_blocks = num_blocks
        self.model: SASRec | None = None
        self.track2idx: dict = {}
        self.idx2track: dict = {}
        self.device = torch.device("cpu")

    def fit(
        self,
        sequences: dict[str, list[str]],
        track2idx: dict,
        epochs: int = EPOCHS,
        batch_size: int = BATCH_SIZE,
        lr: float = LEARNING_RATE,
        patience: int = 8,
    ) -> dict:
        """Train SASRec model."""
        self.track2idx = track2idx
        self.idx2track = {v: k for k, v in track2idx.items()}
        num_items = len(track2idx)

        self.model = SASRec(
            num_items=num_items,
            hidden_dim=self.hidden_dim,
            num_heads=self.num_heads,
            num_blocks=self.num_blocks,
        ).to(self.device)

        optimizer = optim.Adam(self.model.parameters(), lr=lr, weight_decay=1e-5)

        dataset = SASRecDataset(sequences, track2idx)
        if len(dataset) == 0:
            logger.warning("No training samples. Check sequences.")
            return {"train_loss": []}

        # Split last 10% of dataset for validation
        val_size = max(1, len(dataset) // 10)
        train_size = len(dataset) - val_size
        train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)
        val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0)

        best_val_loss = float("inf")
        best_state = None
        no_improve = 0
        history = {"train_loss": [], "val_loss": []}

        for epoch in range(epochs):
            # Train
            self.model.train()
            total_loss = 0.0
            n_samples = 0
            for seq, pos, neg in train_loader:
                seq, pos, neg = seq.to(self.device), pos.to(self.device), neg.to(self.device)

                optimizer.zero_grad()
                seq_output = self.model(seq)
                last_hidden = self.model._get_last_hidden(seq, seq_output)  # (batch, hidden)

                pos_emb = self.model.item_embedding(pos)  # (batch, hidden)
                neg_emb = self.model.item_embedding(neg)  # (batch, num_neg, hidden)

                pos_score = (last_hidden * pos_emb).sum(dim=-1)
                neg_score = (last_hidden.unsqueeze(1) * neg_emb).sum(dim=-1)

                margin = pos_score.unsqueeze(1) - neg_score
                loss = -torch.log(torch.sigmoid(margin) + 1e-8).mean()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=5.0)
                optimizer.step()

                total_loss += loss.item() * len(pos)
                n_samples += len(pos)

            avg_train = total_loss / max(n_samples, 1)
            history["train_loss"].append(avg_train)

            # Validate
            self.model.eval()
            val_total = 0.0
            val_n = 0
            with torch.no_grad():
                for seq, pos, neg in val_loader:
                    seq, pos, neg = seq.to(self.device), pos.to(self.device), neg.to(self.device)
                    seq_output = self.model(seq)
                    last_hidden = self.model._get_last_hidden(seq, seq_output)
                    pos_emb = self.model.item_embedding(pos)
                    neg_emb = self.model.item_embedding(neg)
                    pos_score = (last_hidden * pos_emb).sum(dim=-1)
                    neg_score = (last_hidden.unsqueeze(1) * neg_emb).sum(dim=-1)
                    margin = pos_score.unsqueeze(1) - neg_score
                    loss = -torch.log(torch.sigmoid(margin) + 1e-8).mean()
                    val_total += loss.item() * len(pos)
                    val_n += len(pos)

            avg_val = val_total / max(val_n, 1)
            history["val_loss"].append(avg_val)

            if (epoch + 1) % 5 == 0 or epoch == 0:
                logger.info(f"Epoch {epoch + 1}/{epochs}, Train: {avg_train:.4f}, Val: {avg_val:.4f}")

            if avg_val < best_val_loss:
                best_val_loss = avg_val
                best_state = {k: v.clone() for k, v in self.model.state_dict().items()}
                no_improve = 0
            else:
                no_improve += 1

            if no_improve >= patience:
                logger.info(f"Early stopping at epoch {epoch + 1}")
                break

        if best_state:
            self.model.load_state_dict(best_state)

        logger.info(f"SASRec training complete. Best val loss: {best_val_loss:.4f}")
        return history

    def recommend(self, seq: list[str], top_k: int = 20, exclude_seen: bool = True) -> list[tuple[str, float]]:
        """
        Recommend next items given a play sequence.

        Args:
            seq: list of track_ids (chronological order)
            top_k: number of items to recommend
            exclude_seen: whether to exclude items already in the sequence
        """
        if self.model is None:
            raise RuntimeError("Model not trained.")

        self.model.eval()
        # +1 offset: 0 is padding, items are 1..num_items
        idx_seq = [self.track2idx[tid] + 1 for tid in seq if tid in self.track2idx]
        if not idx_seq:
            return []

        # Remove consecutive duplicates (same as training)
        deduped = [idx_seq[0]]
        for i in range(1, len(idx_seq)):
            if idx_seq[i] != idx_seq[i - 1]:
                deduped.append(idx_seq[i])
        if len(deduped) < 2:
            return []

        # Pad/truncate
        padded = deduped[-MAX_SEQ_LEN:]
        pad_len = MAX_SEQ_LEN - len(padded)
        padded = padded + ([0] * pad_len)

        with torch.no_grad():
            input_tensor = torch.tensor([padded], dtype=torch.long).to(self.device)
            scores = self.model.predict(input_tensor)  # (1, num_items)
            scores = scores.squeeze(0).numpy()

        # Exclude seen items (convert back to 0-based for indexing scores)
        if exclude_seen:
            seen_set = set(deduped)
            for item_1based in seen_set:
                idx_0based = item_1based - 1  # scores array is 0-based
                if 0 <= idx_0based < len(scores):
                    scores[idx_0based] = -np.inf

        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] <= -1e8:
                break
            # idx is 0-based in scores → corresponds to track2idx value
            track_id = self.idx2track.get(idx)
            if track_id:
                results.append((track_id, float(scores[idx])))

        return results

    def save(self, path: str | None = None):
        save_dir = path or os.path.join(MODEL_DIR, "sasrec")
        os.makedirs(save_dir, exist_ok=True)

        torch.save(self.model.state_dict(), os.path.join(save_dir, "sasrec_model.pt"))

        meta = {
            "num_items": self.model.num_items,
            "hidden_dim": self.hidden_dim,
            "num_heads": self.num_heads,
            "num_blocks": self.num_blocks,
            "max_len": MAX_SEQ_LEN,
        }
        with open(os.path.join(save_dir, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2)

        # Save track2idx mapping so inference uses training-time indices
        pd.DataFrame(list(self.track2idx.items()), columns=["track_id", "idx"]).to_parquet(
            os.path.join(save_dir, "track2idx.parquet"), index=False
        )

        logger.info(f"SASRec model saved to {save_dir}")

    def load(self, path: str | None = None):
        load_dir = path or os.path.join(MODEL_DIR, "sasrec")

        with open(os.path.join(load_dir, "meta.json")) as f:
            meta = json.load(f)

        # Load track2idx from model directory (training-time mapping)
        saved_path = os.path.join(load_dir, "track2idx.parquet")
        if os.path.exists(saved_path):
            self.track2idx = dict(pd.read_parquet(saved_path).values)
        else:
            # Fallback for models saved before this fix
            track2idx_df = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet"))
            self.track2idx = dict(track2idx_df.values)
        self.idx2track = {v: k for k, v in self.track2idx.items()}

        self.hidden_dim = meta["hidden_dim"]
        self.num_heads = meta["num_heads"]
        self.num_blocks = meta["num_blocks"]

        self.model = SASRec(
            num_items=meta["num_items"],
            hidden_dim=meta["hidden_dim"],
            num_heads=meta["num_heads"],
            num_blocks=meta["num_blocks"],
            max_len=meta["max_len"],
        ).to(self.device)

        self.model.load_state_dict(torch.load(
            os.path.join(load_dir, "sasrec_model.pt"),
            map_location=self.device,
            weights_only=True,
        ))
        self.model.eval()

        logger.info(f"SASRec model loaded from {load_dir}")
