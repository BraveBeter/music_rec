"""
Feature Engineering Pipeline.
Builds user features, item features, and interaction features
for DeepFM and other models.
"""
import os
import sys
import logging
import json

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder, MinMaxScaler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, NEG_SAMPLE_RATIO, COMPLETION_RATE_THRESHOLD

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def build_user_features(users: pd.DataFrame, interactions: pd.DataFrame) -> pd.DataFrame:
    """
    Build user feature vectors:
    - age_bucket: discretized age
    - gender: categorical
    - country: label-encoded
    - interaction_count: total interactions
    - play_count: total plays
    - like_count: total likes
    - avg_completion: average completion rate
    - genre_preferences: distribution vector (8-dim)
    """
    # Basic features
    user_feats = users[["user_id", "age", "gender", "country"]].copy()

    # Age bucketing
    user_feats["age"] = user_feats["age"].fillna(25)
    user_feats["age_bucket"] = pd.cut(
        user_feats["age"], bins=[0, 18, 25, 35, 50, 100],
        labels=[0, 1, 2, 3, 4]
    ).astype(int)

    # Gender fill
    user_feats["gender"] = user_feats["gender"].fillna(0).astype(int)

    # Country encoding
    le_country = LabelEncoder()
    user_feats["country"] = user_feats["country"].fillna("Unknown")
    user_feats["country_idx"] = le_country.fit_transform(user_feats["country"])

    # Interaction statistics
    user_stats = interactions.groupby("user_id").agg(
        interaction_count=("interaction_id", "count"),
        play_count=("interaction_type", lambda x: (x == 1).sum()),
        like_count=("interaction_type", lambda x: (x == 2).sum()),
        avg_completion=("completion_rate", "mean"),
        avg_rating=("rating", lambda x: x.dropna().mean() if x.dropna().any() else 3.0),
    ).reset_index()

    user_feats = user_feats.merge(user_stats, on="user_id", how="left")
    user_feats = user_feats.fillna(0)

    # Normalize numeric features
    scaler = MinMaxScaler()
    numeric_cols = ["interaction_count", "play_count", "like_count", "avg_completion", "avg_rating"]
    user_feats[numeric_cols] = scaler.fit_transform(user_feats[numeric_cols])

    logger.info(f"Built user features: {user_feats.shape}")
    return user_feats


def build_item_features(tracks: pd.DataFrame, interactions: pd.DataFrame) -> pd.DataFrame:
    """
    Build item feature vectors:
    - acoustic features: danceability, energy, tempo, valence, acousticness (normalized)
    - popularity: log-scaled play_count
    - avg_rating: average rating from interactions
    - interaction_count: total interactions
    """
    item_feats = tracks.copy()

    # Fill missing acoustic features with median
    acoustic_cols = ["danceability", "energy", "tempo", "valence", "acousticness"]
    for col in acoustic_cols:
        item_feats[col] = item_feats[col].fillna(item_feats[col].median())

    # Normalize tempo to [0, 1]
    scaler = MinMaxScaler()
    item_feats[acoustic_cols] = scaler.fit_transform(item_feats[acoustic_cols])

    # Log-scaled popularity
    item_feats["log_popularity"] = np.log1p(item_feats["play_count"].fillna(0))
    max_pop = item_feats["log_popularity"].max()
    if max_pop > 0:
        item_feats["log_popularity"] = item_feats["log_popularity"] / max_pop

    # Interaction statistics per track
    track_stats = interactions.groupby("track_id").agg(
        item_interaction_count=("interaction_id", "count"),
        item_avg_completion=("completion_rate", "mean"),
        item_avg_rating=("rating", lambda x: x.dropna().mean() if x.dropna().any() else 3.0),
        item_like_ratio=("interaction_type", lambda x: (x == 2).sum() / max(len(x), 1)),
    ).reset_index()

    item_feats = item_feats.merge(track_stats, on="track_id", how="left")
    item_feats = item_feats.fillna(0)

    # Normalize
    stat_cols = ["item_interaction_count", "item_avg_completion", "item_avg_rating", "item_like_ratio"]
    item_feats[stat_cols] = MinMaxScaler().fit_transform(item_feats[stat_cols])

    logger.info(f"Built item features: {item_feats.shape}")
    return item_feats


def build_deepfm_dataset(
    train: pd.DataFrame,
    user_features: pd.DataFrame,
    item_features: pd.DataFrame,
    track2idx: dict,
    user2idx: dict,
) -> pd.DataFrame:
    """
    Build the feature matrix for DeepFM training.
    Each row = one interaction with concatenated user + item features.
    """
    # Merge user features
    user_cols = ["user_id", "age_bucket", "gender", "country_idx",
                 "interaction_count", "play_count", "like_count", "avg_completion", "avg_rating"]
    merged = train.merge(user_features[user_cols], on="user_id", how="left", suffixes=("", "_uf"))

    # Merge item features
    item_cols = ["track_id", "danceability", "energy", "tempo", "valence", "acousticness",
                 "log_popularity", "item_interaction_count", "item_avg_completion",
                 "item_avg_rating", "item_like_ratio"]
    merged = merged.merge(item_features[item_cols], on="track_id", how="left", suffixes=("", "_if"))

    merged = merged.fillna(0)

    logger.info(f"Built DeepFM dataset: {merged.shape}")
    return merged


def negative_sampling(
    interactions: pd.DataFrame,
    all_track_ids: list[str],
    ratio: int = NEG_SAMPLE_RATIO,
) -> pd.DataFrame:
    """
    Add random negative samples.
    For each positive interaction, sample `ratio` random negative items.
    """
    positive = interactions[interactions["label"] == 1].copy()

    # Build user-item positive set
    user_pos_items = positive.groupby("user_id")["track_id"].apply(set).to_dict()

    neg_records = []
    for user_id, pos_items in user_pos_items.items():
        n_neg = min(len(pos_items) * ratio, len(all_track_ids) - len(pos_items))
        available = [t for t in all_track_ids if t not in pos_items]
        if not available:
            continue
        neg_items = np.random.choice(available, size=min(n_neg, len(available)), replace=False)
        for track_id in neg_items:
            neg_records.append({
                "user_id": user_id,
                "track_id": track_id,
                "interaction_type": 0,  # synthetic negative
                "label": 0,
                "completion_rate": 0.0,
                "rating": None,
                "play_duration": 0,
            })

    neg_df = pd.DataFrame(neg_records)
    combined = pd.concat([interactions, neg_df], ignore_index=True)
    combined = combined.sample(frac=1, random_state=42).reset_index(drop=True)

    logger.info(f"After negative sampling: {len(combined)} total "
                f"({(combined['label'] == 1).sum()} pos, {(combined['label'] == 0).sum()} neg)")
    return combined


def run_feature_engineering():
    """Main feature engineering pipeline."""
    logger.info("=" * 60)
    logger.info("Starting feature engineering")
    logger.info("=" * 60)

    # Load preprocessed data
    train = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "train.parquet"))
    val = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "val.parquet"))
    test = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "test.parquet"))
    tracks = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "tracks.parquet"))
    users = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "users.parquet"))
    all_interactions = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "all_interactions.parquet"))

    # ID mappings
    user2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet")).values)
    track2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet")).values)

    all_track_ids = list(track2idx.keys())

    # Build features
    logger.info("[1/4] Building user features...")
    user_features = build_user_features(users, all_interactions)

    logger.info("[2/4] Building item features...")
    item_features = build_item_features(tracks, all_interactions)

    # Negative sampling for train
    logger.info("[3/4] Negative sampling for training set...")
    train_augmented = negative_sampling(train, all_track_ids)

    # Build DeepFM datasets
    logger.info("[4/4] Building DeepFM feature matrices...")
    train_dm = build_deepfm_dataset(train_augmented, user_features, item_features, track2idx, user2idx)
    val_dm = build_deepfm_dataset(val, user_features, item_features, track2idx, user2idx)
    test_dm = build_deepfm_dataset(test, user_features, item_features, track2idx, user2idx)

    # Drop non-numeric / datetime columns before saving
    drop_cols = ["created_at", "title", "artist_name", "username", "country"]
    for df_to_save in [user_features, item_features, train_dm, val_dm, test_dm]:
        for col in drop_cols:
            if col in df_to_save.columns:
                df_to_save.drop(columns=[col], inplace=True)

    # Save
    user_features.to_parquet(os.path.join(PROCESSED_DATA_DIR, "user_features.parquet"), index=False)
    item_features.to_parquet(os.path.join(PROCESSED_DATA_DIR, "item_features.parquet"), index=False)
    train_dm.to_parquet(os.path.join(PROCESSED_DATA_DIR, "train_deepfm.parquet"), index=False)
    val_dm.to_parquet(os.path.join(PROCESSED_DATA_DIR, "val_deepfm.parquet"), index=False)
    test_dm.to_parquet(os.path.join(PROCESSED_DATA_DIR, "test_deepfm.parquet"), index=False)

    # Save feature metadata
    sparse_features = ["user_idx", "track_idx", "age_bucket", "gender", "country_idx"]
    dense_features = [
        "interaction_count", "play_count", "like_count", "avg_completion", "avg_rating",
        "danceability", "energy", "tempo", "valence", "acousticness",
        "log_popularity", "item_interaction_count", "item_avg_completion",
        "item_avg_rating", "item_like_ratio",
    ]

    feature_meta = {
        "sparse_features": sparse_features,
        "dense_features": dense_features,
        "sparse_dims": {
            "user_idx": len(user2idx),
            "track_idx": len(track2idx),
            "age_bucket": 5,
            "gender": 3,
            "country_idx": int(user_features["country_idx"].max()) + 1,
        },
        "num_users": len(user2idx),
        "num_items": len(track2idx),
    }

    with open(os.path.join(PROCESSED_DATA_DIR, "feature_meta.json"), "w") as f:
        json.dump(feature_meta, f, indent=2)

    logger.info("=" * 60)
    logger.info("Feature engineering complete!")
    logger.info(f"  Sparse features: {sparse_features}")
    logger.info(f"  Dense features ({len(dense_features)}): {dense_features[:5]}...")
    logger.info(f"  Output: {PROCESSED_DATA_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_feature_engineering()
