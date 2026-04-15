"""Track endpoints."""
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.track import TrackResponse, TrackListResponse
from app.services.track_service import get_tracks, get_track_by_id, get_popular_tracks, get_diverse_popular_tracks

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
    """Get popular tracks with genre diversity."""
    tracks = await get_diverse_popular_tracks(db, limit=limit, max_per_genre=3)
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

    # Build list of URLs to try (fresh first, then stored fallback)
    urls_to_try = [stream_url]
    if fresh_url and fresh_url != track.preview_url:
        urls_to_try.append(track.preview_url)

    # Pre-check CDN: send a streaming request and verify status before
    # committing to StreamingResponse.  The httpx client must stay alive
    # for the duration of the stream, so we create it outside the generator.
    # Connect timeout is generous (15s) because TLS through a proxy to an
    # overseas CDN can be slow.
    client = httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(connect=15.0, read=30.0, write=5.0, pool=5.0),
    )

    cdn_resp = None
    try:
        for url in urls_to_try:
            resp = await client.send(
                client.build_request("GET", url, headers=_PROXY_HEADERS),
                stream=True,
            )
            if resp.status_code in (200, 206):
                cdn_resp = resp
                break
            logger.warning(f"CDN returned {resp.status_code} for track {track_id} (url={url[:80]}...)")
            await resp.aclose()
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        logger.warning(f"CDN connection failed for {track_id}: {type(e).__name__}")
    except Exception as e:
        logger.warning(f"Unexpected CDN error for {track_id}: {e}")

    if cdn_resp is None:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail="Audio preview unavailable: CDN connection failed. "
                   "The track may be geo-restricted or the network is unstable.",
        )

    async def _stream():
        try:
            async for chunk in cdn_resp.aiter_bytes(chunk_size=8192):
                yield chunk
        finally:
            await cdn_resp.aclose()
            await client.aclose()

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

