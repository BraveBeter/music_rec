"""
Enrich Last.fm-imported tracks with cover and preview URLs while preserving LFM IDs.

Usage:
    uv run python -m ml_pipeline.data_process.enrich_lastfm_media --track-prefix LFM --only-missing
"""
import argparse
import asyncio
import json
import logging
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://music_app:music_app_pass_2026@localhost:13307/music_rec",
)

PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REPORT_DIR = PROJECT_ROOT / "data" / "media_enrichment"
ATTEMPTED_PATH = REPORT_DIR / "attempted_track_ids.json"

DEEZER_SEARCH_API = "https://api.deezer.com/search"
JAMENDO_TRACKS_API = "https://api.jamendo.com/v3.0/tracks"
MUSICBRAINZ_SEARCH_API = "https://musicbrainz.org/ws/2/recording"
MUSICBRAINZ_LOOKUP_API = "https://musicbrainz.org/ws/2/recording"
JAMENDO_CLIENT_ID = os.environ.get("JAMENDO_CLIENT_ID", "f2b6da64")
USER_AGENT = "music-rec/1.0 (https://github.com/openai/codex)"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")
_PARENS_RE = re.compile(r"\(([^)]*)\)")
_BRACKETS_RE = re.compile(r"\[([^\]]*)\]")
_FEAT_RE = re.compile(r"\b(feat|ft|featuring)\b.*$", re.IGNORECASE)
_VERSION_HINTS = (
    "live",
    "remaster",
    "remastered",
    "version",
    "edit",
    "mono",
    "stereo",
    "acoustic",
    "instrumental",
)


@dataclass
class TrackRow:
    track_id: str
    title: str
    artist_name: str | None
    album_name: str | None
    duration_ms: int | None
    preview_url: str | None
    cover_url: str | None


@dataclass
class EnrichmentResult:
    track_id: str
    matched_cover: bool = False
    matched_preview: bool = False
    updated_album: bool = False
    updated_duration: bool = False
    cover_source: str | None = None
    preview_source: str | None = None
    confidence: str = "unmatched"
    reason: str = ""


def normalize_text(value: str | None) -> str:
    """Normalize title/artist strings for high-confidence matching."""
    if not value:
        return ""
    text_value = unicodedata.normalize("NFKC", value).casefold().strip()
    text_value = _FEAT_RE.sub("", text_value)

    def _strip_version_tokens(match: re.Match[str]) -> str:
        content = match.group(1)
        lowered = content.casefold()
        if any(token in lowered for token in _VERSION_HINTS):
            return " "
        return f" {content} "

    text_value = _PARENS_RE.sub(_strip_version_tokens, text_value)
    text_value = _BRACKETS_RE.sub(_strip_version_tokens, text_value)
    text_value = text_value.replace("&", " and ")
    text_value = _PUNCT_RE.sub(" ", text_value)
    text_value = _WHITESPACE_RE.sub(" ", text_value)
    return text_value.strip()


def _artist_tokens(value: str | None) -> set[str]:
    normalized = normalize_text(value)
    if not normalized:
        return set()
    parts = re.split(r"\b(?:and|x|with|vs)\b|,|/", normalized)
    return {part.strip() for part in parts if part.strip()}


def artist_matches(base_artist: str | None, candidate_artist: str | None, candidate_credits: list[str] | None = None) -> bool:
    """Accept only high-confidence same-artist matches."""
    base_norm = normalize_text(base_artist)
    if not base_norm:
        return False

    candidates: set[str] = set()
    direct = normalize_text(candidate_artist)
    if direct:
        candidates.add(direct)
    for credit in candidate_credits or []:
        credit_norm = normalize_text(credit)
        if credit_norm:
            candidates.add(credit_norm)

    if base_norm in candidates:
        return True

    base_parts = _artist_tokens(base_artist)
    for candidate in candidates:
        if candidate == base_norm:
            return True
        candidate_parts = _artist_tokens(candidate)
        if base_parts and base_parts.issubset(candidate_parts):
            return True
    return False


def title_matches(base_title: str, candidate_title: str | None) -> bool:
    return normalize_text(base_title) == normalize_text(candidate_title)


def safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def fetch_lfm_tracks(
    session: AsyncSession,
    track_prefix: str,
    only_missing: bool,
    exclude_track_ids: set[str] | None = None,
) -> list[TrackRow]:
    conditions = ["track_id LIKE :prefix"]
    params: dict[str, Any] = {"prefix": f"{track_prefix}%"}
    if only_missing:
        conditions.append("(preview_url IS NULL OR preview_url = '' OR cover_url IS NULL OR cover_url = '')")

    query = f"""
        SELECT track_id, title, artist_name, album_name, duration_ms, preview_url, cover_url
        FROM tracks
        WHERE {' AND '.join(conditions)}
        ORDER BY track_id
    """
    result = await session.execute(text(query), params)
    tracks = [TrackRow(*row) for row in result.fetchall()]
    if exclude_track_ids:
        tracks = [track for track in tracks if track.track_id not in exclude_track_ids]
    return tracks


def load_attempted_track_ids() -> set[str]:
    if not ATTEMPTED_PATH.exists():
        return set()
    try:
        with ATTEMPTED_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return {str(item) for item in data}
    except Exception as exc:
        logger.warning("Could not load enrichment attempt cache: %s", exc)
    return set()


def save_attempted_track_ids(track_ids: set[str]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with ATTEMPTED_PATH.open("w", encoding="utf-8") as fh:
        json.dump(sorted(track_ids), fh, ensure_ascii=False, indent=2)


async def search_musicbrainz_cover(client: httpx.AsyncClient, track: TrackRow) -> tuple[str | None, str | None]:
    params = {
        "query": f'recording:"{track.title}" AND artist:"{track.artist_name or ""}"',
        "fmt": "json",
        "limit": 5,
    }
    response = await client.get(
        MUSICBRAINZ_SEARCH_API,
        params=params,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    recordings = response.json().get("recordings", [])

    for recording in recordings:
        candidate_title = recording.get("title")
        artist_credit = [credit.get("name", "") for credit in recording.get("artist-credit", []) if isinstance(credit, dict)]
        if not title_matches(track.title, candidate_title):
            continue
        if not artist_matches(track.artist_name, None, artist_credit):
            continue

        recording_id = recording.get("id")
        if not recording_id:
            continue
        lookup = await client.get(
            f"{MUSICBRAINZ_LOOKUP_API}/{recording_id}",
            params={"fmt": "json", "inc": "releases+release-groups"},
            headers={"User-Agent": USER_AGENT},
        )
        lookup.raise_for_status()
        lookup_data = lookup.json()

        releases = lookup_data.get("releases", [])
        for release in releases:
            if release.get("status") and release.get("status") != "Official":
                continue
            release_id = release.get("id")
            if not release_id:
                continue
            urls = [
                f"https://coverartarchive.org/release/{release_id}/front-500",
                f"https://coverartarchive.org/release/{release_id}/front",
            ]
            for url in urls:
                check = await client.get(url, follow_redirects=True)
                if check.status_code == 200:
                    return url, "musicbrainz-release"

        release_groups = lookup_data.get("release-groups", [])
        for release_group in release_groups:
            release_group_id = release_group.get("id")
            if not release_group_id:
                continue
            urls = [
                f"https://coverartarchive.org/release-group/{release_group_id}/front-500",
                f"https://coverartarchive.org/release-group/{release_group_id}/front",
            ]
            for url in urls:
                check = await client.get(url, follow_redirects=True)
                if check.status_code == 200:
                    return url, "musicbrainz-release-group"
    return None, None


async def search_deezer_preview(client: httpx.AsyncClient, track: TrackRow) -> dict[str, Any] | None:
    params = {"q": f'track:"{track.title}" artist:"{track.artist_name or ""}"', "limit": 10}
    response = await client.get(DEEZER_SEARCH_API, params=params)
    response.raise_for_status()
    for item in response.json().get("data", []):
        candidate_artist = (item.get("artist") or {}).get("name")
        candidate_title = item.get("title")
        if not title_matches(track.title, candidate_title):
            continue
        if not artist_matches(track.artist_name, candidate_artist):
            continue
        preview_url = item.get("preview")
        if not preview_url:
            continue
        album = item.get("album") or {}
        return {
            "preview_url": preview_url,
            "album_name": album.get("title"),
            "duration_ms": safe_int(item.get("duration")) * 1000 if safe_int(item.get("duration")) else None,
            "source": "deezer",
        }
    return None


async def search_jamendo_preview(client: httpx.AsyncClient, track: TrackRow) -> dict[str, Any] | None:
    params = {
        "client_id": JAMENDO_CLIENT_ID,
        "format": "json",
        "limit": 10,
        "namesearch": track.title,
        "artist_name": track.artist_name or "",
        "audioformat": "mp32",
    }
    response = await client.get(JAMENDO_TRACKS_API, params=params)
    response.raise_for_status()
    for item in response.json().get("results", []):
        candidate_artist = item.get("artist_name")
        candidate_title = item.get("name")
        if not title_matches(track.title, candidate_title):
            continue
        if not artist_matches(track.artist_name, candidate_artist):
            continue
        preview_url = item.get("audio")
        if not preview_url:
            continue
        return {
            "preview_url": preview_url,
            "album_name": item.get("album_name"),
            "duration_ms": safe_int(item.get("duration")) * 1000 if safe_int(item.get("duration")) else None,
            "source": "jamendo",
        }
    return None


async def update_track(
    session: AsyncSession,
    track: TrackRow,
    *,
    cover_url: str | None,
    cover_source: str | None,
    preview: dict[str, Any] | None,
    force: bool,
) -> EnrichmentResult:
    result = EnrichmentResult(track_id=track.track_id)
    updates: dict[str, Any] = {"track_id": track.track_id}
    assignments: list[str] = []

    if cover_url and (force or not track.cover_url):
        updates["cover_url"] = cover_url
        assignments.append("cover_url = :cover_url")
        result.matched_cover = True
        result.cover_source = cover_source or "musicbrainz"

    if preview and (force or not track.preview_url):
        updates["preview_url"] = preview["preview_url"]
        assignments.append("preview_url = :preview_url")
        result.matched_preview = True
        result.preview_source = preview["source"]

        album_name = preview.get("album_name")
        if album_name and album_name != track.album_name:
            updates["album_name"] = album_name
            assignments.append("album_name = :album_name")
            result.updated_album = True

        duration_ms = preview.get("duration_ms")
        if duration_ms and duration_ms != track.duration_ms:
            updates["duration_ms"] = duration_ms
            assignments.append("duration_ms = :duration_ms")
            result.updated_duration = True

    if assignments:
        await session.execute(
            text(f"UPDATE tracks SET {', '.join(assignments)} WHERE track_id = :track_id"),
            updates,
        )
        result.confidence = "exact"
        if result.matched_cover and result.matched_preview:
            result.reason = "matched cover and preview"
        elif result.matched_cover:
            result.reason = "matched cover only"
        else:
            result.reason = "matched preview only"
    else:
        result.reason = "no eligible enrichment match"
    return result


def _report_path() -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return REPORT_DIR / f"lastfm_media_enrichment_{timestamp}.json"


async def enrich_lastfm_media(
    *,
    track_prefix: str = "LFM",
    only_missing: bool = True,
    force: bool = False,
    limit: int | None = None,
    skip_attempted: bool = False,
) -> dict[str, Any]:
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {
        "checked": 0,
        "cover_matched": 0,
        "preview_matched": 0,
        "unmatched": 0,
        "report_path": None,
    }
    report_rows: list[dict[str, Any]] = []
    attempted_track_ids = load_attempted_track_ids() if skip_attempted and not force else set()

    try:
        async with session_factory() as session:
            tracks = await fetch_lfm_tracks(
                session,
                track_prefix=track_prefix,
                only_missing=only_missing,
                exclude_track_ids=attempted_track_ids,
            )
            if limit is not None:
                tracks = tracks[:limit]
            logger.info("Loaded %s tracks for enrichment", len(tracks))

            headers = {"User-Agent": USER_AGENT}
            timeout = httpx.Timeout(connect=15.0, read=20.0, write=10.0, pool=10.0)
            async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
                for idx, track in enumerate(tracks, start=1):
                    stats["checked"] += 1
                    cover_url = None
                    cover_source = None
                    preview = None
                    reason = ""

                    try:
                        if force or not track.cover_url:
                            cover_url, cover_source = await search_musicbrainz_cover(client, track)
                        if force or not track.preview_url:
                            preview = await search_deezer_preview(client, track)
                            if preview is None:
                                preview = await search_jamendo_preview(client, track)
                    except Exception as exc:
                        logger.warning("Failed to enrich %s: %s", track.track_id, exc)
                        attempted_track_ids.add(track.track_id)
                        report_rows.append({
                            "track_id": track.track_id,
                            "title": track.title,
                            "artist_name": track.artist_name,
                            "confidence": "error",
                            "reason": str(exc),
                        })
                        stats["unmatched"] += 1
                        continue

                    update_result = await update_track(
                        session,
                        track,
                        cover_url=cover_url,
                        cover_source=cover_source,
                        preview=preview,
                        force=force,
                    )
                    if update_result.matched_cover:
                        stats["cover_matched"] += 1
                    if update_result.matched_preview:
                        stats["preview_matched"] += 1
                    if not update_result.matched_cover and not update_result.matched_preview:
                        stats["unmatched"] += 1
                        reason = update_result.reason
                    attempted_track_ids.add(track.track_id)

                    report_rows.append({
                        "track_id": track.track_id,
                        "title": track.title,
                        "artist_name": track.artist_name,
                        "cover_source": update_result.cover_source,
                        "preview_source": update_result.preview_source,
                        "confidence": update_result.confidence,
                        "matched_cover": update_result.matched_cover,
                        "matched_preview": update_result.matched_preview,
                        "updated_album": update_result.updated_album,
                        "updated_duration": update_result.updated_duration,
                        "reason": reason or update_result.reason,
                    })

                    if idx % 50 == 0:
                        await session.commit()
                        logger.info(
                            "Enriched %s/%s tracks (cover=%s, preview=%s)",
                            idx,
                            len(tracks),
                            stats["cover_matched"],
                            stats["preview_matched"],
                        )

            await session.commit()
    finally:
        await engine.dispose()
        if skip_attempted and not force:
            save_attempted_track_ids(attempted_track_ids)

    report_path = _report_path()
    stats["report_path"] = str(report_path)
    with report_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "track_prefix": track_prefix,
                "only_missing": only_missing,
                "force": force,
                "skip_attempted": skip_attempted,
                "stats": stats,
                "results": report_rows,
            },
            fh,
            ensure_ascii=False,
            indent=2,
        )
    logger.info("Media enrichment report written to %s", report_path)
    return stats


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich Last.fm tracks with media URLs")
    parser.add_argument("--track-prefix", default="LFM")
    parser.add_argument("--only-missing", action="store_true", default=False)
    parser.add_argument("--force", action="store_true", default=False)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-attempted", action="store_true", default=False)
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    stats = await enrich_lastfm_media(
        track_prefix=args.track_prefix,
        only_missing=args.only_missing,
        force=args.force,
        limit=args.limit,
        skip_attempted=args.skip_attempted,
    )
    logger.info("Done: %s", stats)


if __name__ == "__main__":
    asyncio.run(_main())
