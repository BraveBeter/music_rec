"""
Generate synthetic user interaction data for training recommendation models.
Creates realistic user behavior patterns with genre preferences.
"""
import asyncio
import sys
import os
import random
import math
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://music_app:music_app_pass_2026@localhost:13307/music_rec",
)

# ---------- User Profiles ----------
NUM_SYNTHETIC_USERS = 60
MIN_INTERACTIONS_PER_USER = 40
MAX_INTERACTIONS_PER_USER = 250

# Genre preference archetypes
ARCHETYPES = [
    {"name": "pop_lover",    "prefs": {"Pop": 0.45, "R&B": 0.20, "Latin": 0.15, "Hip-Hop": 0.10, "Electronic": 0.05, "Rock": 0.03, "Jazz": 0.01, "Classical": 0.01}},
    {"name": "rock_fan",     "prefs": {"Rock": 0.50, "Pop": 0.15, "Electronic": 0.10, "Hip-Hop": 0.10, "Jazz": 0.05, "Classical": 0.05, "R&B": 0.03, "Latin": 0.02}},
    {"name": "hiphop_head",  "prefs": {"Hip-Hop": 0.45, "R&B": 0.20, "Pop": 0.15, "Electronic": 0.10, "Latin": 0.05, "Rock": 0.03, "Jazz": 0.01, "Classical": 0.01}},
    {"name": "edm_raver",    "prefs": {"Electronic": 0.50, "Pop": 0.15, "Hip-Hop": 0.10, "Rock": 0.10, "Latin": 0.05, "R&B": 0.05, "Jazz": 0.03, "Classical": 0.02}},
    {"name": "jazz_buff",    "prefs": {"Jazz": 0.40, "Classical": 0.20, "R&B": 0.15, "Pop": 0.10, "Rock": 0.05, "Latin": 0.05, "Electronic": 0.03, "Hip-Hop": 0.02}},
    {"name": "classical",    "prefs": {"Classical": 0.45, "Jazz": 0.20, "Pop": 0.10, "Rock": 0.10, "Electronic": 0.05, "R&B": 0.05, "Latin": 0.03, "Hip-Hop": 0.02}},
    {"name": "latin_vibes",  "prefs": {"Latin": 0.40, "Pop": 0.20, "R&B": 0.15, "Hip-Hop": 0.10, "Electronic": 0.05, "Rock": 0.05, "Jazz": 0.03, "Classical": 0.02}},
    {"name": "eclectic",     "prefs": {"Pop": 0.15, "Rock": 0.15, "Hip-Hop": 0.15, "Electronic": 0.15, "Jazz": 0.10, "Classical": 0.10, "R&B": 0.10, "Latin": 0.10}},
]

COUNTRIES = ["China", "USA", "UK", "Japan", "Korea", "Brazil", "Germany", "France", "India", "Australia"]
GENDERS = [0, 1, 2]  # unknown, male, female


def _pick_archetype() -> dict:
    return random.choice(ARCHETYPES)


def _generate_user(idx: int, archetype: dict) -> dict:
    age = random.choice([
        random.randint(16, 22),  # young
        random.randint(23, 35),  # adult
        random.randint(36, 55),  # mid
    ])
    return {
        "username": f"synth_user_{idx:03d}",
        "password_hash": "$2b$12$iIr5ocgmGsKOhOG4/Ke4AuXeaFukrV/Q9N2dhjATHvHlT3ERecz46",  # hash of "test123"
        "role": "user",
        "age": age,
        "gender": random.choice(GENDERS),
        "country": random.choice(COUNTRIES),
        "archetype": archetype["name"],
    }


def _interaction_type_and_metadata(liked: bool) -> dict:
    """Generate interaction type and metadata based on whether user 'likes' the track."""
    if liked:
        # Positive interaction
        roll = random.random()
        if roll < 0.65:
            # play with high completion
            completion = random.uniform(0.6, 1.0)
            duration_fraction = completion
            return {
                "interaction_type": 1,  # play
                "rating": random.choice([None, None, 4.0, 5.0]) if random.random() < 0.15 else None,
                "completion_rate": round(completion, 3),
                "duration_fraction": duration_fraction,
            }
        elif roll < 0.85:
            # like
            return {
                "interaction_type": 2,  # like
                "rating": None,
                "completion_rate": round(random.uniform(0.5, 1.0), 3),
                "duration_fraction": random.uniform(0.5, 1.0),
            }
        else:
            # rate (high)
            return {
                "interaction_type": 4,  # rate
                "rating": random.choice([4.0, 4.5, 5.0]),
                "completion_rate": round(random.uniform(0.7, 1.0), 3),
                "duration_fraction": random.uniform(0.7, 1.0),
            }
    else:
        # Negative interaction
        roll = random.random()
        if roll < 0.6:
            # skip
            return {
                "interaction_type": 3,  # skip
                "rating": None,
                "completion_rate": round(random.uniform(0.0, 0.25), 3),
                "duration_fraction": random.uniform(0.0, 0.25),
            }
        elif roll < 0.85:
            # play with low completion
            completion = random.uniform(0.05, 0.35)
            return {
                "interaction_type": 1,
                "rating": None,
                "completion_rate": round(completion, 3),
                "duration_fraction": completion,
            }
        else:
            # rate (low)
            return {
                "interaction_type": 4,
                "rating": random.choice([1.0, 1.5, 2.0, 2.5]),
                "completion_rate": round(random.uniform(0.1, 0.4), 3),
                "duration_fraction": random.uniform(0.1, 0.4),
            }


async def generate():
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Check existing synthetic users
        result = await session.execute(
            text("SELECT COUNT(*) FROM users WHERE username LIKE 'synth_user_%'")
        )
        synth_count = result.scalar() or 0
        if synth_count >= NUM_SYNTHETIC_USERS:
            print(f"✅ Already have {synth_count} synthetic users. Skipping generation.")
            await engine.dispose()
            return

        # Load all tracks with their tags
        result = await session.execute(text("""
            SELECT t.track_id, t.duration_ms, tg.tag_name
            FROM tracks t
            LEFT JOIN track_tags tt ON t.track_id = tt.track_id
            LEFT JOIN tags tg ON tt.tag_id = tg.tag_id
            WHERE t.status = 1
        """))
        rows = result.fetchall()

        # Build track-to-genre mapping
        track_genres: dict[str, list[str]] = {}
        track_durations: dict[str, int] = {}
        for track_id, duration_ms, tag_name in rows:
            if track_id not in track_genres:
                track_genres[track_id] = []
                track_durations[track_id] = duration_ms or 30000
            if tag_name:
                track_genres[track_id].append(tag_name)

        all_track_ids = list(track_genres.keys())
        if not all_track_ids:
            print("❌ No tracks in database. Run seed_data.py first.")
            await engine.dispose()
            return

        print(f"📊 Found {len(all_track_ids)} tracks in database.")
        print(f"👤 Generating {NUM_SYNTHETIC_USERS} synthetic users...")

        # Precompute genre-to-tracks mapping
        genre_tracks: dict[str, list[str]] = {}
        for tid, genres in track_genres.items():
            for g in genres:
                if g not in genre_tracks:
                    genre_tracks[g] = []
                genre_tracks[g].append(tid)

        total_interactions = 0
        base_time = datetime.now() - timedelta(days=90)

        for i in range(NUM_SYNTHETIC_USERS):
            archetype = _pick_archetype()
            user_data = _generate_user(i, archetype)

            # Insert user
            await session.execute(
                text("""
                    INSERT IGNORE INTO users (username, password_hash, role, age, gender, country)
                    VALUES (:username, :password_hash, :role, :age, :gender, :country)
                """),
                {k: v for k, v in user_data.items() if k != "archetype"},
            )
            await session.flush()

            # Get user_id
            result = await session.execute(
                text("SELECT user_id FROM users WHERE username = :username"),
                {"username": user_data["username"]},
            )
            user_row = result.first()
            if not user_row:
                continue
            user_id = user_row[0]

            # Generate interactions
            n_interactions = random.randint(MIN_INTERACTIONS_PER_USER, MAX_INTERACTIONS_PER_USER)
            prefs = archetype["prefs"]

            for j in range(n_interactions):
                # Pick a genre based on user preference
                genre = random.choices(list(prefs.keys()), weights=list(prefs.values()), k=1)[0]
                candidates = genre_tracks.get(genre, [])
                if not candidates:
                    candidates = all_track_ids

                track_id = random.choice(candidates)
                # Determine if this is a "liked" interaction (genre preference → higher like probability)
                genre_weight = prefs.get(genre, 0.1)
                liked = random.random() < (0.3 + genre_weight * 0.7)  # 30%-100% positive based on preference

                meta = _interaction_type_and_metadata(liked)

                # Compute play_duration from completion_rate
                duration_ms = track_durations.get(track_id, 30000)
                play_duration = int(duration_ms * meta["duration_fraction"])

                # Random timestamp within last 90 days
                ts = base_time + timedelta(
                    seconds=random.randint(0, 90 * 86400)
                )

                await session.execute(
                    text("""
                        INSERT INTO user_interactions 
                        (user_id, track_id, interaction_type, rating, play_duration, completion_rate, created_at)
                        VALUES (:user_id, :track_id, :interaction_type, :rating, :play_duration, :completion_rate, :created_at)
                    """),
                    {
                        "user_id": user_id,
                        "track_id": track_id,
                        "interaction_type": meta["interaction_type"],
                        "rating": meta["rating"],
                        "play_duration": play_duration,
                        "completion_rate": meta["completion_rate"],
                        "created_at": ts,
                    },
                )
                total_interactions += 1

            if (i + 1) % 10 == 0:
                await session.flush()
                print(f"  👤 Created {i + 1}/{NUM_SYNTHETIC_USERS} users...")

        # Update play_count on tracks based on actual interactions
        await session.execute(text("""
            UPDATE tracks t SET play_count = (
                SELECT COUNT(*) FROM user_interactions ui 
                WHERE ui.track_id = t.track_id AND ui.interaction_type = 1
            )
        """))

        await session.commit()
        print(f"✅ Generated {NUM_SYNTHETIC_USERS} users, {total_interactions} interactions.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(generate())
