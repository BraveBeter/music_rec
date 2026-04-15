"""Track service."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, text

from common.models.track import Track


async def get_tracks(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    query: str | None = None,
) -> tuple[list[Track], int]:
    """Get paginated track list with optional search."""
    stmt = select(Track).where(Track.status == 1)

    if query:
        search = f"%{query}%"
        stmt = stmt.where(
            or_(
                Track.title.ilike(search),
                Track.artist_name.ilike(search),
                Track.album_name.ilike(search),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # Paginate
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    tracks = result.scalars().all()

    return tracks, total


async def get_track_by_id(db: AsyncSession, track_id: str) -> Track | None:
    """Get a single track by ID."""
    result = await db.execute(
        select(Track).where(Track.track_id == track_id, Track.status == 1)
    )
    return result.scalar_one_or_none()


async def get_popular_tracks(db: AsyncSession, limit: int = 20) -> list[Track]:
    """Get most played tracks for cold-start fallback."""
    result = await db.execute(
        select(Track)
        .where(Track.status == 1)
        .order_by(Track.play_count.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_diverse_popular_tracks(
    db: AsyncSession,
    limit: int = 20,
    max_per_genre: int = 3,
) -> list[Track]:
    """Get popular tracks with genre diversity constraints."""
    result = await db.execute(text("""
        SELECT t.track_id, t.title, t.artist_name, t.album_name,
               t.release_year, t.duration_ms, t.play_count, t.status,
               t.preview_url, t.cover_url, t.created_at, tg.tag_name
        FROM tracks t
        LEFT JOIN track_tags tt ON t.track_id = tt.track_id
        LEFT JOIN tags tg ON tt.tag_id = tg.tag_id
        WHERE t.status = 1
        ORDER BY t.play_count DESC
        LIMIT 200
    """))
    rows = result.fetchall()

    # Interleave genres with per-genre cap
    genre_tracks: dict[str, list[Track]] = {}
    seen_ids: set[str] = set()

    for row in rows:
        tid = row[0]
        if tid in seen_ids:
            continue
        seen_ids.add(tid)

        track = await db.execute(
            select(Track).where(Track.track_id == tid)
        )
        track_obj = track.scalar_one_or_none()
        if not track_obj:
            continue

        genre = row[11] or "unknown"
        if genre not in genre_tracks:
            genre_tracks[genre] = []
        if len(genre_tracks[genre]) < max_per_genre:
            genre_tracks[genre].append(track_obj)

    # Collect and sort by play_count
    selected = []
    for tracks in genre_tracks.values():
        selected.extend(tracks)
    selected.sort(key=lambda t: t.play_count, reverse=True)
    return selected[:limit]
