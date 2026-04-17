"""Track schemas."""
from pydantic import BaseModel
from datetime import datetime


class TrackResponse(BaseModel):
    track_id: str
    title: str
    artist_name: str | None = None
    album_name: str | None = None
    release_year: int | None = None
    duration_ms: int | None = None
    play_count: int = 0
    preview_url: str | None = None
    cover_url: str | None = None

    class Config:
        from_attributes = True


class TrackListResponse(BaseModel):
    items: list[TrackResponse]
    total: int
    page: int
    page_size: int


class TrackSearchRequest(BaseModel):
    query: str | None = None
    page: int = 1
    page_size: int = 20


class GenreTracksItem(BaseModel):
    genre: str
    tracks: list[TrackResponse]


class GenreTracksResponse(BaseModel):
    genres: list[GenreTracksItem]
