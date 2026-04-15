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


async def run_preprocessing():
    """Main preprocessing pipeline."""
    logger.info("=" * 60)
    logger.info("Starting data preprocessing pipeline")
    logger.info("=" * 60)

    # 1. Load data
    logger.info("[1/6] Loading data from database...")
    interactions, tracks, users, track_tags = await _load_from_db()
    logger.info(f"  Loaded: {len(interactions)} interactions, {len(tracks)} tracks, {len(users)} users")

    if interactions.empty:
        logger.error("No interactions found! Run generate_synthetic_data.py first.")
        return

    # 2. Clean
    logger.info("[2/6] Cleaning interactions...")
    interactions = _clean_interactions(interactions)

    # 3. Generate labels
    logger.info("[3/6] Generating implicit labels...")
    interactions = _generate_implicit_labels(interactions)

    # 4. Build ID mappings
    logger.info("[4/6] Building ID mappings...")
    user2idx, track2idx = _build_id_mappings(interactions)
    interactions["user_idx"] = interactions["user_id"].map(user2idx)
    interactions["track_idx"] = interactions["track_id"].map(track2idx)

    # 5. Split
    logger.info("[5/6] Temporal train/val/test split...")
    train, val, test = _temporal_split(interactions)

    # 6. Build sequences
    logger.info("[6/6] Building user sequences for SASRec...")
    sequences = _build_user_sequences(interactions)

    # Save everything
    logger.info("💾 Saving processed data...")
    os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

    # Convert datetime columns to string for parquet compatibility
    for df_name, df_ref in [("interactions", interactions), ("train", train), ("val", val), ("test", test), ("users", users)]:
        if "created_at" in df_ref.columns:
            df_ref["created_at"] = df_ref["created_at"].astype(str)

    train.to_parquet(os.path.join(PROCESSED_DATA_DIR, "train.parquet"), index=False)
    val.to_parquet(os.path.join(PROCESSED_DATA_DIR, "val.parquet"), index=False)
    test.to_parquet(os.path.join(PROCESSED_DATA_DIR, "test.parquet"), index=False)
    interactions.to_parquet(os.path.join(PROCESSED_DATA_DIR, "all_interactions.parquet"), index=False)
    tracks.to_parquet(os.path.join(PROCESSED_DATA_DIR, "tracks.parquet"), index=False)
    users.to_parquet(os.path.join(PROCESSED_DATA_DIR, "users.parquet"), index=False)

    # Save ID mappings
    pd.DataFrame(list(user2idx.items()), columns=["user_id", "user_idx"]).to_parquet(
        os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet"), index=False
    )
    pd.DataFrame(list(track2idx.items()), columns=["track_id", "track_idx"]).to_parquet(
        os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet"), index=False
    )

    # Save sequences as JSON for SASRec
    import json
    seq_serializable = {str(k): v for k, v in sequences.items()}
    with open(os.path.join(PROCESSED_DATA_DIR, "user_sequences.json"), "w") as f:
        json.dump(seq_serializable, f)

    # Save track-genre and genre-track mappings for recall diversity
    if not track_tags.empty:
        track_genres_map = track_tags.groupby("track_id")["tag_name"].apply(list).to_dict()
        with open(os.path.join(PROCESSED_DATA_DIR, "track_genres.json"), "w") as f:
            json.dump(track_genres_map, f)
        genre_tracks_map = track_tags.groupby("tag_name")["track_id"].apply(list).to_dict()
        with open(os.path.join(PROCESSED_DATA_DIR, "genre_tracks.json"), "w") as f:
            json.dump(genre_tracks_map, f)
        logger.info(f"  Saved track-genre mappings: {len(track_genres_map)} tracks, {len(genre_tracks_map)} genres")

    # Stats summary
    logger.info("=" * 60)
    logger.info("Preprocessing complete!")
    logger.info(f"  Users: {len(user2idx)}")
    logger.info(f"  Tracks: {len(track2idx)}")
    logger.info(f"  Total interactions: {len(interactions)}")
    logger.info(f"  Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")
    logger.info(f"  User sequences: {len(sequences)}")
    logger.info(f"  Output directory: {PROCESSED_DATA_DIR}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_preprocessing())
