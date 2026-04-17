"""Interaction schemas."""
from pydantic import BaseModel, Field


class InteractionCreate(BaseModel):
    track_id: str
    interaction_type: int = Field(..., ge=1, le=4, description="1=play,2=like,3=skip,4=rate")
    rating: float | None = Field(None, ge=0, le=5)
    play_duration: int | None = Field(None, ge=0, description="ms")
    client_timestamp: int | None = None


class PlayHistoryTrack(BaseModel):
    track_id: str
    title: str
    artist_name: str | None = None
    album_name: str | None = None
    duration_ms: int | None = None
    preview_url: str | None = None
    cover_url: str | None = None
    play_count: int = 0


class PlayHistoryItem(BaseModel):
    interaction_id: int
    track_id: str
    created_at: str
    track: PlayHistoryTrack


class PlayHistoryResponse(BaseModel):
    items: list[PlayHistoryItem]
    total: int
    page: int
    page_size: int
