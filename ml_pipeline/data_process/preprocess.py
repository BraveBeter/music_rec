"""
Data Preprocessing Pipeline.
Reads raw interaction data from MySQL, cleans it, and generates
user-item interaction matrices and train/val/test splits.
"""
import os
import sys
import asyncio
import logging

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from ml_pipeline.config import PROCESSED_DATA_DIR, RAW_DATA_DIR

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://music_app:music_app_pass_2026@localhost:13307/music_rec",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _load_from_db() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load interactions, tracks, users, and track_tags from MySQL."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Interactions
        result = await session.execute(text("""
            SELECT interaction_id, user_id, track_id, interaction_type,
                   rating, play_duration, completion_rate, created_at
            FROM user_interactions ORDER BY created_at
        """))
        interactions = pd.DataFrame(result.fetchall(), columns=[
            "interaction_id", "user_id", "track_id", "interaction_type",
            "rating", "play_duration", "completion_rate", "created_at",
        ])

        # Tracks with features
        result = await session.execute(text("""
            SELECT t.track_id, t.title, t.artist_name, t.duration_ms, t.play_count,
                   tf.danceability, tf.energy, tf.tempo, tf.valence, tf.acousticness
            FROM tracks t
            LEFT JOIN track_features tf ON t.track_id = tf.track_id
            WHERE t.status = 1
        """))
        tracks = pd.DataFrame(result.fetchall(), columns=[
            "track_id", "title", "artist_name", "duration_ms", "play_count",
            "danceability", "energy", "tempo", "valence", "acousticness",
        ])

        # Track tags
        result = await session.execute(text("""
            SELECT tt.track_id, tg.tag_name
            FROM track_tags tt JOIN tags tg ON tt.tag_id = tg.tag_id
        """))
        track_tags = pd.DataFrame(result.fetchall(), columns=["track_id", "tag_name"])

        # Users
        result = await session.execute(text("""
            SELECT user_id, username, age, gender, country, created_at
            FROM users
        """))
        users = pd.DataFrame(result.fetchall(), columns=[
            "user_id", "username", "age", "gender", "country", "created_at",
        ])

    await engine.dispose()
    return interactions, tracks, users, track_tags


def _clean_interactions(df: pd.DataFrame) -> pd.DataFrame:
    """Data cleaning: remove duplicates, filter anomalies."""
    original_len = len(df)

    # Drop exact duplicates
    df = df.drop_duplicates(subset=["user_id", "track_id", "interaction_type", "created_at"])

    # Filter out interactions with invalid types
    df = df[df["interaction_type"].isin([1, 2, 3, 4])].copy()

    # Clip completion_rate to [0, 1]
    df["completion_rate"] = df["completion_rate"].clip(0.0, 1.0)

    # Filter users with too few interactions (< 5)
    user_counts = df["user_id"].value_counts()
    valid_users = user_counts[user_counts >= 5].index
    df = df[df["user_id"].isin(valid_users)].copy()

    # Filter tracks with too few interactions (< 2)
    track_counts = df["track_id"].value_counts()
    valid_tracks = track_counts[track_counts >= 2].index
    df = df[df["track_id"].isin(valid_tracks)].copy()

    logger.info(f"Cleaned interactions: {original_len} → {len(df)} "
                f"({len(df['user_id'].unique())} users, {len(df['track_id'].unique())} tracks)")
    return df


def _generate_implicit_labels(df: pd.DataFrame, threshold: float = 0.3) -> pd.DataFrame:
    """
    Generate binary implicit feedback labels.
    Positive: completion_rate >= threshold OR interaction_type == 2 (like)
    Negative: completion_rate < threshold OR interaction_type == 3 (skip)
    """
    df = df.copy()

    conditions_positive = (
        (df["completion_rate"] >= threshold) |
        (df["interaction_type"] == 2)  # like
    )
    conditions_negative = (
        (df["completion_rate"] < threshold) |
        (df["interaction_type"] == 3)  # skip
    )

    df["label"] = 0
    df.loc[conditions_positive, "label"] = 1
    df.loc[conditions_negative & ~conditions_positive, "label"] = 0

    # For explicit ratings, override
    has_rating = df["rating"].notna()
    df.loc[has_rating & (df["rating"] >= 3.5), "label"] = 1
    df.loc[has_rating & (df["rating"] < 3.0), "label"] = 0

    pos_count = (df["label"] == 1).sum()
    neg_count = (df["label"] == 0).sum()
    logger.info(f"Labels: {pos_count} positive, {neg_count} negative (ratio = 1:{neg_count / max(pos_count, 1):.1f})")
    return df


def _build_id_mappings(interactions: pd.DataFrame) -> tuple[dict, dict]:
    """Build contiguous integer ID mappings for users and items."""
    unique_users = sorted(interactions["user_id"].unique())
    unique_tracks = sorted(interactions["track_id"].unique())

    user2idx = {uid: idx for idx, uid in enumerate(unique_users)}
    track2idx = {tid: idx for idx, tid in enumerate(unique_tracks)}

    return user2idx, track2idx


def _temporal_split(df: pd.DataFrame, val_ratio: float = 0.1, test_ratio: float = 0.1) -> tuple:
    """
    Split data temporally: last interactions per user go to test, second-to-last to val.
    This simulates the real-world scenario where we predict future interactions.
    """
    df = df.sort_values("created_at")

    train_list, val_list, test_list = [], [], []

    for user_id, group in df.groupby("user_id"):
        n = len(group)
        n_test = max(1, int(n * test_ratio))
        n_val = max(1, int(n * val_ratio))
        n_train = n - n_test - n_val

        if n_train < 3:
            # Too few interactions, put everything in train
            train_list.append(group)
            continue

        train_list.append(group.iloc[:n_train])
        val_list.append(group.iloc[n_train:n_train + n_val])
        test_list.append(group.iloc[n_train + n_val:])

    train = pd.concat(train_list, ignore_index=True) if train_list else pd.DataFrame()
    val = pd.concat(val_list, ignore_index=True) if val_list else pd.DataFrame()
    test = pd.concat(test_list, ignore_index=True) if test_list else pd.DataFrame()

    logger.info(f"Split: train={len(train)}, val={len(val)}, test={len(test)}")
    return train, val, test


def _build_user_sequences(interactions: pd.DataFrame, max_len: int = 50) -> dict[int, list[str]]:
    """Build user play sequences (chronologically sorted) for SASRec."""
    play_interactions = interactions[interactions["interaction_type"].isin([1, 2])].copy()
    play_interactions = play_interactions.sort_values("created_at")

    sequences = {}
    for user_id, group in play_interactions.groupby("user_id"):
        seq = group["track_id"].tolist()[-max_len:]
        if len(seq) >= 3:  # Minimum sequence length
            sequences[user_id] = seq

    logger.info(f"Built {len(sequences)} user sequences (min 3 items)")
    return sequences


def _build_deepfm_features(
    interactions: pd.DataFrame,
    tracks: pd.DataFrame,
    users: pd.DataFrame,
    track_tags: pd.DataFrame,
    user2idx: dict,
    track2idx: dict,
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
):
    """Build DeepFM-specific feature data and save to disk."""
    import json

    # Build track feature lookup
    track_feat = tracks.set_index("track_id")
    # Build user feature lookup
    user_feat = users.set_index("user_id")

    # Build genre mapping per track (one-hot index)
    genres = sorted(track_tags["tag_name"].unique()) if not track_tags.empty else []
    genre2idx = {g: i for i, g in enumerate(genres)}
    track_genre_idx = track_tags.groupby("track_id")["tag_name"].first().map(genre2idx).to_dict()

    # Sparse features: user_idx, track_idx, genre_idx
    # Dense features: play_duration_norm, completion_rate, danceability, energy, tempo, valence, acousticness
    sparse_features = ["user_idx", "track_idx", "genre_idx"]
    dense_features = ["play_duration_norm", "completion_rate", "danceability", "energy", "tempo", "valence", "acousticness"]

    sparse_dims = {
        "user_idx": len(user2idx),
        "track_idx": len(track2idx),
        "genre_idx": max(len(genres), 1),
    }

    def _enrich_df(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # Map genre index
        df["genre_idx"] = df["track_id"].map(track_genre_idx).fillna(0).astype(int)
        # Normalize play_duration
        if "play_duration" in df.columns:
            max_dur = df["play_duration"].max() or 1
            df["play_duration_norm"] = df["play_duration"].fillna(0) / max_dur
        else:
            df["play_duration_norm"] = 0.0
        # Fill completion_rate
        if "completion_rate" in df.columns:
            df["completion_rate"] = df["completion_rate"].fillna(0.0)
        else:
            df["completion_rate"] = 0.0
        # Track features
        for feat in ["danceability", "energy", "tempo", "valence", "acousticness"]:
            if feat in df.columns:
                df[feat] = df[feat].fillna(0.0).astype(float)
            else:
                # Lookup from track features
                feat_vals = df["track_id"].map(
                    track_feat[feat] if feat in track_feat.columns else pd.Series(dtype=float)
                ).fillna(0.0)
                df[feat] = feat_vals
        # Ensure user_idx and track_idx
        if "user_idx" not in df.columns:
            df["user_idx"] = df["user_id"].map(user2idx).fillna(0).astype(int)
        if "track_idx" not in df.columns:
            df["track_idx"] = df["track_id"].map(track2idx).fillna(0).astype(int)

        # Select only needed columns
        cols = sparse_features + dense_features + ["label"]
        for c in cols:
            if c not in df.columns:
                df[c] = 0
        return df[cols]

    train_deepfm = _enrich_df(train)
    val_deepfm = _enrich_df(val)
    test_deepfm = _enrich_df(test)

    train_deepfm.to_parquet(os.path.join(PROCESSED_DATA_DIR, "train_deepfm.parquet"), index=False)
    val_deepfm.to_parquet(os.path.join(PROCESSED_DATA_DIR, "val_deepfm.parquet"), index=False)
    test_deepfm.to_parquet(os.path.join(PROCESSED_DATA_DIR, "test_deepfm.parquet"), index=False)

    feature_meta = {
        "sparse_features": sparse_features,
        "dense_features": dense_features,
        "sparse_dims": sparse_dims,
    }
    with open(os.path.join(PROCESSED_DATA_DIR, "feature_meta.json"), "w") as f:
        json.dump(feature_meta, f, indent=2)

    logger.info(f"  DeepFM features: {len(sparse_features)} sparse, {len(dense_features)} dense")
    logger.info(f"  DeepFM data: train={len(train_deepfm)}, val={len(val_deepfm)}, test={len(test_deepfm)}")


async def run_preprocessing(task_id: str | None = None):
    """Main preprocessing pipeline."""
    tracker = None
    phases = ["loading", "cleaning", "labeling", "mapping", "splitting", "sequences", "saving"]
    total_phases = len(phases)

    if task_id:
        from ml_pipeline.training.progress import ProgressTracker
        tracker = ProgressTracker(task_id, "preprocess", total_phases=total_phases)
        tracker.__enter__()

    logger.info("=" * 60)
    logger.info("Starting data preprocessing pipeline")
    logger.info("=" * 60)

    def _phase(idx: int, name: str, log_msg: str):
        logger.info(f"[{idx + 1}/{total_phases}] {log_msg}")
        if tracker:
            tracker.update_phase(name, idx + 1)
            tracker.append_log(f"[{idx + 1}/{total_phases}] {log_msg}")

    # 1. Load data
    _phase(0, "loading", "Loading data from database...")
    interactions, tracks, users, track_tags = await _load_from_db()
    logger.info(f"  Loaded: {len(interactions)} interactions, {len(tracks)} tracks, {len(users)} users")

    if interactions.empty:
        logger.error("No interactions found! Run generate_synthetic_data.py first.")
        if tracker:
            tracker.mark_completed({"error": "no_interactions"})
            tracker.__exit__(None, None, None)
        return

    # 2. Clean
    _phase(1, "cleaning", "Cleaning interactions...")
    interactions = _clean_interactions(interactions)

    # 3. Generate labels
    _phase(2, "labeling", "Generating implicit labels...")
    interactions = _generate_implicit_labels(interactions)

    # 4. Build ID mappings
    _phase(3, "mapping", "Building ID mappings...")
    user2idx, track2idx = _build_id_mappings(interactions)
    interactions["user_idx"] = interactions["user_id"].map(user2idx)
    interactions["track_idx"] = interactions["track_id"].map(track2idx)

    # 5. Split
    _phase(4, "splitting", "Temporal train/val/test split...")
    train, val, test = _temporal_split(interactions)

    # 6. Build sequences
    _phase(5, "sequences", "Building user sequences for SASRec...")
    sequences = _build_user_sequences(interactions)

    # Save everything
    _phase(6, "saving", "Saving processed data...")
    os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

    for df_name, df_ref in [("interactions", interactions), ("train", train), ("val", val), ("test", test), ("users", users)]:
        if "created_at" in df_ref.columns:
            df_ref["created_at"] = df_ref["created_at"].astype(str)

    train.to_parquet(os.path.join(PROCESSED_DATA_DIR, "train.parquet"), index=False)
    val.to_parquet(os.path.join(PROCESSED_DATA_DIR, "val.parquet"), index=False)
    test.to_parquet(os.path.join(PROCESSED_DATA_DIR, "test.parquet"), index=False)
    interactions.to_parquet(os.path.join(PROCESSED_DATA_DIR, "all_interactions.parquet"), index=False)
    tracks.to_parquet(os.path.join(PROCESSED_DATA_DIR, "tracks.parquet"), index=False)
    users.to_parquet(os.path.join(PROCESSED_DATA_DIR, "users.parquet"), index=False)

    pd.DataFrame(list(user2idx.items()), columns=["user_id", "user_idx"]).to_parquet(
        os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet"), index=False
    )
    pd.DataFrame(list(track2idx.items()), columns=["track_id", "track_idx"]).to_parquet(
        os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet"), index=False
    )

    import json
    seq_serializable = {str(k): v for k, v in sequences.items()}
    with open(os.path.join(PROCESSED_DATA_DIR, "user_sequences.json"), "w") as f:
        json.dump(seq_serializable, f)

    if not track_tags.empty:
        track_genres_map = track_tags.groupby("track_id")["tag_name"].apply(list).to_dict()
        with open(os.path.join(PROCESSED_DATA_DIR, "track_genres.json"), "w") as f:
            json.dump(track_genres_map, f)
        genre_tracks_map = track_tags.groupby("tag_name")["track_id"].apply(list).to_dict()
        with open(os.path.join(PROCESSED_DATA_DIR, "genre_tracks.json"), "w") as f:
            json.dump(genre_tracks_map, f)
        logger.info(f"  Saved track-genre mappings: {len(track_genres_map)} tracks, {len(genre_tracks_map)} genres")

    _build_deepfm_features(interactions, tracks, users, track_tags, user2idx, track2idx, train, val, test)

    logger.info("=" * 60)
    logger.info("Preprocessing complete!")
    logger.info(f"  Users: {len(user2idx)}")
    logger.info(f"  Tracks: {len(track2idx)}")
    logger.info(f"  Total interactions: {len(interactions)}")
    logger.info(f"  Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")
    logger.info(f"  User sequences: {len(sequences)}")
    logger.info("=" * 60)

    if tracker:
        tracker.mark_completed({
            "users": len(user2idx),
            "tracks": len(track2idx),
            "interactions": len(interactions),
            "train": len(train),
            "sequences": len(sequences),
        })
        tracker.__exit__(None, None, None)


if __name__ == "__main__":
    task_id = None
    for i, arg in enumerate(sys.argv):
        if arg == "--task-id" and i + 1 < len(sys.argv):
            task_id = sys.argv[i + 1]
    asyncio.run(run_preprocessing(task_id))
