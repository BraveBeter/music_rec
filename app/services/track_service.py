"""Track service."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, text

from common.models.track import Track
from common.models.tag import Tag, TrackTag


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


async def get_genre_random(
    db: AsyncSession,
    per_genre: int = 5,
) -> list[tuple[str, list[Track]]]:
    """Get random tracks per genre. Returns list of (genre_name, tracks)."""
    # Get all genres
    genre_result = await db.execute(select(Tag).order_by(Tag.tag_name))
    genres = genre_result.scalars().all()

    result: list[tuple[str, list[Track]]] = []
    for genre in genres:
        # Random tracks for this genre
        stmt = (
            select(Track)
            .join(TrackTag, Track.track_id == TrackTag.track_id)
            .where(TrackTag.tag_id == genre.tag_id, Track.status == 1)
            .order_by(func.rand())
            .limit(per_genre)
        )
        track_result = await db.execute(stmt)
        tracks = track_result.scalars().all()
        if tracks:
            result.append((genre.tag_name, list(tracks)))

    return result


async def get_genre_ranking(
    db: AsyncSession,
    top_k: int = 10,
) -> list[tuple[str, list[Track]]]:
    """Get top tracks per genre by play_count. Returns list of (genre_name, tracks)."""
    # Get all genres
    genre_result = await db.execute(select(Tag).order_by(Tag.tag_name))
    genres = genre_result.scalars().all()

    # Build global ranking for dedup: tracks sorted by play_count descending
    # A track appearing in multiple tags only keeps its highest-ranked tag
    global_stmt = (
        select(Track.track_id, TrackTag.tag_id, Track.play_count)
        .join(TrackTag, Track.track_id == TrackTag.track_id)
        .where(Track.status == 1)
        .order_by(Track.play_count.desc())
    )
    all_rows = (await db.execute(global_stmt)).fetchall()

    # tag_id -> set of assigned track_ids, for dedup
    tag_assigned: dict[int, set[str]] = {g.tag_id: set() for g in genres}
    track_assigned_tag: dict[str, int] = {}  # track_id -> first (best) tag_id

    for track_id, tag_id, _play_count in all_rows:
        if track_id not in track_assigned_tag:
            track_assigned_tag[track_id] = tag_id
            tag_assigned[tag_id].add(track_id)

    # Build tag_id -> tag_name map
    tag_name_map = {g.tag_id: g.tag_name for g in genres}

    result: list[tuple[str, list[Track]]] = []
    for genre in genres:
        assigned = tag_assigned[genre.tag_id]
        if not assigned:
            continue
        # Get top_k tracks for this genre, ordered by play_count
        stmt = (
            select(Track)
            .where(Track.track_id.in_(assigned), Track.status == 1)
            .order_by(Track.play_count.desc())
            .limit(top_k)
        )
        track_result = await db.execute(stmt)
        tracks = track_result.scalars().all()
        if tracks:
            result.append((tag_name_map[genre.tag_id], list(tracks)))

    return result
