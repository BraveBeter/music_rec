"""
Import tracks from Jamendo API with full streaming URLs.
Jamendo provides Creative Commons music with complete audio streams.

Usage:
    uv run python scripts/import_jamendo.py
    # or in Docker:
    python scripts/import_jamendo.py

Environment:
    DATABASE_URL — MySQL connection string
    JAMENDO_CLIENT_ID — Jamendo API client ID
"""
import asyncio
import sys
import os
import random
import logging

import httpx
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://music_app:music_app_pass_2026@localhost:13307/music_rec",
)
JAMENDO_CLIENT_ID = os.environ.get("JAMENDO_CLIENT_ID", "f2b6da64")

# Jamendo genre tags mapped to our system genre names
GENRE_SEARCH = [
    ("rock", "Rock"),
    ("pop", "Pop"),
    ("hiphop", "Hip-Hop"),
    ("electronic", "Electronic"),
    ("jazz", "Jazz"),
    ("classical", "Classical"),
    ("rnb", "R&B"),
    ("latin", "Latin"),
]

TRACKS_PER_GENRE = 50  # Max tracks to import per genre
JAMENDO_API = "https://api.jamendo.com/v3.0/tracks"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def import_jamendo_tracks():
    """Fetch tracks from Jamendo and insert into database."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Count existing Jamendo tracks
        result = await session.execute(
            text("SELECT COUNT(*) FROM tracks WHERE track_id LIKE 'JM%'")
        )
        existing = result.scalar() or 0
        logger.info(f"Existing Jamendo tracks: {existing}")

        total_inserted = 0
        total_skipped = 0

        async with httpx.AsyncClient(timeout=20) as client:
            for jamendo_tag, genre_name in GENRE_SEARCH:
                logger.info(f"Fetching {genre_name} tracks (tag: {jamendo_tag})...")

                offset = 0
                genre_inserted = 0

                while genre_inserted < TRACKS_PER_GENRE:
                    try:
                        resp = await client.get(JAMENDO_API, params={
                            "client_id": JAMENDO_CLIENT_ID,
                            "format": "json",
                            "limit": 50,
                            "offset": offset,
                            "include": "musicinfo",
                            "audioformat": "mp32",
                            "tags": jamendo_tag,
                            "order": "popularity_total",  # Most popular first
                        })
                        if resp.status_code != 200:
                            logger.warning(f"Jamendo API returned {resp.status_code}")
                            break

                        data = resp.json()
                        tracks = data.get("results", [])
                        if not tracks:
                            break

                    except Exception as e:
                        logger.warning(f"Jamendo API error for '{jamendo_tag}': {e}")
                        break

                    for t in tracks:
                        track_id = f"JM{t['id']}"

                        # Skip if already exists
                        check = await session.execute(
                            text("SELECT track_id FROM tracks WHERE track_id = :tid"),
                            {"tid": track_id},
                        )
                        if check.first():
                            total_skipped += 1
                            continue

                        # Insert track
                        await session.execute(text("""
                            INSERT IGNORE INTO tracks
                            (track_id, title, artist_name, album_name, duration_ms,
                             play_count, status, preview_url, cover_url)
                            VALUES (:track_id, :title, :artist, :album, :duration,
                                    0, 1, :audio_url, :cover_url)
                        """), {
                            "track_id": track_id,
                            "title": t.get("name", "Unknown"),
                            "artist": t.get("artist_name"),
                            "album": t.get("album_name"),
                            "duration": (t.get("duration", 30)) * 1000,
                            "audio_url": t.get("audio"),
                            "cover_url": t.get("image"),
                        })

                        # Insert acoustic features (from musicinfo if available, else random)
                        musicinfo = t.get("musicinfo", {})
                        speed = musicinfo.get("speed", "medium")
                        speed_map = {"slow": 0.4, "medium": 0.6, "fast": 0.8}
                        energy_base = speed_map.get(speed, 0.5)

                        vocal = musicinfo.get("vocalinstrumental", "vocal")
                        acoustic_base = 0.3 if vocal == "instrumental" else 0.1

                        await session.execute(text("""
                            INSERT IGNORE INTO track_features
                            (track_id, danceability, energy, tempo, valence, acousticness)
                            VALUES (:track_id, :danceability, :energy, :tempo, :valence, :acousticness)
                        """), {
                            "track_id": track_id,
                            "danceability": round(random.uniform(0.3, 0.9), 3),
                            "energy": round(energy_base + random.uniform(-0.1, 0.1), 3),
                            "tempo": round(random.uniform(80, 160), 1),
                            "valence": round(random.uniform(0.2, 0.9), 3),
                            "acousticness": round(acoustic_base + random.uniform(-0.05, 0.05), 3),
                        })

                        # Insert genre tag
                        await session.execute(
                            text("INSERT IGNORE INTO tags (tag_name) VALUES (:tag)"),
                            {"tag": genre_name},
                        )
                        tag_result = await session.execute(
                            text("SELECT tag_id FROM tags WHERE tag_name = :tag"),
                            {"tag": genre_name},
                        )
                        tag_row = tag_result.first()
                        if tag_row:
                            await session.execute(text("""
                                INSERT IGNORE INTO track_tags (track_id, tag_id)
                                VALUES (:track_id, :tag_id)
                            """), {"track_id": track_id, "tag_id": tag_row[0]})

                        total_inserted += 1
                        genre_inserted += 1

                    offset += len(tracks)
                    # Jamendo API pagination: stop if no more results
                    if len(tracks) < 50:
                        break

                logger.info(f"  {genre_name}: {genre_inserted} tracks imported")

        await session.commit()
        logger.info(f"Done! Inserted: {total_inserted}, Skipped: {total_skipped}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(import_jamendo_tracks())
