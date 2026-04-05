"""Track endpoints."""
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.track import TrackResponse, TrackListResponse
from app.services.track_service import get_tracks, get_track_by_id, get_popular_tracks

router = APIRouter(prefix="/tracks", tags=["Tracks"])
logger = logging.getLogger("music_rec")

# Headers to send when proxying audio from Deezer CDN
_PROXY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.deezer.com/",
    "Origin": "https://www.deezer.com",
    "Accept": "audio/mpeg, audio/mp4, audio/*;q=0.9, */*;q=0.8",
}


@router.get("", response_model=TrackListResponse)
async def list_tracks(
    query: str | None = Query(None, description="Search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List tracks with optional search and pagination."""
    tracks, total = await get_tracks(db, page=page, page_size=page_size, query=query)
    return TrackListResponse(
        items=[TrackResponse.model_validate(t) for t in tracks],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/popular", response_model=list[TrackResponse])
async def popular_tracks(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get popular tracks (cold-start fallback)."""
    tracks = await get_popular_tracks(db, limit=limit)
    return [TrackResponse.model_validate(t) for t in tracks]


@router.get("/{track_id}/preview")
async def proxy_preview(track_id: str, db: AsyncSession = Depends(get_db)):
    """
    Proxy audio preview via backend.
    Fetches a fresh signed URL from the Deezer API (to get valid hdnea token),
    then streams the audio back to the browser.
    """
    track = await get_track_by_id(db, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    if not track.preview_url:
        raise HTTPException(status_code=404, detail="No preview available for this track")

    # Extract the numeric Deezer ID from our track_id (format: "DZ{numeric_id}")
    fresh_url = None
    if track_id.startswith("DZ"):
        dz_numeric_id = track_id[2:]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                api_resp = await client.get(
                    f"https://api.deezer.com/track/{dz_numeric_id}",
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if api_resp.status_code == 200:
                    api_data = api_resp.json()
                    fresh_url = api_data.get("preview")
                    if fresh_url:
                        logger.debug(f"Got fresh signed URL for {track_id}")
        except Exception as e:
            logger.warning(f"Could not fetch fresh Deezer URL for {track_id}: {e}")

    # Fall back to stored URL if API call failed
    stream_url = fresh_url or track.preview_url
    logger.debug(f"Proxying audio for {track_id}")

    async def _stream():
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0),
        ) as client:
            async with client.stream("GET", stream_url, headers=_PROXY_HEADERS) as resp:
                if resp.status_code not in (200, 206):
                    logger.warning(f"CDN returned {resp.status_code} for track {track_id}")
                    return
                async for chunk in resp.aiter_bytes(chunk_size=8192):
                    yield chunk

    return StreamingResponse(
        _stream(),
        media_type="audio/mpeg",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-store",  # Don't cache - tokens expire
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{track_id}", response_model=TrackResponse)
async def get_track(track_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single track by ID."""
    track = await get_track_by_id(db, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return TrackResponse.model_validate(track)

