"""
Train SASRec sequential recommendation model.
Run: uv run python -m ml_pipeline.training.train_sasrec
"""
import os
import sys
import json
import logging

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, MODEL_DIR
from ml_pipeline.models.sasrec import SASRecRecommender
from ml_pipeline.evaluation.metrics import evaluate_model, format_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("Training SASRec Sequential Model")
    logger.info("=" * 60)

    # Load data
    track2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet")).values)

    with open(os.path.join(PROCESSED_DATA_DIR, "user_sequences.json")) as f:
        sequences = json.load(f)

    test = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "test.parquet"))
    all_interactions = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "all_interactions.parquet"))

    logger.info(f"Sequences: {len(sequences)} users, Items: {len(track2idx)}")

    # Train
    sasrec = SASRecRecommender(hidden_dim=128, num_heads=2, num_blocks=2)
    history = sasrec.fit(
        sequences=sequences,
        track2idx=track2idx,
        epochs=50,
        batch_size=128,
        lr=5e-4,
        patience=12,
    )

    # Save
    sasrec.save()

    # Evaluate — for each user, use prefix of their sequence as input,
    # and check if the held-out test items are recommended
    logger.info("Evaluating SASRec...")

    # Build user sequences for evaluation (exclude last few items as test)
    user2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet")).values)

    # Create a recommend function that uses sequences
    # We need to build input sequences from training data
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

    # Save results
    report_path = os.path.join(MODEL_DIR, "sasrec_report.json")
    with open(report_path, "w") as f:
        json.dump(sasrec_result, f, indent=2, default=str)

    logger.info(f"Report saved to {report_path}")
    logger.info("SASRec training complete!")


if __name__ == "__main__":
    main()
