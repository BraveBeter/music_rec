"""
Train SASRec sequential recommendation model.
Run: uv run python -m ml_pipeline.training.train_sasrec
"""
import os
import sys
import json
import logging
from datetime import datetime

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, MODEL_DIR
from ml_pipeline.models.sasrec import SASRecRecommender
from ml_pipeline.evaluation.metrics import evaluate_model, format_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _get_task_id() -> str | None:
    """Parse --task-id from sys.argv if present."""
    for i, arg in enumerate(sys.argv):
        if arg == "--task-id" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def main():
    task_id = _get_task_id()
    tracker = None

    logger.info("=" * 60)
    logger.info("Training SASRec Sequential Model")
    logger.info("=" * 60)

    # Load data
    logger.info("Loading data...")
    track2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet")).values)

    with open(os.path.join(PROCESSED_DATA_DIR, "user_sequences.json")) as f:
        sequences = json.load(f)

    test = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "test.parquet"))
    all_interactions = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "all_interactions.parquet"))

    logger.info(f"Sequences: {len(sequences)} users, Items: {len(track2idx)}")

    epochs = 50
    if task_id:
        from ml_pipeline.training.progress import ProgressTracker
        tracker = ProgressTracker(task_id, "train_sasrec", total_epochs=epochs)
        tracker.__enter__()
        tracker.update_phase("training", 0)
        tracker.append_log(f"Loaded {len(sequences)} sequences, {len(track2idx)} items")

    # Train with progress tracking via a patched fit
    sasrec = SASRecRecommender(hidden_dim=128, num_heads=2, num_blocks=2)

    # We wrap the training loop manually to track per-epoch progress
    sasrec.track2idx = track2idx
    sasrec.idx2track = {v: k for k, v in track2idx.items()}
    num_items = len(track2idx)

    from ml_pipeline.models.sasrec import SASRec, SASRecDataset
    import torch
    import torch.optim as optim
    from torch.utils.data import DataLoader
    from ml_pipeline.config import MAX_SEQ_LEN

    model = SASRec(num_items=num_items, hidden_dim=128, num_heads=2, num_blocks=2)
    device = torch.device("cpu")
    model = model.to(device)
    optimizer = optim.Adam(model.parameters(), lr=5e-4, weight_decay=1e-5)

    dataset = SASRecDataset(sequences, track2idx)
    if len(dataset) == 0:
        logger.warning("No training samples.")
        if tracker:
            tracker.mark_completed({"error": "no_samples"})
            tracker.__exit__(None, None, None)
        return

    val_size = max(1, len(dataset) // 10)
    train_size = len(dataset) - val_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
    train_loader = DataLoader(train_dataset, batch_size=128, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=128, shuffle=False, num_workers=0)

    best_val_loss = float("inf")
    best_state = None
    no_improve = 0
    patience = 12

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        n_samples = 0
        for seq, pos, neg in train_loader:
            seq, pos, neg = seq.to(device), pos.to(device), neg.to(device)
            optimizer.zero_grad()
            seq_output = model(seq)
            last_hidden = seq_output[:, -1, :]
            pos_emb = model.item_embedding(pos)
            neg_emb = model.item_embedding(neg)
            pos_score = (last_hidden * pos_emb).sum(dim=-1)
            neg_score = (last_hidden * neg_emb).sum(dim=-1)
            loss = -torch.log(torch.sigmoid(pos_score - neg_score) + 1e-8).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            total_loss += loss.item() * len(pos)
            n_samples += len(pos)

        avg_train = total_loss / max(n_samples, 1)

        model.eval()
        val_total = 0.0
        val_n = 0
        with torch.no_grad():
            for seq, pos, neg in val_loader:
                seq, pos, neg = seq.to(device), pos.to(device), neg.to(device)
                seq_output = model(seq)
                last_hidden = seq_output[:, -1, :]
                pos_emb = model.item_embedding(pos)
                neg_emb = model.item_embedding(neg)
                pos_score = (last_hidden * pos_emb).sum(dim=-1)
                neg_score = (last_hidden * neg_emb).sum(dim=-1)
                loss = -torch.log(torch.sigmoid(pos_score - neg_score) + 1e-8).mean()
                val_total += loss.item() * len(pos)
                val_n += len(pos)

        avg_val = val_total / max(val_n, 1)

        if (epoch + 1) % 5 == 0 or epoch == 0:
            logger.info(f"Epoch {epoch + 1}/{epochs}, Train: {avg_train:.4f}, Val: {avg_val:.4f}")

        if tracker:
            tracker.update_epoch(epoch + 1, train_loss=avg_train, val_loss=avg_val)
            tracker.append_log(f"Epoch {epoch + 1}/{epochs} — Train: {avg_train:.4f}, Val: {avg_val:.4f}")

        if avg_val < best_val_loss:
            best_val_loss = avg_val
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1

        if no_improve >= patience:
            logger.info(f"Early stopping at epoch {epoch + 1}")
            if tracker:
                tracker.append_log(f"Early stopping at epoch {epoch + 1}")
            break

    if best_state:
        model.load_state_dict(best_state)

    sasrec.model = model
    logger.info(f"SASRec training complete. Best val loss: {best_val_loss:.4f}")

    # Save
    sasrec.save()

    # Evaluate
    logger.info("Evaluating SASRec...")
    user2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet")).values)
    train = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "train.parquet"))
    train_plays = train[train["interaction_type"].isin([1, 2])].sort_values("created_at")
    user_train_seqs = train_plays.groupby("user_id")["track_id"].apply(list).to_dict()

    def sasrec_recommend(user_id):
        seq = user_train_seqs.get(user_id, [])
        if len(seq) < 3:
            return []
        return sasrec.recommend(seq, top_k=20)

    sasrec_result = evaluate_model(
        model_name="SASRec",
        recommend_fn=sasrec_recommend,
        test_data=test,
        all_interactions=all_interactions,
        num_items=len(track2idx),
    )

    logger.info(f"SASRec results: {sasrec_result}")

    # Version management: save version + compare + promote
    version_id = task_id or f"train_sasrec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    from ml_pipeline.models.versioning import ModelRegistry
    registry = ModelRegistry()
    registry.save_version_artifacts("sasrec", version_id)
    registry.register_version("sasrec", version_id, sasrec_result)
    promoted = registry.compare_and_promote("sasrec", version_id, sasrec_result)
    if promoted:
        logger.info("SASRec: new version promoted to production")
        if tracker:
            tracker.append_log("SASRec: promoted (NDCG@10 improved)")
    else:
        logger.info("SASRec: new version rejected (NDCG@10 did not improve)")
        if tracker:
            tracker.append_log("SASRec: rejected (NDCG@10 did not improve)")

    report_path = os.path.join(MODEL_DIR, "sasrec_report.json")
    with open(report_path, "w") as f:
        json.dump(sasrec_result, f, indent=2, default=str)

    if tracker:
        tracker.mark_completed(sasrec_result)
        tracker.__exit__(None, None, None)

    logger.info(f"Report saved to {report_path}")
    logger.info("SASRec training complete!")


if __name__ == "__main__":
    main()
