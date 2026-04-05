"""
DeepFM: Deep Factorization Machine for CTR / recommendation ranking.
Combines Factorization Machine (FM) and Deep Neural Network (DNN)
for learning both low-order and high-order feature interactions.
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
from ml_pipeline.config import (
    PROCESSED_DATA_DIR, MODEL_DIR, EMBEDDING_DIM,
    HIDDEN_DIMS, LEARNING_RATE, BATCH_SIZE, EPOCHS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class DeepFMDataset(Dataset):
    """Dataset for DeepFM training."""

    def __init__(self, data: pd.DataFrame, sparse_features: list, dense_features: list):
        self.sparse = torch.tensor(
            data[sparse_features].values.astype(np.int64), dtype=torch.long
        )
        self.dense = torch.tensor(
            data[dense_features].values.astype(np.float32), dtype=torch.float32
        )
        self.labels = torch.tensor(
            data["label"].values.astype(np.float32), dtype=torch.float32
        )

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return self.sparse[idx], self.dense[idx], self.labels[idx]


class DeepFM(nn.Module):
    """
    DeepFM Model.
    
    Architecture:
    - First-order linear features
    - FM second-order cross features  
    - Deep component (MLP)
    
    All three paths are concatenated and fed into a final sigmoid layer.
    """

    def __init__(
        self,
        sparse_dims: dict[str, int],
        num_dense: int,
        embedding_dim: int = EMBEDDING_DIM,
        hidden_dims: list[int] = None,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.sparse_feature_names = list(sparse_dims.keys())
        self.num_sparse = len(sparse_dims)
        self.num_dense = num_dense
        self.embedding_dim = embedding_dim
        hidden_dims = hidden_dims or HIDDEN_DIMS

        # --- First-order embeddings (linear part) ---
        self.first_order_embeddings = nn.ModuleDict({
            feat: nn.Embedding(dim, 1) for feat, dim in sparse_dims.items()
        })

        # --- Second-order embeddings (FM part) ---
        self.second_order_embeddings = nn.ModuleDict({
            feat: nn.Embedding(dim, embedding_dim) for feat, dim in sparse_dims.items()
        })

        # --- Dense feature linear ---
        self.dense_linear = nn.Linear(num_dense, 1) if num_dense > 0 else None

        # --- Deep part (DNN) ---
        dnn_input_dim = self.num_sparse * embedding_dim + num_dense
        layers = []
        prev_dim = dnn_input_dim
        for h_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, h_dim),
                nn.BatchNorm1d(h_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
            ])
            prev_dim = h_dim

        self.dnn = nn.Sequential(*layers)
        self.dnn_output = nn.Linear(prev_dim, 1)

        # Global bias
        self.bias = nn.Parameter(torch.zeros(1))

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Embedding):
                nn.init.xavier_normal_(m.weight)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_normal_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, sparse_inputs: torch.Tensor, dense_inputs: torch.Tensor) -> torch.Tensor:
        """
        Args:
            sparse_inputs: (batch, num_sparse_features) - integer indices
            dense_inputs: (batch, num_dense_features) - float values
        Returns:
            (batch,) - prediction scores after sigmoid
        """
        batch_size = sparse_inputs.shape[0]

        # ---- First-order ----
        first_order = torch.zeros(batch_size, 1, device=sparse_inputs.device)
        for i, feat in enumerate(self.sparse_feature_names):
            first_order += self.first_order_embeddings[feat](sparse_inputs[:, i])

        if self.dense_linear is not None and self.num_dense > 0:
            first_order += self.dense_linear(dense_inputs)

        # ---- Second-order FM ----
        embeddings = []
        for i, feat in enumerate(self.sparse_feature_names):
            embeddings.append(self.second_order_embeddings[feat](sparse_inputs[:, i]))

        emb_stack = torch.stack(embeddings, dim=1)  # (batch, num_sparse, emb_dim)

        # FM: 0.5 * (sum_square - square_sum)
        sum_of_emb = emb_stack.sum(dim=1)  # (batch, emb_dim)
        square_of_sum = sum_of_emb.pow(2)  # (batch, emb_dim)
        sum_of_square = emb_stack.pow(2).sum(dim=1)  # (batch, emb_dim)
        fm_output = 0.5 * (square_of_sum - sum_of_square).sum(dim=1, keepdim=True)  # (batch, 1)

        # ---- Deep part ----
        emb_flat = emb_stack.view(batch_size, -1)  # (batch, num_sparse * emb_dim)
        if self.num_dense > 0:
            dnn_input = torch.cat([emb_flat, dense_inputs], dim=1)
        else:
            dnn_input = emb_flat
        dnn_output = self.dnn_output(self.dnn(dnn_input))  # (batch, 1)

        # ---- Combine ----
        logit = first_order + fm_output + dnn_output + self.bias
        return torch.sigmoid(logit.squeeze(1))


class DeepFMRecommender:
    """High-level wrapper for training and inference with DeepFM."""

    def __init__(self):
        self.model: DeepFM | None = None
        self.sparse_features: list = []
        self.dense_features: list = []
        self.sparse_dims: dict = {}
        self.device = torch.device("cpu")

    def fit(
        self,
        train_data: pd.DataFrame,
        val_data: pd.DataFrame | None = None,
        feature_meta: dict = None,
        epochs: int = EPOCHS,
        batch_size: int = BATCH_SIZE,
        lr: float = LEARNING_RATE,
        patience: int = 5,
    ) -> dict:
        """Train the DeepFM model."""
        self.sparse_features = feature_meta["sparse_features"]
        self.dense_features = feature_meta["dense_features"]
        self.sparse_dims = {k: v for k, v in feature_meta["sparse_dims"].items()}

        # Ensure sparse features are in valid range
        for feat in self.sparse_features:
            if feat in train_data.columns:
                train_data[feat] = train_data[feat].fillna(0).astype(int).clip(lower=0)
                max_val = int(train_data[feat].max())
                if feat in self.sparse_dims and max_val >= self.sparse_dims[feat]:
                    self.sparse_dims[feat] = max_val + 1

        self.model = DeepFM(
            sparse_dims=self.sparse_dims,
            num_dense=len(self.dense_features),
        ).to(self.device)

        optimizer = optim.Adam(self.model.parameters(), lr=lr, weight_decay=1e-5)
        criterion = nn.BCELoss()

        train_dataset = DeepFMDataset(train_data, self.sparse_features, self.dense_features)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)

        val_loader = None
        if val_data is not None and len(val_data) > 0:
            for feat in self.sparse_features:
                if feat in val_data.columns:
                    val_data[feat] = val_data[feat].fillna(0).astype(int).clip(lower=0)
            val_dataset = DeepFMDataset(val_data, self.sparse_features, self.dense_features)
            val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0)

        best_val_loss = float("inf")
        best_state = None
        no_improve_count = 0
        history = {"train_loss": [], "val_loss": []}

        for epoch in range(epochs):
            # Train
            self.model.train()
            total_loss = 0.0
            for sparse, dense, labels in train_loader:
                sparse, dense, labels = sparse.to(self.device), dense.to(self.device), labels.to(self.device)
                optimizer.zero_grad()
                preds = self.model(sparse, dense)
                loss = criterion(preds, labels)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=5.0)
                optimizer.step()
                total_loss += loss.item() * len(labels)

            avg_train = total_loss / len(train_dataset)
            history["train_loss"].append(avg_train)

            # Validate
            val_loss_str = "N/A"
            if val_loader:
                self.model.eval()
                val_total = 0.0
                with torch.no_grad():
                    for sparse, dense, labels in val_loader:
                        sparse, dense, labels = sparse.to(self.device), dense.to(self.device), labels.to(self.device)
                        preds = self.model(sparse, dense)
                        val_total += criterion(preds, labels).item() * len(labels)
                avg_val = val_total / len(val_dataset)
                history["val_loss"].append(avg_val)
                val_loss_str = f"{avg_val:.4f}"

                if avg_val < best_val_loss:
                    best_val_loss = avg_val
                    best_state = {k: v.clone() for k, v in self.model.state_dict().items()}
                    no_improve_count = 0
                else:
                    no_improve_count += 1
            else:
                if avg_train < best_val_loss:
                    best_val_loss = avg_train
                    best_state = {k: v.clone() for k, v in self.model.state_dict().items()}

            if (epoch + 1) % 5 == 0 or epoch == 0:
                logger.info(f"Epoch {epoch + 1}/{epochs}, Train: {avg_train:.4f}, Val: {val_loss_str}")

            if no_improve_count >= patience:
                logger.info(f"Early stopping at epoch {epoch + 1}")
                break

        if best_state:
            self.model.load_state_dict(best_state)

        logger.info(f"DeepFM training complete. Best val loss: {best_val_loss:.4f}")
        return history

    def predict(self, sparse_inputs: np.ndarray, dense_inputs: np.ndarray) -> np.ndarray:
        """Predict scores for a batch of samples."""
        self.model.eval()
        with torch.no_grad():
            sparse_t = torch.tensor(sparse_inputs, dtype=torch.long).to(self.device)
            dense_t = torch.tensor(dense_inputs, dtype=torch.float32).to(self.device)
            scores = self.model(sparse_t, dense_t)
        return scores.cpu().numpy()

    def save(self, path: str | None = None):
        save_dir = path or os.path.join(MODEL_DIR, "deepfm")
        os.makedirs(save_dir, exist_ok=True)

        torch.save(self.model.state_dict(), os.path.join(save_dir, "deepfm_model.pt"))

        meta = {
            "sparse_features": self.sparse_features,
            "dense_features": self.dense_features,
            "sparse_dims": self.sparse_dims,
        }
        with open(os.path.join(save_dir, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2)

        logger.info(f"DeepFM model saved to {save_dir}")

    def export_onnx(self, path: str | None = None):
        """Export model to ONNX format for inference optimization."""
        save_dir = path or os.path.join(MODEL_DIR, "deepfm")
        os.makedirs(save_dir, exist_ok=True)

        self.model.eval()
        dummy_sparse = torch.zeros(1, len(self.sparse_features), dtype=torch.long)
        dummy_dense = torch.zeros(1, len(self.dense_features), dtype=torch.float32)

        onnx_path = os.path.join(save_dir, "deepfm_model.onnx")
        torch.onnx.export(
            self.model,
            (dummy_sparse, dummy_dense),
            onnx_path,
            input_names=["sparse_inputs", "dense_inputs"],
            output_names=["score"],
            dynamic_axes={
                "sparse_inputs": {0: "batch"},
                "dense_inputs": {0: "batch"},
                "score": {0: "batch"},
            },
            opset_version=14,
        )
        logger.info(f"DeepFM exported to ONNX: {onnx_path}")

    def load(self, path: str | None = None):
        load_dir = path or os.path.join(MODEL_DIR, "deepfm")

        with open(os.path.join(load_dir, "meta.json")) as f:
            meta = json.load(f)

        self.sparse_features = meta["sparse_features"]
        self.dense_features = meta["dense_features"]
        self.sparse_dims = meta["sparse_dims"]

        self.model = DeepFM(
            sparse_dims=self.sparse_dims,
            num_dense=len(self.dense_features),
        ).to(self.device)
        self.model.load_state_dict(torch.load(
            os.path.join(load_dir, "deepfm_model.pt"),
            map_location=self.device,
            weights_only=True,
        ))
        self.model.eval()

        logger.info(f"DeepFM model loaded from {load_dir}")
