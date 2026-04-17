"""Artist service - search, favorites, and track listing."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from common.models.track import Track
from common.models.artist_favorite import ArtistFavorite

logger = logging.getLogger("music_rec")


async def search_artists(
    db: AsyncSession,
    query: str,
    limit: int = 20,
) -> list[dict]:
    """Search artists by name (fuzzy match). Returns artist_name, track_count, cover_url."""
    search = f"%{query}%"
    stmt = (
        select(
            Track.artist_name,
            func.count(Track.track_id).label("track_count"),
        )
        .where(Track.artist_name.ilike(search), Track.status == 1)
        .group_by(Track.artist_name)
        .order_by(func.count(Track.track_id).desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.fetchall()

    # Get cover URL for each artist (latest track's cover)
    artists = []
    for artist_name, track_count in rows:
        cover_stmt = (
            select(Track.cover_url)
            .where(Track.artist_name == artist_name, Track.status == 1, Track.cover_url.isnot(None))
            .order_by(Track.created_at.desc())
            .limit(1)
        )
        cover_result = await db.execute(cover_stmt)
        cover_url = cover_result.scalar_one_or_none()
        artists.append({
            "artist_name": artist_name,
            "track_count": track_count,
            "cover_url": cover_url,
        })

    return artists


async def get_artist_tracks(
    db: AsyncSession,
    artist_name: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Track], int]:
    """Get all tracks by an artist with pagination."""
    base_stmt = (
        select(Track)
        .where(Track.artist_name == artist_name, Track.status == 1)
    )

    # Count total
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginate
    stmt = base_stmt.order_by(Track.play_count.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    tracks = result.scalars().all()

    return list(tracks), total


async def get_favorite_artists(
    db: AsyncSession,
    user_id: int,
) -> list[dict]:
    """Get user's favorited artists with track count and cover."""
    stmt = (
        select(ArtistFavorite.artist_name)
        .where(ArtistFavorite.user_id == user_id)
        .order_by(ArtistFavorite.created_at.desc())
    )
    result = await db.execute(stmt)
    artist_names = [row[0] for row in result.fetchall()]

    if not artist_names:
        return []

    artists = []
    for name in artist_names:
        # Get track count and cover
        info_stmt = (
            select(
                func.count(Track.track_id).label("track_count"),
            )
            .where(Track.artist_name == name, Track.status == 1)
        )
        info_result = await db.execute(info_stmt)
        row = info_result.fetchone()
        track_count = row[0] if row else 0

        # Get cover
        cover_stmt = (
            select(Track.cover_url)
            .where(Track.artist_name == name, Track.status == 1, Track.cover_url.isnot(None))
            .order_by(Track.created_at.desc())
            .limit(1)
        )
        cover_url = (await db.execute(cover_stmt)).scalar_one_or_none()

        artists.append({
            "artist_name": name,
            "track_count": track_count,
            "cover_url": cover_url,
        })

    return artists


async def get_favorite_artist_ids(
    db: AsyncSession,
    user_id: int,
) -> list[str]:
    """Get user's favorited artist names (lightweight)."""
    stmt = (
        select(ArtistFavorite.artist_name)
        .where(ArtistFavorite.user_id == user_id)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.fetchall()]


async def add_artist_favorite(
    db: AsyncSession,
    user_id: int,
    artist_name: str,
) -> ArtistFavorite:
    """Add an artist to user's favorites."""
    fav = ArtistFavorite(user_id=user_id, artist_name=artist_name)
    db.add(fav)
    await db.flush()
    return fav


async def remove_artist_favorite(
    db: AsyncSession,
    user_id: int,
    artist_name: str,
) -> bool:
    """Remove an artist from user's favorites. Returns True if deleted."""
    result = await db.execute(
        delete(ArtistFavorite).where(
            ArtistFavorite.user_id == user_id,
            ArtistFavorite.artist_name == artist_name,
        )
    )
    return result.rowcount > 0


async def is_artist_favorited(
    db: AsyncSession,
    user_id: int,
    artist_name: str,
) -> bool:
    """Check if an artist is in user's favorites."""
    result = await db.execute(
        select(ArtistFavorite).where(
            ArtistFavorite.user_id == user_id,
            ArtistFavorite.artist_name == artist_name,
        )
    )
    return result.scalar_one_or_none() is not None
