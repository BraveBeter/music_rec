"""Track service."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.models.track import Track


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
