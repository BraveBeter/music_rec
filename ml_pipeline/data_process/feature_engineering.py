"""
Feature Engineering Pipeline.
Builds user features, item features, and interaction features
for DeepFM and other models.

Usage:
  uv run python -m ml_pipeline.data_process.feature_engineering [--task-id <id>]
"""
import argparse
import os
import sys
import logging
import json

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder, MinMaxScaler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, NEG_SAMPLE_RATIO, COMPLETION_RATE_THRESHOLD
from ml_pipeline.training.progress import ProgressTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def build_user_features(
    users: pd.DataFrame,
    interactions: pd.DataFrame,
    track_artist_idx: dict[str, int] | None = None,
    track_genre_idx: dict[str, int] | None = None,
) -> pd.DataFrame:
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

    if track_artist_idx and track_genre_idx:
        positive = interactions[interactions["label"] == 1].copy()
        positive["artist_idx"] = positive["track_id"].map(track_artist_idx).fillna(0).astype(int)
        positive["genre_idx"] = positive["track_id"].map(track_genre_idx).fillna(0).astype(int)

        total_pos = positive.groupby("user_id").size().rename("positive_count")

        top_artist = (
            positive.groupby(["user_id", "artist_idx"]).size().rename("artist_cnt").reset_index()
            .sort_values(["user_id", "artist_cnt"], ascending=[True, False])
            .drop_duplicates("user_id")
            .rename(columns={"artist_idx": "top_artist_idx", "artist_cnt": "top_artist_count"})
        )
        top_genre = (
            positive.groupby(["user_id", "genre_idx"]).size().rename("genre_cnt").reset_index()
            .sort_values(["user_id", "genre_cnt"], ascending=[True, False])
            .drop_duplicates("user_id")
            .rename(columns={"genre_idx": "top_genre_idx", "genre_cnt": "top_genre_count"})
        )

        recent_positive = positive[positive["interaction_type"].isin([1, 2])].sort_values("created_at")
        last_pref = (
            recent_positive.groupby("user_id")[["artist_idx", "genre_idx"]]
            .last()
            .rename(columns={"artist_idx": "last_artist_idx", "genre_idx": "last_genre_idx"})
            .reset_index()
        )

        diversity = positive.groupby("user_id").agg(
            artist_diversity=("artist_idx", "nunique"),
            genre_diversity=("genre_idx", "nunique"),
        ).reset_index()

        user_feats = user_feats.merge(total_pos, on="user_id", how="left")
        user_feats = user_feats.merge(top_artist, on="user_id", how="left")
        user_feats = user_feats.merge(top_genre, on="user_id", how="left")
        user_feats = user_feats.merge(last_pref, on="user_id", how="left")
        user_feats = user_feats.merge(diversity, on="user_id", how="left")

        user_feats["positive_count"] = user_feats["positive_count"].fillna(1)
        user_feats["top_artist_share"] = user_feats["top_artist_count"].fillna(0) / user_feats["positive_count"]
        user_feats["top_genre_share"] = user_feats["top_genre_count"].fillna(0) / user_feats["positive_count"]

        sparse_pref_cols = ["top_artist_idx", "top_genre_idx", "last_artist_idx", "last_genre_idx"]
        for col in sparse_pref_cols:
            user_feats[col] = user_feats[col].fillna(0).astype(int)

        diversity_cols = ["artist_diversity", "genre_diversity", "top_artist_share", "top_genre_share"]
        user_feats[diversity_cols] = user_feats[diversity_cols].fillna(0.0)

    # Normalize numeric features
    scaler = MinMaxScaler()
    numeric_cols = [
        "interaction_count", "play_count", "like_count", "avg_completion", "avg_rating",
        "artist_diversity", "genre_diversity", "top_artist_share", "top_genre_share",
    ]
    numeric_cols = [col for col in numeric_cols if col in user_feats.columns]
    user_feats[numeric_cols] = scaler.fit_transform(user_feats[numeric_cols])

    logger.info(f"Built user features: {user_feats.shape}")
    return user_feats


def build_item_features(
    tracks: pd.DataFrame,
    interactions: pd.DataFrame,
    track_genres: dict[str, list[str]] | None = None,
) -> tuple[pd.DataFrame, dict[str, int], dict[str, int]]:
    """
    Build item feature vectors:
    - acoustic features: danceability, energy, tempo, valence, acousticness (normalized)
    - popularity: log-scaled play_count
    - avg_rating: average rating from interactions
    - interaction_count: total interactions
    """
    item_feats = tracks.copy()
    item_feats["artist_name"] = item_feats["artist_name"].fillna("Unknown")

    artist_encoder = LabelEncoder()
    item_feats["artist_idx"] = artist_encoder.fit_transform(item_feats["artist_name"])

    track_genres = track_genres or {}
    item_feats["primary_genre"] = item_feats["track_id"].map(
        lambda tid: (track_genres.get(tid) or ["Unknown"])[0]
    )
    genre_encoder = LabelEncoder()
    item_feats["primary_genre_idx"] = genre_encoder.fit_transform(item_feats["primary_genre"])

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
    track_artist_idx = dict(zip(item_feats["track_id"], item_feats["artist_idx"]))
    track_genre_idx = dict(zip(item_feats["track_id"], item_feats["primary_genre_idx"]))
    return item_feats, track_artist_idx, track_genre_idx


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
    user_cols = [
        "user_id", "age_bucket", "gender", "country_idx",
        "interaction_count", "play_count", "like_count", "avg_completion", "avg_rating",
        "top_artist_idx", "top_genre_idx", "last_artist_idx", "last_genre_idx",
        "artist_diversity", "genre_diversity", "top_artist_share", "top_genre_share",
    ]
    user_cols = [col for col in user_cols if col in user_features.columns]
    merged = train.merge(user_features[user_cols], on="user_id", how="left", suffixes=("", "_uf"))

    # Merge item features
    item_cols = [
        "track_id", "danceability", "energy", "tempo", "valence", "acousticness",
        "log_popularity", "item_interaction_count", "item_avg_completion",
        "item_avg_rating", "item_like_ratio", "artist_idx", "primary_genre_idx",
    ]
    merged = merged.merge(item_features[item_cols], on="track_id", how="left", suffixes=("", "_if"))

    merged = merged.fillna(0)

    if {"top_artist_idx", "artist_idx"}.issubset(merged.columns):
        merged["top_artist_match"] = (merged["top_artist_idx"] == merged["artist_idx"]).astype(float)
    else:
        merged["top_artist_match"] = 0.0
    if {"top_genre_idx", "primary_genre_idx"}.issubset(merged.columns):
        merged["top_genre_match"] = (merged["top_genre_idx"] == merged["primary_genre_idx"]).astype(float)
    else:
        merged["top_genre_match"] = 0.0
    if {"last_artist_idx", "artist_idx"}.issubset(merged.columns):
        merged["last_artist_match"] = (merged["last_artist_idx"] == merged["artist_idx"]).astype(float)
    else:
        merged["last_artist_match"] = 0.0
    if {"last_genre_idx", "primary_genre_idx"}.issubset(merged.columns):
        merged["last_genre_match"] = (merged["last_genre_idx"] == merged["primary_genre_idx"]).astype(float)
    else:
        merged["last_genre_match"] = 0.0

    logger.info(f"Built DeepFM dataset: {merged.shape}")
    return merged


def negative_sampling(
    interactions: pd.DataFrame,
    all_track_ids: list[str],
    popularity_ranked_track_ids: list[str] | None = None,
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
        popular_candidates = []
        if popularity_ranked_track_ids:
            popular_candidates = [t for t in popularity_ranked_track_ids if t not in pos_items][: max(n_neg * 3, 500)]

        popular_quota = min(len(popular_candidates), max(1, n_neg // 2))
        sampled_popular = []
        if popular_quota > 0:
            sampled_popular = list(np.random.choice(popular_candidates, size=popular_quota, replace=False))

        remaining_quota = max(0, n_neg - len(sampled_popular))
        remaining_pool = [t for t in available if t not in sampled_popular]
        sampled_random = []
        if remaining_quota > 0 and remaining_pool:
            sampled_random = list(
                np.random.choice(remaining_pool, size=min(remaining_quota, len(remaining_pool)), replace=False)
            )

        neg_items = sampled_popular + sampled_random
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


def run_feature_engineering(task_id: str | None = None):
    """Main feature engineering pipeline."""
    tracker = None
    if task_id:
        tracker = ProgressTracker(task_id, "feature_engineering", total_phases=4)
        tracker.__enter__()

    def _log(msg: str):
        logger.info(msg)
        if tracker:
            tracker.append_log(msg)

    def _phase(name: str, idx: int):
        if tracker:
            tracker.update_phase(name, idx)

    _log("=" * 60)
    _log("Starting feature engineering")
    _log("=" * 60)

    # Load preprocessed data
    _log("Loading preprocessed data...")
    train = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "train.parquet"))
    val = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "val.parquet"))
    test = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "test.parquet"))
    tracks = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "tracks.parquet"))
    users = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "users.parquet"))
    with open(os.path.join(PROCESSED_DATA_DIR, "track_genres.json")) as f:
        track_genres = json.load(f)

    # ID mappings
    user2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet")).values)
    track2idx = dict(pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet")).values)

    all_track_ids = list(track2idx.keys())
    tracks = tracks[tracks["track_id"].isin(all_track_ids)].copy()
    popularity_ranked = (
        train[train["label"] == 1]["track_id"].value_counts().index.tolist()
    )

    # Build features
    _phase("Building item features", 1)
    _log("[1/4] Building item features...")
    item_features, track_artist_idx, track_genre_idx = build_item_features(tracks, train, track_genres)

    _phase("Building user features", 2)
    _log("[2/4] Building user features...")
    user_features = build_user_features(users, train, track_artist_idx, track_genre_idx)

    # Negative sampling for train
    _phase("Negative sampling", 3)
    _log("[3/4] Negative sampling for training set...")
    train_augmented = negative_sampling(train, all_track_ids, popularity_ranked_track_ids=popularity_ranked)

    # Build DeepFM datasets
    _phase("Building DeepFM feature matrices", 4)
    _log("[4/4] Building DeepFM feature matrices...")
    train_dm = build_deepfm_dataset(train_augmented, user_features, item_features, track2idx, user2idx)
    val_dm = build_deepfm_dataset(val, user_features, item_features, track2idx, user2idx)
    test_dm = build_deepfm_dataset(test, user_features, item_features, track2idx, user2idx)

    # Drop non-numeric / datetime columns before saving
    drop_cols = ["created_at", "title", "artist_name", "primary_genre", "username", "country"]
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
    sparse_features = [
        "user_idx", "track_idx", "age_bucket", "gender", "country_idx",
        "artist_idx", "primary_genre_idx", "top_artist_idx", "top_genre_idx",
        "last_artist_idx", "last_genre_idx",
    ]
    dense_features = [
        "interaction_count", "play_count", "like_count", "avg_completion", "avg_rating",
        "danceability", "energy", "tempo", "valence", "acousticness",
        "log_popularity", "item_interaction_count", "item_avg_completion",
        "item_avg_rating", "item_like_ratio",
        "artist_diversity", "genre_diversity", "top_artist_share", "top_genre_share",
        "top_artist_match", "top_genre_match", "last_artist_match", "last_genre_match",
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
            "artist_idx": int(item_features["artist_idx"].max()) + 1,
            "primary_genre_idx": int(item_features["primary_genre_idx"].max()) + 1,
            "top_artist_idx": int(item_features["artist_idx"].max()) + 1,
            "top_genre_idx": int(item_features["primary_genre_idx"].max()) + 1,
            "last_artist_idx": int(item_features["artist_idx"].max()) + 1,
            "last_genre_idx": int(item_features["primary_genre_idx"].max()) + 1,
        },
        "num_users": len(user2idx),
        "num_items": len(track2idx),
    }

    with open(os.path.join(PROCESSED_DATA_DIR, "feature_meta.json"), "w") as f:
        json.dump(feature_meta, f, indent=2)

    _log("=" * 60)
    _log("Feature engineering complete!")
    _log(f"  Sparse features: {sparse_features}")
    _log(f"  Dense features ({len(dense_features)}): {dense_features[:5]}...")
    _log(f"  Output: {PROCESSED_DATA_DIR}")
    _log("=" * 60)

    if tracker:
        tracker.__exit__(None, None, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default=None)
    args = parser.parse_args()
    run_feature_engineering(task_id=args.task_id)
