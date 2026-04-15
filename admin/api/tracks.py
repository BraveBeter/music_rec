"""Admin tracks — batch import and Deezer fetch."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from pydantic import BaseModel
from typing import Optional

from common.database import get_db
from common.models.user import User
from common.models.track import Track
from admin.dependencies import get_admin_user

logger = logging.getLogger("admin")
router = APIRouter(prefix="/admin/tracks", tags=["Admin Tracks"])


class TrackItem(BaseModel):
    track_id: str
    title: str
    artist_name: Optional[str] = None
    album_name: Optional[str] = None
    duration_ms: Optional[int] = None
    preview_url: Optional[str] = None
    cover_url: Optional[str] = None
    genre: Optional[str] = None
    danceability: Optional[float] = None
    energy: Optional[float] = None
    tempo: Optional[float] = None
    valence: Optional[float] = None
    acousticness: Optional[float] = None


class BatchTrackRequest(BaseModel):
    tracks: list[TrackItem]


@router.post("/batch")
async def batch_insert_tracks(
    req: BatchTrackRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Batch insert tracks with optional features and tags."""
    inserted = 0
    skipped = 0

    for t in req.tracks:
        # Check if track exists
        result = await db.execute(
            select(Track).where(Track.track_id == t.track_id)
        )
        if result.scalar_one_or_none():
            skipped += 1
            continue

        await db.execute(text("""
            INSERT IGNORE INTO tracks
            (track_id, title, artist_name, album_name, duration_ms, preview_url, cover_url, status)
            VALUES (:track_id, :title, :artist_name, :album_name, :duration_ms, :preview_url, :cover_url, 1)
        """), {
            "track_id": t.track_id, "title": t.title,
            "artist_name": t.artist_name, "album_name": t.album_name,
            "duration_ms": t.duration_ms, "preview_url": t.preview_url,
            "cover_url": t.cover_url,
        })

        # Insert features if provided
        if any([t.danceability, t.energy, t.tempo, t.valence, t.acousticness]):
            await db.execute(text("""
                INSERT IGNORE INTO track_features (track_id, danceability, energy, tempo, valence, acousticness)
                VALUES (:track_id, :danceability, :energy, :tempo, :valence, :acousticness)
            """), {
                "track_id": t.track_id,
                "danceability": t.danceability,
                "energy": t.energy,
                "tempo": t.tempo,
                "valence": t.valence,
                "acousticness": t.acousticness,
            })

        # Insert tag if provided
        if t.genre:
            await db.execute(text("INSERT IGNORE INTO tags (tag_name) VALUES (:tag)"), {"tag": t.genre})
            tag_result = await db.execute(
                text("SELECT tag_id FROM tags WHERE tag_name = :tag"), {"tag": t.genre}
            )
            tag_row = tag_result.first()
            if tag_row:
                await db.execute(text("""
                    INSERT IGNORE INTO track_tags (track_id, tag_id) VALUES (:track_id, :tag_id)
                """), {"track_id": t.track_id, "tag_id": tag_row[0]})

        inserted += 1

    await db.commit()
    return {"inserted": inserted, "skipped": skipped, "total": len(req.tracks)}


class DeezerImportRequest(BaseModel):
    genres: list[str] = ["pop", "rock", "hiphop", "electronic", "jazz", "classical", "rnb", "latin"]
    limit_per_genre: int = 30


@router.post("/deezer-import")
async def deezer_import(
    req: DeezerImportRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Fetch tracks from Deezer API by genre."""
    import httpx
    import random

    GENRE_NAME_MAP = {
        "pop": "Pop", "rock": "Rock", "hiphop": "Hip-Hop",
        "electronic": "Electronic", "jazz": "Jazz", "classical": "Classical",
        "rnb": "R&B", "latin": "Latin",
    }

    total_inserted = 0

    async with httpx.AsyncClient(timeout=15) as client:
        for genre_query in req.genres:
            try:
                resp = await client.get(
                    "https://api.deezer.com/search",
                    params={"q": genre_query, "limit": req.limit_per_genre},
                )
                if resp.status_code != 200:
                    continue
                tracks = resp.json().get("data", [])
            except Exception as e:
                logger.warning(f"Deezer API error for '{genre_query}': {e}")
                continue

            genre_name = GENRE_NAME_MAP.get(genre_query, genre_query)
            for t in tracks:
                track_id = f"DZ{t['id']}"
                result = await db.execute(select(Track).where(Track.track_id == track_id))
                if result.scalar_one_or_none():
                    continue

                album = t.get("album", {})
                artist = t.get("artist", {})

                await db.execute(text("""
                    INSERT IGNORE INTO tracks
                    (track_id, title, artist_name, album_name, duration_ms, play_count, preview_url, cover_url, status)
                    VALUES (:track_id, :title, :artist_name, :album_name, :duration_ms, 0, :preview_url, :cover_url, 1)
                """), {
                    "track_id": track_id, "title": t.get("title", "Unknown"),
                    "artist_name": artist.get("name"), "album_name": album.get("title"),
                    "duration_ms": (t.get("duration", 30)) * 1000,
                    "preview_url": t.get("preview"),
                    "cover_url": album.get("cover_medium") or album.get("cover"),
                })

                # Random features + tag
                await db.execute(text("""
                    INSERT IGNORE INTO track_features (track_id, danceability, energy, tempo, valence, acousticness)
                    VALUES (:track_id, :danceability, :energy, :tempo, :valence, :acousticness)
                """), {
                    "track_id": track_id,
                    "danceability": round(random.uniform(0.1, 0.95), 3),
                    "energy": round(random.uniform(0.1, 0.95), 3),
                    "tempo": round(random.uniform(60, 200), 1),
                    "valence": round(random.uniform(0.05, 0.95), 3),
                    "acousticness": round(random.uniform(0.01, 0.9), 3),
                })

                await db.execute(text("INSERT IGNORE INTO tags (tag_name) VALUES (:tag)"), {"tag": genre_name})
                tag_result = await db.execute(text("SELECT tag_id FROM tags WHERE tag_name = :tag"), {"tag": genre_name})
                tag_row = tag_result.first()
                if tag_row:
                    await db.execute(text("INSERT IGNORE INTO track_tags (track_id, tag_id) VALUES (:tid, :tagid)"),
                                     {"tid": track_id, "tagid": tag_row[0]})

                total_inserted += 1

    await db.commit()
    return {"inserted": total_inserted}
