"""
Seed the database with sample music data from Deezer API.
Fetches real tracks with preview URLs for a working demo.
"""
import asyncio
import sys
import httpx
import random
import hashlib
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Direct DB URL for seeding (can run outside Docker)
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://music_app:music_app_pass_2026@localhost:13307/music_rec"
)

# Deezer API - free, no auth needed
DEEZER_API = "https://api.deezer.com"
GENRES = [
    ("pop", "Pop"),
    ("rock", "Rock"),
    ("hiphop", "Hip-Hop"),
    ("electronic", "Electronic"),
    ("jazz", "Jazz"),
    ("classical", "Classical"),
    ("rnb", "R&B"),
    ("latin", "Latin"),
]


async def fetch_tracks_from_deezer(query: str, limit: int = 25) -> list[dict]:
    """Fetch tracks from Deezer search API."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{DEEZER_API}/search",
                params={"q": query, "limit": limit},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", [])
        except Exception as e:
            print(f"  ⚠ Deezer API error for '{query}': {e}")
    return []


async def seed_database():
    """Seed database with real music data from Deezer."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Check if data already exists
        result = await session.execute(text("SELECT COUNT(*) FROM tracks"))
        count = result.scalar()
        if count and count > 0:
            print(f"✅ Database already has {count} tracks. Skipping seed.")
            await engine.dispose()
            return

        print("🎵 Seeding database with music data from Deezer...")

        all_tracks = []
        tag_set = set()

        for genre_query, genre_name in GENRES:
            print(f"  📀 Fetching {genre_name} tracks...")
            tracks = await fetch_tracks_from_deezer(genre_query, limit=30)

            for t in tracks:
                track_id = f"DZ{t['id']}"
                album = t.get("album", {})
                artist = t.get("artist", {})

                track_data = {
                    "track_id": track_id,
                    "title": t.get("title", "Unknown"),
                    "artist_name": artist.get("name"),
                    "album_name": album.get("title"),
                    "duration_ms": (t.get("duration", 30)) * 1000,
                    "play_count": random.randint(100, 50000),
                    "preview_url": t.get("preview"),
                    "cover_url": album.get("cover_medium") or album.get("cover"),
                    "status": 1,
                }
                all_tracks.append(track_data)
                tag_set.add(genre_name)

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        # Deduplicate by track_id
        seen = set()
        unique_tracks = []
        for t in all_tracks:
            if t["track_id"] not in seen:
                seen.add(t["track_id"])
                unique_tracks.append(t)

        print(f"  💿 Inserting {len(unique_tracks)} unique tracks...")

        # Insert tracks
        for t in unique_tracks:
            await session.execute(
                text("""
                    INSERT IGNORE INTO tracks 
                    (track_id, title, artist_name, album_name, duration_ms, play_count, preview_url, cover_url, status)
                    VALUES (:track_id, :title, :artist_name, :album_name, :duration_ms, :play_count, :preview_url, :cover_url, :status)
                """),
                t,
            )

        # Insert tags
        print(f"  🏷 Inserting {len(tag_set)} tags...")
        for tag_name in tag_set:
            await session.execute(
                text("INSERT IGNORE INTO tags (tag_name) VALUES (:tag_name)"),
                {"tag_name": tag_name},
            )

        # Insert track_tags
        for t, genre_query_name in zip(all_tracks, [g[1] for g in GENRES for _ in range(30)]):
            if t["track_id"] in seen:
                tag_result = await session.execute(
                    text("SELECT tag_id FROM tags WHERE tag_name = :tag_name"),
                    {"tag_name": genre_query_name},
                )
                tag_row = tag_result.first()
                if tag_row:
                    await session.execute(
                        text("INSERT IGNORE INTO track_tags (track_id, tag_id) VALUES (:track_id, :tag_id)"),
                        {"track_id": t["track_id"], "tag_id": tag_row[0]},
                    )

        # Insert sample track features
        print("  🎛 Generating sample acoustic features...")
        for t in unique_tracks:
            await session.execute(
                text("""
                    INSERT IGNORE INTO track_features (track_id, danceability, energy, tempo, valence, acousticness)
                    VALUES (:track_id, :danceability, :energy, :tempo, :valence, :acousticness)
                """),
                {
                    "track_id": t["track_id"],
                    "danceability": round(random.uniform(0.1, 0.95), 3),
                    "energy": round(random.uniform(0.1, 0.95), 3),
                    "tempo": round(random.uniform(60, 200), 1),
                    "valence": round(random.uniform(0.05, 0.95), 3),
                    "acousticness": round(random.uniform(0.01, 0.9), 3),
                },
            )

        # Create admin user
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
        admin_hash = pwd_context.hash("admin123")

        await session.execute(
            text("""
                INSERT IGNORE INTO users (username, password_hash, role, age, gender, country)
                VALUES (:username, :password_hash, :role, :age, :gender, :country)
            """),
            {
                "username": "admin",
                "password_hash": admin_hash,
                "role": "admin",
                "age": 25,
                "gender": 1,
                "country": "China",
            },
        )

        await session.commit()
        print(f"✅ Seeded {len(unique_tracks)} tracks, {len(tag_set)} tags, 1 admin user.")
        print("   Admin credentials: admin / admin123")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_database())
